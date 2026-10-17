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
from ._kiso.hooks import Subscriptions, guard
from .config import ADDON_PACKAGE, migrate
from .display import Display
from .schedule import build_look, screen_source
from .sun import location_sun

log = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent / "web"
# How often the background is worked out again. It only reaches the page when
# something changed (looks are rounded to 0.1%). These steps are small (3.4% at
# most, at sunset), so the page eases them in over 0.8 s; bigger changes ease in
# over transition_seconds (layers.js, Stage.small).
TICK_MS = 30_000
# A screen change waits for Anki's new page to draw (it builds the deck list, overview and
# reviewer after the screen has changed), so the bars and the page fade together from the
# start; this long at most, for a change that brings no page.
SCREEN_SETTLE_MS = 1000
STUDY_STATES = ("overview", "review")


def now_minutes() -> int:
    """Minutes since the epoch, in local time: what shuffles count in."""
    now = datetime.now().astimezone()
    return int(time.time() / 60 + now.utcoffset().total_seconds() / 60)


def same_but_files(a: Optional[dict], b: Optional[dict]) -> bool:
    """Whether two looks differ only in their pictures' files (a copy made for one)."""
    def bare(look: dict) -> dict:
        return dict(look, layers=[{k: v for k, v in layer.items() if k != "src"} for layer in look.get("layers") or []])
    return bool(a and b) and bare(a) == bare(b)


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
        self.chosen: Optional[dict] = None   # a turn picked to show now (schedule.current_turn)
        self.shown: Optional[dict] = None     # the look on screen now
        # A crossfade under way: (the look before, the look it's fading to, when it began
        # (monotonic), seconds, when it began (epoch ms, for the page)).
        self._fading: Optional[Tuple[dict, dict, float, float, int]] = None
        self._progress: Optional[float] = None
        self._all_done: Optional[bool] = None
        self._watching = False   # the screens (watch_screens)
        self.torn_down = False   # a dev reload replaced it (a settings window open since may still call it)
        self.enabled = True   # False once turned off in Tools > Add-ons, until Anki restarts
        self.subs = Subscriptions(log)
        self._geometry = self.subs.debounce(self, self.push_geometry, "Background geometry")
        # A screen change waiting for its page (on_screen_change): looks wait too.
        self._settling = self.subs.debounce(self, self.screen_settled, "Screen change")
        self._web_assets = (WEB / "layers.css").read_text(encoding="utf-8"), \
            (WEB / "layers.js").read_text(encoding="utf-8")
        # Copies are made beside the collection's work, never holding it up (an answer, a sync).
        self.display = Display(lambda fn, done: mw.taskman.run_in_background(
            fn, lambda fut: done(fut.result()), uses_collection=False), lambda: self.refresh())

    # -- wiring -----------------------------------------------------------

    def install(self) -> None:
        refresh_progress = lambda *_: self.refresh(progress_changed=True)  # noqa: E731
        self.subs.add(gui_hooks.webview_will_set_content, self.on_will_set_content, "Page background")
        self.subs.add(gui_hooks.webview_did_inject_style_into_page, self.on_did_inject_style, "Page background")
        self.subs.add(gui_hooks.state_did_change, self.on_screen_change, "Screen change")
        self.subs.add(gui_hooks.reviewer_did_answer_card, self.on_answer, "Answer")
        self.subs.add(gui_hooks.operation_did_execute, self.on_operation, "Collection change")
        # A new day brings new cards: "all done" may no longer hold.
        self.subs.add(gui_hooks.day_did_change, refresh_progress, "New day")
        self.subs.filter(gui_hooks.webview_did_receive_js_message, self.on_js_message, "Page message")
        self.subs.timer(self, TICK_MS, self.refresh, "Background tick")
        try:
            library.prune_display()   # before any copy is in use
        except OSError:
            log.exception("Couldn't prune the display copies")
        self.display.cover(*self.screen_pixels())
        self.on_theme_change(refresh=False)
        self.subs.add(gui_hooks.theme_did_change, self.on_theme_change, "Theme change")
        self.watch_screens()
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
        self.torn_down = True
        self.subs.remove_all()
        self.display.stopped = True
        self._watching = False   # the screens' connections stay, doing nothing (see watch_screens)
        try:
            from aqt.qt import QGuiApplication
            QGuiApplication.instance().screenAdded.disconnect(self._screen_added)
        except (AttributeError, TypeError, RuntimeError):   # never connected
            pass
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

    def choose(self, scene: str, image: str) -> None:
        """Show this album's picture now, on the screens that have the album, until their
        shuffle moves on."""
        self.chosen = {"scene": scene, "image": image, "at": now_minutes()}
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
        return build_look(
            cfg, self.screen(),
            minute_of_day=now.hour * 60 + now.minute + now.second / 60,
            now_minutes=now_minutes(),
            launch_seed=self.launch_seed,
            sun=self.sun_today(cfg["day"], now.date(), now.utcoffset().total_seconds() / 60),
            percent_done=self.percent_done,
            # Unblurred: copies only if asked for (they're a little softer); blurred: always.
            image_url=self.display.url if cfg.get("display_copies") else library.image_url,
            image_stats=library.image_stats,
            image_lights=library.lights_url,
            all_done=self.all_done,
            chosen=self.chosen,
            copy_url=self.display.url,   # a blurred screen: copies
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

    def on_screen_change(self, *_) -> None:
        """A new screen: its look waits until Anki's new page has drawn (on_js_message, ready)
        or SCREEN_SETTLE_MS, whichever comes first. Meanwhile the page that loads starts on the
        look already showing, and then everything fades to the new one together."""
        self._progress = None
        self._all_done = None
        self._settling.restart(SCREEN_SETTLE_MS / 1000)

    def screen_settled(self) -> None:
        self._settling.cancel()
        self.refresh()

    def refresh(self, progress_changed: bool = False) -> None:
        if self.torn_down:
            return   # its timers are gone; the new renderer has the window
        if progress_changed:
            self._progress = None
            self._all_done = None
        if self._settling.pending:
            return   # screen_settled brings the latest look
        if self.mw.col is None:
            return
        look = self.look()
        if look == self.shown:
            return
        before, self.shown = self.shown, look
        seconds = (look or {}).get("fade", 0) / 1000
        fading = self._fading
        if fading and same_but_files(fading[1], look) and time.monotonic() - fading[2] < fading[3]:
            # A copy made mid-fade: the pages swap the file in place and carry on with the
            # fade they're in, so a page that loads now joins that one, from where it began.
            self._fading = (fading[0], look, *fading[2:])
        else:
            self._fading = ((before, look, time.monotonic(), seconds, int(time.time() * 1000))
                            if before and look and seconds else None)
        began_ms = self._fading[4] if self._fading else int(time.time() * 1000)
        js = f"window.keshiki && keshiki.main && keshiki.main.apply({json.dumps(look)}, false, 0, {began_ms})"
        for web in self._webviews():
            web.eval(js)

    def geometry(self, web: AnkiWebView) -> dict:
        central = self.mw.form.centralwidget
        pos = web.mapTo(central, QPoint(0, 0))
        zoom = web.zoomFactor() or 1
        return {"w": central.width() / zoom, "h": central.height() / zoom, "x": pos.x() / zoom, "y": pos.y() / zoom}

    def on_js_message(self, handled: Tuple[bool, Any], message: str, context: Any) -> Tuple[bool, Any]:
        # The main area's new page has drawn its first frame: a screen change can fade now.
        if message == "keshiki:ready":
            if self._settling.pending and self._web_for_context(context) is self.mw.web:
                self.screen_settled()
            # Its place in the window as it is now: a page set up while Anki was still laying the
            # window out (at launch) could otherwise keep a place measured before that settled.
            if not self._geometry.pending:
                self._geometry.restart(0)
            return (True, None)
        # A page resized itself: zooming changes its size in CSS pixels, with no widget event.
        if message != "keshiki:geometry":
            return handled
        if not self._geometry.pending:
            self._geometry.restart(0)
        return (True, None)

    def on_theme_change(self, refresh: bool = True) -> None:
        """A see-through picture's copies are laid on the theme's canvas, which shows through it."""
        from aqt import colors
        from aqt.theme import theme_manager
        self.display.backdrop = library.backdrop_hex(theme_manager.var(colors.CANVAS))
        if refresh:
            self.refresh()

    def screen_pixels(self) -> Tuple[float, float]:
        """The most device pixels a background may have to fill, across and down: the largest
        screen's (the window may move there), or the window's if it's bigger (across two)."""
        from aqt.qt import QGuiApplication
        sizes = [(s.geometry().width() * s.devicePixelRatio(), s.geometry().height() * s.devicePixelRatio())
                 for s in QGuiApplication.screens()]
        central = self.mw.form.centralwidget
        ratio = central.devicePixelRatioF()
        sizes.append((central.width() * ratio, central.height() * ratio))
        return max(w for w, _ in sizes), max(h for _, h in sizes)

    def watch_screens(self) -> None:
        """A screen plugged in, or a screen's resolution or scaling changed, may need bigger
        copies, whether or not Anki's window moves (moving and resizing it are watched anyway).
        Each screen is connected once, when it's first seen. Signals are never compared (that
        crashes PyQt on Windows), and a screen's are never disconnected: one that's gone may
        be, and touching it would crash too. After teardown they do nothing."""
        from aqt.qt import QGuiApplication
        app = QGuiApplication.instance()
        self._watching = True
        self._screens_changed = guard(self.on_screens_changed, log, "Screens changed")
        self._screen_added = guard(self.on_screen_added, log, "Screen added")
        app.screenAdded.connect(self._screen_added)
        for screen in app.screens():
            self.watch_screen(screen)

    def watch_screen(self, screen) -> None:
        screen.geometryChanged.connect(self._screens_changed)
        screen.logicalDotsPerInchChanged.connect(self._screens_changed)

    def on_screen_added(self, screen) -> None:
        if self._watching:
            self.watch_screen(screen)
            self.on_screens_changed()

    def on_screens_changed(self, *_) -> None:
        if self._watching and not self._geometry.pending:
            self._geometry.restart(0)

    def push_geometry(self) -> None:
        if self.display.cover(*self.screen_pixels()):
            self.refresh()   # bigger copies (the pictures themselves until they're made)
        for web in self._webviews():
            web.eval(f"window.keshiki && keshiki.main && keshiki.main.geom({json.dumps(self.geometry(web))})")

    def bootstrap_js(self, web: AnkiWebView) -> str:
        if self.shown is None and self.mw.col is not None:
            self.shown = self.look()
            # The first look. Pages drawn before the collection was open (Anki draws the
            # toolbar once, at launch) started bare: they show it too, as this page will.
            js = f"window.keshiki && keshiki.main && keshiki.main.apply({json.dumps(self.shown)}, true)"
            for other in self._webviews():
                if other is not web:
                    other.eval(js)
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
