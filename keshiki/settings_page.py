"""The settings page: one HTML page in an AnkiWebView, talking to SettingsBridge over pycmd.

The bridge works on plain dicts and takes its Qt side effects as callables,
so it can be tested headless; the dialog keeps its aqt imports local.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from . import library
from .config import ADDON_PACKAGE, DEFAULTS, SUN_MOMENTS, migrate, new_scene, validate
from .schedule import build_look, day_anchors, light, screen_source, version_starts
from .schedule import compose as compose_layers
from .sun import location_sun

WEB_DIR = Path(__file__).resolve().parent / "web"
_PREFIX = "keshiki:"
_GEOM_KEY = "keshikiSettings"


def page_html() -> str:
    def read(name):
        return (WEB_DIR / name).read_text(encoding="utf-8")
    # Inlined: nothing to serve, and the preview reuses the main window's layer code.
    return (read("settings.html")
            .replace("/*STYLE*/", read("layers.css") + read("settings.css"))
            .replace("/*SCRIPT*/", read("layers.js") + read("settings.js")))


def _now():
    now = datetime.now().astimezone()
    return now, now.utcoffset().total_seconds() / 60


def _sun(day_cfg: dict):
    if day_cfg.get("source") != "location":
        return None
    now, offset = _now()
    try:
        return location_sun(now.date(), float(day_cfg["latitude"]), float(day_cfg["longitude"]), offset)
    except (TypeError, ValueError, KeyError):
        return None


def _times(anchors: dict) -> dict:
    """Sunrise and sunset for the page, without the minute-by-minute sun curve."""
    return {"sunrise": anchors["sunrise"], "sunset": anchors["sunset"]}


class SettingsBridge:
    def __init__(self, mw, renderer=None, *, close: Callable[[], None] = lambda: None,
                 pick_files: Callable[[], list] = lambda: [], open_folder: Callable[[Path], None] = lambda p: None,
                 in_background: Callable = lambda fn, done: done(fn()), eval_js: Callable[[str], None] = lambda js: None):
        self.mw = mw
        self.renderer = renderer
        self.close = close
        self.pick_files = pick_files
        self.open_folder = open_folder
        # in_background(fn, done): run fn off the main thread, then done(fn's result
        # or exception) on it. eval_js reaches the page after the reply has gone.
        self.in_background = in_background
        self.eval_js = eval_js
        self.dirty = False

    def handle(self, cmd: str) -> Any:
        if not cmd.startswith(_PREFIX):
            return None
        try:
            msg = json.loads(cmd[len(_PREFIX):])
            return getattr(self, "op_" + msg["op"])(msg.get("arg"))
        except Exception as exc:
            logging.getLogger(__name__).exception("Keshiki settings request failed")
            return {"error": str(exc)}

    def saved(self) -> dict:
        return migrate(self.mw.addonManager.getConfig(ADDON_PACKAGE) or {})[0]

    def op_state(self, _arg) -> dict:
        return {"cfg": self.saved(), "defaults": migrate({})[0], "images": library.list_images(),
                "templates": {k: new_scene(k) for k in ("single", "day", "progress")},
                "percent": self._percent(), "window": self._window_size()}

    def _window_size(self) -> list:
        """The main area's shape, so the image picker can show what it will crop."""
        central = getattr(getattr(self.mw, "form", None), "centralwidget", None)
        return [central.width(), central.height()] if central and central.height() else [16, 10]

    def op_new_scene(self, arg) -> dict:
        return new_scene(arg.get("kind", "single"), image=arg.get("image", ""))

    def op_save(self, cfg) -> dict:
        cfg, _ = migrate(cfg)
        errors = validate(cfg)
        if errors:
            return {"errors": errors}
        self.mw.addonManager.writeConfig(ADDON_PACKAGE, cfg)
        if self.renderer:
            self.renderer.preview = None
            self.renderer.set_config(cfg)
        self.dirty = False
        return {"cfg": cfg}

    def op_draft(self, cfg) -> None:
        # Unsaved edits show live in the main window until Save or Cancel.
        if self.renderer:
            self.renderer.set_preview(migrate(cfg)[0] if cfg else None)

    def op_end_moment(self, _arg) -> None:
        if self.renderer and self.renderer.scene_look is not None:
            self.renderer.show_scene_moment(None)

    def op_dirty(self, value) -> None:
        self.dirty = bool(value)

    def op_close(self, _arg) -> None:
        self.dirty = False
        self.close()

    def op_import(self, _arg) -> dict:
        added = library.import_files(self.pick_files())
        return {"images": library.list_images(), "added": added}

    def op_delete_image(self, name) -> dict:
        library.delete(name)
        return {"images": library.list_images()}

    def op_open_folder(self, _arg) -> None:
        library.IMAGES.mkdir(parents=True, exist_ok=True)
        self.open_folder(library.IMAGES)

    def op_compose(self, arg) -> dict:
        """One scene at a given position, for the scene editor's preview and timeline."""
        scene, day_cfg = arg["scene"], arg.get("day") or DEFAULTS["day"]
        anchors = day_anchors(day_cfg, _sun(day_cfg))
        position = float(arg.get("position") or 0)
        layers = compose_layers(scene, position, anchors)
        # The tint follows the clock: the scrubbed time for a day cycle, now for anything else.
        now, _ = _now()
        minute = position if scene.get("kind") == "day" else now.hour * 60 + now.minute
        layers = light(layers, arg.get("light") or DEFAULTS["light"], minute, anchors, library.image_stats,
                       library.lights_url)
        focus = arg.get("images") or {}
        out = [dict(layer, src=library.image_url(layer["image"]),
                    **{k: (focus.get(layer["image"]) or {}).get(k, 50) for k in ("x", "y")}) for layer in layers]
        if self.renderer and "show" in arg:
            # The scrubbed moment in Anki's main window too, with the current screen's dim and blur.
            moment = None
            if arg["show"] and out:
                cfg = migrate(arg.get("cfg") or {})[0]
                _, look = screen_source(cfg, self.renderer.screen())
                moment = {"layers": out, "dim": round(float(look.get("dim") or 0) / 100, 3),
                          "blur": float(look.get("blur") or 0), "fade": int(arg.get("fade") or 0)}
            if moment or self.renderer.scene_look is not None:
                self.renderer.show_scene_moment(moment)
        return {
            "layers": out,
            "marks": [{"start": start, "fade": fade, "label": v.get("label", ""), "image": v["image"],
                       "index": next(i for i, x in enumerate(scene["versions"]) if x is v)}
                      for start, fade, v in version_starts(scene, anchors)],
            "anchors": _times(anchors),
        }

    def op_look(self, arg) -> Optional[dict]:
        """What a screen would show right now with the draft config."""
        cfg = migrate(arg["cfg"])[0]
        now, offset = _now()
        # "done": the deck list as it looks once everything is studied today.
        done = arg["screen"] == "done"
        return build_look(cfg, "main" if done else arg["screen"], all_done=(lambda: True) if done else self._all_done, minute_of_day=now.hour * 60 + now.minute,
                          now_minutes=int(now.timestamp() / 60 + offset),
                          launch_seed=getattr(self.renderer, "launch_seed", 0), sun=_sun(cfg["day"]),
                          percent_done=self._percent, image_url=library.image_url,
                          image_stats=library.image_stats, image_lights=library.lights_url)

    def op_locate(self, _arg) -> dict:
        """Start a location lookup; the page hears back through keshikiLocated()."""
        from .locate import approximate_location

        def run():
            try:
                return approximate_location()
            except Exception as exc:
                return {"error": f"Couldn't find your location ({exc}). Enter it by hand."}

        def done(result):
            self.eval_js(f"window.keshikiLocated && keshikiLocated({json.dumps(result)})")

        self.in_background(run, done)
        return {"started": True}

    def op_daylight(self, arg) -> dict:
        """How a light grey wall looks every 10 minutes today, for the strip on the Day & time page."""
        from .daylight import grey_seen
        from .sun import elevation_at
        day_cfg = arg.get("day") or DEFAULTS["day"]
        anchors = day_anchors(day_cfg, _sun(day_cfg))
        strength = float(arg.get("strength", 70)) / 100
        return {"samples": [grey_seen(elevation_at(anchors["curve"], m), strength) for m in range(0, 1441, 10)],
                "anchors": _times(anchors)}

    def op_moments(self, arg) -> list:
        """The sun's named moments with today's times, for the day-cycle version rows."""
        from .sun import crossing
        day_cfg = arg.get("day") or DEFAULTS["day"]
        curve = day_anchors(day_cfg, _sun(day_cfg))["curve"]
        return [{"key": key, "direction": direction, "degrees": degrees, "name": name,
                 "time": round(crossing(curve, degrees, direction == "rising"))}
                for key, direction, degrees, name in SUN_MOMENTS]

    def op_sun(self, day_cfg) -> Optional[dict]:
        times = _sun(dict(day_cfg, source="location"))
        return {"sunrise": times[0], "sunset": times[1]} if times else None

    def _all_done(self) -> bool:
        if self.renderer and getattr(self.mw, "col", None):
            try:
                return self.renderer.all_done()
            except Exception:
                pass
        return False

    def _percent(self) -> float:
        if self.renderer and getattr(self.mw, "col", None):
            try:
                return self.renderer.percent_done()
            except Exception:
                pass
        return 0.0


