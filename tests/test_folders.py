import shutil

import pytest

from keshiki import library


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """The library's folders, in a temporary user_files."""
    for attr in ("IMAGES", "THUMBS", "FOLDERS"):
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
