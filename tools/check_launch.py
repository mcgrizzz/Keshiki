"""Real-Anki check of a launch, over two launches of one Anki folder: the first saves a config
with a picture on the deck list; at the second, the toolbar, the deck list and the bottom bar all
show it from the start, with nothing set after Anki opened."""

import os
import subprocess
import sys
import tempfile

LAUNCH = os.environ.get("KESHIKI_CHECK_LAUNCH")


def launch():
    """One launch, in this process (the parent runs it as a child)."""
    # isort: off
    from kiso_dev.harness import addon, js, pump, run, until

    import aqt
    from images import make_test_image
    # isort: on

    def check(app, shots, base):
        mw = aqt.mw
        renderer = addon().addon.feature
        from keshiki.keshiki import library
        from keshiki.keshiki.config import migrate, new_scene

        if LAUNCH == "first":
            name = library.import_files([str(make_test_image(base / "meadow.png", 120))])[0]
            cfg, _ = migrate({})
            scene = new_scene("single", image=name)
            cfg["scenes"] = [scene]
            cfg["screens"]["main"].update(scenes=[scene["id"]], dim=0)
            mw.addonManager.writeConfig("keshiki", cfg)
            print("SAVED", flush=True)
            return
        webs = {"toolbar": mw.toolbarWeb, "main": mw.web, "bottom": mw.bottomWeb}
        shown = """(() => { const s = window.keshiki && keshiki.main;
            return s ? [...s.stack.children].filter((e) => !e.dataset.leaving).map((e) => e.dataset.src.split('/').pop())
                     : null; })()"""
        until(app, lambda: mw.state == "deckBrowser" and renderer.shown, 15, "the deck list never came up")
        for part, web in webs.items():
            until(app, lambda w=web: js(app, w, shown) == ["meadow.png"], 5,
                  f"the {part} didn't show the picture at launch: {js(app, web, shown)}")
        # And it stays: nothing later takes it away. Each part's stage covers the whole window at
        # that part's place in it (one measured mid-layout would leave its picture out of view).
        pump(app, 2)
        missing = [part for part, web in webs.items() if js(app, web, shown) != ["meadow.png"]]
        assert not missing, f"lost the picture after launch: {missing}"
        central = mw.form.centralwidget
        for part, web in webs.items():
            rect = js(app, web, "keshiki.main.root.getBoundingClientRect().toJSON()")
            top = web.mapTo(central, aqt.qt.QPoint(0, 0)).y()
            assert abs(rect["y"] + top) <= 1 and abs(rect["height"] - central.height()) <= 1, (part, rect, top)
        if shots:
            mw.form.centralwidget.grab().save(str(shots / "launch.png"))
        print("PASS: at launch the toolbar, the deck list and the bottom bar show the picture, each at its place.", flush=True)

    run(check, __doc__)


def main():
    with tempfile.TemporaryDirectory(prefix="keshiki-launch-", ignore_cleanup_errors=True) as base:
        for name in ("first", "second"):
            proc = subprocess.run([sys.executable, __file__, *sys.argv[1:]], capture_output=True, text=True,
                                  timeout=240, env={**os.environ, "KISO_CHECK_BASE": base, "KESHIKI_CHECK_LAUNCH": name})
            out = proc.stdout + proc.stderr
            if proc.returncode or ("SAVED" if name == "first" else "PASS:") not in out:
                print(out)
                raise SystemExit(f"the {name} launch failed")
            if name == "second":
                print("\n".join(line for line in out.splitlines() if line.startswith("PASS")))


if __name__ == "__main__":
    launch() if LAUNCH else main()
