"""Which images a screen shows at a given moment. Pure, tested headless.

A scene is a list of versions placed along an axis: minutes of the day for
day-cycle scenes (it wraps at midnight) and percent of today's reviews done
for progress scenes. A day-cycle version is usually tied to the sun's height
("fades in as the rising sun goes from -10° to 0°"), which this module turns
into minutes using the day's sun curve. A version holds from its start until the next one
starts, and fades in over its first `fade` units, so the result is at most
two layers: the previous version underneath, the new one on top.
"""

from __future__ import annotations

import random
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import daylight
from .config import parse_hhmm, scenes_by_id
from .sun import crossing, elevation_at, synthetic_curve

_synthetic = lru_cache(maxsize=8)(lambda sunrise, sunset: synthetic_curve(sunrise, sunset))

DAY = 1440


def screen_source(cfg: dict, screen: str, all_done: Callable[[], bool] = lambda: False
                  ) -> Tuple[Optional[dict], dict]:
    """(where the screen's scenes come from, where its dim and blur come
    from); the first is None when the screen shows no background. Once
    nothing is left to study today, the "done" scenes and look take over if set."""
    screens = cfg["screens"]
    look = screens["study"] if screen == "study" else screens["main"]
    if screen == "study" and not look.get("enabled", True):
        return None, look
    done = screens.get("done") or {}
    if done.get("enabled") and done.get("scenes") and all_done():
        return done, done
    if screen != "study" or look.get("same_as_main"):
        return screens["main"], look
    return look, look


def build_look(cfg: dict, screen: str, *, minute_of_day: float, now_minutes: int, launch_seed: int,
               sun: Optional[Tuple[int, int]], percent_done: Callable[[], float],
               image_url: Callable[[str], str], image_stats: Callable[[str], Optional[dict]] = lambda n: None,
               all_done: Callable[[], bool] = lambda: False,
               image_lights: Callable[[str], Optional[str]] = lambda n: None) -> Optional[dict]:
    """What a screen shows now, in the shape layers.js takes, or None for no background."""
    source, look = screen_source(cfg, screen, all_done)
    if source is None:
        return None
    turn = pick_scene(screen_turns(cfg, source.get("scenes") or []), int(source.get("every") or 0),
                      now_minutes, launch_seed)
    scene = scene_for_turn(cfg, turn or "")
    if scene is None:
        return None
    position = percent_done() if scene.get("kind") == "progress" else minute_of_day
    anchors = day_anchors(cfg["day"], sun)
    layers = compose(scene, position, anchors)
    if not layers:
        return None
    focus = cfg.get("images") or {}
    out = light(layers, cfg.get("light") or {}, minute_of_day, anchors, image_stats, image_lights, kind=scene.get("kind"))
    return {
        "layers": [dict(layer, src=image_url(layer["image"]),
                        x=(focus.get(layer["image"]) or {}).get("x", 50),
                        y=(focus.get(layer["image"]) or {}).get("y", 50)) for layer in out],
        "dim": round(_num(look.get("dim")) / 100, 3),
        "blur": _num(look.get("blur")),
        "fade": int(_num(cfg.get("transition_seconds")) * 1000),
    }


# -- light ------------------------------------------------------------------
# Two optional effects on top of the pictures. Daylight lights every picture
# by the sun's height (daylight.py). Light matching runs during a fade between
# two versions: each picture's colours are shifted toward the other's, so the
# light changes smoothly while the details crossfade.

MATCH_STRENGTH = 0.8


def grade_toward(src: dict, dst: dict, t: float) -> List[List[float]]:
    """Per-channel gains and offsets moving src's colours a fraction t of the way to
    dst's (matching each channel's mean and spread), as [[gains], [offsets]] in 0-1 units."""
    gains, offsets = [], []
    for m0, s0, m1, s1 in zip(src["mean"], src["std"], dst["mean"], dst["std"], strict=True):
        g = min(max(s1 / s0 if s0 > 0.01 else 1.0, 0.6), 1.6)
        gains.append(round(1 + (g - 1) * t, 3))
        offsets.append(round((m1 - g * m0) * t, 3))
    return [gains, offsets]


