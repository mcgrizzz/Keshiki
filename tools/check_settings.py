"""Real-Anki check of the settings page: first-run flow, a day-cycle scene,
live preview in the main window, save, and screenshots of each page."""

import json

# isort: off
# kiso_dev.harness sets Qt up for offscreen use before aqt loads, so it comes first.
from kiso_dev.harness import addon, js, pump, run, until

import aqt
from images import make_test_image
# isort: on

HELPERS = """
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
// The sidebar's unsaved-changes dot isn't part of a name.
const byText = (sel, text) => $$(sel).find((e) => e.textContent.replace("•", "").trim() === text);
const setv = (el, v) => { el.value = v; el.dispatchEvent(new Event("input", {bubbles: true}));
                          el.dispatchEvent(new Event("change", {bubbles: true})); };
"""


def check(app, shots, base):
    mw = aqt.mw
    from keshiki.keshiki.settings_page import make_dialog

    files = [str(make_test_image(base / f"{name}.png", hue)) for name, hue in
             (("dawn", 330), ("day", 200), ("dusk", 25), ("night", 240))]
    renderer = addon().addon.feature

    def open_page():
        dlg = make_dialog(mw, renderer)
        dlg.kiso_bridge.pick_files = lambda: files
        # No network in checks: the location lookup answers at once.
        dlg.kiso_bridge.in_background = lambda fn, done: done(
            {"latitude": 35.68, "longitude": 139.65, "place": "Tokyo, Japan"})
        dlg.show()
        until(app, lambda: js(app, dlg.kiso_web, "window.kisoReady === true"), 15, "settings page never loaded")
        return dlg

    def run_js(dlg, code):
        # Own scope per call; eval returns the last statement's value.
        return js(app, dlg.kiso_web, f"(() => {{ {HELPERS} return eval({json.dumps(code)}); }})()")

    def shoot(dlg, name):
        pump(app, 0.8)
        if shots:
            dlg.grab().save(str(shots / f"settings-{name}.png"))

    dlg = open_page()
    assert run_js(dlg, "$('.blank h2').textContent") == "Start with a picture"
    shoot(dlg, "welcome")

    # First run: "Add images..." makes an album of the pictures and shows it on the deck list.
    run_js(dlg, "byText('button', 'Add images...').click()")
    until(app, lambda: run_js(dlg, "$$('.chip').length") == 1, 10, "the images didn't become an album")
    assert run_js(dlg, "$('.chip-name').textContent") == "Album (4)"
    until(app, lambda: renderer.preview is not None, 5, "draft didn't preview in the main window")
    assert run_js(dlg, "!$('#save').disabled")
    shoot(dlg, "screens")
    print("PASS: first images become an album on the deck list and preview live.")

    # The album on the Scenes page: its pictures as tiles; a tile shows in the preview and
    # opens the picker; × takes one out.
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5, "the album's pictures aren't tiles")
    assert run_js(dlg, "$('.editor .kind').textContent") == "Album · 4 pictures"
    assert run_js(dlg, "!$('.ribbon') && !$('#play')"), "an album has no timeline"
    run_js(dlg, "$$('.album-tile .pick')[2].click()")
    until(app, lambda: run_js(dlg, "!!$('.tile')"), 5, "the tile didn't open the picker")
    until(app, lambda: run_js(dlg, "$$('.preview .keshiki-layer').filter(e => !e.dataset.leaving)"
                                   ".map(e => e.dataset.src.split('/').pop())") == ["dusk.png"], 5,
          "the preview doesn't show the tile's picture")
    run_js(dlg, "$('#modal .dialog-foot button').click()")
    run_js(dlg, "$$('.album-tile .remove')[3].click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5)
    run_js(dlg, "const a = draft.scenes[0]; a.versions.push({ label: '', image: 'night.png' }); changed(true)")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5)
    shoot(dlg, "album")
    print("PASS: an album shows its pictures as tiles; each previews, opens the picker, or comes out.")

    # A day cycle from the template, one image per version.
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    run_js(dlg, "byText('button', 'New day cycle').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 4, 5, "day cycle template missing")
    for i, name in enumerate(["dawn", "day", "dusk", "night"]):
        run_js(dlg, f"$$('.version .pick')[{i}].click()")
        until(app, lambda: run_js(dlg, "!!$('.tile')"), 5)
        run_js(dlg, f"$$('.tile').find(t => t.title === '{name}.png').click(); byText('button', 'Use image').click()")
    until(app, lambda: run_js(dlg, "$$('.ribbon .seg').length") >= 4, 5, "ribbon didn't draw")
    # Versions start and finish at named moments of the sun, with today's times.
    until(app, lambda: run_js(dlg, "$$('.version select')[0].selectedOptions[0].textContent").startswith("First light ·"),
          5, "the dawn version doesn't start at First light")
    assert run_js(dlg, "$$('.version select')[1].selectedOptions[0].textContent").startswith("Sunrise ·")
    assert run_js(dlg, "!$('.versions').textContent.includes('°')"), "sun degrees still show"
    # Scrub to 13:00: the preview shows the day image alone.
    run_js(dlg, "setv($('.ribbon input'), 780)")
    until(app, lambda: run_js(dlg, "$('.preview .readout').textContent") == "13:00", 5)
    until(app, lambda: run_js(dlg, "$$('.preview .keshiki-layer').filter(e => !e.dataset.leaving).map(e => e.dataset.src.split('/').pop())")
          == ["day.png"], 5, "preview at 13:00 isn't the day image")
    shoot(dlg, "scene-day")
    print("PASS: a day cycle scene previews along its ribbon.")

    # Working on a version shows it at the moment it's fully in, the end of its row's times
    # (dusk: the setting sun from +12° to the horizon, a few minutes before the 19:30 sunset).
    run_js(dlg, "$$('.version input.label')[2].focus()")
    until(app, lambda: run_js(dlg, "$('.preview .readout').textContent") ==
          run_js(dlg, "(() => { const m = S.marks.find(m => m.index === 2); return hhmm(m.start + m.fade); })()"),
          5, "focusing a version didn't preview it")
    fully_in = run_js(dlg, "$('.preview .readout').textContent")
    assert "19:2" in fully_in, fully_in
    until(app, lambda: run_js(dlg, "$$('.version.showing').map(r => r.dataset.index)") == ["2"], 5,
          "the version showing isn't marked")
    # Timelapse: the button is on top (not covered by the picture), plays the whole day and stops at the end.
    assert run_js(dlg, """(() => { const b = $('#play').getBoundingClientRect();
        return document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2).closest('#play') !== null; })()"""), \
        "the play button is covered"
    assert run_js(dlg, """(() => { const b = $('.preview .readout').getBoundingClientRect();
        return document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2).closest('.readout') !== null; })()"""), \
        "the time readout is covered"
    run_js(dlg, "setv($('#playSpeed'), '5')")
    # Every frame of the run, how much of the preview the pictures cover (1 - the product
    # of each layer's transparency): a dip is a dark flash where two layers fade at once.
    run_js(dlg, """window._frames = []; window._sampling = true; (function tick() {
        const ops = $$('.preview .keshiki-layer').map(e => Number(getComputedStyle(e).opacity));
        if (ops.length) window._frames.push({ cover: 1 - ops.reduce((p, o) => p * (1 - o), 1), layers: ops.length,
                                              at: $('.preview .readout').textContent, ops: ops.map(o => o.toFixed(2)).join(' ') });
        if (window._sampling) requestAnimationFrame(tick); })()""")
    # Play from now; Anki's window follows.
    run_js(dlg, "$('#play').click()")
    until(app, lambda: run_js(dlg, "$('#play').getAttribute('aria-label')") == "Pause", 3, "timelapse didn't start")
    seen = set()
    until(app, lambda: seen.add(run_js(dlg, "$('.preview .readout').textContent")) or len(seen) > 5, 6,
          "timelapse didn't move")
    until(app, lambda: renderer.scene_look is not None, 3, "Anki's window didn't follow the timelapse")
    # Pause holds the moment; play carries on with the same run.
    run_js(dlg, "$('#play').click()")
    paused_at = run_js(dlg, "$('.preview .readout').textContent")
    pump(app, 0.6)
    assert run_js(dlg, "$('#play').getAttribute('aria-label')") == "Play"
    assert run_js(dlg, "$('.preview .readout').textContent") == paused_at and not paused_at.startswith("Now")
    assert renderer.scene_look is not None and run_js(dlg, "!$('#backToNow').hidden")
    run_js(dlg, "$('#play').click()")
    # 24 hours on it's back at now: the readout says so and Anki's window has its own look again.
    until(app, lambda: run_js(dlg, "$('#play').getAttribute('aria-label')") == "Play", 8, "timelapse didn't finish")
    run_js(dlg, "window._sampling = false")
    frames = run_js(dlg, "window._frames")
    assert len(frames) > 50, f"only {len(frames)} frames sampled"
    darkest = min(f["cover"] for f in frames)
    assert darkest > 0.97, f"the timelapse flashes dark: coverage fell to {darkest:.2f}: " + \
        str([f for f in frames if f["cover"] <= 0.97][:5])
    assert max(f["layers"] for f in frames) <= 4, "layers pile up during the timelapse"
    until(app, lambda: renderer.scene_look is None, 3, "the end of the run didn't hand Anki's window back")
    assert run_js(dlg, "$('.preview .readout').textContent.startsWith('Now') && $('#backToNow').hidden")
    # Back to now also ends a paused run.
    run_js(dlg, "$('#play').click()")
    pump(app, 0.5)
    run_js(dlg, "$('#play').click(); $('#backToNow').click()")
    until(app, lambda: renderer.scene_look is None, 5, "Back to now didn't hand Anki's window back")
    print("PASS: focusing a version previews it; play runs the next 24 hours at the chosen speed with pause, "
          "with no dark frames, and Anki's window follows until it's back at now.")

    # Light: halfway through dusk's fade (19:00), both pictures carry a colour grade toward each other.
    def mid_fade_filters():
        return run_js(dlg, "$$('.preview .keshiki-layer').filter(e => !e.dataset.leaving).map(e => e.querySelector('.keshiki-pic').style.filter)")
    run_js(dlg, "(() => { const m = S.marks.find(m => m.index === 2); setv($('.ribbon input'), m.start + m.fade / 2); })()")
    until(app, lambda: len(mid_fade_filters()) == 2 and all(f.startswith("url(") for f in mid_fade_filters()), 5,
          "light matching didn't grade the fade")
    shoot(dlg, "fade-matched")
    run_js(dlg, "draft.light.tint = true; draft.light.tint_strength = 100; changed(true)")
    # Daylight is a colour matrix on the whole picture: low evening sun, so red is lifted over blue.
    # Each picture's filter carries the daylight matrix (its second step, after the fade's grade).
    top_filter = ("(() => { const el = $$('.preview .keshiki-layer').filter(e => !e.dataset.leaving).pop(); "
                  "return document.getElementById(el.querySelector('.keshiki-pic').style.filter.match(/#([^\"')]+)/)[1]); })()")
    until(app, lambda: run_js(dlg, top_filter + " !== null"), 5, "daylight didn't apply to the preview")
    values = [float(v) for v in run_js(dlg, top_filter.replace("})()", "})().children[1].getAttribute('values')")).split()]
    assert values[0] > values[12], values
    shoot(dlg, "fade-tint")
    run_js(dlg, "draft.light.tint = false; draft.light.tint_strength = 50; changed(true)")
    print("PASS: fades smooth their colour, and lighting by the sun reaches the preview.")

    # A long name stays inside the list, cut short with an ellipsis; Delete sits beside the name.
    run_js(dlg, "setv($('.editor .name'), 'Midday train over blue waters with a very long name indeed')")
    assert run_js(dlg, """(() => { const n = $('[aria-current=true] .item-name'), list = $('.scene-list');
        return n.scrollWidth > n.clientWidth && n.getBoundingClientRect().right <= list.getBoundingClientRect().right; })()""")
    assert run_js(dlg, "Math.abs($('#deleteScene').getBoundingClientRect().top - $('.editor .name').getBoundingClientRect().top) < 8")
    run_js(dlg, "setv($('.editor .name'), 'Day cycle')")
    print("PASS: long scene names are cut short, and Delete scene is on the name's line.")

    # A set time's clock wraps under its dropdown instead of widening every row off the panel.
    run_js(dlg, "byText('button', '+ Add version').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 5, 5)
    run_js(dlg, "setv($$('.version')[4].querySelector('select'), 'clock')")
    until(app, lambda: run_js(dlg, "!!$('.version input[type=time]')"), 5, "no clock for a set time")
    overflow = run_js(dlg, "Math.max(...$$('.versions *').map(e => e.getBoundingClientRect().right))"
                           " - $('.versions').getBoundingClientRect().right")
    assert overflow <= 0, f"versions table overflows by {overflow}px with a set time"
    # Editing the time keeps the box's focus and the page's scroll position.
    run_js(dlg, "const m = $('main'); m.scrollTop = m.scrollHeight; window._top = m.scrollTop")
    assert run_js(dlg, "window._top") > 0, "the page doesn't scroll in this window"
    run_js(dlg, "const t = $('.version input[type=time]'); t.focus(); setv(t, '22:15')")
    pump(app, 0.4)
    assert run_js(dlg, "document.activeElement === $('.version input[type=time]')"), "the time box lost its focus"
    assert run_js(dlg, "$('main').scrollTop") == run_js(dlg, "window._top"), "editing the time scrolled the page"
    assert run_js(dlg, "draft.scenes.find(s => s.kind === 'day').versions[4].offset") == 22 * 60 + 15
    # A change that rebuilds the page keeps its place too.
    run_js(dlg, "const f = $$('.version')[0].querySelectorAll('select')[1]; setv(f, f.options[1].value)")
    pump(app, 0.4)
    assert run_js(dlg, "$('main').scrollTop") == run_js(dlg, "window._top"), "a rebuild scrolled the page"
    run_js(dlg, "$('main').scrollTop = 0")
    run_js(dlg, "$$('.version')[4].querySelector('[aria-label=\"Remove version\"]').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 4, 5)
    print("PASS: a version at a set time fits the panel, and editing its time keeps focus and scroll.")

    # A new version follows the last: it starts as Night is fully in, with no time to set.
    day_scene = "draft.scenes.find(s => s.kind === 'day')"
    run_js(dlg, "byText('button', '+ Add version').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 5, 5)
    starts = "$$('.version')[4].querySelector('select')"
    assert run_js(dlg, f"{starts}.value") == "after"
    assert run_js(dlg, f"{starts}.selectedOptions[0].textContent") == "When Night is fully in"
    run_js(dlg, f"{day_scene}.versions[4].image = 'dawn.png'; {day_scene}.versions[4].label = 'Midnight'; changed(true)")
    night_full = "(() => { const n = S.marks.find(m => m.index === 3); return (n.start + n.fade) % 1440; })()"
    midnight = "(S.marks.find(m => m.index === 4) || {}).start"
    until(app, lambda: run_js(dlg, midnight) is not None, 5, "the new version has no time")
    assert run_js(dlg, midnight) == run_js(dlg, night_full)
    # A wait after Night: no rebuild, and the time follows.
    run_js(dlg, "const w = $('.version .wait input'); w.focus(); setv(w, '15')")
    until(app, lambda: run_js(dlg, midnight) == (run_js(dlg, night_full) + 15) % 1440, 5, "the wait didn't move it")
    assert run_js(dlg, "document.activeElement === $('.version .wait input')"), "the wait box lost its focus"
    # Renaming Night renames the option below it at once.
    run_js(dlg, "const n = $$('.version input.label')[3]; n.value = 'Late night'; n.dispatchEvent(new Event('input'))")
    assert run_js(dlg, f"{starts}.selectedOptions[0].textContent") == "When Late night is fully in"
    run_js(dlg, "const n = $$('.version input.label')[3]; setv(n, 'Night')")
    shoot(dlg, "scene-follows")
    run_js(dlg, "$$('.version')[4].querySelector('[aria-label=\"Remove version\"]').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 4, 5)
    print("PASS: a new version starts as the one above is fully in, plus a wait, with no time to set.")

    # A narrow window: each version takes two lines, so its dropdowns keep their width.
    row = """(() => { const v = $$('.version')[0], name = v.querySelector('input.label').getBoundingClientRect();
        const sel = [...v.querySelectorAll('select')].map(s => s.getBoundingClientRect());
        return { twoLines: sel[0].top >= name.bottom, widths: sel.map(r => Math.round(r.width)),
                 overflow: Math.max(...$$('.versions *').map(e => e.getBoundingClientRect().right))
                           - $('.versions').getBoundingClientRect().right }; })()"""
    dlg.resize(800, 780)
    until(app, lambda: run_js(dlg, row)["twoLines"], 5, "versions stay on one line in a narrow window")
    narrow = run_js(dlg, row)
    assert min(narrow["widths"]) >= 170 and narrow["overflow"] <= 0, narrow
    shoot(dlg, "versions-narrow")
    dlg.resize(1100, 780)
    until(app, lambda: not run_js(dlg, row)["twoLines"], 5, "versions stay on two lines in a wide window")
    assert run_js(dlg, row)["overflow"] <= 0
    print("PASS: in a narrow window each version takes two lines, and its dropdowns keep their width.")

    # The preview keeps the shape of Anki's main window however wide the dialog is.
    shape = """(() => { const r = $('.preview').getBoundingClientRect();
        return { ratio: (r.width / r.height) / (S.window[0] / S.window[1]), share: r.height / innerHeight }; })()"""
    for width, height in ((1100, 780), (1800, 1000)):
        dlg.resize(width, height)
        pump(app, 0.6)
        got = run_js(dlg, shape)
        assert abs(got["ratio"] - 1) < 0.02 and got["share"] < 0.5, (width, got)
    dlg.resize(1100, 780)
    pump(app, 0.4)
    print("PASS: the scene preview has the main window's shape at any dialog size.")

    # Delete scene asks first, with focus on the safe answer; No keeps the scene.
    count = run_js(dlg, "draft.scenes.length")
    run_js(dlg, "$('#deleteScene').click()")
    until(app, lambda: run_js(dlg, "!!$('#confirmYes')"), 5, "Delete scene didn't ask")
    assert run_js(dlg, "document.activeElement.id") == "confirmNo"
    run_js(dlg, "$('#confirmNo').click()")
    assert run_js(dlg, "draft.scenes.length") == count and run_js(dlg, "!$('#modal').firstChild")
    # A confirmation stacks over the picture picker; Esc takes off only the top one.
    run_js(dlg, "$$('.version .pick')[0].click()")
    until(app, lambda: run_js(dlg, "!!$('.tile')"), 5)
    assert run_js(dlg, """(() => { const b = $('.ribbon').getBoundingClientRect();
        return document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2).closest('.overlay') !== null; })()"""), \
        "the timeline takes clicks through the picture picker"
    run_js(dlg, "confirmDialog({ title: 'Stacked?' })")
    assert run_js(dlg, "$$('#modal .overlay').length") == 2
    run_js(dlg, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    assert run_js(dlg, "$$('#modal .overlay').length") == 1 and run_js(dlg, "!!$('.tile')")
    run_js(dlg, "$('#modal .dialog-foot button').click()")
    assert run_js(dlg, "!$('#modal').firstChild")
    print("PASS: deleting asks first, and a confirmation stacks over the picture picker.")

    # Lining up a scene's pictures: one drag moves them all, until that's turned off.
    run_js(dlg, "window._window = S.window; S.window = [2.4, 1]; "   # a wide window: every picture crops
                "Element.prototype.setPointerCapture = () => {}")    # synthetic pointers can't be captured
    drag = ("(() => { const b = $('.focus-box'), r = b.getBoundingClientRect(); "
            "const ev = (t) => b.dispatchEvent(new PointerEvent(t, { bubbles: true, pointerId: 1, "
            "clientX: r.x + r.width / 2, clientY: r.y + r.height * %s })); ev('pointerdown'); ev('pointerup'); })()")
    ys = "['dawn', 'day', 'dusk', 'night'].map(n => (draft.images[n + '.png'] || { y: 50 }).y)"
    run_js(dlg, "$$('.version .pick')[1].click()")
    until(app, lambda: run_js(dlg, "!!$('#alignPictures') && !$('.align').hidden"), 5, "no line-up option in the picker")
    assert run_js(dlg, "$('#alignPictures').checked"), "untouched pictures aren't shown as lined up"
    assert run_js(dlg, "$$('.mini').length") == 3
    # Selecting another version's picture still shows every other version.
    run_js(dlg, "$$('.tile').find(t => t.title === 'dawn.png').click()")
    assert run_js(dlg, "$$('.mini-label').map(l => l.textContent)") == ["Dawn", "Dusk", "Night"]
    run_js(dlg, "$$('.tile').find(t => t.title === 'day.png').click()")
    run_js(dlg, drag % "0.02")
    assert run_js(dlg, ys) == [0, 0, 0, 0], run_js(dlg, ys)
    until(app, lambda: run_js(dlg, "$$('.mini .crop-frame').every(f => f.style.top === '0%')"), 5,
          "the small frames didn't follow")
    shoot(dlg, "picker-aligned")
    run_js(dlg, "$('#alignPictures').click()")
    assert run_js(dlg, "draft.scenes.find(s => s.kind === 'day').aligned") is False
    run_js(dlg, drag % "0.98")
    assert run_js(dlg, ys) == [0, 100, 0, 0], run_js(dlg, ys)
    run_js(dlg, "$('#modal .dialog-foot button').click()")
    # Reopened: positions differ, so it isn't ticked; ticking lines the others up with this one.
    run_js(dlg, "$$('.version .pick')[1].click()")
    until(app, lambda: run_js(dlg, "!!$('#alignPictures')"), 5)
    assert not run_js(dlg, "$('#alignPictures').checked"), "shown as lined up while the pictures differ"
    run_js(dlg, "$('#alignPictures').click()")
    assert run_js(dlg, ys) == [100, 100, 100, 100], run_js(dlg, ys)
    assert run_js(dlg, "!('aligned' in draft.scenes.find(s => s.kind === 'day'))")
    run_js(dlg, "$('#modal .dialog-foot button').click(); S.window = window._window")
    print("PASS: a day cycle's pictures move together in the picker, and can be set apart.")

    # Use the day cycle while studying, then save.
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    run_js(dlg, "byText('label', 'Scenes of its own').querySelector('input').click()")
    run_js(dlg, "const sel = $$('select[aria-label=\"Add a scene\"]')[1]; setv(sel, [...sel.options].find(o => o.text === 'Day cycle').value)")
    run_js(dlg, "$('#save').click()")
    until(app, lambda: run_js(dlg, "$('#status').textContent") == "Saved", 5, "save didn't finish")
    pump(app, 0.3)
    assert dlg.isVisible(), "Save closed the window"
    cfg = mw.addonManager.getConfig("keshiki")
    day_id = next(s["id"] for s in cfg["scenes"] if s["kind"] == "day")
    assert cfg["screens"]["study"] == dict(cfg["screens"]["study"], same_as_main=False, scenes=[day_id]), cfg["screens"]
    assert len(cfg["screens"]["main"]["scenes"]) == 1 and renderer.preview is None
    shoot(dlg, "screens-saved")
    assert run_js(dlg, "(() => { const [a, b] = $$('.two > .panel'); return Math.abs(a.offsetHeight - b.offsetHeight) <= 1; })()"), \
        "Deck list and Studying panels differ in height"
    print("PASS: save writes the config, keeps the window open and ends the live preview.")

    # A screen's scenes, and an album's pictures, take turns: the deck list (an album of four)
    # can shuffle; studying, with one day cycle, says how, and shuffles once it has the album too.
    main_card, study_card = "$$('.two > .panel')[0]", "$$('.two > .panel')[1]"
    assert run_js(dlg, f"!!{main_card}.querySelector('select.shuffle')")
    assert run_js(dlg, f"!{study_card}.querySelector('select.shuffle') && !!{study_card}.querySelector('.shuffle-hint')")
    run_js(dlg, f"const a = {study_card}.querySelector('select[aria-label=\"Add a scene\"]'); "
                "setv(a, [...a.options].find(o => o.text === 'Album').value)")
    until(app, lambda: run_js(dlg, "draft.screens.study.scenes.length") == 2, 5, "the album didn't join studying")
    assert run_js(dlg, f"!{study_card}.querySelector('.add-images')"), "screens add scenes, not images"
    assert run_js(dlg, f"!!{study_card}.querySelector('select.shuffle')"), "no shuffle with two scenes"
    assert run_js(dlg, "draft.screens.main.scenes.length") == 1
    assert run_js(dlg, "!$('.combine')"), "combining belongs on the Scenes page"
    shoot(dlg, "screens-shuffle")
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: run_js(dlg, "draft.screens.study.scenes.length") == 1, 5)
    print("PASS: each screen shows its shuffle once it has more than one turn.")

    # Single pictures combine into an album on the Scenes page: the ticked ones go in, and a
    # screen that showed them shows the album where the first one was.
    run_js(dlg, """(async () => { for (const image of ['dawn.png', 'dusk.png', 'day.png']) {
        const sc = await call('new_scene', { kind: 'single', image }); draft.scenes.push(sc);
        if (image !== 'day.png') draft.screens.main.scenes.push(sc.id); } changed(true); })()""")
    until(app, lambda: run_js(dlg, "draft.scenes.filter(s => s.kind === 'single').length") == 3, 5)
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    until(app, lambda: run_js(dlg, "!!$('#combine')"), 5, "no Combine with three single pictures")
    run_js(dlg, "$('#combine').click()")
    until(app, lambda: run_js(dlg, "$$('.combine-list input').length") == 3, 5, "the dialog doesn't list them")
    assert run_js(dlg, "$('#combineGo').textContent") == "Combine 3 pictures"
    run_js(dlg, "$$('.combine-list input')[2].click(); setv($('.combine-dialog input.album-name'), 'Stills')")
    assert run_js(dlg, "$('#combineGo').textContent") == "Combine 2 pictures"
    shoot(dlg, "combine-dialog")
    run_js(dlg, "$('#combineGo').click()")
    until(app, lambda: run_js(dlg, "!!draft.scenes.find(s => s.name === 'Stills')"), 5, "Combine didn't make the album")
    stills = "draft.scenes.find(s => s.name === 'Stills')"
    assert run_js(dlg, f"{stills}.versions.map(v => v.image)") == ["dawn.png", "dusk.png"]
    assert run_js(dlg, "draft.scenes.filter(s => s.kind === 'single').map(s => s.versions[0].image)") == ["day.png"]
    assert run_js(dlg, "draft.screens.main.scenes.map(id => sceneById(id).name)") == ["Album", "Stills"]
    assert run_js(dlg, "!$('#combine')"), "Combine stays with one single picture left"
    shoot(dlg, "combined")
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: run_js(dlg, "!draft.scenes.find(s => s.name === 'Stills')"), 5)
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    print("PASS: single pictures combine into an album on the Scenes page, in place on the screens that showed them.")

    # A folder as an album, linked: its pictures are read from the folder through a link,
    # served by Anki's media server, and follow the folder on a rescan.
    from keshiki.keshiki import library
    wall = base / "Wallpapers"
    (wall / "trip").mkdir(parents=True)
    for name, hue in (("lake.png", 100), ("hills.png", 40), ("trip/coast.png", 190)):
        make_test_image(wall / name, hue)
    dlg.kiso_bridge.pick_folder = lambda: str(wall)
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    run_js(dlg, "$('#addFolder').click()")
    until(app, lambda: run_js(dlg, "($('.folder-count') || {}).textContent") == "3 pictures", 5, "the folder dialog didn't count")
    run_js(dlg, "$('#folderSubfolders').click()")
    until(app, lambda: run_js(dlg, "$('.folder-count').textContent") == "2 pictures", 5, "subfolders didn't change the count")
    run_js(dlg, "$('#folderSubfolders').click()")
    until(app, lambda: run_js(dlg, "$('.folder-count').textContent") == "3 pictures", 5)
    shoot(dlg, "folder-dialog")
    run_js(dlg, "$('#addFolderGo').click()")
    album = "draft.scenes.find(s => s.name === 'Wallpapers')"
    until(app, lambda: run_js(dlg, f"!!{album}"), 5, "the folder didn't become an album")
    link = run_js(dlg, f"{album}.folder.link")
    assert run_js(dlg, f"{album}.versions.map(v => v.image)") == [f"@{link}/hills.png", f"@{link}/lake.png",
                                                                  f"@{link}/trip/coast.png"]
    assert (library.FOLDERS / link).is_symlink(), "no link to the folder"
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5)
    run_js(dlg, f"(() => {{ window._st = null; fetch(imageUrl({album}.versions[2].image))"
                ".then(r => { window._st = r.status; }); })()")
    until(app, lambda: run_js(dlg, "window._st") is not None, 5)
    assert run_js(dlg, "window._st") == 200, "Anki's media server didn't serve the linked picture"
    assert run_js(dlg, "!$('.album-add') && $('.album-tile .remove').title.startsWith('Hide')"), \
        "a folder's pictures are added in the folder, and only hidden here"
    make_test_image(wall / "dunes.png", 30)
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5, "Rescan didn't pick up the new picture")
    run_js(dlg, "$('#albumSubfolders').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5, "subfolders stayed in")
    # Hiding a picture leaves it in the folder and out of the album, through rescans; Show brings it back.
    run_js(dlg, "$$('.album-tile .remove')[0].click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 2, 5, "Hide didn't take it out")
    assert run_js(dlg, f"{album}.folder.hidden") == [f"@{link}/dunes.png"] and (wall / "dunes.png").is_file()
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "$$('.hidden-tile').length") == 1, 5)
    assert run_js(dlg, "$$('.album-tile').length") == 2, "a rescan brought a hidden picture back"
    shoot(dlg, "folder-album")
    run_js(dlg, "$('.hidden-tile .show').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5, "Show didn't bring it back")
    assert run_js(dlg, "!$('.hidden-row')") and run_js(dlg, f"{album}.versions[0].image") == f"@{link}/dunes.png"
    # A folder that's gone keeps its last pictures and says so.
    wall.rename(base / "Wallpapers-away")
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "!!$('.folder-missing')"), 5, "no warning for a missing folder")
    assert run_js(dlg, "$$('.album-tile').length") == 3
    (base / "Wallpapers-away").rename(wall)
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "!$('.folder-missing')"), 5)
    # Saved, the link stays; the album deleted and saved, the link goes and the folder stays whole.
    run_js(dlg, "$('#save').click()")
    until(app, lambda: run_js(dlg, "$('#status').textContent") == "Saved", 5)
    assert (library.FOLDERS / link).is_symlink()
    run_js(dlg, "byText('.scene-item span', 'Wallpapers').parentElement.click()")
    run_js(dlg, "$('#deleteScene').click()")
    until(app, lambda: run_js(dlg, "!!$('#confirmYes')"), 5)
    run_js(dlg, "$('#confirmYes').click()")
    run_js(dlg, "$('#save').click()")
    until(app, lambda: run_js(dlg, "$('#status').textContent") == "Saved", 5)
    assert not (library.FOLDERS / link).exists(), "the unused link stayed"
    assert sorted(p.name for p in wall.rglob("*.png")) == ["coast.png", "dunes.png", "hills.png", "lake.png"]
    print("PASS: a linked folder's pictures are served live, follow rescans, can be hidden, survive a "
          "missing folder, and dropping the album removes only the link.")

    # A folder copied once: an ordinary album of the copied pictures.
    run_js(dlg, "$('#addFolder').click()")
    until(app, lambda: run_js(dlg, "($('.folder-count') || {}).textContent") == "4 pictures", 5)
    run_js(dlg, "byText('label', 'Copy the pictures now').querySelector('input').click(); $('#addFolderGo').click()")
    until(app, lambda: run_js(dlg, f"!!{album}"), 5, "the copied folder didn't become an album")
    assert run_js(dlg, f"!{album}.folder && {album}.versions.every(v => !v.image.startsWith('@'))")
    assert {"lake.png", "coast.png"} <= {p.name for p in library.IMAGES.iterdir()}
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: run_js(dlg, f"!{album}"), 5)
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    print("PASS: a folder copied once becomes an ordinary album.")

    # The picture library: unused pictures go to the trash, come back, or go for good.
    from keshiki.keshiki import library as lib
    spares = [str(make_test_image(base / f"spare{i}.png", 60 + 40 * i)) for i in (1, 2)]
    dlg.kiso_bridge.pick_files = lambda: spares
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    run_js(dlg, "(async () => { const r = await call('import'); images = r.images; })()")
    until(app, lambda: run_js(dlg, "images.some(i => i.name === 'spare2.png')"), 5)
    dlg.kiso_bridge.pick_files = lambda: files
    run_js(dlg, "$('#openLibrary').click()")
    until(app, lambda: run_js(dlg, "!!$('.library-dialog')"), 5, "no picture library")
    unused = run_js(dlg, "$$('.lib-tile').filter(t => t.querySelector('.lib-action')).map(t => t.title)")
    assert {"spare1.png", "spare2.png"} <= set(unused) and "dawn.png" not in unused, unused
    shoot(dlg, "library")
    run_js(dlg, "$('#trashUnused').click()")
    until(app, lambda: run_js(dlg, "trashed.length") == len(unused), 5, "the unused pictures didn't go to the trash")
    assert not (lib.IMAGES / "spare1.png").exists() and (lib.TRASH / "spare1.png").exists()
    assert run_js(dlg, "$('#tab-trash').textContent") == f"Trash · {len(unused)}"
    run_js(dlg, "$('#tab-trash').click()")
    until(app, lambda: run_js(dlg, "$$('.lib-tile').length") == len(unused), 5)
    shoot(dlg, "library-trash")
    run_js(dlg, "$$('.lib-tile').find(t => t.title === 'spare1.png').querySelector('.lib-action').click()")
    until(app, lambda: (lib.IMAGES / "spare1.png").exists(), 5, "Restore didn't bring it back")
    run_js(dlg, "$('#emptyTrash').click()")
    until(app, lambda: run_js(dlg, "!!$('#confirmYes')"), 5, "Empty trash didn't ask")
    run_js(dlg, "$('#confirmYes').click()")
    until(app, lambda: run_js(dlg, "trashed.length") == 0, 5, "the trash didn't empty")
    assert not (lib.TRASH / "spare2.png").exists() and (lib.IMAGES / "spare1.png").exists()
    run_js(dlg, "$('.library-dialog .dialog-foot .primary').click(); byText('#nav button', 'Screens').click()")
    print("PASS: unused pictures go to the trash, come back from it, or are deleted for good after asking.")

    # Cancel drops unsaved edits and keeps the window open.
    run_js(dlg, "setv($$('input[aria-label=Blur]')[0], '12')")
    until(app, lambda: run_js(dlg, "!$('#cancel').disabled"), 5)
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: run_js(dlg, "$$('input[aria-label=Blur]')[0].value") == "0", 5, "Cancel didn't drop the edit")
    pump(app, 0.3)
    assert dlg.isVisible() and run_js(dlg, "$('#cancel').disabled && $('#save').disabled")
    until(app, lambda: renderer.preview is None, 5, "Cancel left the preview in the main window")
    print("PASS: Cancel drops unsaved edits without closing.")

    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    run_js(dlg, "byText('label', 'The sun where I am').querySelector('input').click()")
    # Nothing is looked up until the button is pressed.
    pump(app, 0.5)
    assert run_js(dlg, "$('.locate span').textContent") == "Not set yet", "location was looked up without asking"
    run_js(dlg, "$('#locate').click()")
    until(app, lambda: run_js(dlg, "$('.locate span').textContent") == "Near Tokyo, Japan", 5, "location wasn't looked up")
    assert run_js(dlg, "$('[data-field=latitude]').value + ',' + $('[data-field=longitude]').value") == "35.68,139.65"
    until(app, lambda: "sunrise" in run_js(dlg, "$('.panel .help').textContent"), 5, "sun times didn't show")
    assert run_js(dlg, "$('#locate').textContent") == "Find again"
    shoot(dlg, "day")
    print("PASS: the Day & time page looks up a rough location once and works out today's sun.")

    # Per-page Revert and Restore: only that page changes, and only in the draft.
    assert run_js(dlg, "!!$('#revertPage') && !!byText('#nav button', 'Day & time').querySelector('.dot')")
    run_js(dlg, "$('#revertPage').click()")
    until(app, lambda: run_js(dlg, "byText('label', 'Times I set').querySelector('input').checked"), 5, "Revert didn't undo the page")
    assert run_js(dlg, "!$('#revertPage') && !byText('#nav button', 'Day & time').querySelector('.dot') && $('#save').disabled")
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    run_js(dlg, "setv($$('input[aria-label=Dim]')[0], '60')")
    until(app, lambda: run_js(dlg, "!!$('#restorePage')"), 5, "no Restore defaults after changing dim")
    run_js(dlg, "$('#restorePage').click()")
    until(app, lambda: run_js(dlg, "$$('input[aria-label=Dim]')[0].value") == "15", 5, "Restore didn't reset dim")
    assert run_js(dlg, "$$('.chip').length") == 2, "Restore dropped the chosen scenes"
    assert mw.addonManager.getConfig("keshiki")["screens"]["main"]["dim"] == 15
    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    run_js(dlg, "byText('label', 'The sun where I am').querySelector('input').click()")
    print("PASS: Revert and Restore defaults change only their own page.")

    # Unsaved edits ask before closing; Discard drops the preview.
    dlg.reject()
    until(app, lambda: run_js(dlg, "!!byText('h2', 'Save your changes?')"), 5, "close didn't ask about unsaved edits")
    run_js(dlg, "byText('button', 'Discard').click()")
    until(app, lambda: not dlg.isVisible(), 5)
    assert renderer.preview is None
    print("PASS: closing with unsaved edits asks first, and Discard drops them.")

    from aqt.theme import Theme
    mw.set_theme(Theme.DARK)
    pump(app, 0.5)
    dlg = open_page()
    run_js(dlg, "byText('#nav button', 'Scenes').click(); byText('.scene-item span', 'Day cycle').parentElement.click()")
    shoot(dlg, "scene-day-dark")
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    shoot(dlg, "screens-dark")
    dlg.reject()
    if shots:
        pump(app, 2.5)
        mw.form.centralwidget.grab().save(str(shots / "main-dark.png"))


if __name__ == "__main__":
    run(check, __doc__)
