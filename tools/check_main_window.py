"""Real-Anki check: the background reaches every main-window webview, runs on
across the toolbar and bottom-bar seams, follows screen changes and progress."""

import json

from qt_harness import addon, aqt, js, make_test_image, pump, run, until


def stage_state(app, web):
    return js(app, web, """(() => { const s = window.keshiki && keshiki.main;
        if (!s) return null;
        return { look: JSON.parse(s.shown), on: document.documentElement.classList.contains("keshiki-on"),
                 layers: [...s.stack.children].filter(e => !e.dataset.leaving).map(e => [e.dataset.src, e.style.opacity]),
                 rect: s.root.getBoundingClientRect().toJSON() }; })()""")


def seam_mismatch(img, y, x0, x1):
    """How badly row y fails to continue row y-1. The test image's lines run at
    45 degrees, so a continuous picture has row[y][x+1] == row[y-1][x]."""
    total = 0
    for x in range(x0, x1):
        a, b = img.pixelColor(x, y - 1), img.pixelColor(x + 1, y)
        total += abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
    return total / (x1 - x0)


def check(app, shots, base):
    mw = aqt.mw
    pkg = addon()
    renderer = pkg._renderer
    from keshiki.keshiki import library
    from keshiki.keshiki.config import migrate, new_scene

    a, b = (library.import_files([str(make_test_image(base / f"{n}.png", hue))])[0]
            for n, hue in (("meadow", 120), ("dusk", 20)))
    cfg, _ = migrate({})
    scene = new_scene("single", image=a)
    cfg["scenes"] = [scene]
    cfg["screens"]["main"].update(scenes=[scene["id"]], dim=0)
    cfg["screens"]["study"]["dim"] = 30
    mw.addonManager.writeConfig("keshiki", cfg)
    renderer.set_config(cfg)

    webs = {"toolbar": mw.toolbarWeb, "main": mw.web, "bottom": mw.bottomWeb}
    for name, web in webs.items():
        until(app, lambda w=web: (stage_state(app, w) or {}).get("on"), 10, f"no background in {name}")
    print("PASS: background reaches toolbar, deck list and bottom bar.")

    # Every stage covers the whole central widget, shifted by its webview's offset.
    central = mw.form.centralwidget
    for name, web in webs.items():
        rect = stage_state(app, web)["rect"]
        top = web.mapTo(central, aqt.qt.QPoint(0, 0)).y()
        assert (round(rect["width"]), round(rect["height"])) == (central.width(), central.height()), (name, rect)
        assert round(rect["y"]) == -top, (name, rect, top)
    print("PASS: each stage spans the window at its webview's offset.")

    pump(app, 2.5)   # past the fade-in
    img = central.grab().toImage()
    if shots:
        img.save(str(shots / "deck-list.png"))
    seams = {"toolbar": mw.toolbarWeb.height(), "bottom bar": mw.web.y() + mw.web.height() - central.y()}
    reference = seam_mismatch(img, 300, 10, 200)
    for name, y in seams.items():
        mismatch = seam_mismatch(img, y, 10, 200)
        print(f"  {name} seam mismatch {mismatch:.1f} (inside the image: {reference:.1f})")
        assert mismatch < reference + 25, f"{name} seam breaks the image"
    print("PASS: the image runs on across both seams.")

    # Studying: same scene, its own dim, crossfaded rather than reloaded on the bars.
    did = mw.col.decks.id("Default")
    note = mw.col.new_note(mw.col.models.by_name("Basic"))
    note["Front"], note["Back"] = "景色", "scenery"
    mw.col.add_note(note, did)
    mw.col.decks.select(did)
    mw.moveToState("review")
    until(app, lambda: mw.state == "review" and ((stage_state(app, mw.web) or {}).get("look") or {}).get("dim") == 0.3,
          10, "reviewer didn't get the study look")
    assert stage_state(app, mw.bottomWeb)["look"]["dim"] == 0.3
    assert stage_state(app, mw.toolbarWeb)["look"]["dim"] == 0.3
    pump(app, 2.5)
    if shots:
        central.grab().save(str(shots / "reviewer.png"))
    print("PASS: the reviewer and both bars switch to the study look.")

    # Anki's "hide bottom bar" collapses it mid-review; its stage follows its new offset.
    mw.pm.set_hide_bottom_bar(True)
    mw.bottomWeb.hide()
    until(app, lambda: mw.bottomWeb.height() <= 1, 5, "bottom bar didn't collapse")
    pump(app, 0.3)
    top = mw.bottomWeb.mapTo(central, aqt.qt.QPoint(0, 0)).y()
    assert round(stage_state(app, mw.bottomWeb)["rect"]["y"]) == -top, "bottom stage kept its old offset"
    mw.bottomWeb.show()
    mw.pm.set_hide_bottom_bar(False)
    until(app, lambda: mw.bottomWeb.height() > 1, 5)
    print("PASS: the bottom bar's slice follows it when Anki collapses it.")

    # A progress scene: start image before answering, finished image after.
    prog = new_scene("progress")
    for v in prog["versions"]:
        v["image"] = b if v["label"] == "Finished" else a
    cfg["scenes"].append(prog)
    cfg["screens"]["study"].update(same_as_main=False, scenes=[prog["id"]])
    renderer.set_config(cfg)
    srcs = lambda: [s for s, _ in (stage_state(app, mw.web) or {}).get("layers", [])]  # noqa: E731
    until(app, lambda: srcs() and srcs()[-1].endswith(a), 5, "progress scene didn't start on its first image")
    mw.reviewer._showAnswer()
    until(app, lambda: mw.reviewer.state == "answer")
    mw.reviewer._answerCard(4)   # Easy: graduates, so the deck is done
    until(app, lambda: mw.state == "overview", 10, "deck didn't finish")
    until(app, lambda: srcs() and srcs()[-1].endswith(b),
          10, "congratulations screen didn't get the finished image")
    pump(app, 2.5)
    if shots:
        central.grab().save(str(shots / "finished.png"))
    print("PASS: a progress scene ends on its finished image on the congratulations screen.")

    # All done for today: with nothing left in any deck, the done scene takes over the deck list.
    done = new_scene("single", image=b)
    cfg["scenes"].append(done)
    cfg["screens"]["done"].update(enabled=True, scenes=[done["id"]])
    renderer.set_config(cfg)
    mw.moveToState("deckBrowser")
    until(app, lambda: srcs() and srcs()[-1].endswith(b), 10, "the all-done scene didn't show on the deck list")
    print("PASS: once everything is studied, the all-done scene shows on the deck list.")
    mw.moveToState("overview")
    until(app, lambda: mw.state == "overview", 5)

    # Turning studying off clears the reviewer's background and Anki's own look returns.
    cfg["screens"]["study"]["enabled"] = False
    renderer.set_config(cfg)
    until(app, lambda: not (stage_state(app, mw.web) or {"on": True})["on"], 5, "background didn't clear")
    print("PASS: a screen without a background shows Anki's own.")

    # A note type that paints its own page (like Kiku's DaisyUI themes): its full-width
    # wrappers let the picture through, its narrower card panel keeps its background.
    cfg["screens"]["study"].update(enabled=True, same_as_main=True)
    cfg["screens"]["done"]["enabled"] = False
    renderer.set_config(cfg)
    models = mw.col.models
    themed = models.new("Themed")
    for name in ("Front", "Back"):
        models.add_field(themed, models.new_field(name))
    template = models.new_template("Card 1")
    template["qfmt"] = (
        '<div id="root" style="background:#1d232a"><div id="panel" style="max-width:420px;margin:auto;'
        'background:#2a323c;padding:20px">{{Front}}</div></div>'
        '<themed-bar id="bar"></themed-bar>'
        "<script>if (!customElements.get('themed-bar')) customElements.define('themed-bar', class extends HTMLElement {"
        " constructor() { super(); this.attachShadow({mode: 'open'}).innerHTML ="
        " '<div id=\\'shadowbar\\' style=\\'background:#111;height:40px\\'>bar</div>'; } });</script>")
    template["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
    models.add_template(themed, template)
    models.add(themed)
    note = mw.col.new_note(models.by_name("Themed"))
    note["Front"], note["Back"] = "直る", "to be fixed"
    did = mw.col.decks.id("Themed")
    mw.col.add_note(note, did)
    mw.col.decks.select(did)
    mw.moveToState("review")
    background = lambda sel: js(app, mw.web, f"""(() => {{ const el = {sel}; return el ? getComputedStyle(el).backgroundColor : null; }})()""")  # noqa: E731
    until(app, lambda: mw.state == "review" and background("document.getElementById('root')") == "rgba(0, 0, 0, 0)",
          10, "the note type's full-width backdrop still covers the picture")
    assert background("document.getElementById('panel')") == "rgb(42, 50, 60)", "the card's own panel lost its background"
    until(app, lambda: background("document.getElementById('bar').shadowRoot.getElementById('shadowbar')") == "rgba(0, 0, 0, 0)",
          5, "a full-width backdrop inside a web component still covers the picture")
    if shots:
        pump(app, 2.5)
        central.grab().save(str(shots / "themed-reviewer.png"))
    # With no background on this screen, the note type looks as its author made it.
    cfg["screens"]["study"]["enabled"] = False
    renderer.set_config(cfg)
    until(app, lambda: background("document.getElementById('root')") == "rgb(29, 35, 42)", 5,
          "the note type's backdrop didn't come back")
    print("PASS: note types that paint their own page let the picture through their full-width wrappers only.")
    print(json.dumps({"seams": seams}))


if __name__ == "__main__":
    run(check, __doc__)
