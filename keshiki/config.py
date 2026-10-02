"""Config defaults, migration and scene templates. Pure dict-in/dict-out, tested headless."""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Sequence, Tuple

from ._kiso import config as kiso_config

# Top-level package name of the add-on (= installed folder name); the key for
# addonManager.getConfig/writeConfig.
ADDON_PACKAGE = __name__.split(".")[0]

CONFIG_VERSION = 3

# "every" is how long a screen keeps one scene when it shuffles several, in
# minutes; 0 picks a new one each time Anki starts.
DEFAULTS: Dict[str, Any] = {
    "scenes": [],
    # Per image file: {"x": 50, "y": 50}, the point kept in view when cropping.
    "images": {},
    "screens": {
        "main": {"scenes": [], "every": 60, "dim": 15, "blur": 0},
        # same_as_main: studying shows whatever the deck list shows.
        "study": {"enabled": True, "same_as_main": True, "scenes": [], "every": 60, "dim": 45, "blur": 0},
        # Once nothing is left to study today (in any deck), both screens show these
        # scenes, with this dim and blur.
        "done": {"enabled": False, "scenes": [], "every": 60, "dim": 15, "blur": 0},
    },
    # Where sunrise and sunset come from for day-cycle scenes: the times typed
    # here ("manual"), or the sun at latitude/longitude ("location").
    # place: the name a location lookup found, shown beside the coordinates.
    "day": {"source": "manual", "sunrise": "06:30", "sunset": "19:30", "latitude": None, "longitude": None,
            "place": ""},
    "transition_seconds": 2.0,
    # tint: light the pictures by the sun's height (daylight.py), at tint_strength percent.
    # bloom: how much a night picture's own lights glow, in percent (50 is the standard look).
    "light": {"tint": False, "tint_strength": 70, "bloom": 50},
    "config_version": CONFIG_VERSION,
}

KINDS = ("single", "day", "progress")
# A day version is tied to the sun ("sun": fades in as the sun, rising or
# setting, goes from one elevation to another, in degrees) or to the clock
# ("clock": starts at offset minutes after midnight, fades in over fade
# minutes). "sunrise"/"sunset" with minute offsets are the version 1 form.
ANCHORS = ("sun", "clock")

# Named moments of the sun, as the settings offer them: (key, direction, sun
# height in degrees, name). Twilight follows the usual definitions: civil (dawn,
# dusk) at -6°, nautical (first and last light) at -12°, astronomical (night) at
# -18°; golden hour is the sun below +6°. "Noon" is the sun's highest point.
SUN_MOMENTS = [
    ("night-ends", "rising", -18, "Night ends"),
    ("first-light", "rising", -12, "First light"),
    ("dawn", "rising", -6, "Dawn"),
    ("sunrise", "rising", 0, "Sunrise"),
    ("golden-ends", "rising", 6, "Golden hour ends"),
    ("mid-morning", "rising", 12, "Mid-morning"),
    ("morning", "rising", 20, "Morning"),
    ("noon", "rising", 90, "Noon"),
    ("afternoon", "setting", 20, "Afternoon"),
    ("late-afternoon", "setting", 12, "Late afternoon"),
    ("golden", "setting", 6, "Golden hour"),
    ("sunset", "setting", 0, "Sunset"),
    ("dusk", "setting", -6, "Dusk"),
    ("last-light", "setting", -12, "Last light"),
    ("night", "setting", -18, "Night"),
]

# What "New day cycle" and "New progress scene" start with; "at" and fades are
# percent done for progress. Dawn fills first light up to sunrise; day arrives
# as golden hour ends; dusk is late afternoon into sunset; night comes in from
# dusk (the blue hour) to last light.
_DAY_TEMPLATE = [
    {"label": "Dawn", "anchor": "sun", "direction": "rising", "from": -12, "to": 0},
    {"label": "Day", "anchor": "sun", "direction": "rising", "from": 6, "to": 20},
    {"label": "Dusk", "anchor": "sun", "direction": "setting", "from": 12, "to": 0},
    {"label": "Night", "anchor": "sun", "direction": "setting", "from": -6, "to": -12},
]
# Version 1 offsets to sun heights: near the horizon the sun moves about 0.2° a minute at mid-latitudes.
_DEGREES_PER_MINUTE = 0.2
_PROGRESS_TEMPLATE = [
    {"label": "Start", "at": 0, "fade": 0},
    {"label": "Halfway", "at": 50, "fade": 30},
    {"label": "Almost there", "at": 85, "fade": 15},
    {"label": "Finished", "at": 100, "fade": 0},
]


