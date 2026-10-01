"""How much of today's studying is done, for progress scenes."""

from __future__ import annotations

from typing import Optional

from anki.collection import Collection
from anki.utils import ids2str


def percent_done(col: Collection, did: Optional[int]) -> float:
    """Percent of today's cards done in deck `did` and its subdecks, or in the
    whole collection when did is None. Cards studied today count as done and
    cards still due as left, so it reads the same after a restart; nothing
    left at all is 100."""
    if did is None:
        tree = col.sched.deck_due_tree()
        left = sum(c.new_count + c.learn_count + c.review_count for c in tree.children)
        deck_filter = ""
    else:
        left = sum(col.sched.counts())
        dids = ids2str(col.decks.deck_and_child_ids(did))
        deck_filter = f"and cid in (select id from cards where did in {dids} or odid in {dids})"
    if left == 0:
        return 100.0
    day_start_ms = (col.sched.day_cutoff - 86400) * 1000
    # Types 0-3 are learning, review, relearning and filtered-deck answers;
    # manual reschedules don't count as studying.
    done = col.db.scalar(
        f"select count(distinct cid) from revlog where id > ? and type < 4 {deck_filter}", day_start_ms) or 0
    return 100.0 * done / (done + left)


def nothing_left(col: Collection) -> bool:
    """Whether every deck is done for today: no new, learning or review cards left."""
    tree = col.sched.deck_due_tree()
    return not any(c.new_count or c.learn_count or c.review_count for c in tree.children)
