from keshiki.config import migrate, new_scene
from keshiki.schedule import build_look, compose, day_anchors, grade_toward, light, pick_scene, version_starts

ANCHORS = {"sunrise": 6 * 60, "sunset": 19 * 60}


def day_scene():
    # Minutes from sunrise and sunset (the version 1 form, still understood):
    # the composition rules are easiest to read in fixed times.
    # dawn 5:30 (45m fade), day 7:30 (3h), dusk 18:00 (1h), night 19:30 (1h)
    versions = [("dawn.jpg", "sunrise", -30, 45), ("day.jpg", "sunrise", 90, 180),
                ("dusk.jpg", "sunset", -60, 60), ("night.jpg", "sunset", 30, 60)]
    return {"id": "d", "name": "Day", "kind": "day",
            "versions": [{"image": i, "anchor": a, "offset": o, "fade": f} for i, a, o, f in versions]}


def images(layers):
    return [(layer["image"], layer["opacity"]) for layer in layers]


def test_day_scene_holds_between_fades():
    assert images(compose(day_scene(), 12 * 60, ANCHORS)) == [("day.jpg", 1.0)]
    assert images(compose(day_scene(), 3 * 60, ANCHORS)) == [("night.jpg", 1.0)]


def test_day_scene_crossfades_from_the_previous_version():
    layers = compose(day_scene(), 7 * 60 + 30 + 90, ANCHORS)   # halfway through day's 3h fade
    assert images(layers) == [("dawn.jpg", 1.0), ("day.jpg", 0.5)]


def test_fade_eases_at_both_ends():
    early = compose(day_scene(), 18 * 60 + 6, ANCHORS)[1]["opacity"]    # 10% into dusk's fade
    late = compose(day_scene(), 18 * 60 + 54, ANCHORS)[1]["opacity"]    # 90%
    assert early < 0.1 and late > 0.9


def test_night_wraps_past_midnight_and_dawn_fades_from_night():
    scene = day_scene()
    assert images(compose(scene, 23 * 60 + 59, ANCHORS)) == [("night.jpg", 1.0)]
    assert images(compose(scene, 5 * 60 + 30 + 22.5, ANCHORS)) == [("night.jpg", 1.0), ("dawn.jpg", 0.5)]


def test_a_fade_never_runs_past_the_next_start():
    scene = day_scene()
    scene["versions"][0]["fade"] = 600   # dawn's fade would reach 15:30
    # At 7:29, dawn is clamped to its 2h slot: nearly done, not ~20%.
    assert compose(scene, 7 * 60 + 29, ANCHORS)[1]["opacity"] > 0.99


def test_versions_without_images_are_skipped():
    scene = day_scene()
    scene["versions"][1]["image"] = ""
    assert images(compose(scene, 12 * 60, ANCHORS)) == [("dawn.jpg", 1.0)]


def test_clock_anchor():
    scene = {"kind": "day", "versions": [
        {"image": "a", "anchor": "clock", "offset": 9 * 60, "fade": 0},
        {"image": "b", "anchor": "clock", "offset": 21 * 60, "fade": 0}]}
    assert images(compose(scene, 8 * 60, ANCHORS)) == [("b", 1.0)]
    assert images(compose(scene, 10 * 60, ANCHORS)) == [("a", 1.0)]


def progress_scene():
    scene = new_scene("progress")
    for v, name in zip(scene["versions"], ["start", "half", "almost", "done"], strict=True):
        v["image"] = name
    return scene   # 0, 50 (fade 30), 85 (fade 15), 100


def test_progress_scene():
    scene = progress_scene()
    assert images(compose(scene, 0, ANCHORS)) == [("start", 1.0)]
    assert images(compose(scene, 49, ANCHORS)) == [("start", 1.0)]
    assert images(compose(scene, 65, ANCHORS)) == [("start", 1.0), ("half", 0.5)]
    assert images(compose(scene, 99.9, ANCHORS))[-1][0] == "almost"
    assert images(compose(scene, 100, ANCHORS)) == [("done", 1.0)]


