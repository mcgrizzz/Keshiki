"""The light of the time of day, as one colour matrix for the background pictures.

From the sun's elevation:
- colour temperature: direct sun blended with sky light, warm near the horizon
  and very blue in twilight (Hernández-Andrés et al. 2001, Peyvandi et al.
  2016, Spitschan et al. 2016), applied at half strength the way eyes partly
  adapt (CIECAM02's degree of adaptation);
- brightness: clear-sky illuminance (Janiczek & DeYoung 1987), squeezed from
  eight orders of magnitude into 100%-25%;
- night vision: the Purkinje shift toward a dim, blue, desaturated picture as
  light falls through the mesopic range (Jensen et al., "Night Rendering").

Two things the light doesn't do: a picture that already shows night (it's
dark on average) isn't darkened again, and things that give off their own
light (lit windows, lamps, stars: the brightest parts of a picture) keep it.
That second part is a mask in layers.js; `glow` says how much of it applies.
Brightness is the only clue to what's a light, so it's kept only in pictures
that show night: in a day picture the bright parts are sky and sunlit things.

The matrix works on linear RGB, which is how SVG filters apply it. Pure, tested headless.
"""

from __future__ import annotations

import math
from typing import List, Tuple

# Sun elevation (degrees) -> colour temperature (K), interpolated in mired (1/K).
# Below -14° night takes over (a perception effect, see below), so the colour itself goes neutral.
_CCT = [(-90, 6500), (-14, 6500), (-12, 15000), (-9, 15000), (-6, 12000), (-4, 9000), (-2, 5000), (0, 2500),
        (3, 3000), (6, 3600), (10, 4200), (20, 5000), (30, 5500), (40, 5800), (90, 5800)]
NEUTRAL = 6500
ADAPTATION = 0.5     # share of the colour shift an adapted eye still sees
DARKEST = 0.25       # brightness at full night
GREYEST = 0.4        # least colour left at night: the viewer isn't dark-adapted
# Night vision: rod sensitivity in linear sRGB (white = 1), and the blue it tints toward.
_ROD = (-0.072, 0.645, 0.427)
_NIGHT_BLUE = (0.85, 1.0, 1.42)
_XYZ_TO_RGB = ((3.2406, -1.5372, -0.4986), (-0.9689, 1.8758, 0.0415), (0.0557, -0.2040, 1.0570))

Matrix = List[List[float]]


def colour_temperature(elevation: float) -> float:
    for (h0, t0), (h1, t1) in zip(_CCT, _CCT[1:], strict=False):
        if h0 <= elevation <= h1:
            k = (elevation - h0) / (h1 - h0)
            return 1 / ((1 - k) / t0 + k / t1)
    return NEUTRAL


def _chromaticity(kelvin: float) -> Tuple[float, float]:
    """CIE daylight locus from 4000 K, the Planckian locus (Kang et al. 2002) below."""
    t = kelvin
    if t >= 4000:
        x = (0.244063 + 0.09911e3 / t + 2.9678e6 / t ** 2 - 4.6070e9 / t ** 3 if t <= 7000
             else 0.237040 + 0.24748e3 / t + 1.9018e6 / t ** 2 - 2.0064e9 / t ** 3)
        return x, -3.0 * x * x + 2.870 * x - 0.275
    x = -0.2661239e9 / t ** 3 - 0.2343589e6 / t ** 2 + 0.8776956e3 / t + 0.179910
    if t <= 2222:
        y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    else:
        y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    return x, y


def _linear_rgb(kelvin: float) -> Tuple[float, float, float]:
    x, y = _chromaticity(min(max(kelvin, 1667), 25000))
    xyz = (x / y, 1.0, (1 - x - y) / y)
    return tuple(sum(m * c for m, c in zip(row, xyz, strict=True)) for row in _XYZ_TO_RGB)


def white_balance(kelvin: float) -> Tuple[float, float, float]:
    """Per-channel gains for light of this colour, neutral at 6500 K, keeping brightness."""
    seen = 1 / (1 / NEUTRAL + ADAPTATION * (1 / kelvin - 1 / NEUTRAL))
    gains = [max(c / n, 0.02) for c, n in zip(_linear_rgb(seen), _linear_rgb(NEUTRAL), strict=True)]
    luma = 0.2126 * gains[0] + 0.7152 * gains[1] + 0.0722 * gains[2]
    return tuple(g / luma for g in gains)


def illuminance(elevation: float) -> float:
    """Clear-sky light on the ground in lux (Janiczek & DeYoung 1987)."""
    x = 753.66156
    h = math.radians(elevation)
    s = math.asin(x * math.cos(h) / (x + 1))
    m = x * (math.cos(s) - math.sin(h)) + math.cos(s)
    lux = 133775 * (math.exp(-0.21 * m) * math.sin(h)
                    + 0.0289 * math.exp(-0.042 * m) * (1 + (elevation + 90) * math.sin(h) / 57.2958))
    return max(lux, 0.0) + 0.0005


def _smooth(edge0: float, edge1: float, x: float) -> float:
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def light_at(elevation: float) -> dict:
    """What the light is like: colour temperature, brightness (0-1) and how much colour vision is left (0-1)."""
    lux = illuminance(elevation)
    brightness = DARKEST + (1 - DARKEST) * _smooth(-3, 4, math.log10(lux))
    # Jensen et al.: photopic above log L = 0.6, scotopic below -2 (L in cd/m², a mid-grey scene).
    log_l = math.log10(max(0.18 * lux / math.pi, 1e-9))
    colour = max(_smooth(-2, 0.6, log_l), GREYEST)
    return {"kelvin": colour_temperature(elevation), "brightness": brightness, "colour": colour}


# A picture whose average brightness (sRGB luma) is below the first value
# already shows night and gets none of the night darkening; above the second, all of it.
NIGHT_PICTURE = (0.12, 0.40)


def picture_daylight(luma: float) -> float:
    """How much a picture shows daylight (0: a night scene, 1: a day scene), from its average brightness."""
    return _smooth(NIGHT_PICTURE[0], NIGHT_PICTURE[1], luma)


def matrix(elevation: float, strength: float = 1.0, luma: float = 0.5) -> Matrix:
    """A 3x3 linear-RGB matrix: brightness x (colour vision x white balance + the rest x night vision),
    blended toward no change by `strength` (0-1). `luma` is the picture's average brightness:
    the darker it is, the less night is added on top."""
    light = light_at(elevation)
    gains = white_balance(light["kelvin"])
    day = picture_daylight(luma)
    brightness = 1 - (1 - light["brightness"]) * day
    s = 1 - (1 - light["colour"]) * day
    full = [[brightness * (s * (gains[i] if i == j else 0.0) + (1 - s) * _NIGHT_BLUE[i] * _ROD[j])
             for j in range(3)] for i in range(3)]
    return [[round((1 - strength) * (1.0 if i == j else 0.0) + strength * full[i][j], 3) for j in range(3)]
            for i in range(3)]


def glow(elevation: float, strength: float = 1.0) -> float:
    """How much a picture's own lights are kept as they are (0 by day, 1 at full night)."""
    return round(strength * (1 - light_at(elevation)["brightness"]) / (1 - DARKEST), 3)


def grey_seen(elevation: float, strength: float = 1.0) -> str:
    """How a light grey wall looks under this light, as "#rrggbb" (for the strip in the settings)."""
    def to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def to_srgb(c):
        c = min(max(c, 0.0), 1.0)
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    g = to_linear(0.6)
    rgb = [to_srgb(sum(row) * g) for row in matrix(elevation, strength)]
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in rgb)