def open_settings(mw, renderer) -> None:
    make_dialog(mw, renderer).exec()


def make_dialog(mw, renderer):
    from aqt.qt import QDialog, QFileDialog, QTimer, QVBoxLayout
    from aqt.utils import disable_help_button, openFolder, restoreGeom, saveGeom
    from aqt.webview import AnkiWebView

    class SettingsDialog(QDialog):
        def reject(self):   # X / Esc
            if bridge.dirty:
                web.eval("askClose()")
            else:
                super().reject()

    dlg = SettingsDialog(mw)
    dlg.setWindowTitle("Keshiki Backgrounds")
    disable_help_button(dlg)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    web = AnkiWebView(parent=dlg, title="Keshiki settings")
    layout.addWidget(web)

    def pick_files():
        paths, _ = QFileDialog.getOpenFileNames(
            dlg, "Add background images", "", "Images (" + " ".join("*" + e for e in library.EXTENSIONS) + ")")
        return paths

    # Deferred so the bridge's reply reaches the page before the page goes.
    def in_background(fn, done):
        mw.taskman.run_in_background(fn, lambda future: done(future.result()))

    bridge = SettingsBridge(mw, renderer, close=lambda: QTimer.singleShot(0, dlg.accept),
                            pick_files=pick_files, open_folder=lambda p: openFolder(str(p)),
                            in_background=in_background, eval_js=lambda js: web.eval(js))
    dlg.keshiki_bridge, dlg.keshiki_web = bridge, web   # for tools/check_settings.py
    web.set_bridge_command(bridge.handle, dlg)
    web.stdHtml(page_html(), context=dlg)

    def finished(_result):
        saveGeom(dlg, _GEOM_KEY)
        if renderer:
            renderer.scene_look = None
            renderer.set_preview(None)
        web.cleanup()

    dlg.finished.connect(finished)
    dlg.resize(1100, 780)
    restoreGeom(dlg, _GEOM_KEY)
    return dlg
