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
DISPLAY = ADDON_DIR / "user_files" / "display"
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")
# Served by Anki's media server under /_addons/<folder>/ (see setWebExports in the root __init__).
WEB_EXPORTS = r"user_files/(images|thumbs|folders|trash|display)/.+"
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
    """A linked picture for the settings page. Its thumbnail may not be made yet (it's made in
    the background): then "" (the page fills it in later), never the picture itself."""
    made = (THUMBS / _thumb_name(name)).exists()
    return {"name": name, "url": image_url(name), "thumb": thumb_url(name) if made else ""}


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
    """Delete a picture for good, with its thumbnail, measurements and display copies."""
    _stats.pop(name, None)
    remove_display(name)
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
    remove_display(src.name)   # made again when it shows
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


# -- display copies ------------------------------------------------------------
# A picture straight from a camera or a 4K wallpaper can be many times the window's size, and
# every webview showing it decodes all of it (about 100 MB for 24 megapixels; each crossfade to
# it stalls while it does). A copy that just covers the screen costs a fraction of that. It isn't
# quite the same: Chromium shrinks a big picture with crisp sampling, and a copy resampled
# twice (here, then by Chromium to the window) shows visibly softer fine detail, whatever its
# format or size (measured: about half the detail of a 4K picture on a 1440p screen). So the
# settings' small previews always use copies, and Anki's window only on a blurred screen, where
# the blur hides the difference (schedule.BLUR_COPIES).
# Copies are made on a worker thread (display.py says when) and kept in user_files/display
# like a cache: any of them can go, and it's made again when it's needed.

# The screens copies are made to cover (device pixels): the smallest of these that covers the
# largest screen. Fixed steps, so a slightly different window or screen reuses the same copies.
DISPLAY_BOXES = ((1920, 1080), (2560, 1440), (3840, 2160), (5120, 2880))
# Only a copy at most this fraction of the picture's width is worth having.
DISPLAY_MAX_SCALE = 0.8
DISPLAY_QUALITY = 92
DISPLAY_BUDGET = 1 << 30   # bytes; the copies used least lately go past this
# <picture>.<box>.<stamp>[.<backdrop>].jpg: a see-through picture's copy is laid on the colour
# that shows through it (the stage's background, the theme's canvas), so it names that colour.
_DISPLAY_FILE = re.compile(r"\.(\d+)x(\d+)\.[0-9a-f]{8}(\.[0-9a-f]{6})?\.jpg$")
_HEX = re.compile(r"#?([0-9a-fA-F]{6})")


def display_box(w: float, h: float) -> Optional[tuple]:
    """The smallest box in DISPLAY_BOXES covering w x h, or None when none does."""
    return next(((bw, bh) for bw, bh in DISPLAY_BOXES if bw >= w and bh >= h), None)


def display_size(w: int, h: int, box: tuple) -> Optional[tuple]:
    """A w x h picture scaled down to just cover box (as the stage's "cover" does), if that's
    clearly smaller than the picture."""
    scale = max(box[0] / w, box[1] / h)
    if scale > DISPLAY_MAX_SCALE:
        return None
    return max(1, math.ceil(w * scale - 1e-6)), max(1, math.ceil(h * scale - 1e-6))


def display_name(name: str, box: tuple) -> Optional[str]:
    """The name (without its ending) a picture's copy for box is kept under: it names the
    picture's size and time, so a picture changed in place (or another one under the same name
    later) gets a copy of its own. None when the picture can't be found."""
    try:
        st = image_path(name).stat()
    except OSError:
        return None
    stamp = hashlib.sha1(f"{name}|{st.st_size}-{int(st.st_mtime)}".encode()).hexdigest()[:8]
    return f"{_cache_name(name)}.{box[0]}x{box[1]}.{stamp}"


def backdrop_hex(color: Optional[str]) -> Optional[str]:
    """"#2C2C2C" -> "2c2c2c" (None for anything else)."""
    m = _HEX.fullmatch((color or "").strip())
    return m.group(1).lower() if m else None


def display_file(base: str, backdrop: Optional[str]) -> Optional[str]:
    """The copy made under that name (display_name), if there is one: the picture's own, or one
    laid on the backdrop colour (a see-through picture)."""
    names = [base + ".jpg"] + ([f"{base}.{backdrop}.jpg"] if backdrop else [])
    return next((n for n in names if (DISPLAY / n).is_file()), None)


def display_url(file: str) -> str:
    return f"/_addons/{ADDON_DIR.name}/user_files/display/{quote(file)}"