def test_single_scene():
    assert images(compose(new_scene("single", image="a.png"), 0, ANCHORS)) == [("a.png", 1.0)]
    assert compose(new_scene("single"), 0, ANCHORS) == []


def test_day_anchors():
    cfg = {"source": "manual", "sunrise": "09:00", "sunset": "21:15"}
    anchors = day_anchors(cfg)
    assert (anchors["sunrise"], anchors["sunset"], len(anchors["curve"])) == (540, 1275, 1441)
    curve = [0.0] * 1441
    assert day_anchors(dict(cfg, source="location"), sun=(400, 1100, curve)) == {
        "sunrise": 400, "sunset": 1100, "curve": curve}
    # No sun times (polar day, bad coordinates): the typed times stand in.
    assert day_anchors(dict(cfg, source="location"), sun=None)["sunrise"] == 540


def test_shuffle_shows_each_scene_once_per_round_without_back_to_back_repeats():
    ids = ["a", "b", "c", "d"]
    picks = [pick_scene(ids, 30, minute, 0) for minute in range(0, 30 * 4 * 50, 30)]
    for i in range(0, len(picks), 4):
        assert sorted(picks[i:i + 4]) == ids
    assert all(x != y for x, y in zip(picks, picks[1:], strict=False))


def test_shuffle_holds_for_the_interval_and_per_launch():
    assert pick_scene(["a", "b"], 60, 120, 0) == pick_scene(["a", "b"], 60, 179, 0)
    assert pick_scene(["a", "b", "c"], 0, 0, 7) == pick_scene(["a", "b", "c"], 0, 99999, 7)
    assert pick_scene([], 60, 0, 0) is None


def look(cfg, screen, percent=0.0):
    return build_look(cfg, screen, minute_of_day=12 * 60, now_minutes=0, launch_seed=0, sun=None,
                      percent_done=lambda: percent, image_url=lambda n: "/img/" + n)


def test_build_look_per_screen():
    cfg, _ = migrate({})
    day, prog = day_scene(), progress_scene()
    cfg["scenes"] = [day, prog]
    cfg["images"] = {"day.jpg": {"x": 30, "y": 70}}
    cfg["screens"]["main"]["scenes"] = [day["id"]]
    main = look(cfg, "main")
    assert main["layers"] == [{"image": "day.jpg", "src": "/img/day.jpg", "opacity": 1.0, "x": 30, "y": 70}]
    assert main["dim"] == 0.15 and main["fade"] == 2000
    # Studying follows the deck list by default, with its own dim.
    assert look(cfg, "study")["layers"] == main["layers"] and look(cfg, "study")["dim"] == 0.45
    cfg["screens"]["study"].update(same_as_main=False, scenes=[prog["id"]])
    assert look(cfg, "study", percent=100)["layers"][0]["src"] == "/img/done"
    cfg["screens"]["study"]["enabled"] = False
    assert look(cfg, "study") is None


def test_migrate_fills_defaults_and_drops_missing_scene_ids():
    cfg, changed = migrate({"screens": {"main": {"scenes": ["gone"]}}})
    assert changed and cfg["screens"]["main"]["scenes"] == [] and cfg["screens"]["main"]["dim"] == 15
    assert cfg["screens"]["study"]["same_as_main"] is True
    assert migrate(cfg) == (cfg, False)


def test_the_template_day_cycle_follows_the_sun():
    anchors = day_anchors({"source": "manual", "sunrise": "06:30", "sunset": "19:30"})
    scene = new_scene("day")
    for v, name in zip(scene["versions"], ["dawn", "day", "dusk", "night"], strict=True):
        v["image"] = name
    starts = {v["image"]: (start, fade) for start, fade, v in version_starts(scene, anchors)}
    # Dawn fills in from first light (-12°) until the sun's centre reaches the horizon,
    # a few minutes after sunrise (which counts the top edge, -0.83°); dusk mirrors it.
    assert 0 < sum(starts["dawn"]) - 390 < 8 and 45 < starts["dawn"][1] < 100
    assert 0 < 1170 - sum(starts["dusk"]) < 8
    # Night starts at dusk, in the blue hour after sunset; the day is fully in before 9.
    assert 1180 < starts["night"][0] < 1215 and starts["day"][0] + starts["day"][1] < 9 * 60
    assert images(compose(scene, 13 * 60, anchors)) == [("day", 1.0)]
    assert images(compose(scene, 1 * 60, anchors)) == [("night", 1.0)]


