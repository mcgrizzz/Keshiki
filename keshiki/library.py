"""The user's images: copied into user_files (which survives add-on updates), with small thumbnails."""

from __future__ import annotations

import filecmp
import json
import math
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

ADDON_DIR = Path(__file__).resolve().parents[1]
IMAGES = ADDON_DIR / "user_files" / "images"
THUMBS = ADDON_DIR / "user_files" / "thumbs"
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")
# Served by Anki's media server under /_addons/<folder>/ (see setWebExports in the root __init__).
WEB_EXPORTS = r"user_files/(images|thumbs)/.+"
THUMB_WIDTH = 480


def image_url(name: str) -> str:
    return f"/_addons/{ADDON_DIR.name}/user_files/images/{quote(name)}"


def thumb_url(name: str) -> str:
    if (THUMBS / _thumb_name(name)).exists():
        return f"/_addons/{ADDON_DIR.name}/user_files/thumbs/{quote(_thumb_name(name))}"
    return image_url(name)


def list_images() -> List[Dict[str, str]]:
    if not IMAGES.is_dir():
        return []
    files = sorted((p for p in IMAGES.iterdir() if p.suffix.lower() in EXTENSIONS), key=lambda p: p.name.lower())
    return [{"name": p.name, "url": image_url(p.name), "thumb": thumb_url(p.name)} for p in files]


def import_files(paths: List[str]) -> List[str]:
    """Copy images in and return their names in the library. A file already
    there unchanged is reused; a different one with the same name gets a suffix."""
    IMAGES.mkdir(parents=True, exist_ok=True)
    names = []
    for src in map(Path, paths):
        if src.suffix.lower() not in EXTENSIONS or not src.is_file():
            continue
        dest = IMAGES / _safe_name(src.name)
        n = 2
        while dest.exists() and not filecmp.cmp(src, dest, shallow=False):
            dest = dest.with_name(f"{_safe_name(src.stem)}-{n}{src.suffix.lower()}")
            n += 1
        if not dest.exists():
            shutil.copyfile(src, dest)
        make_thumb(dest)
        names.append(dest.name)
    return names


def delete(name: str) -> None:
    _stats.pop(name, None)
    for path in (IMAGES / _safe_name(name), THUMBS / _thumb_name(name), THUMBS / _stats_name(name),
                 THUMBS / _lights_name(name)):
        if path.is_file():
            path.unlink()


def make_thumb(path: Path) -> None:
    from aqt.qt import QImage, Qt

    image = QImage(str(path))
    if image.isNull():
        return   # a format Qt can't read; the full image stands in
    THUMBS.mkdir(parents=True, exist_ok=True)
    if image.width() > THUMB_WIDTH:
        image = image.scaledToWidth(THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
    image.save(str(THUMBS / _thumb_name(path.name)), "JPG", 85)


def _thumb_name(name: str) -> str:
    return name + ".jpg"


def _safe_name(name: str) -> str:
    """A plain file name: no folders, no characters Windows or a URL would trip on."""
    name = re.sub(r'[\\/:*?"<>|#%&{}$!\'@+`=]', "_", Path(name).name).strip(" .")
    return name or "image"


_stats: Dict[str, Optional[dict]] = {}


def image_stats(name: str) -> Optional[dict]:
    """Each colour channel's mean and spread (0-1) for light matching, and whether the
    picture has lights of its own ("lights"), or None when the image can't be read.
    Worked out once, then kept beside the thumbnail."""
    if name not in _stats:
        path = THUMBS / _stats_name(name)
        try:
            stats = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stats = _measure(name)
        if stats is not None and "lights" not in stats:
            luma = 0.2126 * stats["mean"][0] + 0.7152 * stats["mean"][1] + 0.0722 * stats["mean"][2]
            # Only a picture that shows night has lights worth finding.
            stats["lights"] = luma < NIGHT_LUMA and find_lights(IMAGES / name, THUMBS / _lights_name(name))
            THUMBS.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stats), encoding="utf-8")
        _stats[name] = stats
    return _stats[name]


