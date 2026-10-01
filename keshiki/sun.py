"""Sunrise and sunset from latitude and longitude (NOAA's approximation, about a minute off)."""

from __future__ import annotations

import math
from datetime import date
from functools import lru_cache
from typing import List, Optional, Tuple


def sun_times(day: date, latitude: float, longitude: float, utc_offset_minutes: float) -> Optional[Tuple[int, int]]:
    """(sunrise, sunset) as local minutes after midnight, or None when the sun
    doesn't rise or doesn't set that day (polar day and night)."""
    gamma = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    lat = math.radians(latitude)
    # 90.833 degrees: the sun's disc plus refraction at the horizon.
    cos_ha = math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl)) - math.tan(lat) * math.tan(decl)
    if not -1 <= cos_ha <= 1:
        return None
    ha = math.degrees(math.acos(cos_ha))
    sunrise = 720 - 4 * (longitude + ha) - eqtime + utc_offset_minutes
    sunset = 720 - 4 * (longitude - ha) - eqtime + utc_offset_minutes
    return round(sunrise) % 1440, round(sunset) % 1440


# -- the sun's height through a day -------------------------------------------
# A day as 1441 elevations in degrees, one per minute from local midnight,
# so a version tied to the sun's height ("rising past -10°") finds its time.


def _declination_and_eqtime(day: date, minute: float) -> Tuple[float, float]:
    gamma = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1 + (minute / 60 - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    return decl, eqtime


def elevation_curve(day: date, latitude: float, longitude: float, utc_offset_minutes: float) -> List[float]:
    """The sun's elevation each minute of a local day (NOAA's solar position equations)."""
    lat = math.radians(latitude)
    curve = []
    for minute in range(1441):
        decl, eqtime = _declination_and_eqtime(day, minute - utc_offset_minutes)
        true_solar = minute + eqtime + 4 * longitude - utc_offset_minutes
        ha = math.radians(true_solar / 4 - 180)
        cos_zenith = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
        curve.append(round(90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith)))), 3))
    return curve


def synthetic_curve(sunrise: int, sunset: int, latitude: float = 45.0) -> List[float]:
    """The sun's elevation each minute when only sunrise and sunset are known: the
    declination that gives that day length at `latitude`, on the sun's real path."""
    length = (sunset - sunrise) % 1440 or 720
    noon = (sunrise + length / 2) % 1440
    h0 = math.radians(length / 4 / 2)   # half the day, as an hour angle (15° an hour)
    lat = math.radians(latitude)
    target = math.sin(math.radians(-0.833))
    lo, hi = math.radians(-23.44), math.radians(23.44)
    for _ in range(60):   # day length grows with declination: bisect for the one that fits
        mid = (lo + hi) / 2
        value = math.sin(lat) * math.sin(mid) + math.cos(lat) * math.cos(mid) * math.cos(h0)
        lo, hi = (mid, hi) if value < target else (lo, mid)
    decl = (lo + hi) / 2
    curve = []
    for minute in range(1441):
        ha = math.radians(((minute - noon + 720) % 1440 - 720) / 4)
        s = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
        curve.append(round(math.degrees(math.asin(max(-1.0, min(1.0, s)))), 3))
    return curve


def crossing(curve: List[float], degrees: float, rising: bool) -> float:
    """The minute the sun passes `degrees` going up (rising) or down. If it never
    gets there today, the moment it comes closest: its lowest or highest point."""
    top = max(range(1441), key=curve.__getitem__)
    bottom = min(range(1441), key=curve.__getitem__)
    if degrees >= curve[top]:
        return float(top)
    if degrees <= curve[bottom]:
        return float(bottom)
    # Walk the day from the lowest point (rising) or the highest (setting), wrapping at midnight.
    start = bottom if rising else top
    for step in range(1440):
        a, b = (start + step) % 1440, (start + step + 1) % 1440
        ea, eb = curve[a], curve[b]
        if (rising and ea <= degrees <= eb) or (not rising and ea >= degrees >= eb):
            frac = (degrees - ea) / (eb - ea) if eb != ea else 0.0
            return (a + frac) % 1440
    return float(start)


def elevation_at(curve: List[float], minute: float) -> float:
    minute %= 1440
    i = int(minute)
    return curve[i] + (curve[i + 1] - curve[i]) * (minute - i)


@lru_cache(maxsize=8)
def location_sun(day: date, latitude: float, longitude: float, utc_offset_minutes: float):
    """(sunrise, sunset, elevation curve) for a place and day, or None when the sun
    doesn't rise or set there that day (the typed times then stand in)."""
    times = sun_times(day, latitude, longitude, utc_offset_minutes)
    if times is None:
        return None
    return times[0], times[1], elevation_curve(day, latitude, longitude, utc_offset_minutes)
