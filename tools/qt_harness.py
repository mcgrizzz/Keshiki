"""Run a check against a real, offscreen Anki with Keshiki installed in a throwaway profile.

The add-on is copied into the temporary addons21 folder, so images the check
imports land there and not in the repo's user_files.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ["ANKI_SOFTWAREOPENGL"] = "1"

import aqt  # noqa: E402
from aqt.profiles import ProfileManager  # noqa: E402
from aqt.qt import QColor, QCoreApplication, QEvent, QImage, QPainter, QPoint, sip  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
import anki_notices  # noqa: E402

anki_notices.install(lambda: "real Anki")
SHIPPED = ["__init__.py", "manifest.json", "config.json", "config.md", "keshiki"]


def until(app, predicate, seconds=20, message="Qt condition timed out"):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def pump(app, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def js(app, web, code, seconds=10):
    out = []
    web.page().runJavaScript(code, out.append)
    until(app, lambda: bool(out), seconds, f"no JS result for {code[:60]!r}")
    return out[0]


def addon():
    """The running add-on's root module."""
    return sys.modules["keshiki"]


def make_test_image(path: Path, hue: int, w=1600, h=1000) -> Path:
    """A gradient crossed by thin diagonal lines: any offset or scale mismatch
    between two webviews breaks the lines at the seam."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    for y in range(h):
        p.setPen(QColor.fromHsv(hue, 160, 90 + int(140 * y / h)))
        p.drawLine(0, y, w, y)
    p.setPen(QColor(255, 255, 255))
    for x in range(-h, w, 40):
        p.drawLine(QPoint(x, 0), QPoint(x + h, h))
    p.end()
    img.save(str(path))
    return path


def run(check, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--screenshots", type=Path, help="folder to save screenshots in")
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="keshiki-qt-") as base:
        dest = Path(base) / "addons21" / "keshiki"
        dest.mkdir(parents=True)
        for name in SHIPPED:
            src = REPO / name
            if src.is_dir():
                shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.exists():
                shutil.copy(src, dest / name)
        pm = ProfileManager(Path(base))
        pm.setupMeta()
        pm.create("KeshikiCheck")
        pm.openProfile("KeshikiCheck")
        pm.meta["defaultLang"] = "en_US"
        pm.save()
        pm.db.close()
        # Bypass IPC so this process cannot signal another Anki instance.
        aqt.AnkiApp.secondInstance = lambda self: False
        app = aqt._run(["anki", "-b", base, "-p", "KeshikiCheck", "-l", "en"], exec=False)
        assert app is not None
        errors = []
        original_hook = sys.excepthook

        def exception_hook(kind, value, tb):
            errors.append(str(value))
            traceback.print_exception(kind, value, tb)

        sys.excepthook = exception_hook
        try:
            until(app, lambda: aqt.mw.col is not None and aqt.mw.state == "deckBrowser")
            anki_notices.install(lambda: "real Anki")   # again, for modules Anki and Keshiki loaded since
            aqt.mw.resize(1280, 800)
            pump(app, 0.5)
            check(app, args.screenshots, Path(base))
            assert not errors, errors
            pump(app, 1)   # let Anki's queued page refreshes finish before the collection closes
        finally:
            if not sip.isdeleted(aqt.mw):
                aqt.mw.close()
                until(app, lambda: sip.isdeleted(aqt.mw), 30)
            sys.excepthook = original_hook
    print("PASS: Anki shut down cleanly.", flush=True)
    for where, msg in anki_notices.notices:
        print(f"Anki deprecation notice ({where}): {msg}", flush=True)
    # KESHIKI_STRICT_ANKI_NOTICES=1 (qt_checks.sh sets it) fails the check on any notice.
    if anki_notices.notices and anki_notices.STRICT:
        sys.exit(1)