def lights_url(name: str) -> Optional[str]:
    """The picture's lights alone (everything else transparent), if it has any."""
    stats = image_stats(name)
    if not (stats and stats.get("lights")):
        return None
    return f"/_addons/{ADDON_DIR.name}/user_files/thumbs/{quote(_lights_name(name))}"


# Pictures darker than this on average show night (matches daylight.NIGHT_PICTURE's top).
NIGHT_LUMA = 0.40


def _smooth(edge0: float, edge1: float, x: float) -> float:
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def light_score(r: float, g: float, b: float, local: float) -> float:
    """How much a pixel (0-1 sRGB) looks like a light in a night scene, given the
    brightness around it. The usual cues: bright in itself, much brighter than its
    surroundings (a lit window, not a pale moonlit cloud), and the colour of a lamp
    (warm, like incandescent or sodium light) or near-white (stars, the moon)."""
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    top, low = max(r, g, b), min(r, g, b)
    saturation = (top - low) / top if top else 0.0
    lamp = _smooth(0.42, 0.7, luma) * _smooth(0.02, 0.2, r - b)
    # Stars: small and not that bright, but near-white and standing well clear of the sky.
    star = _smooth(0.35, 0.6, luma) * (1 - _smooth(0.2, 0.4, saturation)) * _smooth(0.15, 0.3, luma - local)
    return max(_smooth(0.08, 0.22, luma - local) * lamp, star)


def find_lights(src: Path, dest: Path, width: int = 960) -> bool:
    """Save the picture's lights alone to `dest` (a PNG, transparent elsewhere), found
    on a `width`-wide copy and cut from the full picture. False when there are none."""
    from aqt.qt import QImage, QPainter, Qt

    full = QImage(str(src))
    if full.isNull():
        return False
    if full.width() > 2560:
        full = full.scaledToWidth(2560, Qt.TransformationMode.SmoothTransformation)
    full = full.convertToFormat(QImage.Format.Format_ARGB32)
    small = full.scaledToWidth(min(width, full.width()), Qt.TransformationMode.SmoothTransformation)
    w, h = small.width(), small.height()
    # The surroundings: shrink a lot, then grow back smoothly (a cheap wide blur).
    step = max(2, w // 40)
    around = small.scaled(max(1, w // step), max(1, h // step), Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation).scaled(
        w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    px = bytes(small.constBits().asarray(small.sizeInBytes()))
    bg = bytes(around.constBits().asarray(around.sizeInBytes()))
    line, bg_line = small.bytesPerLine(), around.bytesPerLine()
    mask = bytearray(w * h)
    lit = 0
    for y in range(h):
        row, bg_row = y * line, y * bg_line
        for x in range(w):
            i, j = row + 4 * x, bg_row + 4 * x   # ARGB32 is B, G, R, A in memory
            local = (0.2126 * bg[j + 2] + 0.7152 * bg[j + 1] + 0.0722 * bg[j]) / 255
            score = light_score(px[i + 2] / 255, px[i + 1] / 255, px[i] / 255, local)
            if score > 0.02:
                mask[y * w + x] = int(score * 255)
                lit += 1
    if lit < w * h * 0.0002:
        return False
    alpha = QImage(bytes(mask), w, h, w, QImage.Format.Format_Alpha8).scaled(
        full.width(), full.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(full)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, alpha)
    painter.end()
    dest.parent.mkdir(parents=True, exist_ok=True)
    return full.save(str(dest), "PNG")


def _measure(name: str) -> Optional[dict]:
    from aqt.qt import QImage, Qt

    thumb = THUMBS / _thumb_name(name)
    image = QImage(str(thumb if thumb.exists() else IMAGES / name))
    if image.isNull():
        return None
    image = image.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    sums, squares, n = [0.0] * 3, [0.0] * 3, image.width() * image.height()
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            for i, v in enumerate((c.redF(), c.greenF(), c.blueF())):
                sums[i] += v
                squares[i] += v * v
    mean = [v / n for v in sums]
    std = [math.sqrt(max(sq / n - m * m, 0)) for sq, m in zip(squares, mean, strict=True)]
    return {"mean": [round(v, 4) for v in mean], "std": [round(v, 4) for v in std]}


def _stats_name(name: str) -> str:
    return name + ".stats.json"


def _lights_name(name: str) -> str:
    return name + ".lights.png"