def light(layers: List[dict], cfg: dict, minute: float, anchors: Dict[str, Any],
          image_stats: Callable[[str], Optional[dict]],
          image_lights: Callable[[str], Optional[str]] = lambda n: None, kind: Optional[str] = None) -> List[dict]:
    """The layers with their colour grade (fades), daylight matrix, and at night their
    own lights (an image of just the lights) and how much they shine (glow). Daylight
    lights only day cycles (`kind` "day") unless its scope is "all"."""
    layers = [dict(layer) for layer in layers]
    # Smoothing the colour between versions: always on (it helps or changes nothing).
    strength = MATCH_STRENGTH
    if len(layers) == 2:
        below, above = (image_stats(layer["image"]) for layer in layers)
        if below and above:
            # The light leads the pixels: the colours finish moving by 60% of the
            # fade, while the details are still crossfading.
            lead = min(layers[1]["opacity"] / 0.6, 1.0)
            lead = lead * lead * (3 - 2 * lead)
            layers[0]["grade"] = grade_toward(below, above, round(lead * strength, 4))
            layers[1]["grade"] = grade_toward(above, below, round((1 - lead) * strength, 4))
    if cfg.get("tint") and anchors.get("curve") and (cfg.get("scope", "day") == "all" or kind == "day"):
        # Per picture: how much night it gets depends on whether it already shows night.
        elevation = elevation_at(anchors["curve"], minute)
        strength = _num(cfg.get("tint_strength", 70)) / 100
        glow = daylight.glow(elevation, strength)
        for layer in layers:
            stats = image_stats(layer["image"])
            luma = 0.2126 * stats["mean"][0] + 0.7152 * stats["mean"][1] + 0.0722 * stats["mean"][2] if stats else 0.5
            layer["light"] = daylight.matrix(elevation, strength, luma)
            # Bright spots are lights only in a picture that shows night: in a day
            # picture they're sky and sunlit things, which darken with the rest.
            layer["glow"] = round(glow * (1 - daylight.picture_daylight(luma)), 3)
            lights = image_lights(layer["image"]) if layer["glow"] > 0 else None
            if lights:
                layer["lights"] = lights
                layer["bloom"] = _num(cfg.get("bloom", 50)) / 100
    return layers


def day_anchors(day_cfg: dict, sun: Optional[Tuple[int, int, List[float]]] = None) -> Dict[str, Any]:
    """Sunrise and sunset in minutes after midnight, and the sun's elevation each
    minute ("curve"). `sun` is today's (sunrise, sunset, curve) for a location;
    otherwise the typed times stand in, on the sun path that fits them."""
    if day_cfg.get("source") == "location" and sun:
        return {"sunrise": sun[0], "sunset": sun[1], "curve": sun[2]}
    sunrise = parse_hhmm(day_cfg.get("sunrise")) or 390
    sunset = parse_hhmm(day_cfg.get("sunset")) or 1170
    return {"sunrise": sunrise, "sunset": sunset, "curve": _synthetic(sunrise, sunset)}


def version_starts(scene: dict, anchors: Dict[str, int]) -> List[Tuple[float, float, dict]]:
    """(start, fade, version) for the versions that have an image, sorted by start.

    A day version can start when the one above it is fully in, `offset` minutes
    later (anchor "after"), so times are worked out in list order, versions without
    an image included: the chain holds while a picture is still to be chosen."""
    marks = []
    above_full = None   # when the version above is fully in (a day scene)
    for v in scene.get("versions") or []:
        start, fade = _start_and_fade(scene, v, anchors, above_full)
        if scene.get("kind") == "day":
            above_full = (start + fade) % DAY
        if v.get("image"):
            marks.append((start, fade, v))
    marks.sort(key=lambda m: m[0])
    return marks


def _start_and_fade(scene: dict, v: dict, anchors: Dict[str, int], above_full: Optional[float]) -> Tuple[float, float]:
    kind = scene.get("kind")
    if kind == "day" and v.get("anchor") == "sun" and anchors.get("curve"):
        rising = v.get("direction", "rising") == "rising"
        start = crossing(anchors["curve"], _num(v.get("from")), rising)
        full = crossing(anchors["curve"], _num(v.get("to")), rising)
        return start, (full - start) % DAY
    if kind == "day":
        if v.get("anchor") == "after":
            base = above_full or 0   # the first version has nothing above: midnight
            start = (base + max(_num(v.get("offset")), 0)) % DAY
        else:
            base = 0 if v.get("anchor") == "clock" else anchors.get(v.get("anchor"), 0)
            start = (base + _num(v.get("offset"))) % DAY
    elif kind == "progress":
        start = min(max(_num(v.get("at")), 0), 100)
    else:
        start = 0
    return start, max(_num(v.get("fade")), 0)


