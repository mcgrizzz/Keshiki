import pytest

anki = pytest.importorskip("anki")
from anki.collection import Collection  # noqa: E402

from keshiki.progress import nothing_left, percent_done  # noqa: E402


@pytest.fixture
def col(tmp_path):
    col = Collection(str(tmp_path / "collection.anki2"))
    yield col
    col.close()


def add_cards(col, deck_name, n):
    did = col.decks.id(deck_name)
    for i in range(n):
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = f"{deck_name} {i}"
        col.add_note(note, did)
    return did


def answer_easy(col):
    card = col.sched.getCard()
    col.sched.answerCard(card, 4)


def test_progress_through_a_deck(col):
    did = add_cards(col, "Japanese", 4)
    add_cards(col, "Other", 4)
    col.decks.select(did)
    assert percent_done(col, did) == 0
    answer_easy(col)
    assert percent_done(col, did) == 25
    # The whole collection: 1 of 8 done.
    assert percent_done(col, None) == 12.5
    for _ in range(3):
        answer_easy(col)
    assert percent_done(col, did) == 100


def test_an_empty_deck_counts_as_finished(col):
    did = col.decks.id("Empty")
    col.decks.select(did)
    assert percent_done(col, did) == 100


def test_nothing_left_once_every_deck_is_done(col):
    did = add_cards(col, "Japanese", 1)
    col.decks.select(did)
    assert not nothing_left(col)
    answer_easy(col)
    assert nothing_left(col)
