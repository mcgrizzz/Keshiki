import shutil

import pytest

from keshiki import folders, library


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """The library's folders, in a temporary user_files."""
    for attr in ("IMAGES", "THUMBS", "FOLDERS", "TRASH"):
        monkeypatch.setattr(library, attr, tmp_path / "user_files" / attr.lower())
    return tmp_path


def make_folder(base, *names):
    for name in names:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not really a picture")
    return base


def test_a_linked_folder_is_read_live(lib):
    photos = make_folder(lib / "Photos", "b.png", "a.JPG", "notes.txt", ".hidden.png", "trip/c.webp")
    link = library.link_folder(str(photos))
    assert library.scan_link(link, str(photos), subfolders=False) == [f"@{link}/a.JPG", f"@{link}/b.png"]
    assert library.scan_link(link, str(photos), subfolders=True) == [
        f"@{link}/a.JPG", f"@{link}/b.png", f"@{link}/trip/c.webp"]
    # Pictures added to the folder appear on the next scan.
    make_folder(photos, "d.png")
    assert f"@{link}/d.png" in library.scan_link(link, str(photos), subfolders=False)
    name = f"@{link}/trip/c.webp"
    assert library.image_path(name).read_bytes() == b"not really a picture"
    assert library.image_url(name).endswith(f"/user_files/folders/{link}/trip/c.webp")


def test_a_changed_picture_gets_fresh_thumbnails(lib):
    photos = make_folder(lib / "Photos", "a.png")
    link = library.link_folder(str(photos))
    name = f"@{link}/a.png"
    before = library._thumb_name(name)
    (photos / "a.png").write_bytes(b"a different picture, longer than before")
    assert library._thumb_name(name) != before and "/" not in before


def test_a_missing_folder_scans_as_none_and_a_lost_link_comes_back(lib):
    photos = make_folder(lib / "Photos", "a.png")
    link = library.link_folder(str(photos))
    shutil.rmtree(photos)
    assert library.scan_link(link, str(photos), subfolders=False) is None
    make_folder(photos, "a.png")
    library.unlink_folder(link)                       # e.g. user_files restored without its links
    assert library.scan_link(link, str(photos), subfolders=False) == [f"@{link}/a.png"]


def test_removing_links_never_touches_the_pictures(lib):
    photos = make_folder(lib / "Photos", "a.png", "trip/b.png")
    keep = library.link_folder(str(photos))
    drop = library.link_folder(str(photos))
    library.prune_links([keep])
    assert not (library.FOLDERS / drop).exists() and (library.FOLDERS / keep).is_dir()
    # Uninstalling deletes user_files (send2trash, or rmtree without a trash): links go,
    # the folder they point to stays whole.
    shutil.rmtree(library.FOLDERS.parent)
    assert (photos / "a.png").is_file() and (photos / "trip" / "b.png").is_file()


def test_the_trash_keeps_pictures_until_it_is_emptied(lib):
    library.IMAGES.mkdir(parents=True)
    library.THUMBS.mkdir(parents=True)
    for name in ("a.png", "b.png"):
        (library.IMAGES / name).write_bytes(name.encode())
        (library.THUMBS / library._thumb_name(name)).write_bytes(b"thumb")
    assert library.trash(["a.png", "gone.png"]) == ["a.png"]
    assert not (library.IMAGES / "a.png").exists() and [t["name"] for t in library.list_trash()] == ["a.png"]
    assert library.list_trash()[0]["thumb"].endswith("/thumbs/a.png.jpg")
    # A second a.png in the trash gets a name of its own, and its thumbnail follows it.
    (library.IMAGES / "a.png").write_bytes(b"another a")
    (library.THUMBS / library._thumb_name("a.png")).write_bytes(b"thumb 2")
    assert library.trash(["a.png"]) == ["a-2.png"]
    assert (library.THUMBS / library._thumb_name("a-2.png")).read_bytes() == b"thumb 2"
    assert library.restore(["a.png"]) == ["a.png"] and (library.IMAGES / "a.png").read_bytes() == b"a.png"
    assert library.empty_trash() == 1
    assert library.list_trash() == [] and not (library.THUMBS / library._thumb_name("a-2.png")).exists()
    assert sorted(p.name for p in library.IMAGES.iterdir()) == ["a.png", "b.png"]


def test_a_hidden_picture_stays_in_the_folder_but_out_of_the_album(lib):
    photos = make_folder(lib / "Photos", "a.png", "b.png", "c.png")
    link = library.link_folder(str(photos))
    album = {"id": "x", "kind": "album", "versions": [],
             "folder": {"path": str(photos), "link": link, "subfolders": False, "hidden": [f"@{link}/b.png"]}}
    cfg = {"scenes": [album]}
    assert folders.refresh(cfg) == (True, [])
    assert [v["image"] for v in album["versions"]] == [f"@{link}/a.png", f"@{link}/c.png"]
    assert (photos / "b.png").is_file() and f"@{link}/b.png" in folders.pictures(cfg)
    # Gone from the folder, it's forgotten as hidden too.
    (photos / "b.png").unlink()
    assert folders.refresh(cfg) == (True, []) and album["folder"]["hidden"] == []
