"""The user's images: copied into user_files (which survives add-on updates), with small thumbnails.

A folder can also be linked instead of copied: user_files/folders/<link id> is a link to it (a
symlink, or a junction on Windows, which needs no special rights), so Anki's media server serves
its pictures live. Its pictures are named "@<link id>/<path in the folder>". Anki moves
user_files aside while it updates the add-on and back afterwards, so links survive updates;
removing a link never touches what it points to.
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import math
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

ADDON_DIR = Path(__file__).resolve().parents[1]
IMAGES = ADDON_DIR / "user_files" / "images"
THUMBS = ADDON_DIR / "user_files" / "thumbs"
FOLDERS = ADDON_DIR / "user_files" / "folders"
TRASH = ADDON_DIR / "user_files" / "trash"
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")
# Served by Anki's media server under /_addons/<folder>/ (see setWebExports in the root __init__).
WEB_EXPORTS = r"user_files/(images|thumbs|folders|trash)/.+"
THUMB_WIDTH = 480


def is_linked(name: str) -> bool:
    return name.startswith("@")


def image_path(name: str) -> Path:
    return FOLDERS / name[1:] if is_linked(name) else IMAGES / name


def image_url(name: str) -> str:
    if is_linked(name):
        return f"/_addons/{ADDON_DIR.name}/user_files/folders/{quote(name[1:])}"
    return f"/_addons/{ADDON_DIR.name}/user_files/images/{quote(name)}"


def picture_info(name: str) -> Dict[str, str]:
    return {"name": name, "url": image_url(name), "thumb": thumb_url(name)}


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


def delete(name: str, folder: Optional[Path] = None) -> None:
    """Delete a picture for good, with its thumbnail and measurements."""
    _stats.pop(name, None)
    for path in ((folder or IMAGES) / _safe_name(name), *_caches(name)):
        if path.is_file():
            path.unlink()


# -- the trash -----------------------------------------------------------------
# Pictures no scene uses can be moved to user_files/trash, then restored or deleted for good.
# They keep their thumbnails, which are kept by name.

def _caches(name: str) -> List[Path]:
    return [THUMBS / _thumb_name(name), THUMBS / _stats_name(name), THUMBS / _lights_name(name)]


def _free(folder: Path, name: str) -> Path:
    """A path for `name` in `folder` that doesn't hold a file yet (name-2.png, ...)."""
    dest, n = folder / name, 2
    while dest.exists():
        dest = folder / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    return dest


def _move(src: Path, folder: Path) -> str:
    """Move a picture (and its caches) into `folder`, renamed if the name is taken there."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = _free(folder, src.name)
    shutil.move(str(src), str(dest))
    if dest.name != src.name:
        _stats.pop(src.name, None)
        for old, new in zip(_caches(src.name), _caches(dest.name), strict=True):
            if old.is_file():
                old.replace(new)
    return dest.name


def trash(names: Iterable[str]) -> List[str]:
    """Move library pictures to the trash; their names there."""
    return [_move(IMAGES / _safe_name(n), TRASH) for n in names if (IMAGES / _safe_name(n)).is_file()]


def restore(names: Iterable[str]) -> List[str]:
    """Move pictures back from the trash; their names in the library."""
    return [_move(TRASH / _safe_name(n), IMAGES) for n in names if (TRASH / _safe_name(n)).is_file()]


def list_trash() -> List[Dict[str, str]]:
    if not TRASH.is_dir():
        return []
    files = sorted((p for p in TRASH.iterdir() if p.suffix.lower() in EXTENSIONS), key=lambda p: p.name.lower())
    url = f"/_addons/{ADDON_DIR.name}/user_files/trash/"
    return [{"name": p.name, "url": url + quote(p.name),
             "thumb": thumb_url(p.name) if (THUMBS / _thumb_name(p.name)).exists() else url + quote(p.name)}
            for p in files]


def empty_trash() -> int:
    """Delete everything in the trash for good; how many pictures went."""
    gone = [p.name for p in TRASH.iterdir() if p.is_file()] if TRASH.is_dir() else []
    for name in gone:
        delete(name, TRASH)
    return len(gone)


def make_thumb(path: Path, name: str = "") -> None:
    from aqt.qt import QImage, Qt

    image = QImage(str(path))
    if image.isNull():
        return   # a format Qt can't read; the full image stands in
    THUMBS.mkdir(parents=True, exist_ok=True)
    if image.width() > THUMB_WIDTH:
        image = image.scaledToWidth(THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
    image.save(str(THUMBS / _thumb_name(name or path.name)), "JPG", 85)


def _cache_name(name: str) -> str:
    """The name a picture's thumbnail and measurements are kept under. A linked picture can
    change in its folder, so its name includes the file's size and time."""
    if not is_linked(name):
        return name
    try:
        st = image_path(name).stat()
        mark = f"{st.st_size}-{int(st.st_mtime)}"
    except OSError:
        mark = "missing"
    digest = hashlib.sha1(f"{name}|{mark}".encode()).hexdigest()[:16]
    return f"linked-{digest}{Path(name).suffix.lower()}"


