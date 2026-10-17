"""Real-Anki check of display copies: a big picture is shown from a copy that covers the
screen once it's made, swapped in without a fade, a flash or any change to what shows; a
phone photo's rotation and colour profile come out as Chromium shows the picture itself."""

import json
import time

# isort: off
# kiso_dev.harness sets Qt up for offscreen use before aqt loads, so it comes first.
from kiso_dev.harness import addon, js, pump, run, until

import aqt
from aqt.qt import QColor, QColorSpace, QImage, QImageIOHandler, QImageWriter, QPainter, Qt
from images import make_test_image
# isort: on

LIVE = """(() => { const s = window.keshiki && keshiki.main; if (!s) return null;
    return [...s.stack.children].filter(e => !e.dataset.leaving).map(e => ({
        src: e.dataset.src, opacity: e.style.opacity, pics: e.querySelectorAll('.keshiki-pic').length })); })()"""


def js_wait(app, web, promise):
    """The value a promise in the page resolves to (runJavaScript doesn't wait for one)."""
    js(app, web, f"window.__got = undefined; ({promise}).then((v) => {{ window.__got = JSON.stringify(v); }}); true")
    until(app, lambda: js(app, web, "window.__got !== undefined"), 10, "the page's promise never resolved")
    return json.loads(js(app, web, "window.__got"))


def small(img: QImage) -> QImage:
    return img.scaled(160, 100, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def difference(a: QImage, b: QImage) -> float:
    """Mean difference per channel (0-255) between two grabs, at a small size."""
    a, b = small(a), small(b)
    total = 0
    for y in range(a.height()):
        for x in range(a.width()):
            p, q = a.pixelColor(x, y), b.pixelColor(x, y)
            total += abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())
    return total / (3 * a.width() * a.height())