def test_grade_runs_from_no_change_to_matching_the_other_picture():
    dark = {"mean": [0.2, 0.2, 0.3], "std": [0.1, 0.1, 0.1]}
    warm = {"mean": [0.7, 0.5, 0.3], "std": [0.15, 0.1, 0.05]}
    assert grade_toward(dark, warm, 0) == [[1, 1, 1], [0, 0, 0]]
    gains, offsets = grade_toward(dark, warm, 1)
    # Fully graded, the dark picture's average colour lands on the warm one's.
    assert [round(g * m + o, 3) for g, m, o in zip(gains, dark["mean"], offsets, strict=True)] == [0.7, 0.5, 0.3]
    assert gains[2] == 0.6   # spread ratios are kept within 0.6-1.6


def test_light_grades_both_pictures_of_a_fade_and_adds_the_tint():
    stats = {"a": {"mean": [0.2] * 3, "std": [0.1] * 3}, "b": {"mean": [0.6] * 3, "std": [0.1] * 3}}
    layers = [{"image": "a", "opacity": 1.0}, {"image": "b", "opacity": 0.25}]
    anchors = day_anchors({"source": "manual", "sunrise": "06:00", "sunset": "19:00"})
    out = light(layers, {"match": True, "match_strength": 100, "tint": True, "tint_strength": 100},
                19 * 60, anchors, stats.get)
    # A quarter into the fade the light has already moved further (it leads, finishing at 60%):
    # smoothstep(0.25 / 0.6) = 0.3762, at the fixed 80% strength.
    assert out[0]["grade"] == grade_toward(stats["a"], stats["b"], round(0.3762 * 0.8, 4))
    assert out[1]["grade"] == grade_toward(stats["b"], stats["a"], round(0.6238 * 0.8, 4))
    late = light([layers[0], dict(layers[1], opacity=0.7)], {"match": True, "match_strength": 100}, 0, anchors,
                 stats.get)
    assert late[1]["grade"] == [[1, 1, 1], [0, 0, 0]]   # past 60%: the new picture shows in its own colours
    # The sun on the horizon: warm light on each picture; it isn't night yet, so no lights are kept apart.
    assert all(layer["light"][0][0] > layer["light"][2][2] for layer in out) and out[0]["glow"] < 0.2
    plain = light(layers, {"tint": False}, 0, anchors, stats.get)
    assert "light" not in plain[0] and "grade" in plain[0]   # smoothing the fade is always on


def test_version_1_minutes_become_sun_heights():
    v1 = {"scenes": [{"id": "s", "name": "S", "kind": "day", "versions": [
        {"label": "Dawn", "image": "a", "anchor": "sunrise", "offset": -60, "fade": 45},
        {"label": "Dusk", "image": "b", "anchor": "sunset", "offset": -75, "fade": 60},
        {"label": "Clock", "image": "c", "anchor": "clock", "offset": 600, "fade": 30}]}], "config_version": 1}
    cfg, changed = migrate(v1)
    dawn, dusk, clock = cfg["scenes"][0]["versions"]
    assert changed and cfg["config_version"] == 3
    assert dawn == {"label": "Dawn", "image": "a", "anchor": "sun", "direction": "rising", "from": -12.0, "to": -3.0}
    assert dusk == {"label": "Dusk", "image": "b", "anchor": "sun", "direction": "setting", "from": 15.0, "to": 3.0}
    assert clock["anchor"] == "clock" and clock["offset"] == 600