def compose(scene: Optional[dict], position: float, anchors: Dict[str, int]) -> List[dict]:
    """Layers, bottom first, as {"image", "opacity"}. `position` is minutes
    after midnight for day scenes and percent done for progress scenes."""
    if not scene:
        return []
    marks = version_starts(scene, anchors)
    if not marks:
        return []
    if len(marks) > 1 and scene.get("kind") == "day":
        return _circular(marks, position % DAY)
    if len(marks) > 1 and scene.get("kind") == "progress":
        return _linear(marks, position)
    return [_layer(marks[0][2], 1.0)]


def _linear(marks, position):
    current = 0
    for i, (start, _fade, _v) in enumerate(marks):
        if start <= position:
            current = i
    start, fade, version = marks[current]
    if current == 0:
        return [_layer(version, 1.0)]
    # A fade can't run past the next version's start.
    nxt = marks[current + 1][0] if current + 1 < len(marks) else 100
    return _blend(marks[current - 1][2], version, position - start, min(fade, nxt - start))


def _circular(marks, position):
    current = len(marks) - 1   # before the first start of the day, the last version is still on
    for i, (start, _fade, _v) in enumerate(marks):
        if start <= position:
            current = i
    start, fade, version = marks[current]
    prev = marks[current - 1][2]
    nxt = marks[(current + 1) % len(marks)][0]
    gap = (nxt - start) % DAY or DAY
    return _blend(prev, version, (position - start) % DAY, min(fade, gap))


def _blend(below: dict, above: dict, elapsed: float, fade: float) -> List[dict]:
    if fade <= 0 or elapsed >= fade or below.get("image") == above.get("image"):
        return [_layer(above, 1.0)]
    p = elapsed / fade
    eased = p * p * (3 - 2 * p)   # smoothstep: gentle at both ends of the fade
    return [_layer(below, 1.0), _layer(above, round(eased, 3))]


def _layer(version: dict, opacity: float) -> dict:
    return {"image": version["image"], "opacity": opacity}


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def screen_turns(cfg: dict, scene_ids: Sequence[str]) -> List[str]:
    """What takes turns on a screen: each scene, but each picture of an album
    ("<album id>#<picture index>"), so an album shuffles its pictures with the rest."""
    by_id = scenes_by_id(cfg)
    turns: List[str] = []
    for sid in scene_ids:
        scene = by_id.get(sid)
        if scene and scene.get("kind") == "album":
            turns += [f"{sid}#{i}" for i, v in enumerate(scene.get("versions") or []) if v.get("image")]
        elif scene:
            turns.append(sid)
    return turns


def scene_for_turn(cfg: dict, turn: str) -> Optional[dict]:
    """The scene a turn shows: an album's turn is a scene of just that picture."""
    sid, _, index = turn.partition("#")
    scene = scenes_by_id(cfg).get(sid)
    if scene is None or not index:
        return scene
    versions = scene.get("versions") or []
    i = int(index)
    return dict(scene, kind="single", versions=[versions[i]]) if 0 <= i < len(versions) else None


def pick_scene(ids: Sequence[str], every_minutes: int, now_minutes: int, launch_seed: int) -> Optional[str]:
    """The scene a shuffling screen shows now. Each round shows every scene
    once in a shuffled order, and a round never starts with the scene the last
    one ended on. `every_minutes` 0 keeps one pick for the whole launch."""
    ids = list(ids)
    if len(ids) <= 1:
        return ids[0] if ids else None
    if every_minutes <= 0:
        return random.Random(launch_seed).choice(ids)
    period = now_minutes // every_minutes
    if len(ids) == 2:
        return sorted(ids)[period % 2]
    rnd, slot = divmod(period, len(ids))
    order = _round_order(ids, rnd)
    # Swapping the first two leaves the last alone, so the previous round's
    # last scene is just its shuffled order's last.
    if order[0] == _round_order(ids, rnd - 1)[-1]:
        order[0], order[1] = order[1], order[0]
    return order[slot]


def _round_order(ids: List[str], rnd: int) -> List[str]:
    order = sorted(ids)
    random.Random(rnd).shuffle(order)
    return order
