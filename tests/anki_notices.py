"""Anki's deprecation notices, recorded so tests can list them and fail on them.

Anki prints most deprecations through anki._legacy.print_deprecation_warning
instead of raising a warning, so pytest's filterwarnings never sees them.
Used by tests/conftest.py and tools/qt_harness.py. Adapted from Tsunagi.
"""

import os
import sys

STRICT = os.environ.get("KESHIKI_STRICT_ANKI_NOTICES") == "1"
notices = []   # (where, message)


def install(where=lambda: os.environ.get("PYTEST_CURRENT_TEST", "")):
    """Record every notice from now on. Safe to call again after more modules load."""
    import anki._legacy

    original = getattr(anki._legacy.print_deprecation_warning, "keshiki_original",
                       anki._legacy.print_deprecation_warning)

    def record(msg, frame=1):
        notices.append((where(), msg))
        return original(msg, frame + 1)

    record.keshiki_original = original
    # Modules such as anki.decks import the function by name, so rebind it there too.
    for module in [anki._legacy, *list(sys.modules.values())]:
        current = getattr(module, "print_deprecation_warning", None)
        if current is original or getattr(current, "keshiki_original", None) is original:
            module.print_deprecation_warning = record