def still(path: Path) -> bool:
    """Whether a picture is a still image Qt can resize: animated GIFs, PNGs (APNG) and
    WebPs are shown as they are, and so are formats Qt can't read (AVIF)."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".bmp"):
        return True
    try:
        with path.open("rb") as f:
            head = f.read(64)
            if suffix == ".webp":
                # An extended WebP's flags say whether it's animated.
                return head[:4] == b"RIFF" and head[8:12] == b"WEBP" and not (head[12:16] == b"VP8X" and head[20] & 0x02)
            if suffix == ".png" and head[:8] == b"\x89PNG\r\n\x1a\n":
                # An animated PNG has an acTL chunk before its first image data.
                f.seek(8)
                while True:
                    chunk = f.read(8)
                    if len(chunk) < 8 or chunk[4:] in (b"IDAT", b"IEND"):
                        return True
                    if chunk[4:] == b"acTL":
                        return False
                    f.seek(int.from_bytes(chunk[:4], "big") + 4, 1)
    except OSError:
        pass
    return False


def make_display(name: str, box: tuple, backdrop: Optional[str] = None) -> Optional[str]:
    """Make the picture's copy for box (any thread) and return its file name, or None when the
    picture is better shown as it is: animated, unreadable, not much bigger than the box, or in
    colours other than RGB (CMYK). A see-through picture is laid on `backdrop` (hex, the colour
    showing through it: the theme's canvas), or gets no copy without one."""
    from aqt.qt import QColor, QColorSpace, QImage, QImageReader, QPainter, Qt

    path, base = image_path(name), display_name(name, box)
    if base is None or not still(path):
        return None
    if display_file(base, backdrop):
        return display_file(base, backdrop)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)   # a phone photo's rotation, as Chromium shows it
    image = reader.read()
    if image.isNull() or image.format() == getattr(QImage.Format, "Format_CMYK8888", None):
        return None
    size = display_size(image.width(), image.height(), box)
    if size is None:
        return None
    image = image.scaled(*size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    file = base + ".jpg"
    if image.hasAlphaChannel():
        alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
        bits, line, w = bytes(alpha.constBits().asarray(alpha.sizeInBytes())), alpha.bytesPerLine(), alpha.width()
        if any(min(bits[y * line:y * line + w]) < 255 for y in range(alpha.height())):
            # See-through: what shows through it is the stage's background, so lay it on that.
            if not backdrop:
                return None
            if image.colorSpace().isValid() and image.colorSpace() != QColorSpace(QColorSpace.NamedColorSpace.SRgb):
                image = image.convertedToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))   # the backdrop's
            flat = QImage(image.size(), QImage.Format.Format_RGB32)
            flat.fill(QColor("#" + backdrop))
            painter = QPainter(flat)
            painter.drawImage(0, 0, image)
            painter.end()
            flat.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
            image, file = flat, f"{base}.{backdrop}.jpg"
        else:
            image = image.convertToFormat(QImage.Format.Format_RGB32)
    DISPLAY.mkdir(parents=True, exist_ok=True)
    part = DISPLAY / (file + ".part")
    # The colour profile goes with it (Qt keeps it), so it's shown in the same colours.
    if not image.save(str(part), "JPG", DISPLAY_QUALITY):
        part.unlink(missing_ok=True)
        return None
    os.replace(part, DISPLAY / file)   # whole, or not there: the page may ask for it any time
    return file


def remove_display(name: str) -> None:
    """Delete a picture's display copies (any size, any version of it)."""
    if not DISPLAY.is_dir():
        return
    prefix = _cache_name(name) + "."
    for path in DISPLAY.iterdir():
        if path.name.startswith(prefix) and _DISPLAY_FILE.fullmatch(path.name[len(prefix) - 1:]):
            _unlink(path)


def prune_display(budget: int = DISPLAY_BUDGET) -> int:
    """Keep the copies within budget, dropping those used least lately (display.py touches a
    copy when it's first used in a session); how many went. Leftover .part files go too."""
    if not DISPLAY.is_dir():
        return 0
    files, gone = [], 0
    for path in DISPLAY.iterdir():
        try:
            st = path.stat()
        except OSError:
            continue
        if path.name.endswith(".part"):
            _unlink(path)
        else:
            files.append((st.st_mtime, st.st_size, path))
    total = sum(size for _, size, _ in files)
    for _, size, path in sorted(files):
        if total <= budget:
            break
        if _unlink(path):
            total -= size
            gone += 1
    return gone


def _unlink(path: Path) -> bool:
    """Delete a copy; one that can't go now (in use on Windows) goes another time."""
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


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
