"""Albums linked to a folder: their pictures are whatever the folder holds, rescanned when
Anki starts and when the settings open (library.py has the links themselves).

A linked album keeps "folder": {"path", "link", "subfolders"} beside its pictures, which
are the last scan's, so a folder that's missing for a while (an unplugged drive) shows them.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from . import library


def linked_albums(cfg: dict) -> List[dict]:
    return [s for s in cfg.get("scenes") or [] if s.get("kind") == "album" and s.get("folder")]


def links_in_use(cfg: dict) -> List[str]:
    return [s["folder"]["link"] for s in linked_albums(cfg)]


def scan(folder: dict):
    return library.scan_link(folder["link"], folder.get("path", ""), bool(folder.get("subfolders")))


def refresh(cfg: dict) -> Tuple[bool, List[str]]:
    """Give each linked album the pictures its folder has now (cfg is changed in place).
    Returns whether anything changed, and the ids of albums whose folder can't be found."""
    changed, missing = False, []
    for album in linked_albums(cfg):
        names = scan(album["folder"])
        if names is None:
            missing.append(album["id"])
            continue
        versions = [{"label": "", "image": name} for name in names]
        if versions != album.get("versions"):
            album["versions"] = versions
            changed = True
    return changed, missing


def pictures(cfg: dict) -> Dict[str, Dict[str, str]]:
    """Where the page finds each linked picture (they aren't in the image library's list)."""
    return {v["image"]: library.picture_info(v["image"])
            for album in linked_albums(cfg) for v in album.get("versions") or [] if v.get("image")}


def make_thumbs(names: Iterable[str]) -> None:
    """Thumbnails for linked pictures that don't have one yet (slow for big folders: run it
    off the main thread)."""
    for name in names:
        if not (library.THUMBS / library._thumb_name(name)).exists():
            library.make_thumb(library.image_path(name), name)
