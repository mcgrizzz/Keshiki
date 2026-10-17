import os

import pytest

from keshiki import library
from keshiki.display import Display

qt = pytest.importorskip("aqt.qt")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    for attr in ("IMAGES", "THUMBS", "FOLDERS", "TRASH", "DISPLAY"):
        monkeypatch.setattr(library, attr, tmp_path / "user_files" / attr.lower())
    library.IMAGES.mkdir(parents=True)
    return tmp_path


def picture(name, w, h, *, alpha=None, rotate=False, space=None):
    """A picture in the library: a left half green, a right half red (so a turn shows)."""
    fmt = qt.QImage.Format.Format_ARGB32 if alpha is not None else qt.QImage.Format.Format_RGB32
    img = qt.QImage(w, h, fmt)
    img.fill(qt.QColor(220, 30, 30, 255 if alpha is None else alpha))
    p = qt.QPainter(img)
    p.setCompositionMode(qt.QPainter.CompositionMode.CompositionMode_Source)
    p.fillRect(0, 0, w // 2, h, qt.QColor(30, 200, 30, 255 if alpha is None else alpha))
    p.end()
    if space:
        img.setColorSpace(qt.QColorSpace(space))
    path = library.IMAGES / name
    writer = qt.QImageWriter(str(path))
    if rotate:
        writer.setTransformation(qt.QImageIOHandler.Transformation.TransformationRotate90)
    assert writer.write(img)
    return name


def read(file):
    return qt.QImage(str(library.DISPLAY / file))


def test_the_box_is_the_smallest_step_that_covers_the_screens():
    assert library.display_box(1920, 1080) == (1920, 1080)
    assert library.display_box(1920, 1200) == (2560, 1440)   # 16:10
    assert library.display_box(3840, 2160) == (3840, 2160)   # 4K, or 2560x1440 at 150%
    assert library.display_box(1080, 1920) == (3840, 2160)   # a screen on its side
    assert library.display_box(7680, 4320) is None


def test_a_copy_just_covers_the_box_and_only_when_clearly_smaller():
    assert library.display_size(6000, 4000, (1920, 1080)) == (1920, 1280)
    assert library.display_size(4000, 6000, (1920, 1080)) == (1920, 2880)   # portrait: covers the width
    assert library.display_size(8000, 2000, (1920, 1080)) == (4320, 1080)   # a panorama: covers the height
    assert library.display_size(2200, 1300, (1920, 1080)) is None   # not much bigger: as it is
    assert library.display_size(1600, 1000, (1920, 1080)) is None


def test_animated_pictures_are_left_alone(lib):
    def file(name, data):
        (library.IMAGES / name).write_bytes(data)
        return library.IMAGES / name

    def chunk(kind, data=b""):
        return len(data).to_bytes(4, "big") + kind + data + b"\0\0\0\0"

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", bytes(13))
    assert library.still(file("still.png", png + chunk(b"IDAT", b"x") + chunk(b"IEND")))
    assert not library.still(file("apng.png", png + chunk(b"acTL", bytes(8)) + chunk(b"IDAT", b"x")))
    vp8x = lambda flags: b"RIFF" + bytes(4) + b"WEBP" + b"VP8X" + (10).to_bytes(4, "little") + bytes([flags]) + bytes(9)  # noqa: E731
    assert library.still(file("still.webp", vp8x(0x10)))   # alpha only
    assert not library.still(file("anim.webp", vp8x(0x02)))
    assert not library.still(file("any.gif", b"GIF89a"))
    assert not library.still(file("x.avif", b"...."))
    assert library.still(file("p.jpg", b"...."))


def test_a_copy_for_a_big_photo(lib):
    name = picture("big.jpg", 4000, 2400)
    file = library.make_display(name, (1920, 1080))
    assert file == library.display_name(name, (1920, 1080)) + ".jpg"
    img = read(file)
    assert (img.width(), img.height()) == (1920, 1152)
    assert img.pixelColor(100, 500).green() > 180 and img.pixelColor(1800, 500).red() > 200
    assert not list(library.DISPLAY.glob("*.part"))
    mtime = (library.DISPLAY / file).stat().st_mtime_ns
    assert library.make_display(name, (1920, 1080)) == file   # kept, not made again
    assert (library.DISPLAY / file).stat().st_mtime_ns == mtime


def test_no_copy_when_it_would_not_help_or_could_change_the_look(lib):
    box = (1920, 1080)
    assert library.make_display(picture("small.png", 1600, 1000), box) is None
    assert library.make_display("missing.jpg", box) is None
    (library.IMAGES / "broken.jpg").write_bytes(b"not a picture")
    assert library.make_display("broken.jpg", box) is None
    assert not library.DISPLAY.exists() or not list(library.DISPLAY.iterdir())


def test_a_see_through_picture_is_laid_on_the_backdrop(lib):
    name = picture("glass.png", 4000, 2400, alpha=128)
    assert library.make_display(name, (1920, 1080)) is None   # nothing to lay it on
    file = library.make_display(name, (1920, 1080), "2c2c2c")
    assert file == library.display_name(name, (1920, 1080)) + ".2c2c2c.jpg"
    img = read(file)
    assert not img.hasAlphaChannel()
    c = img.pixelColor(100, 500)   # green (30, 200, 30) at half over #2c2c2c (44, 44, 44)
    assert abs(c.red() - 37) <= 3 and abs(c.green() - 122) <= 3 and abs(c.blue() - 37) <= 3, c.getRgb()
    # Another theme: another copy; an opaque picture's doesn't depend on it.
    assert library.make_display(name, (1920, 1080), "f5f5f5").endswith(".f5f5f5.jpg")
    solid = picture("solid.png", 4000, 2400)
    assert library.make_display(solid, (1920, 1080), "2c2c2c") == library.display_name(solid, (1920, 1080)) + ".jpg"
    assert library.backdrop_hex("#2C2C2C") == "2c2c2c" and library.backdrop_hex("rgb(1, 2, 3)") is None


def test_an_opaque_png_gets_a_jpeg_copy(lib):
    file = library.make_display(picture("opaque.png", 4000, 2400, alpha=255), (1920, 1080))
    assert file and not read(file).hasAlphaChannel()


def test_a_phone_photo_is_turned_and_its_colour_profile_kept(lib):
    # Stored 4000x2400 with "turn 90" in its EXIF: shown 2400x4000, the green half on top.
    name = picture("phone.jpg", 4000, 2400, rotate=True, space=qt.QColorSpace.NamedColorSpace.DisplayP3)
    img = read(library.make_display(name, (1920, 1080)))
    assert (img.width(), img.height()) == (1920, 3200)
    assert img.pixelColor(960, 200).green() > 180 and img.pixelColor(960, 3000).red() > 200
    assert img.colorSpace() == qt.QColorSpace(qt.QColorSpace.NamedColorSpace.DisplayP3)


def test_a_picture_changed_in_place_gets_a_new_copy(lib):
    name = picture("p.jpg", 4000, 2400)
    before = library.display_name(name, (1920, 1080))
    picture("p.jpg", 4200, 2400)
    os.utime(library.IMAGES / name, (1, 1))
    assert library.display_name(name, (1920, 1080)) != before
    assert library.display_name("gone.jpg", (1920, 1080)) is None


def test_copies_go_with_the_picture(lib):
    keep, name = picture("keep.jpg", 4000, 2400), picture("p.jpg", 4000, 2400)
    for n in (keep, name):
        library.make_display(n, (1920, 1080))
        library.make_display(n, (2560, 1440))
    assert len(list(library.DISPLAY.iterdir())) == 4
    library.trash([name])
    assert sorted(p.name.split(".")[0] for p in library.DISPLAY.iterdir()) == ["keep", "keep"]
    library.restore([name])
    library.make_display(name, (1920, 1080))
    library.delete(name)
    assert sorted(p.name.split(".")[0] for p in library.DISPLAY.iterdir()) == ["keep", "keep"]


def test_pruning_keeps_the_copies_used_lately(lib):
    library.DISPLAY.mkdir(parents=True)
    for i in range(4):
        path = library.DISPLAY / f"p{i}.jpg.1920x1080.0000000{i}.jpg"
        path.write_bytes(bytes(100))
        os.utime(path, (1000 + i, 1000 + i))
    (library.DISPLAY / "half.jpg.part").write_bytes(b"x")
    assert library.prune_display(budget=250) == 2
    assert sorted(p.name[:2] for p in library.DISPLAY.iterdir()) == ["p2", "p3"]


def test_display_shows_the_picture_until_its_copy_is_made(lib):
    runs, made = [], []
    display = Display(lambda fn, done: runs.append((fn, done)), lambda: made.append(1))
    name = picture("big.jpg", 4000, 2400)
    assert display.url(name) == library.image_url(name)   # no box yet
    assert display.cover(1920, 1080) and not display.cover(1366, 768)   # only ever grows
    assert display.url(name) == library.image_url(name) == display.url(name)
    assert len(runs) == 1   # asked for once
    fn, done = runs.pop()
    done(fn())
    assert made == [1]
    file = library.display_name(name, (1920, 1080)) + ".jpg"
    assert display.url(name) == library.display_url(file)
    # A bigger screen: the picture itself until the bigger copy is made.
    assert display.cover(2560, 1440)
    assert display.url(name) == library.image_url(name)
    fn, done = runs.pop()
    done(fn())
    assert display.url(name) == library.display_url(library.display_name(name, (2560, 1440)) + ".jpg")


def test_display_remembers_a_picture_that_gets_no_copy(lib):
    runs = []
    display = Display(lambda fn, done: runs.append((fn, done)), lambda: pytest.fail("nothing was made"))
    display.cover(1920, 1080)
    name = picture("small.png", 1600, 1000)
    display.url(name)
    fn, done = runs.pop()
    done(fn())
    assert display.url(name) == library.image_url(name) and not runs


def test_a_screen_bigger_than_every_box_shows_pictures_as_they_are(lib):
    runs = []
    display = Display(lambda fn, done: runs.append((fn, done)), lambda: None)
    assert display.cover(1920, 1080) and display.cover(7680, 4320)
    name = picture("big.jpg", 9000, 5000)
    assert display.url(name) == library.image_url(name) and not runs
    assert not display.cover(1920, 1080)


def test_a_stopped_display_ignores_late_results(lib):
    runs, made = [], []
    display = Display(lambda fn, done: runs.append((fn, done)), lambda: made.append(1))
    display.cover(1920, 1080)
    display.url(picture("big.jpg", 4000, 2400))
    display.stopped = True
    fn, done = runs.pop()
    done(fn())
    assert not made


def test_a_blurred_screens_copy_is_smaller(lib):
    runs = []
    display = Display(lambda fn, done: runs.append((fn, done)), lambda: None)
    display.cover(1920, 1080)
    name = picture("big.jpg", 4000, 2400)
    display.url(name)
    display.url(name, 4)
    while runs:   # the second waits for the first batch
        fn, done = runs.pop(0)
        done(fn())
    assert display.url(name, 4) == library.display_url(library.display_name(name, (480, 270)) + ".jpg")
    assert read(library.display_name(name, (480, 270)) + ".jpg").width() == 480
    assert display.url(name) == library.display_url(library.display_name(name, (1920, 1080)) + ".jpg")