def _thumb_name(name: str) -> str:
    return _cache_name(name) + ".jpg"


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
            stats["lights"] = luma < NIGHT_LUMA and find_lights(image_path(name), THUMBS / _lights_name(name))
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
    image = QImage(str(thumb if thumb.exists() else image_path(name)))
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
    return _cache_name(name) + ".stats.json"


def _lights_name(name: str) -> str:
    return _cache_name(name) + ".lights.png"


# -- linked folders ----------------------------------------------------------

def folder_pictures(folder: Path, subfolders: bool) -> List[Path]:
    """The pictures in a folder (and its subfolders), in name order, skipping hidden files."""
    paths = folder.rglob("*") if subfolders else folder.iterdir()
    return sorted((p for p in paths if p.suffix.lower() in EXTENSIONS and p.is_file()
                   and not any(part.startswith(".") for part in p.relative_to(folder).parts)),
                  key=lambda p: p.relative_to(folder).as_posix().lower())


def link_folder(folder: str, link_id: str = "") -> str:
    """Link a folder into user_files/folders and return the link's id."""
    target = Path(folder).expanduser().resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"No folder at {folder}")
    FOLDERS.mkdir(parents=True, exist_ok=True)
    link_id = link_id or secrets.token_hex(4)
    dest = FOLDERS / link_id
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(dest))
    else:
        dest.symlink_to(target, target_is_directory=True)
    return link_id


def _is_link(path: Path) -> bool:
    return path.is_symlink() or getattr(os.path, "isjunction", lambda _p: False)(path)


def unlink_folder(link_id: str) -> None:
    """Remove a link, never what it points to (a real folder there is left alone)."""
    dest = FOLDERS / link_id
    if dest.is_symlink():
        dest.unlink()
    elif _is_link(dest):
        os.rmdir(dest)   # a junction: rmdir removes the junction itself


def scan_link(link_id: str, path: str, subfolders: bool) -> Optional[List[str]]:
    """The linked folder's pictures as names, or None when the folder can't be found. A link
    that's gone while its folder is still there (a restored backup, another computer) is made again."""
    dest = FOLDERS / link_id
    if not _is_link(dest) and not dest.exists() and Path(path).expanduser().is_dir():
        link_folder(path, link_id)
    if not dest.is_dir():
        return None
    return [f"@{link_id}/{p.relative_to(dest).as_posix()}" for p in folder_pictures(dest, subfolders)]


def prune_links(keep: Iterable[str]) -> None:
    """Remove links no album uses any more."""
    if not FOLDERS.is_dir():
        return
    keep = set(keep)
    for entry in FOLDERS.iterdir():
        if entry.name not in keep and _is_link(entry):
            unlink_folder(entry.name)