def new_id() -> str:
    return secrets.token_hex(4)


def new_scene(kind: str, name: str = "", image: str = "", images: Sequence[str] = ()) -> dict:
    """A scene of the given kind, laid out from its template. An album is a set of
    pictures that take turns on a screen, one each turn of its shuffle."""
    if kind == "day":
        versions = [dict(v, image="") for v in _DAY_TEMPLATE]
    elif kind == "progress":
        versions = [dict(v, image="") for v in _PROGRESS_TEMPLATE]
    elif kind == "album":
        versions = [{"label": "", "image": name_} for name_ in images]
    else:
        kind, versions = "single", [{"label": "Image", "image": image}]
    default_name = {"day": "Day cycle", "progress": "Review progress", "album": "Album"}.get(kind, _stem(image) or "Scene")
    return {"id": new_id(), "name": name or default_name, "kind": kind, "versions": versions}


def _stem(filename: str) -> str:
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()


def migrate(cfg: dict) -> Tuple[dict, bool]:
    """Bring a config up to date and fill defaults; drop references to scenes that
    no longer exist. Returns (cfg, changed)."""
    cfg, changed = kiso_config.migrate(cfg, DEFAULTS, CONFIG_VERSION,
                                       [(2, _sun_heights), (3, _smoothing_always_on)], free_form=["images"])
    ids = {s.get("id") for s in cfg["scenes"] if isinstance(s, dict)}
    for screen in cfg["screens"].values():
        kept = [i for i in screen.get("scenes") or [] if i in ids]
        if kept != screen.get("scenes"):
            screen["scenes"] = kept
            changed = True
    return cfg, changed


def _sun_heights(cfg: dict) -> None:
    """Version 2: day versions moved from minutes around sunrise and sunset to sun heights."""
    for scene in cfg.get("scenes") or []:
        for v in scene.get("versions") or []:
            if scene.get("kind") == "day" and v.get("anchor") in ("sunrise", "sunset"):
                _to_sun(v)


def _smoothing_always_on(cfg: dict) -> None:
    """Version 3: smoothing the colour between versions is always on; its switch went."""
    for key in ("match", "match_strength"):
        (cfg.get("light") or {}).pop(key, None)


def _to_sun(v: dict) -> None:
    """A version 1 sunrise/sunset version, in sun heights."""
    rising = v.pop("anchor") == "sunrise"
    sign = 1 if rising else -1
    start = sign * float(v.pop("offset", 0) or 0) * _DEGREES_PER_MINUTE
    full = start + sign * float(v.pop("fade", 0) or 0) * _DEGREES_PER_MINUTE

    def clamp(d):
        return round(min(max(d, -18.0), 60.0) * 2) / 2
    v.update(anchor="sun", direction="rising" if rising else "setting", **{"from": clamp(start), "to": clamp(full)})


def scenes_by_id(cfg: dict) -> Dict[str, dict]:
    return {s["id"]: s for s in cfg.get("scenes") or [] if isinstance(s, dict) and s.get("id")}


def images_in_use(cfg: dict) -> List[str]:
    return sorted({v.get("image") for s in cfg.get("scenes") or [] for v in s.get("versions") or [] if v.get("image")})


def validate(cfg: dict) -> List[dict]:
    """Problems that would stop a save, as {"message", "page", "field"}."""
    errors = []
    day = cfg.get("day") or {}
    if day.get("source") == "location":
        for key, limit in (("latitude", 90), ("longitude", 180)):
            value = day.get(key)
            if not isinstance(value, (int, float)) or not -limit <= value <= limit:
                errors.append({"message": f"Enter a {key} between -{limit} and {limit}.", "page": "day", "field": key})
    for key in ("sunrise", "sunset"):
        if parse_hhmm(day.get(key)) is None:
            errors.append({"message": f"Enter the {key} time as HH:MM.", "page": "day", "field": key})
    for scene in cfg.get("scenes") or []:
        if not str(scene.get("name") or "").strip():
            errors.append({"message": "Every scene needs a name.", "page": "scenes", "field": scene.get("id")})
    return errors


def parse_hhmm(text: Any) -> int | None:
    """Minutes after midnight for "HH:MM", or None."""
    try:
        h, m = str(text).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return h * 60 + m if 0 <= h < 24 and 0 <= m < 60 else None
