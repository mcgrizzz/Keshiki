"""Which file of each picture the backgrounds show: the picture, or its display copy
(library.py makes them).

A look gives the page each picture's URL, and this picks it. Until a picture has a copy for
this computer's screens, the URL is the picture's own, as it always was, and the copy is made
on a worker thread. The look after that has the copy's URL, and the stage swaps it in under
the picture already showing (layers.js, resize). The box the copies cover only grows in a
session: a window moved to a smaller screen keeps what it has.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Dict, List, Optional

from . import library

log = logging.getLogger(__name__)


class Display:
    def __init__(self, run_in_background: Callable, on_made: Callable[[], None]) -> None:
        # run_in_background(fn, done): fn off the main thread, then done(its result) on it.
        self.run_in_background = run_in_background
        self.on_made = on_made   # copies have been made: looks built now use them
        self.box: Optional[tuple] = None
        self.backdrop: Optional[str] = None   # hex: what shows through a see-through picture (the theme's canvas)
        self.full = False   # a screen bigger than every box: pictures as they are
        self._known: Dict[str, Optional[str]] = {}   # copy file -> its URL, or None: the picture's own
        self._wanted: List[tuple] = []   # (picture, box) waiting for the worker
        self._making: List[tuple] = []   # with the worker now
        self._busy = False
        self.stopped = False

    def cover(self, w: float, h: float) -> bool:
        """The screens need w x h device pixels covered; whether that's more than before."""
        if self.full:
            return False
        box = library.display_box(w, h)
        if box is None:
            self.full, self.box = True, None
            return True
        if self.box and box[0] <= self.box[0]:
            return False
        self.box = box
        return True

    def url(self, name: str, divisor: int = 1) -> str:
        """The URL to show a picture by: its copy (covering the screen divided by `divisor`, for
        a blurred screen) once there is one, else its own."""
        box = (self.box[0] // divisor, self.box[1] // divisor) if self.box else None
        base = library.display_name(name, box) if box else None
        if base is None:
            return library.image_url(name)
        key = f"{base}|{self.backdrop}"   # a see-through picture's copy depends on the theme
        if key not in self._known:
            file = library.display_file(base, self.backdrop)
            if file is None:
                if (name, box) not in self._wanted and (name, box) not in self._making:
                    self._wanted.append((name, box))
                    self._start()
                return library.image_url(name)
            self._use(key, file)
        return self._known[key] or library.image_url(name)

    def _use(self, key: str, file: str) -> None:
        self._known[key] = library.display_url(file)
        try:
            os.utime(library.DISPLAY / file)   # used lately: kept when the copies are pruned
        except OSError:
            pass

    def _start(self) -> None:
        if self._busy or not self._wanted or self.stopped:
            return
        self._busy = True
        asked, backdrop = list(self._wanted), self.backdrop
        self._making, self._wanted = asked, []

        def work():
            out = []
            for name, box in asked:
                try:
                    out.append((library.display_name(name, box), library.make_display(name, box, backdrop)))
                except Exception:   # a picture Qt chokes on is shown as it is
                    log.exception("Couldn't make a display copy of %s", name)
                    out.append((library.display_name(name, box), None))
            return out

        def done(out):
            self._busy, self._making = False, []
            if self.stopped:
                return
            made = False
            for base, file in out:
                if file and base:
                    self._use(f"{base}|{backdrop}", file)
                    made = True
                elif base:
                    self._known[f"{base}|{backdrop}"] = None
            self._start()
            if made:
                self.on_made()

        self.run_in_background(work, done)
