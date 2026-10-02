"""Albums linked to a folder: their pictures are whatever the folder holds, rescanned when
Anki starts and when the settings open (library.py has the links themselves).

A linked album keeps "folder": {"path", "link", "subfolders", "hidden"} beside its pictures,
which are the last scan's, so a folder that's missing for a while (an unplugged drive) shows
them. "hidden" lists pictures left out of the album though they're still in the folder.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from . import library


def linked_albums(cfg: dict) -> List[dict]:
    return [s for s in cfg.get("scenes") or [] if s.get("kind") == "album" and s.get("folder")]


def links_in_use(cfg: dict) -> List[str]:
    return [s["folder"]["link"] for s in linked_albums(cfg)]


def scan(folder: dict) -> Optional[List[str]]:
    """The folder's pictures the album shows (all but the hidden ones), or None when it can't
    be found. Hidden pictures no longer in the folder are forgotten (folder is changed in place)."""
    names = library.scan_link(folder["link"], folder.get("path", ""), bool(folder.get("subfolders")))
    if names is None:
        return None
    hidden = [n for n in folder.get("hidden") or [] if n in names]
    if hidden != (folder.get("hidden") or []):
        folder["hidden"] = hidden
    return [n for n in names if n not in hidden]


def refresh(cfg: dict) -> Tuple[bool, List[str]]:
    """Give each linked album the pictures its folder has now (cfg is changed in place).
    Returns whether anything changed, and the ids of albums whose folder can't be found."""
    changed, missing = False, []
    for album in linked_albums(cfg):
        hidden_before = list(album["folder"].get("hidden") or [])
        names = scan(album["folder"])
        changed |= (album["folder"].get("hidden") or []) != hidden_before
        if names is None:
            missing.append(album["id"])
            continue
        versions = [{"label": "", "image": name} for name in names]
        if versions != album.get("versions"):
            album["versions"] = versions
            changed = True
    return changed, missing


def pictures(cfg: dict) -> Dict[str, Dict[str, str]]:
    """Where the page finds each linked picture, hidden ones too (they aren't in the image
    library's list)."""
    return {name: library.picture_info(name) for album in linked_albums(cfg)
            for name in [v.get("image") for v in album.get("versions") or []] + list(album["folder"].get("hidden") or [])
            if name}


def make_thumbs(names: Iterable[str]) -> None:
    """Thumbnails for linked pictures that don't have one yet (slow for big folders: run it
    off the main thread)."""
    for name in names:
        if not (library.THUMBS / library._thumb_name(name)).exists():
            library.make_thumb(library.image_path(name), name)
