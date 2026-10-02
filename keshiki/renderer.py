"""Puts the background into Anki's main window and keeps it current.

The main window is three webviews stacked in one layout: the top toolbar,
the main area and the bottom bar. Each gets the same stage, sized to the
whole central widget and offset by its own position, so the image runs on
across all three without seams.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from aqt import gui_hooks
from aqt.qt import QEvent, QObject, QPoint, QTimer
from aqt.webview import AnkiWebView, WebContent

from . import library
from ._kiso import config as kiso_config
from ._kiso.hooks import Subscriptions, guard
from .config import ADDON_PACKAGE, migrate
from .schedule import build_look
from .sun import location_sun

log = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent / "web"
# How often the background is worked out again. It only reaches the page when
# something changed (looks are rounded to 0.1%). These steps are small (3.4% at
# most, at sunset), so the page eases them in over 0.8 s; bigger changes ease in
# over transition_seconds (layers.js, Stage.small).
TICK_MS = 30_000
STUDY_STATES = ("overview", "review")


def load_config(mw) -> dict:
    return kiso_config.load(mw.addonManager, ADDON_PACKAGE, migrate)


class Renderer(QObject):
    def __init__(self, mw) -> None:
        super().__init__(mw)
        self.mw = mw
        self.cfg = load_config(mw)
        self.preview: Optional[dict] = None   # the settings page's unsaved draft, shown live
        self.scene_look: Optional[dict] = None   # a moment the scene editor is scrubbed to
        self.launch_seed = random.randrange(1 << 30)
        self.shown: Optional[dict] = None     # the look on screen now
        self._progress: Optional[float] = None
        self._all_done: Optional[bool] = None
        self._geometry_queued = False
        self.enabled = True   # False once turned off in Tools > Add-ons, until Anki restarts
        self.subs = Subscriptions(log)
        self._web_assets = (WEB / "layers.css").read_text(encoding="utf-8"), \
            (WEB / "layers.js").read_text(encoding="utf-8")

    # -- wiring -----------------------------------------------------------

    def install(self) -> None:
        refresh_progress = lambda *_: self.refresh(progress_changed=True)  # noqa: E731
        self.subs.add(gui_hooks.webview_will_set_content, self.on_will_set_content, "Page background")
        self.subs.add(gui_hooks.webview_did_inject_style_into_page, self.on_did_inject_style, "Page background")
        self.subs.add(gui_hooks.state_did_change, refresh_progress, "Screen change")
        self.subs.add(gui_hooks.reviewer_did_answer_card, refresh_progress, "Answer")
        self.subs.add(gui_hooks.operation_did_execute, self.on_operation, "Collection change")
        # A new day brings new cards: "all done" may no longer hold.
        self.subs.add(gui_hooks.day_did_change, refresh_progress, "New day")
        self.subs.timer(self, TICK_MS, self.refresh, "Background tick")
        for widget in self._webviews() + [self.mw.form.centralwidget]:
            widget.installEventFilter(self)

    def teardown(self) -> None:
        """Undo install(), for a dev reload; pages keep their background until redrawn."""
        self.subs.remove_all()
        for widget in self._webviews() + [self.mw.form.centralwidget]:
            widget.removeEventFilter(self)
        self.deleteLater()

    def _webviews(self):
        return [self.mw.toolbarWeb, self.mw.web, self.mw.bottomWeb]

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move) and not self._geometry_queued:
            self._geometry_queued = True
            QTimer.singleShot(0, guard(self.push_geometry, log, "Background geometry"))
        return False

    # -- config -----------------------------------------------------------

    def set_config(self, cfg: dict) -> None:
        self.cfg = cfg
        self.refresh()

    def set_preview(self, cfg: Optional[dict]) -> None:
        self.preview = cfg
        self.refresh()

    def show_scene_moment(self, look: Optional[dict]) -> None:
        """Show this look instead of the screen's own (None: back to normal)."""
        self.scene_look = look
        self.refresh()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.refresh()

    def active_config(self) -> dict:
        return self.preview or self.cfg

    # -- what to show -----------------------------------------------------

    def screen(self) -> str:
        return "study" if self.mw.state in STUDY_STATES else "main"

    def look(self) -> Optional[dict]:
        if not self.enabled:
            return None
        if self.scene_look is not None:
            return self.scene_look
        cfg = self.active_config()
        now = datetime.now().astimezone()
        offset = now.utcoffset().total_seconds() / 60
        return build_look(
            cfg, self.screen(),
            minute_of_day=now.hour * 60 + now.minute + now.second / 60,
            now_minutes=int(time.time() / 60 + offset),
            launch_seed=self.launch_seed,
            sun=self.sun_today(cfg["day"], now.date(), offset),
            percent_done=self.percent_done,
            image_url=library.image_url,
            image_stats=library.image_stats,
            image_lights=library.lights_url,
            all_done=self.all_done,
        )

    def sun_today(self, day_cfg: dict, today: date, offset: float):
        if day_cfg.get("source") != "location":
            return None
        try:
            return location_sun(today, float(day_cfg["latitude"]), float(day_cfg["longitude"]), offset)
        except (TypeError, ValueError):
            return None

    def percent_done(self) -> float:
        if self._progress is None:
            col = self.mw.col
            if col is None:
                return 0.0
            from .progress import percent_done
            did = col.decks.get_current_id() if self.screen() == "study" else None
            self._progress = percent_done(col, did)
        return self._progress

    def all_done(self) -> bool:
        if self._all_done is None:
            col = self.mw.col
            if col is None:
                return False
            from .progress import nothing_left
            self._all_done = nothing_left(col)
        return self._all_done

    def on_operation(self, changes, handler) -> None:
        if getattr(changes, "study_queues", False):
            self.refresh(progress_changed=True)

    # -- pushing it to the page -------------------------------------------

    def refresh(self, progress_changed: bool = False) -> None:
        if progress_changed:
            self._progress = None
            self._all_done = None
        if self.mw.col is None:
            return
        look = self.look()
        if look == self.shown:
            return
        self.shown = look
        js = f"window.keshiki && keshiki.main && keshiki.main.apply({json.dumps(look)})"
        for web in self._webviews():
            web.eval(js)

    def geometry(self, web: AnkiWebView) -> dict:
        central = self.mw.form.centralwidget
        pos = web.mapTo(central, QPoint(0, 0))
        zoom = web.zoomFactor() or 1
        return {"w": central.width() / zoom, "h": central.height() / zoom, "x": pos.x() / zoom, "y": pos.y() / zoom}

    def push_geometry(self) -> None:
        self._geometry_queued = False
        for web in self._webviews():
            web.eval(f"window.keshiki && keshiki.main && keshiki.main.geom({json.dumps(self.geometry(web))})")

    def bootstrap_js(self, web: AnkiWebView) -> str:
        if self.shown is None and self.mw.col is not None:
            self.shown = self.look()
        return f"{self._web_assets[1]}\nkeshiki.mount({json.dumps(self.geometry(web))}, {json.dumps(self.shown)});"

    def _web_for_context(self, context: Any) -> Optional[AnkiWebView]:
        from aqt.deckbrowser import DeckBrowser, DeckBrowserBottomBar
        from aqt.overview import Overview, OverviewBottomBar
        from aqt.reviewer import Reviewer, ReviewerBottomBar
        from aqt.toolbar import BottomToolbar, TopToolbar

        if isinstance(context, TopToolbar):
            return self.mw.toolbarWeb
        if isinstance(context, (DeckBrowser, Overview, Reviewer)):
            return self.mw.web
        if isinstance(context, (BottomToolbar, DeckBrowserBottomBar, OverviewBottomBar, ReviewerBottomBar)):
            return self.mw.bottomWeb
        return None

    def on_will_set_content(self, content: WebContent, context: Any) -> None:
        web = self._web_for_context(context)
        if web is None:
            return
        # The page starts on the look already showing, so a screen change
        # crossfades in step with the bars instead of popping.
        content.head += f"<style>{self._web_assets[0]}</style><script>{self.bootstrap_js(web)}</script>"

    def on_did_inject_style(self, web: AnkiWebView) -> None:
        # Pages Anki builds with Svelte (like the congratulations screen)
        # don't go through webview_will_set_content.
        if web is self.mw.web:
            css = json.dumps(self._web_assets[0])
            web.eval(f"""(() => {{ if (window.keshiki) return;
                const s = document.createElement("style"); s.textContent = {css}; document.head.append(s);
                {self.bootstrap_js(web)} }})();""")
