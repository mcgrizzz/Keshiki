"""Package the add-on as dist/keshiki-<version>.ankiaddon (a zip Anki installs).

Timestamps and permissions are fixed, so an unchanged tree builds byte-identical.
"""

import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT_FILES = ["__init__.py", "manifest.json", "config.json", "config.md"]
SKIP = {"__pycache__"}


def version() -> str:
    return re.search(r'^version = "([^"]+)"', (REPO / "pyproject.toml").read_text(), re.M).group(1)


def files():
    yield from (REPO / name for name in ROOT_FILES)
    for path in sorted((REPO / "keshiki").rglob("*")):
        if path.is_file() and not SKIP & set(path.parts) and path.suffix != ".pyc" and not path.name.startswith("."):
            yield path


def build() -> Path:
    out = REPO / "dist" / f"keshiki-{version()}.ankiaddon"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files():
            info = zipfile.ZipInfo(path.relative_to(REPO).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert zf.testzip() is None
    assert all(n in names for n in ROOT_FILES) and "meta.json" not in names
    return out


if __name__ == "__main__":
    path = build()
    print(f"{path.relative_to(REPO)} ({path.stat().st_size // 1024} KiB)")
    sys.exit(0)
