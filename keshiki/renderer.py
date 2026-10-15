"""Puts the background into Anki's main window and keeps it current.

The main window is three webviews stacked in one layout: the top toolbar,
the main area and the bottom bar. Each gets the same stage, sized to the
whole central widget and offset by its own position, so the image runs on
across all three without seams.
"""

from __future__ import annotations

import copy
import json
import logging
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Tuple

from aqt import gui_hooks
from aqt.qt import QEvent, QObject, QPoint
from aqt.webview import AnkiWebView, WebContent

from . import folders, library
from ._kiso import config as kiso_config
from ._kiso.hooks import Subscriptions
from .config import ADDON_PACKAGE, migrate
from .schedule import build_look, screen_source
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
        # A crossfade under way: (the look before, the look it's fading to, when it began
        # (monotonic), seconds, when it began (epoch ms, for the page)).
        self._fading: Optional[Tuple[dict, dict, float, float, int]] = None
        self._progress: Optional[float] = None
        self._all_done: Optional[bool] = None
        self.enabled = True   # False once turned off in Tools > Add-ons, until Anki restarts
        self.subs = Subscriptions(log)
        self._geometry = self.subs.debounce(self, self.push_geometry, "Background geometry")
        self._web_assets = (WEB / "layers.css").read_text(encoding="utf-8"), \
            (WEB / "layers.js").read_text(encoding="utf-8")

    # -- wiring -----------------------------------------------------------

    def install(self) -> None:
        refresh_progress = lambda *_: self.refresh(progress_changed=True)  # noqa: E731
        self.subs.add(gui_hooks.webview_will_set_content, self.on_will_set_content, "Page background")
        self.subs.add(gui_hooks.webview_did_inject_style_into_page, self.on_did_inject_style, "Page background")
        self.subs.add(gui_hooks.state_did_change, refresh_progress, "Screen change")
        self.subs.add(gui_hooks.reviewer_did_answer_card, self.on_answer, "Answer")
        self.subs.add(gui_hooks.operation_did_execute, self.on_operation, "Collection change")
        # A new day brings new cards: "all done" may no longer hold.
        self.subs.add(gui_hooks.day_did_change, refresh_progress, "New day")
        self.subs.filter(gui_hooks.webview_did_receive_js_message, self.on_js_message, "Page message")
        self.subs.timer(self, TICK_MS, self.refresh, "Background tick")
        self.refresh_folders()
        for widget in self._webviews() + [self.mw.form.centralwidget]:
            widget.installEventFilter(self)

    def refresh_folders(self) -> None:
        """Linked albums catch up with their folders (at startup); links no album uses go.
        A folder problem is logged, never stops the background."""
        cfg = copy.deepcopy(self.cfg)
        try:
            changed, _missing = folders.refresh(cfg)
            library.prune_links(folders.links_in_use(cfg))
        except OSError:
            log.exception("Couldn't rescan linked folders")
            return
        if changed:
            self.mw.addonManager.writeConfig(ADDON_PACKAGE, cfg)
            self.set_config(cfg)

    def teardown(self) -> None:
        """Undo install(), for a dev reload; pages keep their background until redrawn."""
        self.subs.remove_all()
        for widget in self._webviews() + [self.mw.form.centralwidget]:
            widget.removeEventFilter(self)
        self.deleteLater()

    def _webviews(self):
        return [self.mw.toolbarWeb, self.mw.web, self.mw.bottomWeb]

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move) and not self._geometry.pending:
            self._geometry.restart(0)   # once per event-loop turn, however many events
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

    def on_answer(self, *_) -> None:
        if self.shows_progress():
            self.refresh(progress_changed=True)

    def on_operation(self, changes, handler) -> None:
        if not getattr(changes, "study_queues", False):
            return
        # Answering a card is an operation too. In the reviewer nothing but a progress scene
        # moves with it: "all done" can't come true there (Anki leaves the reviewer when the
        # cards run out, and that screen change checks again), and working it out goes through
        # every deck's counts. Elsewhere (cards added, a sync, deck options) it may change.
        if self.mw.state == "review" and not self.shows_progress():
            return
        self.refresh(progress_changed=True)

    def shows_progress(self) -> bool:
        """Whether a screen shows a progress scene (they can't be made now; older configs may have one)."""
        cfg = self.active_config()
        progress = {s.get("id") for s in cfg.get("scenes") or [] if s.get("kind") == "progress"}
        if not progress:
            return False
        # The scenes each screen really shows (Studying may follow the deck list's).
        done = cfg["screens"].get("done") or {}
        sources = [screen_source(cfg, screen)[0] for screen in ("main", "study")] + [done if done.get("enabled") else None]
        return any(progress & set((source or {}).get("scenes") or []) for source in sources)

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
        before, self.shown = self.shown, look
        seconds = (look or {}).get("fade", 0) / 1000
        self._fading = ((before, look, time.monotonic(), seconds, int(time.time() * 1000))
                        if before and look and seconds else None)
        js = f"window.keshiki && keshiki.main && keshiki.main.apply({json.dumps(look)})"
        for web in self._webviews():
            web.eval(js)

    def geometry(self, web: AnkiWebView) -> dict:
        central = self.mw.form.centralwidget
        pos = web.mapTo(central, QPoint(0, 0))
        zoom = web.zoomFactor() or 1
        return {"w": central.width() / zoom, "h": central.height() / zoom, "x": pos.x() / zoom, "y": pos.y() / zoom}

    def on_js_message(self, handled: Tuple[bool, Any], message: str, context: Any) -> Tuple[bool, Any]:
        # A page resized itself: zooming changes its size in CSS pixels, with no widget event.
        if message != "keshiki:geometry":
            return handled
        if not self._geometry.pending:
            self._geometry.restart(0)
        return (True, None)

    def push_geometry(self) -> None:
        for web in self._webviews():
            web.eval(f"window.keshiki && keshiki.main && keshiki.main.geom({json.dumps(self.geometry(web))})")

    def bootstrap_js(self, web: AnkiWebView) -> str:
        if self.shown is None and self.mw.col is not None:
            self.shown = self.look()
        # A page that loads during a crossfade (Anki builds the deck list and the overview
        # after the screen has changed) starts on the look before and catches up with the
        # bars, which have been fading all along: from when it actually runs (layers.js, join).
        start, then = self.shown, ""
        if self._fading and self._fading[1] is self.shown:
            before, look, began, seconds, began_ms = self._fading
            if seconds - (time.monotonic() - began) > 0.05:
                start = before
                then = f"keshiki.main.join({json.dumps(look)}, {began_ms});"
        return f"{self._web_assets[1]}\nkeshiki.mount({json.dumps(self.geometry(web))}, {json.dumps(start)});{then}"

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
