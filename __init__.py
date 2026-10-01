# Keshiki (景色): background scenes for Anki's main window.

import logging
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
# Records from every Keshiki module land here; at profile open it also gets
# Anki's handler for logs/addons/<folder>/<folder>.log.
log = logging.getLogger(__name__)

try:
    from aqt import gui_hooks, mw
except ImportError:   # imported outside Anki (tests)
    mw = None

_renderer = None

if mw is not None:
    from .keshiki import library

    def _start_renderer():
        global _renderer
        from .keshiki.renderer import Renderer
        _renderer = Renderer(mw)
        _renderer.install()

    # Add-ons load after the main window's webviews exist and before the
    # first page renders, so the first deck list already has its background.
    _start_renderer()

    def _open_settings():
        # Function-local import so reload_addon()'s module purge picks up new dialog code.
        try:
            from .keshiki.settings_page import open_settings
            open_settings(mw, _renderer)
        except Exception:
            log.exception("Keshiki settings failed to open")
            return False   # literal False: Anki falls back to its JSON editor

    def _reload_config(*_args):
        # A new profile, or a save from Anki's raw JSON editor.
        try:
            from .keshiki.renderer import load_config
            _renderer.set_config(load_config(mw))
        except Exception:
            log.exception("Keshiki couldn't load its config")

    def _on_profile_open():
        try:
            addon_logger = mw.addonManager.get_logger(__name__)
            for handler in addon_logger.handlers:
                if handler not in log.handlers:
                    log.addHandler(handler)
            log.setLevel(logging.INFO)
        except Exception:
            log.exception("Couldn't attach Anki's add-on log")
        _reload_config()
        try:
            _start_dev_watch()
        except Exception:
            log.exception("Dev watch failed")

    def _on_toggled(enabled):
        if _renderer is not None:
            _renderer.set_enabled(enabled)

    mw.addonManager.setWebExports(__name__, library.WEB_EXPORTS)
    mw.addonManager.setConfigAction(__name__, _open_settings)
    mw.addonManager.setConfigUpdatedAction(__name__, _reload_config)
    gui_hooks.profile_did_open.append(_on_profile_open)

    try:
        from .keshiki.addon_toggle import watch_own_toggle
        watch_own_toggle(mw.addonManager, __name__, _on_toggled)
    except Exception:
        log.exception("Couldn't watch Keshiki's add-on switch")

    from aqt.qt import QAction
    _action = QAction("Keshiki Backgrounds...", mw)
    _action.triggered.connect(_open_settings)
    mw.form.menuTools.addAction(_action)


# -- dev reload -------------------------------------------------------------
# tools/dev_sync.py --watch leaves a DEV_WATCH file in the installed copy;
# with it, Anki reloads Keshiki whenever the synced source changes. Real
# installs never have the file, so for them none of this runs.

DEV_MARKER = BASE / "DEV_WATCH"
_watch_timer = None
_watch_stamp = None
_watch_pending = None


def _source_stamp():
    """(file count, newest mtime) across our own package - a cheap change signal."""
    newest, count = 0.0, 0
    for path in (BASE / "keshiki").rglob("*"):
        if path.suffix in (".py", ".js", ".css", ".html"):
            try:
                newest = max(newest, path.stat().st_mtime)
                count += 1
            except OSError:
                pass
    return count, newest


def _start_dev_watch() -> None:
    global _watch_timer, _watch_stamp
    if not DEV_MARKER.exists() or _watch_timer is not None:
        return
    from aqt.qt import QTimer
    _watch_stamp = _source_stamp()

    def _tick() -> None:
        global _watch_stamp, _watch_pending
        stamp = _source_stamp()
        if stamp == _watch_stamp:
            _watch_pending = None
            return
        # One quiet tick first: dev_sync rewrites the whole tree, and
        # reloading mid-copy would import a half-written package.
        if stamp != _watch_pending:
            _watch_pending = stamp
            return
        _watch_stamp, _watch_pending = stamp, None
        message = reload_addon()
        log.info("Dev watch: %s", message)
        from aqt.utils import tooltip
        tooltip(f"Keshiki: {message}", period=3000)

    _watch_timer = QTimer(mw)
    _watch_timer.timeout.connect(_tick)
    _watch_timer.start(1000)
    log.info("Dev watch active")


def reload_addon() -> str:
    """Dev helper: run the code now on disk without restarting Anki. From
    Anki's debug console (Ctrl+Shift+;):

        import keshiki; keshiki.reload_addon()

    Only the inner package is purged; editing this file still needs a restart.
    The settings dialog, if open, keeps its old code until reopened."""
    global _renderer
    if mw is None:
        return "not running inside Anki"
    if _renderer is not None:
        _renderer.uninstall()
        _renderer = None
    pkg = __name__ + ".keshiki"
    purged = [n for n in list(sys.modules) if n == pkg or n.startswith(pkg + ".")]
    for name in purged:
        del sys.modules[name]
    try:
        _start_renderer()
        _reload_config()
        # Pages carry the old layer code; redraw them.
        mw.toolbar.draw()
        if mw.state in ("deckBrowser", "overview", "review"):
            mw.moveToState(mw.state)
    except Exception:
        return "reload failed:\n" + traceback.format_exc()
    return f"reloaded {len(purged)} modules"