def check(app, shots, base):
    mw = aqt.mw
    renderer = addon().addon.feature
    from keshiki.keshiki import library
    from keshiki.keshiki.config import migrate, new_scene

    display = renderer.display
    assert display.box == (1920, 1080), display.box   # the offscreen screen is small
    # The worker's results wait until the check lets them through.
    held = []
    run_for_real = display.run_in_background
    display.run_in_background = lambda fn, done: held.append((fn, done))

    def release():
        until(app, lambda: bool(held), 10, "no display copy was asked for")
        fn, done = held.pop(0)
        done(fn())

    big = library.import_files([str(make_test_image(base / "big.jpg", 200, 4000, 2400))])[0]
    small_pic = library.import_files([str(make_test_image(base / "small.png", 30))])[0]   # 1600x1000
    cfg, _ = migrate({})
    scene = new_scene("single", image=big)
    cfg["scenes"] = [scene]
    cfg["screens"]["main"].update(scenes=[scene["id"]], dim=0)
    cfg["screens"]["main"]["blur"] = 2   # a blurred screen shows copies whatever the setting
    mw.addonManager.writeConfig("keshiki", cfg)
    renderer.set_config(cfg)
    webs = {"toolbar": mw.toolbarWeb, "main": mw.web, "bottom": mw.bottomWeb}
    original = library.image_url(big)
    for name, web in webs.items():
        until(app, lambda w=web: [x["src"] for x in js(app, w, LIVE) or []] == [original], 10,
              f"{name} doesn't show the picture itself first")
    print("PASS: a big picture shows as it is until its copy is made.")

    pump(app, 2.5)   # past the fade-in
    central = mw.form.centralwidget
    before = central.grab().toImage()
    release()
    copy = library.display_url(library.display_name(big, (1920, 1080)) + ".jpg")
    assert renderer.shown["layers"][0]["src"] == copy, renderer.shown
    # The swap, watched: no frame goes dark or blank. (Compared small: this doesn't show fine
    # detail, which a copy has a little less of; that's why copies in Anki's window are opt-in.)
    worst, t0 = 0.0, time.monotonic()
    while time.monotonic() - t0 < 1.5:
        app.processEvents()
        worst = max(worst, difference(before, central.grab().toImage()))
    for name, web in webs.items():
        until(app, lambda w=web: js(app, w, LIVE) == [{"src": copy, "opacity": "1", "pics": 1}], 10,
              f"{name} didn't swap to the copy in place: {js(app, web, LIVE)}")
    after = central.grab().toImage()
    if shots:
        before.save(str(shots / "display-before.png"))
        after.save(str(shots / "display-after.png"))
    print(f"  swap: worst difference while swapping {worst:.2f}, after {difference(before, after):.2f} (of 255)")
    assert worst < 2.5 and difference(before, after) < 2.5, "the swap flashed or changed the picture"
    size = js_wait(app, mw.web, f"""new Promise((ok) => {{ const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]);
        i.onerror = () => ok(null); i.src = {copy!r}; }})""")
    assert size == [1920, 1152], size
    print("PASS: the copy (1920x1152, covering the screen) swaps in without a fade or a flash.")

    # A picture not much bigger than the screen is shown as it is, and asked about once.
    scene2 = new_scene("single", image=small_pic)
    cfg["scenes"].append(scene2)
    cfg["screens"]["main"]["scenes"] = [scene2["id"]]
    renderer.set_config(cfg)
    release()
    renderer.refresh()
    assert renderer.shown["layers"][0]["src"] == library.image_url(small_pic) and not held
    print("PASS: a picture close to the screen's size has no copy.")

    # Mid-crossfade between two copied pictures (a day cycle's transition): both swap in place,
    # at their opacity, with nothing else entering.
    other = library.import_files([str(make_test_image(base / "other.jpg", 300, 4000, 2400))])[0]

    def two():
        return {"layers": [{"image": big, "src": display.url(big), "opacity": 1, "x": 50, "y": 50},
                           {"image": other, "src": display.url(other), "opacity": 0.5, "x": 50, "y": 50}],
                "dim": 0, "blur": 0, "fade": 0}
    renderer.show_scene_moment(two())
    pump(app, 1)
    before = central.grab().toImage()
    release()   # the other picture's copy
    renderer.show_scene_moment(two())
    other_copy = library.display_url(library.display_name(other, (1920, 1080)) + ".jpg")
    until(app, lambda: js(app, mw.web, LIVE) == [{"src": copy, "opacity": "1", "pics": 1},
                                                 {"src": other_copy, "opacity": "0.5", "pics": 1}], 10,
          f"the crossfade's layers didn't swap in place: {js(app, mw.web, LIVE)}")
    print(f"  mid-crossfade swap: difference {difference(before, central.grab().toImage()):.2f}")
    assert difference(before, central.grab().toImage()) < 2.5
    renderer.show_scene_moment(None)
    print("PASS: a crossfade's two pictures swap to their copies in place.")

    # The settings previews use the copies too.
    from keshiki.keshiki.settings_page import make_dialog
    cfg["screens"]["main"]["scenes"] = [scene["id"]]
    renderer.set_config(cfg)
    dlg = make_dialog(mw, renderer)
    dlg.show()
    until(app, lambda: js(app, dlg.kiso_web, "window.kisoReady === true"), 15, "settings page never loaded")
    preview = "[...document.querySelectorAll('[data-screen=main] .keshiki-layer')].map(e => e.dataset.src)"
    until(app, lambda: js(app, dlg.kiso_web, preview) == [copy], 10, f"the preview: {js(app, dlg.kiso_web, preview)}")
    dlg.reject()
    pump(app, 0.5)
    print("PASS: the settings previews show the copy.")

    # Unblurred, Anki's window shows the copy too, unless Optimize large backgrounds is off: then
    # the picture itself. More blur, a smaller copy (8 px: a quarter of the screen).
    def shows(src):
        return lambda: [x["src"] for x in js(app, mw.web, LIVE) or []] == [src]
    cfg["screens"]["main"]["blur"] = 0
    renderer.set_config(cfg)
    until(app, shows(copy), 10, f"Anki's window: {js(app, mw.web, LIVE)}")
    cfg["display_copies"] = False   # "Optimize large backgrounds" off
    renderer.set_config(cfg)
    until(app, shows(original), 10, f"turned off, the copy stayed: {js(app, mw.web, LIVE)}")
    cfg["display_copies"] = True
    renderer.set_config(cfg)
    until(app, shows(copy), 10, f"Anki's window: {js(app, mw.web, LIVE)}")
    cfg["screens"]["main"]["blur"] = 8
    renderer.set_config(cfg)
    quarter = library.display_url(library.display_name(big, (480, 270)) + ".jpg")
    def made_and_shown():
        while held:   # the worker's results, let through
            fn, done = held.pop(0)
            done(fn())
        return shows(quarter)()
    until(app, made_and_shown, 15, f"an 8 px blur didn't use a quarter-size copy: {js(app, mw.web, LIVE)}")
    cfg["screens"]["main"]["blur"] = 2
    renderer.set_config(cfg)
    print("PASS: unblurred, Anki's window shows the copy (the picture itself if that's off); blurred, a copy, smaller the "
          "more the blur.")

    # A linked folder of big pictures: the album's tiles never load a picture itself, and fill in
    # with thumbnails as the background work makes them, a few at a time.
    folder = base / "Big"
    folder.mkdir()
    for i in range(20):
        make_test_image(folder / f"big{i:02}.jpg", 10 * i, 4000, 2400)
    dlg = make_dialog(mw, renderer)
    dlg.kiso_bridge.pick_folder = lambda: str(folder)
    dlg.show()
    until(app, lambda: js(app, dlg.kiso_web, "window.kisoReady === true"), 15, "settings page never loaded")
    tiles = "[...document.querySelectorAll('.album-tile .pick')].map(e => e.style.backgroundImage)"
    js(app, dlg.kiso_web, "[...document.querySelectorAll('#nav button')].find(b => b.textContent.includes('Scenes')).click()")
    js(app, dlg.kiso_web, "document.getElementById('addFolder').click()")
    until(app, lambda: js(app, dlg.kiso_web, "!!document.getElementById('addFolderGo') && "
                                             "!document.getElementById('addFolderGo').disabled"), 10, "no Add")
    js(app, dlg.kiso_web, "document.getElementById('addFolderGo').click()")
    until(app, lambda: len(js(app, dlg.kiso_web, tiles)) == 20, 10, "no tiles")
    seen = set()
    def all_thumbs():
        got = js(app, dlg.kiso_web, tiles)
        seen.update(got)
        return all("/thumbs/" in t for t in got)
    until(app, all_thumbs, 60, f"the tiles didn't fill in: {js(app, dlg.kiso_web, tiles)}")
    assert not [t for t in seen if "/folders/" in t], "a tile loaded a picture itself"
    dlg.reject()
    pump(app, 0.5)
    print("PASS: a linked folder's tiles never load the pictures themselves, and fill in with thumbnails.")

    # A phone photo (turned by its EXIF, in Display P3) comes out as Chromium shows the picture.
    img = QImage(6000, 3600, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.red)
    p = QPainter(img)
    p.fillRect(0, 0, 1500, 3600, QColor(40, 200, 60))
    p.fillRect(1500, 0, 1500, 1800, QColor(30, 60, 220))
    p.end()
    img.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))
    writer = QImageWriter(str(base / "phone.jpg"))
    writer.setTransformation(QImageIOHandler.Transformation.TransformationRotate90)
    assert writer.write(img)
    phone = library.import_files([str(base / "phone.jpg")])[0]
    display.run_in_background = run_for_real
    while held:   # anything still waiting (the settings may have asked for copies)
        fn, done = held.pop(0)
        done(fn())
    display.url(phone)
    # Made on a worker: Anki's main thread keeps turning meanwhile.
    gaps, last = [], time.monotonic()
    while display.url(phone) == library.image_url(phone):
        app.processEvents()
        now = time.monotonic()
        gaps.append(now - last)
        last = now
        assert sum(gaps) < 20, "no copy of the phone photo"
        time.sleep(0.005)
    print(f"  phone photo (6000x3600) copied in {sum(gaps):.2f} s; the main thread's longest wait {max(gaps) * 1000:.0f} ms")
    same = js_wait(app, mw.web, f"""Promise.all([{library.image_url(phone)!r}, {display.url(phone)!r}].map((src) => new Promise((ok) => {{
        const i = new Image(); i.onload = () => {{
          const c = Object.assign(document.createElement('canvas'), {{ width: 30, height: 50 }}), x = c.getContext('2d');
          x.drawImage(i, 0, 0, 30, 50); ok([i.naturalWidth > i.naturalHeight, [...x.getImageData(0, 0, 30, 50).data]]); }};
        i.src = src; }}))).then(([a, b]) => [a[0], b[0], a[1].reduce((s, v, k) => s + Math.abs(v - b[1][k]), 0) / a[1].length])""")
    print(f"  phone photo: landscape as shown {same[0]}, copy {same[1]}; difference {same[2]:.2f} (of 255)")
    assert same[0] is False and same[1] is False and same[2] < 3, same
    print("PASS: a turned Display P3 photo's copy shows as the photo does.")

    # A see-through picture: its copy is laid on the canvas colour showing through it, and looks
    # the same as the picture over the stage.
    img = QImage(4000, 2400, QImage.Format.Format_ARGB32)
    img.fill(QColor(220, 40, 40, 255))
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    p.fillRect(0, 0, 2000, 2400, QColor(40, 200, 60, 110))
    p.fillRect(2000, 0, 2000, 1200, QColor(0, 0, 0, 0))
    p.end()
    img.save(str(base / "glass.png"))
    glass = library.import_files([str(base / "glass.png")])[0]
    display.url(glass)
    until(app, lambda: display.url(glass) != library.image_url(glass), 20, "no copy of the see-through picture")
    canvas = js(app, mw.web, "getComputedStyle(keshiki.main.root).backgroundColor")
    assert display.url(glass).endswith(f".{display.backdrop}.jpg"), (display.url(glass), canvas)
    grabs = []
    for src in (library.image_url(glass), display.url(glass)):
        renderer.show_scene_moment({"layers": [{"image": src, "src": src, "opacity": 1, "x": 50, "y": 50}],
                                    "dim": 0, "blur": 0, "fade": 0})
        pump(app, 2.0)
        grabs.append(central.grab().toImage())
    renderer.show_scene_moment(None)
    print(f"  see-through picture on {canvas}: copy differs by {difference(*grabs):.2f} (of 255)")
    assert difference(*grabs) < 2, "the laid-down copy doesn't look like the picture"
    print("PASS: a see-through picture's copy is laid on the canvas colour and looks the same.")

    # A bigger screen: the picture itself again (a 4000 px picture is close to 4K's width),
    # swapped in place.
    # A screen's resolution goes up (the window doesn't move): the picture itself swaps back in.
    renderer.screen_pixels = lambda: (3840, 2160)
    screen = aqt.qt.QGuiApplication.screens()[0]
    screen.geometryChanged.emit(screen.geometry())
    until(app, lambda: display.box == (3840, 2160), 5, f"the screen change wasn't heard: {display.box}")
    until(app, lambda: js(app, mw.web, LIVE) == [{"src": original, "opacity": "1", "pics": 1}], 10,
          f"no swap back to the picture: {js(app, mw.web, LIVE)}")
    print("PASS: when a screen's resolution goes up, the picture itself swaps back in.")


if __name__ == "__main__":
    run(check, __doc__)
