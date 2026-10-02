import json
from types import SimpleNamespace

from keshiki import library
from keshiki.config import migrate
from keshiki.settings_page import SettingsBridge, page_html


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
        self.preview, self.cfg = None, None

    def set_preview(self, cfg):
        self.preview = cfg

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


def test_moments_give_other_heights_their_times_too():
    day = {"source": "manual", "sunrise": "06:30", "sunset": "19:30"}
    moments = send(bridge(), "moments", {"day": day, "extra": [["rising", 15], ["setting", 3]]})
    named = [m for m in moments if not m.get("custom")]
    custom = {(m["direction"], m["degrees"]): m["time"] for m in moments if m.get("custom")}
    assert len(named) == 15 and set(custom) == {("rising", 15), ("setting", 3)}
    by_key = {m["key"]: m["time"] for m in named}
    assert by_key["mid-morning"] < custom[("rising", 15)] < by_key["morning"]   # between 12° and 20°, rising
    assert by_key["golden"] < custom[("setting", 3)] < by_key["sunset"]        # between 6° and 0°, setting
