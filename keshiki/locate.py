"""Approximate location from the computer's internet address, for "The sun where I am".

Only runs when the user clicks Find my location.
It sends one request to ipapi.co, or ipwho.is if that fails, and nothing else.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Callable

TIMEOUT = 8


def _get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Keshiki Anki add-on"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _ipapi(data: dict) -> dict:
    if data.get("error"):
        raise ValueError(data.get("reason") or "ipapi.co refused the request")
    return {"latitude": data["latitude"], "longitude": data["longitude"],
            "place": ", ".join(p for p in (data.get("city"), data.get("region"), data.get("country_name")) if p)}


def _ipwho(data: dict) -> dict:
    if not data.get("success", False):
        raise ValueError(data.get("message") or "ipwho.is refused the request")
    return {"latitude": data["latitude"], "longitude": data["longitude"],
            "place": ", ".join(p for p in (data.get("city"), data.get("region"), data.get("country")) if p)}


SERVICES = [("https://ipapi.co/json/", _ipapi), ("https://ipwho.is/", _ipwho)]


def approximate_location(get: Callable[[str], dict] = _get) -> dict:
    """{"latitude", "longitude", "place"}, rounded to about a kilometre. Raises
    with the last service's reason when none answers."""
    error: Exception = RuntimeError("no location service")
    for url, parse in SERVICES:
        try:
            found = parse(get(url))
            return {"latitude": round(float(found["latitude"]), 2), "longitude": round(float(found["longitude"]), 2),
                    "place": found["place"]}
        except Exception as exc:
            error = exc
    raise error
