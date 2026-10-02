# Keshiki (景色): background scenes for Anki's main window.
#
# The wiring with Anki (settings action, Tools menu, log file, add-on switch,
# dev reload) is Kiso's Addon; the callbacks here import Keshiki's modules inside
# the function, so a reload brings in the new code.

try:
    from aqt import mw
except ImportError:   # imported outside Anki (tests)
    mw = None

addon = None

if mw is not None:
    from .keshiki import library
    from .keshiki._kiso.addon import Addon

    def _start():
        from .keshiki.renderer import Renderer
        renderer = Renderer(mw)
        renderer.install()
        return renderer

    def _settings():
        from .keshiki.settings_page import open_settings
        open_settings(mw, addon.feature)

    def _config(a):
        # A new profile, or a save from Anki's raw JSON editor.
        from .keshiki.renderer import load_config
        if a.feature:
            a.feature.set_config(load_config(mw))

    def _toggled(a, enabled):
        if a.feature:
            a.feature.set_enabled(enabled)

    def _redraw(_a):
        # Pages carry the old layer code; redraw them.
        mw.toolbar.draw()
        if mw.state in ("deckBrowser", "overview", "review"):
            mw.moveToState(mw.state)

    # Add-ons load after the main window's webviews exist and before the first
    # page renders, so the first deck list already has its background.
    addon = Addon(__name__, inner="keshiki", start=_start, stop=lambda r: r.teardown(),
                  settings=_settings, menu="Keshiki Backgrounds...", on_config=_config,
                  on_toggle=_toggled, after_reload=_redraw, web_exports=library.WEB_EXPORTS)
    addon.install()


def reload_addon() -> str:
    """Dev helper: run the code now on disk without restarting Anki. From Anki's
    debug console (Ctrl+Shift+;): import keshiki; keshiki.reload_addon()"""
    return addon.reload() if addon else "not running inside Anki"