def test_all_done_switches_both_screens_to_the_done_scenes():
    cfg, _ = migrate({})
    day, done = day_scene(), dict(day_scene(), id="z", name="Done")
    cfg["scenes"] = [day, done]
    cfg["screens"]["main"]["scenes"] = [day["id"]]
    cfg["screens"]["done"].update(enabled=True, scenes=["z"])
    def src(screen, finished):
        return build_look(cfg, screen, minute_of_day=12 * 60, now_minutes=0, launch_seed=0, sun=None,
                          percent_done=lambda: 0, image_url=lambda n: n, all_done=lambda: finished)
    assert src("main", False)["layers"] == src("main", True)["layers"]   # same pictures here...
    # ...so tell them apart by which scene the shuffle had to choose from.
    from keshiki.schedule import screen_source
    assert screen_source(cfg, "main", lambda: True)[0] is cfg["screens"]["done"]
    assert screen_source(cfg, "study", lambda: True)[0] is cfg["screens"]["done"]
    assert screen_source(cfg, "study", lambda: True)[1] is cfg["screens"]["done"]   # its dim and blur too
    assert screen_source(cfg, "main", lambda: False)[0] is cfg["screens"]["main"]
    cfg["screens"]["done"]["enabled"] = False
    assert screen_source(cfg, "main", lambda: True)[0] is cfg["screens"]["main"]


def test_lights_are_kept_in_night_pictures_but_a_day_picture_darkens_all_over():
    stats = {"night": {"mean": [0.1, 0.12, 0.25], "std": [0.1] * 3}, "noon": {"mean": [0.6, 0.7, 0.9], "std": [0.2] * 3}}
    anchors = day_anchors({"source": "manual", "sunrise": "06:00", "sunset": "19:00"})
    cfg = {"tint": True, "tint_strength": 100}
    night = light([{"image": "night", "opacity": 1.0}], cfg, 23 * 60, anchors, stats.get)[0]
    noon = light([{"image": "noon", "opacity": 1.0}], cfg, 23 * 60, anchors, stats.get)[0]
    assert night["glow"] > 0.9 and noon["glow"] == 0
    assert noon["light"][1][1] < 0.3 < night["light"][1][1]    # and only the day picture is darkened much


def test_a_night_picture_brings_its_lights_and_a_day_picture_doesnt():
    stats = {"night": {"mean": [0.1, 0.12, 0.25], "std": [0.1] * 3}, "noon": {"mean": [0.6, 0.7, 0.9], "std": [0.2] * 3}}
    anchors = day_anchors({"source": "manual", "sunrise": "06:00", "sunset": "19:00"})
    lights = {"night": "/lights/night", "noon": "/lights/noon"}.get
    cfg = {"tint": True, "tint_strength": 100}
    assert light([{"image": "night", "opacity": 1.0}], cfg, 23 * 60, anchors, stats.get, lights)[0]["lights"] == "/lights/night"
    assert "lights" not in light([{"image": "noon", "opacity": 1.0}], cfg, 23 * 60, anchors, stats.get, lights)[0]
    # By day there's nothing to shine.
    assert "lights" not in light([{"image": "night", "opacity": 1.0}], cfg, 13 * 60, anchors, stats.get, lights)[0]


def test_bloom_rides_along_with_a_pictures_lights():
    stats = {"night": {"mean": [0.1, 0.12, 0.25], "std": [0.1] * 3}}
    anchors = day_anchors({"source": "manual", "sunrise": "06:00", "sunset": "19:00"})
    layer = light([{"image": "night", "opacity": 1.0}], {"tint": True, "tint_strength": 100, "bloom": 80},
                  23 * 60, anchors, stats.get, lambda n: "/l")[0]
    assert layer["bloom"] == 0.8


def test_version_3_drops_the_smoothing_switch():
    cfg, changed = migrate({"light": {"tint": True, "match": False, "match_strength": 40}, "config_version": 2})
    assert changed and cfg["light"] == {"tint": True, "tint_strength": 70, "bloom": 50} and cfg["config_version"] == 3
