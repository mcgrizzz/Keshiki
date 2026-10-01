"""Copy the add-on into an installed Anki's addons21/keshiki.

    python tools/dev_sync.py --watch    # leave running: save a file, done

The copy gets a DEV_WATCH file, so a running Anki notices each sync and
reloads Keshiki by itself (a tooltip says so). The first sync, and any change
to the root __init__.py, still needs an Anki restart. The copy is listed as
"Keshiki (dev)" in Tools > Add-ons. user_files and the settings in meta.json
(your images and config) are left alone.

The folder comes from --dest, $KESHIKI_ADDON_DIR, or the usual Anki2
location (on WSL, the Windows one). Adapted from Tsunagi's tools/dev_sync.py.
"""

import argparse
import glob
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TREE = "keshiki"
ROOT_FILES = ["__init__.py", "manifest.json", "config.json", "config.md"]
DEV_NAME = "Keshiki (dev)"


def default_dest() -> Path | None:
    if os.environ.get("KESHIKI_ADDON_DIR"):
        return Path(os.environ["KESHIKI_ADDON_DIR"])
    candidates = [os.path.expandvars(r"%APPDATA%\Anki2"), *glob.glob("/mnt/c/Users/*/AppData/Roaming/Anki2"),
                  os.path.expanduser("~/.local/share/Anki2"), os.path.expanduser("~/Library/Application Support/Anki2")]
    for base in candidates:
        if (Path(base) / "addons21").is_dir():
            return Path(base) / "addons21" / "keshiki"
    return None


def copy_tree(src: Path, dest: Path) -> None:
    # Stage beside the destination, then swap, so Anki never imports a
    # half-written package (an interrupted copy, or Anki reloading mid-copy).
    stage = dest.with_name(dest.name + ".syncing")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(src, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(stage, dest)


def name_dev_copy(dest: Path) -> None:
    """Anki lists an add-on by meta.json's "name"; only that key changes."""
    path = dest / "meta.json"
    meta = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if meta.get("name") != DEV_NAME:
        meta["name"] = DEV_NAME
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def sync(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    copy_tree(REPO / TREE, dest / TREE)
    for name in ROOT_FILES:
        shutil.copy2(REPO / name, dest / name)
    (dest / "DEV_WATCH").touch()
    name_dev_copy(dest)


def source_stamp() -> tuple:
    files = [p for p in (REPO / TREE).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files += [REPO / name for name in ROOT_FILES]
    return len(files), max(p.stat().st_mtime for p in files)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", type=Path, default=default_dest())
    parser.add_argument("--watch", action="store_true", help="stay running and sync whenever the source changes")
    args = parser.parse_args()
    if args.dest is None:
        sys.exit("No Anki add-ons folder found; pass --dest or set KESHIKI_ADDON_DIR.")
    first = not (args.dest / TREE).exists()
    sync(args.dest)
    print(f"Synced to {args.dest}.")
    print("Restart Anki to load it." if first else "A running Anki reloads it within a few seconds "
          "(changes to the root __init__.py need a restart).")
    if not args.watch:
        return
    print("Watching for changes (Ctrl+C to stop)")
    stamp = source_stamp()
    try:
        while True:
            time.sleep(1)
            current = source_stamp()
            if current != stamp:
                stamp = current
                sync(args.dest)
                print(f"  synced {time.strftime('%H:%M:%S')}")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
