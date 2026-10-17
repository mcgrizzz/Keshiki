"""Real-Anki check: the background reaches every main-window webview, runs on
across the toolbar and bottom-bar seams, follows screen changes and progress."""

import json
import time

# isort: off
# kiso_dev.harness sets Qt up for offscreen use before aqt loads, so it comes first.
from kiso_dev.harness import addon, js, pump, run, until

import aqt
from images import make_test_image
# isort: on


def stage_state(app, web):
    """The page's stage, or None: before it has one, or when the answer is lost to the page
    loading again (on a slow machine Anki can still be drawing it), to be asked again."""
    try:
        return js(app, web, """(() => { const s = window.keshiki && keshiki.main;
            if (!s) return null;
            return { look: JSON.parse(s.shown), on: document.documentElement.classList.contains("keshiki-on"),
                     layers: [...s.stack.children].filter(e => !e.dataset.leaving).map(e => [e.dataset.src, e.style.opacity]),
                     rect: s.root.getBoundingClientRect().toJSON() }; })()""", 3)
    except AssertionError:
        return None


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
    renderer = pkg.addon.feature
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

    # Launch: Anki draws the toolbar once, before the collection is open, so it starts bare,
    # and the deck list, drawn once it is, brings the first look. The toolbar shows it too.
    js(app, mw.toolbarWeb, "keshiki.main.apply(null, true)")
    renderer.shown = None
    mw.deckBrowser.refresh()
    until(app, lambda: (stage_state(app, mw.toolbarWeb) or {}).get("on"), 5, "the toolbar stayed bare at launch")
    # The toolbar can have it before the deck list's page has loaded (a slow machine): wait for both.
    looks = lambda: [(stage_state(app, w) or {}).get("look") for w in (mw.toolbarWeb, mw.web)]  # noqa: E731
    until(app, lambda: looks() == [renderer.shown] * 2, 5, f"the toolbar and the deck list differ at launch: {looks()}")
    print("PASS: at launch, the toolbar Anki drew before the collection opened gets the first look too.")

    # Zooming the deck list (Ctrl+wheel, View > Zoom) keeps its stage on the whole window:
    # the page is smaller or larger in CSS pixels, and the stage follows.
    def spans(web, zoom):
        rect = stage_state(app, web)["rect"]
        top = web.mapTo(central, aqt.qt.QPoint(0, 0)).y()
        return (abs(rect["width"] * zoom - central.width()) <= 2 and abs(rect["height"] * zoom - central.height()) <= 2
                and abs(rect["y"] * zoom + top) <= 2)
    for zoom in (1.5, 0.75, 1.0):
        mw.web.setZoomFactor(zoom)
        until(app, lambda z=zoom: spans(mw.web, z), 5, f"the stage didn't follow a zoom to {zoom}")
    print("PASS: zooming the deck list keeps its picture lined up with the bars.")

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

    # Other add-ons' content under the deck table (a stand-in for Review Heatmap and Study Time
    # Stats) gets a backdrop in the table's style: fitted to it, clear of the table, following it.
    from aqt import gui_hooks
    cells = "".join('<div style="width:12px;height:12px;background:#5b8fd8"></div>' for _ in range(60))
    def extra(_browser, content):
        content.stats += ('<div id="fakeAddon"><div style="display:flex;justify-content:center;gap:40px;margin:16px 0">'
                          '<span>Past week<br><b style="color:#4a90e2">9.39 hrs</b></span><span>Total<br><b style="color:#4a90e2">807 hrs</b></span></div>'
                          '<div id="fakeHeat" style="display:grid;grid-template-columns:repeat(30,12px);gap:2px;'
                          f'justify-content:center">{cells}</div></div>')
    gui_hooks.deck_browser_will_render_content.append(extra)
    mw.deckBrowser.refresh()
    until(app, lambda: js(app, mw.web, "!!document.getElementById('fakeHeat')"), 10, "the stand-in add-on didn't render")
    panel = """(() => { const p = document.querySelector('.keshiki-panel');
        if (!p || p.style.display === 'none') return null;
        const r = (el) => el.getBoundingClientRect().toJSON();
        const cells = [...document.getElementById('fakeHeat').children].map(r);   // the grid box itself is full width
        const heat = { left: Math.min(...cells.map(c => c.left)), right: Math.max(...cells.map(c => c.right)),
                       bottom: Math.max(...cells.map(c => c.bottom)) };
        return { panel: r(p), heat, table: r(document.querySelector('center > table')),
                 stats: r(document.getElementById('studiedToday')), width: innerWidth }; })()"""
    assert js(app, mw.web, panel) is None, "a backdrop shows while it's off"
    cfg["backdrops"]["table"]["frost"] = 10
    cfg["backdrops"]["panel"]["frost"] = 10
    renderer.set_config(cfg)
    pump(app, 0.5)
    assert js(app, mw.web, panel) is None, "a backdrop shows on a screen that doesn't use them"
    cfg["screens"]["main"]["backdrops"] = True
    renderer.set_config(cfg)
    until(app, lambda: js(app, mw.web, panel) is not None, 10, "no backdrop behind the add-on's content")
    got = js(app, mw.web, panel)
    p, heat, table = got["panel"], got["heat"], got["table"]
    assert p["left"] < heat["left"] and p["right"] > heat["right"] and p["bottom"] > heat["bottom"], got
    assert p["top"] < got["stats"]["top"] + 8 and p["top"] >= table["bottom"], got   # from the stats line, below the table
    assert p["width"] < got["width"] * 0.9, f"the backdrop isn't fitted: {got}"
    # It and the deck table blur the picture behind them; outlined text has a halo.
    frosted = ("[getComputedStyle(document.querySelector('.keshiki-panel')).backdropFilter, "
               "getComputedStyle(document.querySelector('center > table')).backdropFilter]")
    assert js(app, mw.web, frosted) == ["blur(10px)", "blur(10px)"], js(app, mw.web, frosted)
    # Each panel has its own opacity (the defaults differ: the add-ons' is lighter).
    fills = ("[getComputedStyle(document.querySelector('.keshiki-panel')).backgroundColor, "
             "getComputedStyle(document.querySelector('center > table')).backgroundColor]")
    at40 = js(app, mw.web, fills)
    assert at40[0] != at40[1], at40
    cfg["backdrops"]["table"]["opacity"] = 75
    renderer.set_config(cfg)
    until(app, lambda: js(app, mw.web, fills)[1] != at40[1], 5, "opacity didn't reach the deck table")
    assert js(app, mw.web, fills)[0] == at40[0], "the add-ons' panel has its own opacity"
    cfg["backdrops"]["table"]["opacity"] = 40
    renderer.set_config(cfg)
    # Text on the picture. Where needed: only text short of 4.5:1 is helped, and enough.
    report = "keshiki.contrast.report"
    shadow = "(s) => getComputedStyle(document.querySelector(s)).textShadow"
    cfg["backdrops"]["text"] = {"outline": "needed", "strength": 60}
    renderer.set_config(cfg)
    until(app, lambda: len(js(app, mw.web, report)) > 5, 10, "the text wasn't measured")
    got = js(app, mw.web, report)
    helped = [r for r in got if r["color"] or r["halo"]]
    assert helped, got
    assert all(r["after"] >= 4.5 or r["halo"] for r in got), [r for r in got if r["after"] < 4.5 and not r["halo"]]
    assert all(r["before"] < 4.5 for r in helped), "text that read well was changed"
    assert any(r["color"] and r["text"] in ("9.39 hrs", "807 hrs") for r in got), got   # the blue numbers shift
    zero_untouched = "[...document.querySelectorAll('.zero-count')].every(e => !e.style.color && !e.style.textShadow)"
    assert js(app, mw.web, zero_untouched), "Anki's faint zero counts were changed"
    # The outline is the text's opposite: a light theme's dark text gets a light one, a dark
    # theme's light text a dark one (Anki follows the system's theme: Windows may be dark).
    from aqt.theme import theme_manager
    haloed = "[...keshiki.contrast.touched.keys()].map(e => e.style.textShadow).filter(Boolean)"
    halos = js(app, mw.web, haloed)
    opposite = "0, 0, 0" if theme_manager.night_mode else "255, 255, 255"
    assert halos and all(opposite in h for h in halos), (theme_manager.night_mode, halos)
    # Everywhere: all text has the outline (the deck table's too), more where needed.
    cfg["backdrops"]["text"]["outline"] = "everywhere"
    renderer.set_config(cfg)
    until(app, lambda: js(app, mw.web, f"({shadow})('center > table th')") != "none", 5, "the deck table isn't outlined")
    assert js(app, mw.web, "[...document.querySelectorAll('#studiedToday, #studiedToday *')]"
                           ".some(e => getComputedStyle(e).textShadow !== 'none')"), "the stats line isn't outlined"
    assert js(app, mw.web, zero_untouched)
    pump(app, 0.5)
    if shots:
        central.grab().save(str(shots / "deck-list-backdrop.png"))
    cfg["backdrops"]["text"]["outline"] = "off"
    renderer.set_config(cfg)
    until(app, lambda: js(app, mw.web, "keshiki.contrast.touched.size") == 0, 5, "the outline stayed after turning it off")
    # The content grows (another row of the heatmap): the backdrop follows.
    js(app, mw.web, f"document.getElementById('fakeHeat').insertAdjacentHTML('beforeend', {json.dumps(cells)})")
    until(app, lambda: js(app, mw.web, panel)["panel"]["bottom"] > p["bottom"] + 20, 5, "the backdrop didn't follow its content")
    cfg["screens"]["main"]["backdrops"] = False
    renderer.set_config(cfg)
    until(app, lambda: js(app, mw.web, panel) is None, 5, "the backdrop stayed after turning it off")
    gui_hooks.deck_browser_will_render_content.remove(extra)
    mw.deckBrowser.refresh()
    print("PASS: on a screen that uses backdrops, other add-ons' content under the deck table gets a fitted, "
          "frosted panel that follows it, and text on the picture is outlined where needed or everywhere.")

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

    # Back to the deck list: Anki builds that page after the screen has changed, so it loads
    # mid-crossfade. It fades with the bars from where they are, instead of jumping to the end.
    # The new look waits for the deck list to draw: when it goes out, the page is already there,
    # and it and the bars fade together from the start.
    dim = "Number(getComputedStyle(keshiki.main.dim).opacity)"
    before = renderer.shown
    started = time.monotonic()
    mw.moveToState("deckBrowser")
    until(app, lambda: renderer.shown is not before, 5, "the deck list's look never went out")
    waited = time.monotonic() - started
    assert js(app, mw.web, "!!(window.keshiki && keshiki.main && document.querySelector('center > table tr.deck'))"), \
        "the look went out before the deck list was there"
    print(f"  the look waited {waited * 1000:.0f} ms for the deck list")
    pump(app, 0.7)
    main_dim, bar_dim = js(app, mw.web, dim), js(app, mw.toolbarWeb, dim)
    assert 0.03 < main_dim < 0.29 and abs(main_dim - bar_dim) < 0.05, (main_dim, bar_dim)
    until(app, lambda: js(app, mw.web, dim) == 0 and js(app, mw.toolbarWeb, dim) == 0, 5)
    mw.moveToState("review")
    until(app, lambda: mw.state == "review", 5)
    pump(app, 2.5)
    print("PASS: a screen change waits for Anki's new page, then it and the bars fade together.")

    # Studying straight from the overview, its fade not done: the reviewer's pages load
    # mid-fade, on a look already going out, and join it where the bars are. Another picture,
    # blurred, as studying often has. A long fade, so a slow machine (CI's Windows) still has the
    # reviewer load during it.
    other = new_scene("single", image=b)
    cfg["scenes"].append(other)
    cfg["screens"]["study"].update(same_as_main=False, scenes=[other["id"]], blur=8)
    cfg["transition_seconds"] = 4
    renderer.set_config(cfg)
    mw.moveToState("deckBrowser")
    loaded_dim = f"window.keshiki && keshiki.main ? {dim} : -1"   # -1 while the page loads
    until(app, lambda: js(app, mw.web, loaded_dim) == 0 and js(app, mw.toolbarWeb, dim) == 0, 10)
    before = renderer.shown
    mw.moveToState("overview")
    until(app, lambda: renderer.shown is not before, 5, "the overview's look never went out")
    # Its picture's copy is made a moment later: the same look, another file.
    pump(app, 0.2)
    real = renderer.look
    renderer.look = lambda: (lambda lk: dict(lk, layers=[dict(x, src=x["src"] + "#copy") for x in lk["layers"]]))(real())
    renderer.refresh()
    del renderer.look
    pump(app, 0.3)
    js(app, mw.web, "window.__overview = true")
    mw.moveToState("review")
    until(app, lambda: mw.state == "review" and js(app, mw.web, "!window.__overview && !!(window.keshiki && keshiki.main)"),
          5, "the reviewer's page never loaded")
    pump(app, 0.2)
    main_dim, bar_dim, bottom_dim = (js(app, w, dim) for w in (mw.web, mw.toolbarWeb, mw.bottomWeb))
    print(f"  reviewer loaded mid-fade: main area {main_dim:.2f}, toolbar {bar_dim:.2f}, bottom {bottom_dim:.2f}")
    assert 0.005 < bar_dim < 0.27, "the toolbar isn't mid-fade"
    assert abs(main_dim - bar_dim) < 0.04 and abs(bottom_dim - bar_dim) < 0.04, (main_dim, bar_dim, bottom_dim)
    newest = """(() => { const live = [...keshiki.main.stack.children];
        const el = live[live.length - 1]; return [el.dataset.key, Number(getComputedStyle(el).opacity), live.length]; })()"""
    # The pages are asked one after the other, and the fade moves on between (on a slow machine,
    # a lot): the toolbar's falls between the main area's just before and just after.
    main_pic, bar_pic, main_after = js(app, mw.web, newest), js(app, mw.toolbarWeb, newest), js(app, mw.web, newest)
    print(f"  newest picture: main area {main_pic} then {main_after[1]:.3f}, toolbar {bar_pic}")
    lo, hi = sorted((main_pic[1], main_after[1]))
    assert main_pic[0] == bar_pic[0] and lo - 0.04 < bar_pic[1] < hi + 0.04 and main_pic[2] == 2, (main_pic, bar_pic, main_after)
    until(app, lambda: js(app, mw.web, loaded_dim) == 0.3 and js(app, mw.toolbarWeb, dim) == 0.3, 10)
    cfg["scenes"].remove(other)
    cfg["screens"]["study"].update(same_as_main=True, scenes=[], blur=0)
    cfg["transition_seconds"] = 2.0
    renderer.set_config(cfg)
    pump(app, 2.5)
    print("PASS: pages that load while a fade is under way join it, in step with the bars.")

    # A page held up just as a look arrives (on a real GPU, a big picture can stall frames for
    # 200 ms) starts its fade that far in: it and the bars stay in step.
    js(app, mw.web, """(() => { const s = keshiki.main, was = s.apply;
        s.apply = function (...a) { const r = was.apply(this, a); const end = performance.now() + 300;
                                     while (performance.now() < end) {} s.apply = was; return r; }; })()""")
    key = "study" if mw.state in ("overview", "review") else "main"
    was = cfg["screens"][key]["dim"]
    start = js(app, mw.web, dim)
    target = 0.9 if start < 0.5 else 0.1
    cfg["screens"][key]["dim"] = round(target * 100)
    renderer.set_config(cfg)
    pump(app, 0.9)
    main_dim, bar_dim = js(app, mw.web, dim), js(app, mw.toolbarWeb, dim)
    print(f"  held up 300 ms, dim {start:.2f} -> {target}: main area {main_dim:.2f}, toolbar {bar_dim:.2f}")
    lo, hi = sorted((start, target))
    assert lo + 0.1 < bar_dim < hi - 0.1, "the toolbar isn't mid-fade"
    assert abs(main_dim - bar_dim) < 0.04, (main_dim, bar_dim)
    until(app, lambda: abs(js(app, mw.web, dim) - target) < 0.01, 5)
    cfg["screens"][key]["dim"] = was
    renderer.set_config(cfg)
    until(app, lambda: abs(js(app, mw.web, dim) - start) < 0.01 and abs(js(app, mw.toolbarWeb, dim) - start) < 0.01, 5)
    print("PASS: a page held up as a look arrives starts its fade that far in, in step with the bars.")

    # Anki's "hide bottom bar" collapses it mid-review; its stage follows its new offset.
    mw.pm.set_hide_bottom_bar(True)
    mw.bottomWeb.hide()
    until(app, lambda: mw.bottomWeb.height() <= 1, 5, "bottom bar didn't collapse")
    top = mw.bottomWeb.mapTo(central, aqt.qt.QPoint(0, 0)).y()
    until(app, lambda: round(stage_state(app, mw.bottomWeb)["rect"]["y"]) == -top, 5, "bottom stage kept its old offset")
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
    def showing(image):
        # One read: the page can reload between two.
        layers = (stage_state(app, mw.web) or {}).get("layers", [])
        return bool(layers) and layers[-1][0].endswith(image)
    until(app, lambda: showing(a), 5, "progress scene didn't start on its first image")
    mw.reviewer._showAnswer()
    until(app, lambda: mw.reviewer.state == "answer")
    mw.reviewer._answerCard(4)   # Easy: graduates, so the deck is done
    until(app, lambda: mw.state == "overview", 10, "deck didn't finish")
    until(app, lambda: showing(b),
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
    until(app, lambda: showing(b), 10, "the all-done scene didn't show on the deck list")
    print("PASS: once everything is studied, the all-done scene shows on the deck list.")

    # New cards (an operation outside the reviewer, like a sync) end it on the deck list.
    from aqt.operations.note import add_note
    cfg["screens"]["study"]["same_as_main"] = True   # no progress scene on any screen now
    renderer.set_config(cfg)
    more = mw.col.decks.id("More")
    for i in range(3):
        note = mw.col.new_note(mw.col.models.by_name("Basic"))
        note["Front"], note["Back"] = f"more {i}", "..."
        add_note(parent=mw, note=note, target_deck_id=more).run_in_background()
    until(app, lambda: showing(a), 10, "new cards didn't end the all-done scene")
    # In the reviewer, answering doesn't work out "all done" again (every deck's counts).
    from keshiki.keshiki import progress
    real, calls = progress.nothing_left, []
    progress.nothing_left = lambda col: calls.append(1) or real(col)
    try:
        mw.col.decks.select(more)
        mw.moveToState("review")
        until(app, lambda: mw.state == "review" and mw.reviewer.card is not None, 10)
        until(app, lambda: not renderer._settling.pending, 5)   # the screen change's own check, done
        first = mw.reviewer.card.id
        calls.clear()
        mw.reviewer._showAnswer()
        until(app, lambda: mw.reviewer.state == "answer")
        mw.reviewer._answerCard(3)
        until(app, lambda: mw.reviewer.card is not None and mw.reviewer.card.id != first, 10, "the next card didn't come")
        pump(app, 0.5)
        assert not calls, f"'all done' was worked out {len(calls)} times for one answer"
    finally:
        progress.nothing_left = real
    print("PASS: new cards end all done on the deck list; answering a card doesn't check it again.")
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
