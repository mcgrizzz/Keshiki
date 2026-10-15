import json
from types import SimpleNamespace

import pytest

from keshiki import library, settings_page
from keshiki.config import migrate
from keshiki.settings_page import SettingsBridge, page_html


@pytest.fixture(autouse=True)
def preferences_file(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    monkeypatch.setattr(settings_page, "PREFERENCES", path)
    return path


class FakeManager:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}

    def getConfig(self, _pkg):
        return self.cfg

    def writeConfig(self, _pkg, cfg):
        self.cfg = cfg


class FakeRenderer:
    launch_seed = 0

    def __init__(self):
        self.preview, self.cfg, self.scene_look = None, None, None

    def set_preview(self, cfg):
        self.preview = cfg

    def show_scene_moment(self, look):
        self.scene_look = look

    def screen(self):
        return "main"

    def set_config(self, cfg):
        self.cfg = cfg


def bridge(cfg=None):
    mw = SimpleNamespace(addonManager=FakeManager(cfg), col=None)
    return SettingsBridge(mw, FakeRenderer())


def send(b, op, arg=None):
    return b.handle("keshiki:" + json.dumps({"op": op, "arg": arg}))


def test_page_assets_are_inlined():
    html = page_html()
    assert "/*STYLE*/" not in html and "/*SCRIPT*/" not in html
    assert "keshiki-stage" in html and "pycmd(" in html


def test_ignores_other_messages_and_reports_errors():
    assert bridge().handle("domDone") is None
    assert "error" in send(bridge(), "no_such_op")


def test_state_has_a_migrated_config():
    state = send(bridge({"transition_seconds": 5}), "state")
    assert state["cfg"]["transition_seconds"] == 5 and state["cfg"]["screens"]["main"]["dim"] == 15
    assert state["defaults"]["transition_seconds"] == 2.0


def test_draft_previews_and_save_writes():
    b = bridge()
    cfg = migrate({})[0]
    cfg["transition_seconds"] = 4
    send(b, "draft", cfg)
    assert b.renderer.preview["transition_seconds"] == 4
    assert send(b, "save", cfg) == {"cfg": cfg}
    assert b.mw.addonManager.cfg == cfg and b.renderer.cfg == cfg and b.renderer.preview is None


def test_preview_in_window_can_be_turned_off_for_good(monkeypatch, preferences_file):
    monkeypatch.setattr(library, "image_url", lambda name: "/img/" + name)
    b = bridge()
    cfg = migrate({})[0]
    cfg["transition_seconds"] = 4
    scene = {"kind": "single", "versions": [{"label": "", "image": "a.jpg"}]}
    moment = {"scene": scene, "position": 0, "show": True, "cfg": cfg}
    assert send(b, "state")["in_window"] is True
    send(b, "draft", cfg)
    send(b, "compose", moment)
    assert b.renderer.preview and b.renderer.scene_look
    # Off: what Anki's window was previewing goes, and nothing new reaches it.
    send(b, "in_window", False)
    assert b.renderer.preview is None and b.renderer.scene_look is None
    send(b, "draft", cfg)
    send(b, "compose", moment)
    send(b, "moment_at", {"cfg": cfg, "minute": 600})
    assert b.renderer.preview is None and b.renderer.scene_look is None
    # Saving still reaches it, and the switch is remembered apart from the config.
    send(b, "save", cfg)
    assert b.renderer.cfg == cfg and "preview_in_window" not in b.mw.addonManager.cfg
    assert json.loads(preferences_file.read_text()) == {"preview_in_window": False}
    assert send(bridge(), "state")["in_window"] is False
    # On again: the page's draft previews as before.
    b = bridge()
    send(b, "in_window", True)
    send(b, "draft", cfg)
    assert b.renderer.preview["transition_seconds"] == 4


def test_a_broken_preferences_file_means_the_defaults(preferences_file):
    preferences_file.write_text("[not a dict")
    assert send(bridge(), "state")["in_window"] is True


def test_save_refuses_a_bad_location():
    b = bridge()
    cfg = migrate({})[0]
    cfg["day"].update(source="location", latitude=123, longitude=10)
    res = send(b, "save", cfg)
    assert res["errors"][0]["field"] == "latitude" and b.mw.addonManager.cfg == {}


def test_compose_returns_layers_and_timeline_marks(monkeypatch):
    monkeypatch.setattr(library, "image_url", lambda name: "/img/" + name)
    scene = {"kind": "day", "versions": [
        {"label": "Day", "image": "d.jpg", "anchor": "sunrise", "offset": 0, "fade": 60},
        {"label": "Night", "image": "n.jpg", "anchor": "sunset", "offset": 0, "fade": 60}]}
    day = {"source": "manual", "sunrise": "06:00", "sunset": "18:00"}
    res = send(bridge(), "compose", {"scene": scene, "day": day, "position": 6 * 60 + 30,
                                     "images": {"d.jpg": {"x": 10, "y": 20}}})
    assert [layer["src"] for layer in res["layers"]] == ["/img/n.jpg", "/img/d.jpg"]
    assert res["layers"][1]["x"] == 10 and res["layers"][1]["opacity"] == 0.5
    assert [(m["start"], m["label"]) for m in res["marks"]] == [(360, "Day"), (1080, "Night")]


def test_sun_for_a_location():
    assert send(bridge(), "sun", {"latitude": 51.5, "longitude": 0})["sunrise"] >= 0


def test_locate_reports_back_to_the_page(monkeypatch):
    import keshiki.locate
    monkeypatch.setattr(keshiki.locate, "approximate_location", lambda: {"latitude": 1.0, "longitude": 2.0, "place": "X"})
    sent = []
    b = bridge()
    b.eval_js = sent.append
    assert send(b, "locate") == {"started": True}
    assert sent == ['window.keshikiLocated && keshikiLocated({"latitude": 1.0, "longitude": 2.0, "place": "X"})']

    def offline():
        raise OSError("offline")
    monkeypatch.setattr(keshiki.locate, "approximate_location", offline)
    send(b, "locate")
    assert "offline" in sent[-1] and "error" in sent[-1]


def test_moments_name_the_sun_with_todays_times():
    moments = send(bridge(), "moments", {"day": {"source": "manual", "sunrise": "06:30", "sunset": "19:30"}})
    by_key = {m["key"]: m for m in moments}
    assert [m["key"] for m in moments][:4] == ["night-ends", "first-light", "dawn", "sunrise"]
    assert abs(by_key["sunrise"]["time"] - 390) <= 6 and abs(by_key["sunset"]["time"] - 1170) <= 6
    assert by_key["first-light"]["time"] < by_key["dawn"]["time"] < by_key["sunrise"]["time"] < by_key["noon"]["time"]
