import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Import the inner package as `keshiki` without the root __init__ (which needs a running Anki).
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import anki_notices  # noqa: E402

anki_notices.install()


def pytest_terminal_summary(terminalreporter):
    if anki_notices.notices:
        terminalreporter.section("Anki deprecation notices")
        for test, msg in anki_notices.notices:
            terminalreporter.line(f"{test}: {msg}")


def pytest_sessionfinish(session):
    # KESHIKI_STRICT_ANKI_NOTICES=1 fails the run on any notice.
    if anki_notices.notices and anki_notices.STRICT:
        session.exitstatus = 1
