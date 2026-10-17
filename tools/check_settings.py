"""Real-Anki check of the settings page: first-run flow, a day-cycle scene,
live preview in the main window, save, and screenshots of each page."""

import json
import os

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
        dlg.kiso_bridge.in_background = lambda fn, done, **_: done(
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

    # The album on the Scenes page: its pictures as tiles. It opens on the picture Anki's window
    # shows now (marked Active), not shown in Anki's window as a moment; a tile clicked shows in the
    # preview and in Anki's window; its crop button opens the crop; Set as active image makes the
    # previewed one the album's picture on screen; × takes one out.
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5, "the album's pictures aren't tiles")
    assert run_js(dlg, "$('.editor .kind').textContent") == "Album · 4 pictures"
    assert run_js(dlg, "!$('.ribbon') && !$('#play')"), "an album has no timeline"
    previewed = ("$$('.preview .keshiki-layer').filter(e => !e.dataset.leaving)"
                 ".map(e => e.dataset.src.split('/').pop())")
    until(app, lambda: run_js(dlg, "$$('.album-tile .now-badge').length") == 1, 5, "no Active on the picture showing")
    showing = renderer.shown["layers"][0]["image"]
    assert run_js(dlg, "$('.album-tile.shown .now-badge') && draft.scenes[0].versions[albumShown].image") == showing
    until(app, lambda: run_js(dlg, previewed) == [showing], 5, "the album didn't open on the picture showing now")
    assert run_js(dlg, "$('#showNow').disabled"), "Set as active image offered for the picture already showing"
    assert run_js(dlg, "$('#showNow').textContent") == "Set as active image"
    assert renderer.scene_look is None, "opening the album showed a moment in Anki's window"
    other = 2 if showing != "dusk.png" else 1
    want = run_js(dlg, f"draft.scenes[0].versions[{other}].image")
    run_js(dlg, f"$$('.album-tile .pick')[{other}].click()")
    until(app, lambda: run_js(dlg, previewed) == [want], 5, "the preview doesn't show the tile's picture")
    until(app, lambda: [x["image"] for x in (renderer.scene_look or {}).get("layers", [])] == [want], 5,
          "a clicked tile didn't show in Anki's window")
    assert run_js(dlg, "!$('#modal .dialog')"), "clicking a tile opened a dialog"
    assert run_js(dlg, "!$('.album-tile .adjust')"), "a crop button on the tiles"
    run_js(dlg, "$('#adjustCrop').click()")
    until(app, lambda: run_js(dlg, "!!$('.position-dialog')"), 5, "Adjust crop... didn't open the crop")
    run_js(dlg, "$('.position-dialog .primary').click()")
    run_js(dlg, "$('#showNow').click()")
    until(app, lambda: (renderer.chosen or {}).get("image") == want, 5, "Set as active image didn't reach Anki's window")
    until(app, lambda: run_js(dlg, f"!!$$('.album-tile')[{other}].querySelector('.now-badge') && $('#showNow').disabled"), 5,
          "the Active mark didn't move")
    assert run_js(dlg, "$('.now-note').textContent").startswith("Active on the deck list"), \
        run_js(dlg, "$('.now-note').textContent")
    shoot(dlg, "album-now")
    # Taking a picture out renumbers the rest: Set as active image still picks the one previewed,
    # even before Anki's window has the edit.
    removed = run_js(dlg, "draft.scenes[0].versions[0].image")
    run_js(dlg, "$$('.album-tile .remove')[0].click()")
    names = run_js(dlg, "draft.scenes[0].versions.map(v => v.image)")
    pick = next(i for i in range(len(names) - 1, -1, -1) if names[i] != renderer.chosen["image"])
    run_js(dlg, f"$$('.album-tile .pick')[{pick}].click(); $('#showNow').click()")
    until(app, lambda: renderer.chosen["image"] == names[pick], 5,
          f"Set as active image chose {renderer.chosen['image']}, not {names[pick]}")
    until(app, lambda: run_js(dlg, f"!!$$('.album-tile')[{pick}].querySelector('.now-badge')"), 5, "Active isn't on it")
    run_js(dlg, f"draft.scenes[0].versions.unshift({{ label: '', image: {removed!r} }}); changed(true)")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5)
    # The cause of that once: a look asked for while a new stage's first fade waits for its first
    # frame wins; the waiting one is dropped, not laid over it afterwards.
    run_js(dlg, """(() => { const box = document.createElement('div'); document.body.append(box); window._stBox = box;
        const st = new keshiki.Stage(box, false);
        const look = (name) => ({ layers: [{ src: imageUrl(name), opacity: 1 }], dim: 0, blur: 0, fade: 300 });
        st.apply(look('dawn.png'), false); st.apply(look('dusk.png'), true); })()""")
    pump(app, 0.8)
    assert run_js(dlg, "[..._stBox.querySelectorAll('.keshiki-layer')].filter(e => !e.dataset.leaving)"
                       ".map(e => e.dataset.src.split('/').pop())") == ["dusk.png"], "a look waiting for a frame won"
    run_js(dlg, "_stBox.remove()")
    run_js(dlg, "$$('.album-tile .remove')[3].click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5)
    run_js(dlg, "const a = draft.scenes[0]; a.versions.push({ label: '', image: 'night.png' }); changed(true)")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5)
    # A long album: scrolled down to its last tiles, the preview and its buttons stay in view,
    # and a tile chosen there shows in it with the tiles left where they were.
    run_js(dlg, "const a = draft.scenes[0]; for (let i = 0; i < 40; i++) a.versions.push({ label: '', image: "
                "['dawn.png', 'day.png', 'dusk.png', 'night.png'][i % 4] }); changed(true)")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 44, 5)
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    pump(app, 0.4)
    last = run_js(dlg, "$$('.album-tile').length - 2")
    want = run_js(dlg, f"draft.scenes[0].versions[{last}].image")
    top = run_js(dlg, "$('main').scrollTop")
    run_js(dlg, f"$$('.album-tile .pick')[{last}].click()")
    until(app, lambda: run_js(dlg, previewed) == [want], 5, "the preview doesn't show the tile chosen down the album")
    assert run_js(dlg, "$('main').scrollTop") == top > 0, "choosing a tile moved the tiles"
    assert run_js(dlg, """(() => { const m = $('main').getBoundingClientRect(), inView = (e) => { const r = e.getBoundingClientRect();
        return r.top >= m.top - 1 && r.bottom <= m.bottom + 1
               && document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('.album-stage') !== null; };
        return inView($('.album-stage .preview')) && inView($('#showNow')) && inView($('#adjustCrop')); })()"""), \
        "the album's preview and buttons scrolled away"
    shoot(dlg, "album-scrolled")
    run_js(dlg, "draft.scenes[0].versions.splice(4); albumShown = 0; changed(true); $('main').scrollTop = 0")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 4, 5)
    # Not on any screen: Set as active image says why it can't.
    run_js(dlg, "window._mainScenes = draft.screens.main.scenes; draft.screens.main.scenes = []; changed(true)")
    until(app, lambda: run_js(dlg, "$('#showNow').disabled && $('.now-note').textContent.includes('use this album on a screen')"),
          5, "no reason given for Set as active image being off")
    run_js(dlg, "draft.screens.main.scenes = window._mainScenes; changed(true)")
    until(app, lambda: run_js(dlg, "$('.now-note').textContent") != "" and not run_js(
        dlg, "$('.now-note').textContent.includes('use this album')"), 5)
    shoot(dlg, "album")
    # The clicked tile's moment lasts while the Scenes page shows.
    assert renderer.scene_look is not None
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    until(app, lambda: renderer.scene_look is None, 5, "leaving Scenes kept the album's picture in Anki's window")
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    print("PASS: an album opens on the picture showing now (marked Active); a tile previews, in Anki's window too, "
          "Adjust crop... opens the crop, Set as active image puts it on screen (or says why it can't), both stay in "
          "view down a long album, and × takes one out.")

    # A day cycle from the template, one image per version.
    run_js(dlg, "byText('#nav button', 'Scenes').click()")
    run_js(dlg, "$('#addDay').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 4, 5, "day cycle template missing")
    for i, name in enumerate(["dawn", "day", "dusk", "night"]):
        run_js(dlg, f"$$('.version .pick')[{i}].click()")
        until(app, lambda: run_js(dlg, "!!$('.tile')"), 5)
        run_js(dlg, f"$$('.tile').find(t => t.title === '{name}.png').click(); byText('button', 'Use image').click()")
    until(app, lambda: run_js(dlg, "$$('.ribbon .seg').length") >= 4, 5, "ribbon didn't draw")
    # Versions start and finish at named moments of the sun, with today's times.
    # The dropdowns name the rule; today's time it makes is on the line under each.
    until(app, lambda: run_js(dlg, "$$('.version select')[0].selectedOptions[0].textContent") == "First light",
          5, "the dawn version doesn't start at First light")
    assert run_js(dlg, "$$('.version select')[1].selectedOptions[0].textContent") == "Sunrise"
    until(app, lambda: run_js(dlg, "$('.version .when-start').textContent").startswith("Today, "), 5, "no time under the rule")
    assert run_js(dlg, "/^Today, \\d\\d:\\d\\d$/.test($('.version .when-end').textContent)")
    assert run_js(dlg, "!$('.versions').textContent.includes('°')"), "sun degrees still show"
    assert run_js(dlg, "$$('.vhead span').map(s => s.textContent)") == ["Version", "Transition starts", "Transition ends"]
    assert run_js(dlg, "$('#playSpeed').selectedOptions[0].textContent") == "24 h in 10 s"
    # Scrub to 13:00: the preview shows the day image alone.
    run_js(dlg, "setv($('.ribbon input'), 780)")
    until(app, lambda: run_js(dlg, "$('.preview .readout').textContent") == "Preview, 13:00", 5)
    until(app, lambda: run_js(dlg, "$$('.preview .keshiki-layer').filter(e => !e.dataset.leaving).map(e => e.dataset.src.split('/').pop())")
          == ["day.png"], 5, "preview at 13:00 isn't the day image")
    shoot(dlg, "scene-day")
    print("PASS: a day cycle scene previews along its ribbon.")

    # Working on a version shows it at the moment it's fully in, the end of its row's times
    # (dusk: the setting sun from +12° to the horizon, a few minutes before the 19:30 sunset).
    run_js(dlg, "$$('.version .vname')[2].focus()")
    until(app, lambda: run_js(dlg, "$('.preview .readout').textContent") ==
          run_js(dlg, "(() => { const m = S.marks.find(m => m.index === 2); return 'Preview, ' + hhmm(m.start + m.fade); })()"),
          5, "focusing a version didn't preview it")
    fully_in = run_js(dlg, "$('.preview .readout').textContent")
    assert "19:2" in fully_in, fully_in
    until(app, lambda: run_js(dlg, "$$('.version.showing').map(r => r.dataset.index)") == ["2"], 5,
          "the version showing isn't marked")
    # Timelapse: the button is on top (not covered by the picture), plays the whole day and stops at the end.
    run_js(dlg, "$('main').scrollTop = 0")   # focusing the version scrolled to it
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
    # A shared CI runner draws only a few frames a second (Windows' about 5), and frame timing
    # there is too uneven for the dark-flash test: a slow frame can catch a picture mid-fade. It
    # runs locally, where a real dark flash shows; on CI the frames only show that it sampled.
    assert len(frames) > (10 if os.environ.get("CI") else 50), f"only {len(frames)} frames sampled"
    darkest = min(f["cover"] for f in frames)
    assert os.environ.get("CI") or darkest > 0.97, f"the timelapse flashes dark: coverage fell to {darkest:.2f}: " + \
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
    # Scrolled down, the scene list and its New scene buttons stay in view.
    assert run_js(dlg, """(() => { const m = $('main').getBoundingClientRect(), b = $('#addDay').getBoundingClientRect();
        return b.top >= m.top && b.bottom <= m.bottom; })()"""), "the scene list scrolled away with the editor"
    pump(app, 1)   # what the steps before set going has settled (a slow machine takes a while)
    run_js(dlg, "const t = $('.version input[type=time]'); t.focus(); setv(t, '22:15')")
    pump(app, 0.4)
    assert run_js(dlg, "document.activeElement === $('.version input[type=time]')"), \
        "the time box lost its focus: " + str(run_js(dlg, "[document.activeElement.outerHTML.slice(0, 120), "
                                                     "!!$('.version input[type=time]'), document.hasFocus()]"))
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

    # A new version follows the last: it starts after Night's transition ends, with no time to
    # set, and opens with its name box.
    day_scene = "draft.scenes.find(s => s.kind === 'day')"
    run_js(dlg, "byText('button', '+ Add version').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 5, 5)
    starts = "$$('.version')[4].querySelector('select')"
    assert run_js(dlg, f"{starts}.value") == "after"
    assert run_js(dlg, f"{starts}.selectedOptions[0].textContent") == "After Night's transition ends"
    until(app, lambda: run_js(dlg, "document.activeElement === $$('.version')[4].querySelector('input.label')"), 5,
          "a new version's name box isn't open")
    run_js(dlg, f"{day_scene}.versions[4].image = 'dawn.png'; {day_scene}.versions[4].label = 'Midnight'; changed(true)")
    night_full = "(() => { const n = S.marks.find(m => m.index === 3); return (n.start + n.fade) % 1440; })()"
    midnight = "(S.marks.find(m => m.index === 4) || {}).start"
    until(app, lambda: run_js(dlg, midnight) is not None, 5, "the new version has no time")
    assert run_js(dlg, midnight) == run_js(dlg, night_full)
    # A delay after Night: no rebuild, and the time follows.
    run_js(dlg, "const w = $('.version .wait input'); w.focus(); setv(w, '15')")
    until(app, lambda: run_js(dlg, midnight) == (run_js(dlg, night_full) + 15) % 1440, 5, "the wait didn't move it")
    assert run_js(dlg, "document.activeElement === $('.version .wait input')"), "the wait box lost its focus"
    # A version's name is a heading; Rename opens a box. Typing renames the option below at once,
    # Escape puts the old name back, and Enter keeps the new one.
    assert run_js(dlg, "$$('.version')[4].querySelector('.vname').textContent") == "Midnight"
    # Real key presses: Escape in the box is the box's, and doesn't go on to close the window.
    from aqt.qt import Qt
    from PyQt6.QtTest import QTest
    name_box = "$$('.version')[3].querySelector('input.label')"
    for finish, label in ((Qt.Key.Key_Escape, "Night"), (Qt.Key.Key_Return, "Late night")):
        run_js(dlg, "$$('.version .vname')[3].click()")
        until(app, lambda: run_js(dlg, f"document.activeElement === {name_box}"), 5, "Rename didn't open the name box")
        run_js(dlg, f"const n = {name_box}; n.value = 'Late night'; n.dispatchEvent(new Event('input'))")
        assert run_js(dlg, f"{starts}.selectedOptions[0].textContent") == "After Late night's transition ends"
        dlg.activateWindow()
        QTest.keyClick(dlg.kiso_web.focusProxy() or dlg.kiso_web, finish)
        until(app, lambda: run_js(dlg, f"!{name_box}"), 5, f"{label}: the name box stayed open")
        pump(app, 0.3)
        assert dlg.isVisible() and run_js(dlg, "!$('#modal').firstChild"), "Escape went on to the window"
        assert run_js(dlg, "$$('.version .vname')[3].textContent") == label, label
        assert run_js(dlg, f"{day_scene}.versions[3].label") == label, finish
        assert run_js(dlg, f"{starts}.selectedOptions[0].textContent") == f"After {label}'s transition ends"
    run_js(dlg, f"{day_scene}.versions[3].label = 'Night'; changed(true)")
    # Its rule and delay under Transition starts; its length under its own label, Transition
    # duration, with the end it makes under it; the two times on one line along the bottom.
    lines = run_js(dlg, """(() => { const v = $$('.version')[4], r = (s) => v.querySelector(s).getBoundingClientRect();
        return { rule: r('.c-start select').top, wait: r('.c-start .wait input').top, length: r('.c-end.duration input').top,
                 label: v.querySelector('.c-end .cell-label').textContent, shown: r('.c-end .cell-label').height > 0,
                 start: r('.when-start').top, end: r('.when-end').top }; })()""")
    assert lines["wait"] > lines["rule"] and lines["start"] > lines["wait"], lines
    assert lines["label"] == "Transition duration" and lines["shown"] and lines["end"] > lines["length"], lines
    assert abs(lines["start"] - lines["end"]) < 2, lines
    until(app, lambda: run_js(dlg, "$$('.version')[4].querySelector('.when-end').textContent").startswith("Ends today, "), 5)
    assert run_js(dlg, "$$('.version')[4].querySelector('.when-start').textContent").startswith("Starts today, ")
    # Preview on a version: the preview comes into view and plays its transition, from a little
    # before it starts to fully in, and stays there.
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    mark = run_js(dlg, "S.marks.find((m) => m.index === 4)")
    run_js(dlg, "$$('.version')[4].querySelector('.preview-transition').click()")
    until(app, lambda: run_js(dlg, "!!playing"), 3, "Preview didn't play the transition")
    until(app, lambda: run_js(dlg, "!playing"), 8, "the transition kept playing")
    end = (mark["start"] + mark["fade"]) % 1440
    assert abs(((run_js(dlg, "scrub") - end + 720) % 1440) - 720) <= 20, (run_js(dlg, "scrub"), mark)
    assert run_js(dlg, """(() => { const r = $('.editor .preview').getBoundingClientRect(), m = $('main').getBoundingClientRect();
        return r.top >= m.top - 1 && r.bottom <= m.bottom + 1; })()"""), "the preview wasn't brought into view"
    run_js(dlg, "$('#backToNow').click(); $('main').scrollTop = 0")
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    shoot(dlg, "scene-follows")
    run_js(dlg, "$('main').scrollTop = 0")
    run_js(dlg, "$$('.version')[4].querySelector('[aria-label=\"Remove version\"]').click()")
    until(app, lambda: run_js(dlg, "$$('.version').length") == 4, 5)
    # The times run on through the cycle: one past midnight after the evening is the next day's.
    assert run_js(dlg, "cycleTimes([{ index: 1, start: 1159, fade: 11 }, { index: 0, start: 369, fade: 47 }, "
                       "{ index: 2, start: 44, fade: 90 }])") == [[0, 369, 416], [1, 1159, 1170], [2, 1484, 1574]]
    assert run_js(dlg, "[dayAndTime(1170), dayAndTime(1484)]") == ["Today, 19:30", "Next day, 00:44"]
    print("PASS: a new version starts after the one above's transition, plus a delay, with no time to set; "
          "its name is a heading to rename; Preview plays its transition.")

    # A height that isn't a named moment (from an older version) stays, with its time today under it.
    run_js(dlg, f"Object.assign({day_scene}.versions[1], {{ direction: 'rising', from: 15 }}); changed(true)")
    until(app, lambda: run_js(dlg, "$$('.version')[1].querySelector('select').selectedOptions[0].textContent")
          == "Sun at 15° (morning)", 5, "a sun height without a name isn't shown")
    until(app, lambda: run_js(dlg, "$$('.version')[1].querySelector('.when-start').textContent").startswith("Today, "), 5,
          "a sun height without a name has no time")
    run_js(dlg, f"Object.assign({day_scene}.versions[1], {{ from: 6 }}); changed(true)")

    # A narrow window: each version takes two lines, so its dropdowns keep their width.
    row = """(() => { const v = $$('.version')[0], name = v.querySelector('.vname').getBoundingClientRect();
        const sel = [...v.querySelectorAll('select')].map(s => s.getBoundingClientRect());
        return { twoLines: sel[0].top >= name.bottom, widths: sel.map(r => Math.round(r.width)),
                 overflow: Math.max(...$$('.versions *').map(e => e.getBoundingClientRect().right))
                           - $('.versions').getBoundingClientRect().right }; })()"""
    dlg.resize(800, 780)
    until(app, lambda: run_js(dlg, row)["twoLines"], 5, "versions stay on one line in a narrow window")
    narrow = run_js(dlg, row)
    assert min(narrow["widths"]) >= 170 and narrow["overflow"] <= 0, narrow
    shoot(dlg, "versions-narrow")
    # Scrolled down, a dropdown of the scenes stays at the top, on its own background over the
    # editor (the list and the New scene buttons go), and opens another scene.
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    pump(app, 0.3)
    assert run_js(dlg, """(() => { const m = $('main').getBoundingClientRect(), bar = $('.scene-select'),
        l = bar.getBoundingClientRect(), s = bar.querySelector('select').getBoundingClientRect();
        return $('main').scrollTop > 0 && l.top >= m.top - 1 && l.top <= m.top + 1 && $('.scene-list').offsetParent === null
               && getComputedStyle(bar).backgroundColor !== 'rgba(0, 0, 0, 0)'
               && document.elementFromPoint(s.x + s.width / 2, s.y + s.height / 2).closest('.scene-select') !== null; })()"""), \
        "the scene dropdown scrolled away in a narrow window"
    was = run_js(dlg, "sel")
    other = run_js(dlg, "[...$('.scene-select select').options].map((o) => o.value).find((v) => v !== sel)")
    assert other, "only one scene to choose from"
    for want in (other, was):
        run_js(dlg, f"setv($('.scene-select select'), {json.dumps(want)})")
        until(app, lambda w=want: run_js(dlg, "sel") == w and run_js(dlg, "$('.scene-select select').value") == w, 5,
              "the scene dropdown didn't open the scene")
    run_js(dlg, "$('main').scrollTop = 0")
    # Two lines until a row's dropdowns have room for the longer rules ("After Night's transition ends").
    dlg.resize(1100, 780)
    until(app, lambda: run_js(dlg, row)["twoLines"], 5, "versions squeeze onto one line")
    dlg.resize(1300, 780)
    until(app, lambda: not run_js(dlg, row)["twoLines"], 5, "versions stay on two lines in a wide window")
    wide = run_js(dlg, row)
    assert min(wide["widths"]) >= 205 and wide["overflow"] <= 0, wide
    dlg.resize(1100, 780)
    print("PASS: each version takes two lines until its dropdowns have room on one, and they keep their width.")

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
    run_js(dlg, "byText('label', 'Choose different scenes').querySelector('input').click()")
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
    # A deck-list screen only switches backdrops on; the Backdrops page sets them up, with a preview.
    assert run_js(dlg, "$$('[data-card=main] input[type=range]').length") == 2, "backdrop sliders on a screen's card"
    # Every card's controls start in one column, whatever indents them (at both widths).
    run_js(dlg, "draft.screens.done.enabled = true; changed(true)")
    dim_x = "$$('input[aria-label=Dim]').map(e => Math.round(e.getBoundingClientRect().left))"
    size = (dlg.width(), dlg.height())
    for width in (1100, 800):
        dlg.resize(width, 780)
        pump(app, 0.4)
        xs = run_js(dlg, dim_x)
        assert len(xs) == 3 and len(set(xs)) == 1, (width, xs)
    dlg.resize(*size)
    run_js(dlg, "draft.screens.done.enabled = false; changed(true)")
    assert run_js(dlg, "$('[data-card=main] .backdrop-switch .link').disabled"), "Configure works with backdrops off"
    run_js(dlg, "$('[data-card=main] .backdrop-switch input').click()")
    assert run_js(dlg, "draft.screens.main.backdrops === true")
    run_js(dlg, "$('[data-card=main] .backdrop-switch .link').click()")
    until(app, lambda: run_js(dlg, "page") == "backdrops", 5, "Configure didn't open the Backdrops page")
    until(app, lambda: run_js(dlg, "$$('.backdrop-mock .keshiki-layer').length") > 0, 10, "the backdrop preview has no picture")
    # By the heading: which screens use backdrops, and a way to them.
    assert run_js(dlg, "$('.page-status').textContent") == "In use on: Deck listManage screens"
    # A preview about 240px high, kept in view while the cards scroll under it.
    height = run_js(dlg, "$('.backdrop-mock').getBoundingClientRect().height")
    assert 220 <= height <= 260, height
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    pump(app, 0.3)
    assert run_js(dlg, """(() => { const m = $('main').getBoundingClientRect(), p = $('.backdrop-preview').getBoundingClientRect();
        return $('main').scrollTop > 0 && Math.abs(p.top - m.top) <= 1
               && $('select.text-outline').getBoundingClientRect().top > p.bottom; })()"""), "the preview scrolled away"
    # Sliders line up across the cards, those under a checkbox included.
    xs = run_js(dlg, "$$('.aligned input[type=range]').map(e => Math.round(e.getBoundingClientRect().left))")
    assert len(xs) == 6 and len(set(xs)) == 1, xs
    # A card marks its part of the preview while focus is in it.
    run_js(dlg, "$$('.aligned input[type=range]')[0].focus()")
    until(app, lambda: run_js(dlg, "$('.backdrop-mock').classList.contains('mark-table')"), 5, "the deck list panel isn't marked")
    run_js(dlg, "$$('.aligned input[type=range]')[2].focus()")
    until(app, lambda: run_js(dlg, "$('.backdrop-mock').className.includes('mark-addon') "
                                   "&& !$('.backdrop-mock').className.includes('mark-table')"), 5, "the statistics panel isn't marked")
    # The color picker shows only for a custom color.
    run_js(dlg, "draft.backdrops.panel.enabled = true; changed(true)")
    assert run_js(dlg, "$('.color-choice input[type=color]').hidden")
    run_js(dlg, "setv($('.color-choice select'), 'custom')")
    until(app, lambda: run_js(dlg, "!$('.color-choice input[type=color]').hidden"), 5, "no picker for a custom color")
    assert run_js(dlg, "$('#restorePage').textContent") == "Reset backdrop settings"
    run_js(dlg, "$('main').scrollTop = 0")
    # The preview runs the same text help as Anki's window.
    run_js(dlg, "setv($('select.text-outline'), 'everywhere')")
    outlined = ("$$('.backdrop-mock .mock-table [style*=\"text-shadow\"], .backdrop-mock .mock-table[style*=\"text-shadow\"]').length"
                " + $$('.backdrop-mock .mock-addon [style*=\"text-shadow\"]').length")
    try:
        until(app, lambda: run_js(dlg, outlined) > 0, 10)
    except AssertionError:
        raise AssertionError("the preview's text isn't outlined: " + str(run_js(dlg, """(() => {
            const b = $('.backdrop-mock'), s = stageFor(b);
            return { shown: (s.shown || '').slice(0, 80), contrast: !!b.contrast, settings: b.contrast && b.contrast.settings,
                     running: b.contrast && b.contrast.running, outline: draft.backdrops.text }; })()"""))) from None
    shoot(dlg, "backdrops")
    run_js(dlg, "$('#cancel').click(); byText('#nav button', 'Screens').click()")
    until(app, lambda: run_js(dlg, "draft.screens.main.backdrops === false"), 5)
    # Each preview sits beside its controls, and All done for today starts within the window.
    assert run_js(dlg, "$('[data-card=done] h2').getBoundingClientRect().bottom <= $('main').getBoundingClientRect().bottom"), \
        "All done for today is below the fold"
    assert run_js(dlg, """(() => { const c = $('[data-card=main]'), m = c.querySelector('.mock').getBoundingClientRect();
        return m.right < c.querySelector('.screen-controls').getBoundingClientRect().left; })()"""), "the preview isn't beside its controls"
    print("PASS: save writes the config, keeps the window open and ends the live preview.")

    # A screen's scenes, and an album's pictures, take turns: the deck list (an album of four)
    # can shuffle; studying, with one day cycle, says how, and shuffles once it has the album too.
    main_card, study_card = "$('[data-card=main]')", "$('[data-card=study]')"
    assert run_js(dlg, f"!!{main_card}.querySelector('select.shuffle')")
    assert run_js(dlg, f"!{study_card}.querySelector('select.shuffle') && !{study_card}.textContent.includes('Shuffle')")
    run_js(dlg, f"const a = {study_card}.querySelector('select[aria-label=\"Add a scene\"]'); "
                "setv(a, [...a.options].find(o => o.text === 'Album').value)")
    until(app, lambda: run_js(dlg, "draft.screens.study.scenes.length") == 2, 5, "the album didn't join studying")
    assert run_js(dlg, f"!{study_card}.querySelector('.add-images')"), "screens add scenes, not images"
    assert run_js(dlg, f"!!{study_card}.querySelector('select.shuffle')"), "no shuffle with two scenes"
    assert run_js(dlg, "draft.screens.main.scenes.length") == 1
    assert run_js(dlg, "!$('.combine')"), "combining belongs on the Scenes page"
    shoot(dlg, "screens-shuffle")
    # The unsaved changes show in the footer, marked.
    assert run_js(dlg, "$('#status').classList.contains('dirty')")
    # Studying's options sit under its checkbox, and are disabled (not hidden) while it's off.
    run_js(dlg, f"{study_card}.querySelector('.check input').click()")
    until(app, lambda: run_js(dlg, f"{study_card}.querySelector('fieldset.dependent').disabled"), 5,
          "studying's options aren't disabled with the checkbox off")
    assert run_js(dlg, f"{study_card}.querySelectorAll('fieldset.dependent input[type=range]').length") == 2
    shoot(dlg, "screens-study-off")
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: run_js(dlg, "draft.screens.study.scenes.length") == 1, 5)
    assert run_js(dlg, "!$('#status').classList.contains('dirty')")
    print("PASS: each screen shows its shuffle once it has more than one turn; dependent options are disabled.")

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
    # A day cycle scrubbed to a moment shows it in Anki's window; opening the new album ends that.
    run_js(dlg, "byText('.scene-item span', 'Day cycle').parentElement.click()")
    run_js(dlg, "setv($('.ribbon input'), 780)")
    until(app, lambda: renderer.scene_look is not None, 5, "the scrubbed moment didn't reach Anki's window")
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
    assert library._is_link(library.FOLDERS / link), "no link to the folder"   # a junction on Windows
    # Open folder shows the folder itself (not the link) in the file manager.
    opened = []
    dlg.kiso_bridge.open_folder = opened.append
    until(app, lambda: run_js(dlg, "!!$('#openAlbumFolder')"), 5, "no Open folder for a linked album")
    run_js(dlg, "$('#openAlbumFolder').click()")
    until(app, lambda: bool(opened), 5, "Open folder didn't open anything")
    assert opened[0].resolve() == wall.resolve(), opened
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5)
    until(app, lambda: renderer.scene_look is None, 5, "the day cycle's moment stayed in Anki's window")
    run_js(dlg, "$$('.album-tile .pick')[0].click(); $('#adjustCrop').click()")
    until(app, lambda: run_js(dlg, "!!$('.position-dialog')"), 5, "a linked picture didn't open for positioning")
    # A linked album's picture, clicked, shows in Anki's window too.
    until(app, lambda: [x["image"] for x in (renderer.scene_look or {}).get("layers", [])] == [f"@{link}/hills.png"], 5,
          f"a linked album's picture didn't show in Anki's window: {renderer.scene_look}")
    run_js(dlg, "$('.position-dialog .primary').click()")
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
    # On a screen, hiding the picture Anki's window shows moves it off at once, before saving.
    main_before = run_js(dlg, "draft.screens.main.scenes.slice()")
    run_js(dlg, f"draft.screens.main.scenes = [{album}.id]; changed(true)")
    shown = lambda: renderer.look()["layers"][-1]["src"].split("/")[-1]  # noqa: E731
    until(app, lambda: renderer.preview is not None and shown() in ("hills.png", "lake.png", "dunes.png"), 5)
    showing = shown()
    run_js(dlg, f"$$('.album-tile .remove')[{album}.versions.findIndex(v => v.image.endsWith('/{showing}'))].click()")
    until(app, lambda: shown() != showing, 5, "Anki's window kept showing a hidden picture")
    run_js(dlg, f"Object.assign({album}.folder, {{ hidden: [] }}); draft.screens.main.scenes = {main_before}; changed(true)")
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5)
    # Hiding a picture leaves it in the folder and out of the album, through rescans; Show brings it back.
    assert float(run_js(dlg, "getComputedStyle($('.album-tile .remove')).opacity")) >= 0.8, "the Hide × only shows on hover"
    run_js(dlg, "$$('.album-tile .remove')[0].click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 2, 5, "Hide didn't take it out")
    assert run_js(dlg, f"{album}.folder.hidden") == [f"@{link}/dunes.png"] and (wall / "dunes.png").is_file()
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "$$('.hidden-tile').length") == 1, 5)
    assert run_js(dlg, "$$('.album-tile').length") == 2, "a rescan brought a hidden picture back"
    assert run_js(dlg, "$('.album-wrap details summary').textContent") == "Hidden pictures (1)"
    run_js(dlg, "$('.album-wrap details summary').click()")
    run_js(dlg, "$('.album-wrap .info').click()")
    shoot(dlg, "folder-album")
    run_js(dlg, "$('.hidden-tile .show').click()")
    until(app, lambda: run_js(dlg, "$$('.album-tile').length") == 3, 5, "Show didn't bring it back")
    assert run_js(dlg, "!$('.hidden-row')") and run_js(dlg, f"{album}.versions[0].image") == f"@{link}/dunes.png"
    # A folder that's gone keeps its last pictures and says so.
    wall.rename(base / "Wallpapers-away")
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "!!$('.folder-missing')"), 5, "no warning for a missing folder")
    assert run_js(dlg, "$$('.album-tile').length") == 3
    assert run_js(dlg, "$('#openAlbumFolder').disabled"), "Open folder is offered for a folder that's gone"
    (base / "Wallpapers-away").rename(wall)
    run_js(dlg, "$('#rescan').click()")
    until(app, lambda: run_js(dlg, "!$('.folder-missing')"), 5)
    # Saved, the link stays; the album deleted and saved, the link goes and the folder stays whole.
    run_js(dlg, "$('#save').click()")
    until(app, lambda: run_js(dlg, "$('#status').textContent") == "Saved", 5)
    assert library._is_link(library.FOLDERS / link)
    run_js(dlg, "byText('.scene-item span', 'Wallpapers').parentElement.click()")
    run_js(dlg, "$('#deleteScene').click()")
    until(app, lambda: run_js(dlg, "!!$('#confirmYes')"), 5)
    run_js(dlg, "$('#confirmYes').click()")
    run_js(dlg, "$('#save').click()")
    until(app, lambda: run_js(dlg, "$('#status').textContent") == "Saved", 5)
    assert not (library.FOLDERS / link).exists(), "the unused link stayed"
    assert sorted(p.name for p in wall.rglob("*.png")) == ["coast.png", "dunes.png", "hills.png", "lake.png"]
    print("PASS: a linked folder's pictures are served live, follow rescans, can be hidden, open in the file manager, "
          "survive a missing folder, and dropping the album removes only the link.")

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
    assert float(run_js(dlg, "getComputedStyle($('.lib-action')).opacity")) >= 0.8, "Move to trash only shows on hover"
    assert {"spare1.png", "spare2.png"} <= set(unused) and "dawn.png" not in unused, unused
    shoot(dlg, "library")
    run_js(dlg, "$('#trashUnused').click()")
    until(app, lambda: run_js(dlg, "trashed.length") == len(unused), 5, "the unused pictures didn't go to the trash")
    # Nothing unused: no Move button, and the note says so.
    assert run_js(dlg, "!$('#trashUnused') && $('.library-dialog .foot-note').textContent") \
        == f"All {run_js(dlg, 'images.length')} pictures are used by scenes."
    assert run_js(dlg, "$('.library-dialog h2').textContent") == "Picture library"
    # The library is imported pictures only: with a linked folder's album, it says so.
    assert run_js(dlg, "$('.library-scope').hidden")
    run_js(dlg, "draft.scenes[0].folder = { path: 'x' }; $('#tab-library').click()")
    assert run_js(dlg, "!$('.library-scope').hidden && getComputedStyle($('.library-scope')).display !== 'none'")
    run_js(dlg, "delete draft.scenes[0].folder; $('#tab-library').click()")
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
    # Empty: a note in the middle, and only Done (at its usual place).
    assert run_js(dlg, "!$('#restoreAll') && !$('#emptyTrash') && $('.empty-note').textContent") == "The trash is empty."
    assert run_js(dlg, """(() => { const n = $('.empty-note').getBoundingClientRect(), b = $('.library-body').getBoundingClientRect(),
        d = $('.library-dialog .dialog-foot .primary').getBoundingClientRect(), f = $('.library-dialog').getBoundingClientRect();
        return Math.abs((n.left + n.right) - (b.left + b.right)) < 4 && Math.abs((n.top + n.bottom) - (b.top + b.bottom)) < 4
               && f.right - d.right < 30; })()"""), "the empty trash note isn't centred, or Done moved"
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

    # Previewing in Anki's window turned off (a slow computer): edits stay in the dialog until
    # Save; turned on again, the edit as it is now shows there.
    from keshiki.keshiki import settings_page
    run_js(dlg, "$('#in-window').click()")
    until(app, lambda: not dlg.kiso_bridge.in_window, 5, "the switch didn't reach Python")
    assert settings_page.preferences() == {"preview_in_window": False}
    run_js(dlg, "setv($$('input[aria-label=Blur]')[0], '12')")
    until(app, lambda: run_js(dlg, "!$('#cancel').disabled"), 5)
    pump(app, 0.6)
    assert renderer.preview is None, "an edit reached Anki's window with previewing off"
    shoot(dlg, "preview-off")
    run_js(dlg, "$('#in-window').click()")
    until(app, lambda: (renderer.preview or {}).get("screens", {}).get("main", {}).get("blur") == 12, 5,
          "turning it back on didn't preview the edit")
    run_js(dlg, "$('#cancel').click()")
    until(app, lambda: renderer.preview is None, 5)
    print("PASS: previewing in Anki's window can be turned off, and on again, from the footer.")

    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    run_js(dlg, "byText('label', 'Use my location').querySelector('input').click()")
    # Nothing is looked up until the button is pressed; until then the details are open.
    pump(app, 0.5)
    assert run_js(dlg, "$('.locate .place').textContent") == "Not set yet", "location was looked up without asking"
    assert run_js(dlg, "!!$('[data-field=latitude]')")
    run_js(dlg, "$('#locate').click()")
    until(app, lambda: run_js(dlg, "$('.locate .place').textContent") == "Near Tokyo, Japan", 5, "location wasn't looked up")
    # Found: the everyday view is the place and today's sun; Change opens the details.
    until(app, lambda: run_js(dlg, "$('.sun-today').textContent").startswith("Sunrise "), 5, "sun times didn't show")
    assert run_js(dlg, "!$('[data-field=latitude]')"), "the coordinates aren't folded away"
    shoot(dlg, "day")
    run_js(dlg, "$('#changeLocation').click()")
    assert run_js(dlg, "$('[data-field=latitude]').value + ',' + $('[data-field=longitude]').value") == "35.68,139.65"
    assert run_js(dlg, "$('#locate').textContent") == "Find again"
    shoot(dlg, "day-change")
    run_js(dlg, "$('#changeLocation').click()")
    # Light: a picture in the light at a time picked on today's strip.
    run_js(dlg, "byText('label', 'Adjust lighting throughout the day').querySelector('input').click()")
    until(app, lambda: run_js(dlg, "$$('.light-preview .keshiki-layer').length") > 0, 5, "no light preview")
    run_js(dlg, "setv($('.daylight-wrap input'), 1140)")
    until(app, lambda: run_js(dlg, "$('.light-preview .readout').textContent") == "Preview, 19:00", 5,
          "the strip didn't move the preview")
    # The picked time shows in Anki's window too, until Back to now.
    until(app, lambda: renderer.scene_look is not None, 5, "Anki's window didn't show the picked time")
    assert run_js(dlg, "!$('#lightNow').hidden")
    run_js(dlg, "$('#lightNow').click()")
    until(app, lambda: renderer.scene_look is None, 5, "Back to now didn't hand Anki's window back")
    assert run_js(dlg, "$('#lightNow').hidden && $('.light-preview .readout').textContent.startsWith('Now')")
    run_js(dlg, "setv($('.daylight-wrap input'), 1140)")
    until(app, lambda: renderer.scene_look is not None, 5)
    run_js(dlg, "$('main').scrollTop = $('main').scrollHeight")
    shoot(dlg, "day-light")
    # By default only day cycles are lit, and the preview shows one; every scene can be.
    assert run_js(dlg, "draft.light.scope === 'day' && byText('label', 'Day-cycle scenes only').querySelector('input').checked")
    run_js(dlg, "byText('label', 'All scenes').querySelector('input').click()")
    until(app, lambda: run_js(dlg, "draft.light.scope") == "all", 5)
    until(app, lambda: run_js(dlg, "$$('.light-preview .keshiki-layer').length") > 0, 5, "no light preview for every scene")
    run_js(dlg, "byText('label', 'Day-cycle scenes only').querySelector('input').click()")
    # The place in short, the whole of it on hover.
    run_js(dlg, "draft.day.place = 'Somerville, New Jersey, United States'; changed(true)")
    assert run_js(dlg, "[$('.locate .place').textContent, $('.locate .place').title]") \
        == ["Near Somerville, New Jersey", "Somerville, New Jersey, United States"]
    # Narrow, the preview sits above the controls, and the lighting sliders line up, end to end.
    dlg.resize(800, 780)
    pump(app, 0.5)
    ends = run_js(dlg, "$$('.day-panel .slider input').map(e => { const r = e.getBoundingClientRect(); "
                       "return [Math.round(r.left), Math.round(r.right)]; })")
    assert len(ends) == 2 and len({tuple(e) for e in ends}) == 1, ends
    assert abs(run_js(dlg, "$('.daylight').getBoundingClientRect().right") - ends[0][1]) <= 2, "the day's strip overhangs the sliders"
    assert run_js(dlg, "$('.light-preview').getBoundingClientRect().bottom <= $('.light-controls').getBoundingClientRect().top")
    dlg.resize(1100, 780)
    pump(app, 0.3)
    run_js(dlg, "byText('label', 'Adjust lighting throughout the day').querySelector('input').click(); $('main').scrollTop = 0")
    # Leaving the page hands Anki's window back.
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    until(app, lambda: renderer.scene_look is None, 5, "leaving Day & time kept the picked time in Anki's window")
    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    print("PASS: the Day & time page looks up a rough location once, works out today's sun, and previews the light.")

    # General: the crossfade, and Optimize large backgrounds, on by default; its Reset puts both back.
    run_js(dlg, "byText('#nav button', 'General').click()")
    until(app, lambda: run_js(dlg, "!!$('.general-panel .slider input')"), 5, "no General page")
    shoot(dlg, "general")
    optimize = "byText('label', 'Optimize large backgrounds').querySelector('input')"
    assert run_js(dlg, f"{optimize}.checked && draft.display_copies === true")
    assert "Video driver: OpenGL" in run_js(dlg, "$('.performance .video-driver').textContent")
    run_js(dlg, f"setv($('.general-panel .slider input'), '6'); {optimize}.click()")
    until(app, lambda: run_js(dlg, "!!byText('#nav button', 'General').querySelector('.dot')"), 5, "no unsaved dot on General")
    assert run_js(dlg, "[draft.display_copies, draft.transition_seconds, $('#restorePage').textContent]") \
        == [False, 6, "Reset general settings"]
    run_js(dlg, "$('#restorePage').click()")
    until(app, lambda: run_js(dlg, f"{optimize}.checked && draft.transition_seconds === 2"), 5, "Reset didn't put General back")
    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    print("PASS: the General page has the crossfade and Optimize large backgrounds (on by default), and resets both.")

    # Per-page Revert and Restore: only that page changes, and only in the draft.
    assert run_js(dlg, "!!$('#revertPage') && !!byText('#nav button', 'Day & time').querySelector('.dot')")
    run_js(dlg, "$('#revertPage').click()")
    until(app, lambda: run_js(dlg, "byText('label', 'Use fixed times').querySelector('input').checked"), 5, "Revert didn't undo the page")
    assert run_js(dlg, "!$('#revertPage') && !byText('#nav button', 'Day & time').querySelector('.dot') && $('#save').disabled")
    run_js(dlg, "byText('#nav button', 'Screens').click()")
    run_js(dlg, "setv($$('input[aria-label=Dim]')[0], '60')")
    until(app, lambda: run_js(dlg, "!!$('#restorePage')"), 5, "no Restore defaults after changing dim")
    assert run_js(dlg, "$('#restorePage').textContent") == "Reset adjustments"
    run_js(dlg, "draft.screens.done.enabled = true; changed(true)")
    run_js(dlg, "$('#restorePage').click()")
    until(app, lambda: run_js(dlg, "$$('input[aria-label=Dim]')[0].value") == "15", 5, "Restore didn't reset dim")
    assert run_js(dlg, "draft.screens.done.enabled && draft.screens.study.enabled"), "Reset turned a screen on or off"
    run_js(dlg, "draft.screens.done.enabled = false; changed(true)")
    assert run_js(dlg, "$$('.chip').length") == 2, "Restore dropped the chosen scenes"
    assert mw.addonManager.getConfig("keshiki")["screens"]["main"]["dim"] == 15
    run_js(dlg, "byText('#nav button', 'Day & time').click()")
    run_js(dlg, "byText('label', 'Use my location').querySelector('input').click()")
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

    # kiso shots: the settings as Anki shows them, opened the way the Tools menu opens them
    # (modally), every page from top to bottom and each scene, at the saved size and narrow
    # (640 px here: the offscreen screen keeps the dialog under 800).
    # The run leaves the config and the dialog's remembered size as they were.
    import logging

    from aqt.qt import QImage
    from keshiki.keshiki._kiso import settings as kiso_settings
    from keshiki.keshiki._kiso import shots as kiso_shots
    until(app, lambda: not kiso_settings.open_dialogs, 5)
    geometry = lambda: {k: bytes(v) for k, v in mw.pm.profile.items() if "keshikiSettings" in k}  # noqa: E731
    cfg_before, geom_before = mw.addonManager.getConfig("keshiki"), geometry()
    # Nothing here keeps the run, as in Anki's dev watch (PyQt holds a timer's callback weakly).
    kiso_shots.start(mw, addon().addon._settings, '{"id": "check", "narrow": 640}', base, logging.getLogger("check"))
    out = base / "kiso_shots" / "check"
    until(app, lambda: (out / "done.json").is_file(), 240, "the screenshot run didn't finish")
    done = json.loads((out / "done.json").read_text())
    assert not done["errors"], done["errors"]
    names = done["files"]
    for tag in ("saved", "640px"):
        for p in ("screens", "scenes", "backdrops", "day", "general"):
            assert any(n.startswith(tag) and f"-{p}-" in n for n in names), (tag, p, names)
        assert any(n.startswith(tag) and "-picture-library" in n for n in names), names
        assert any(n.startswith(tag) and "-trash" in n for n in names), names
    scenes = mw.addonManager.getConfig("keshiki")["scenes"]
    assert all(any(f"-scenes-{kiso_shots.slug(s['name'])}" in n for n in names) for s in scenes), names
    assert any(n.endswith("-02.png") for n in names), "nothing was scrolled through"
    assert QImage(str(out / next(n for n in names if n.startswith("640px")))).width() == 640
    assert not kiso_settings.open_dialogs and mw.addonManager.getConfig("keshiki") == cfg_before
    assert geometry() == geom_before, "the run changed the dialog's remembered size"
    # Tours named for no page (the README's pictures) run only when asked for, alone, at the size asked for.
    assert not any("-readme-" in n or "-day-film-" in n for n in names), names
    kiso_shots.start(mw, addon().addon._settings, '{"id": "tour", "tour": "readme", "size": [700, 500]}', base,
                     logging.getLogger("check"))
    until(app, lambda: (base / "kiso_shots" / "tour" / "done.json").is_file(), 60, "the tour didn't finish")
    done = json.loads((base / "kiso_shots" / "tour" / "done.json").read_text())
    assert not done["errors"] and done["files"] == ["700x500-001-readme-screens.png"], done
    assert QImage(str(base / "kiso_shots" / "tour" / done["files"][0])).size().width() == 700
    assert mw.addonManager.getConfig("keshiki") == cfg_before and geometry() == geom_before
    # A settings window already open is left alone.
    dlg = open_page()
    kiso_shots.start(mw, addon().addon._settings, '{"id": "busy"}', base, logging.getLogger("check"))
    until(app, lambda: (base / "kiso_shots" / "busy" / "done.json").is_file(), 10)
    assert "close it first" in json.loads((base / "kiso_shots" / "busy" / "done.json").read_text())["errors"][0]
    assert dlg.isVisible()
    dlg.reject()
    until(app, lambda: not dlg.isVisible(), 5)
    print(f"PASS: kiso shots grabs every page and scene at both sizes ({len(names)} shots), and leaves "
          "the config, the window's size and an open settings window alone.")


if __name__ == "__main__":
    run(check, __doc__)
