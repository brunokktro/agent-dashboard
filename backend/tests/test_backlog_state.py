"""Backlog execution state: an item being worked on, and one that failed.

The v2 dashboard drew "Running: Agent" and "Failed" columns for the backlog, but
they were never populated - its collector only ever read `backlog/` (inbox) and
`backlog/done/`. So this is not a port of dead UI: it is the contract those
columns were meant to have.

Contract, deliberately the smallest thing that works with what already exists:
a `state:` field in the item's own frontmatter, written by whoever executes it.
No new directory, no second source of truth - the file stays exactly where it is,
so a reorder, a review note and a soft delete keep working untouched.
"""
from __future__ import annotations

import pytest

ITEM = """---
autonomy: review
agent: meta-agent
priority: high
created: 2026-08-18
---

# Reclaim stale locks
"""


@pytest.fixture()
def board(ecosystem):
    base = ecosystem.agents_dir / "backlog"
    (base / "done").mkdir(parents=True)
    (base / "review-notes").mkdir()
    (base / "idle.md").write_text(ITEM)
    auto = "autonomy: auto"
    (base / "working.md").write_text(
        ITEM.replace("autonomy: review", f"{auto}\nstate: running"))
    (base / "broken.md").write_text(
        ITEM.replace("autonomy: review", f"{auto}\nstate: failed"))
    (base / "done" / "shipped.md").write_text(ITEM)
    return base


def test_state_is_read_from_frontmatter(client, board):
    d = client.get("/api/backlog").json()
    assert [i["file"] for i in d["active"]] == ["idle.md"], "only idle items are active"
    assert [i["file"] for i in d["running"]] == ["working.md"]
    assert [i["file"] for i in d["failed"]] == ["broken.md"]
    assert [i["file"] for i in d["done"]] == ["shipped.md"]


def test_unknown_state_stays_active_rather_than_disappearing(client, board):
    """A typo in someone's frontmatter must not make their item vanish."""
    (board / "typo.md").write_text(ITEM.replace("autonomy: review", "state: runnnning"))
    files = [i["file"] for i in client.get("/api/backlog").json()["active"]]
    assert "typo.md" in files


def test_set_state_writes_frontmatter_and_is_reversible(client, board):
    r = client.post("/api/backlog/state", json={"file": "idle.md", "state": "running"})
    assert r.status_code == 200
    assert "state: running" in (board / "idle.md").read_text()
    d = client.get("/api/backlog").json()
    assert [i["file"] for i in d["running"]] == ["idle.md", "working.md"]

    # back to the board: the field is cleared, not left as a dangling value
    r = client.post("/api/backlog/state", json={"file": "idle.md", "state": "active"})
    assert r.status_code == 200
    text = (board / "idle.md").read_text()
    assert "state:" not in text, "returning to active must clear the field"
    assert "autonomy: review" in text, "the rest of the frontmatter is untouched"


def test_editing_frontmatter_does_not_reformat_the_body(client, board):
    """The item belongs to whoever wrote it: an edit touches the one field and
    leaves the document alone. A greedy delimiter match used to eat the blank
    line after the frontmatter on every write."""
    before = (board / "idle.md").read_text()
    client.post("/api/backlog/state", json={"file": "idle.md", "state": "running"})
    client.post("/api/backlog/state", json={"file": "idle.md", "state": "active"})
    assert (board / "idle.md").read_text() == before, "round trip must be byte-identical"


def test_set_state_rejects_garbage_and_traversal(client, board):
    assert client.post("/api/backlog/state",
                       json={"file": "idle.md", "state": "yolo"}).status_code == 422
    assert client.post("/api/backlog/state",
                       json={"file": "../secrets.md", "state": "running"}).status_code == 400
    assert client.post("/api/backlog/state",
                       json={"file": "ghost.md", "state": "running"}).status_code == 404


def test_running_and_failed_items_keep_their_review_note_flow(client, board):
    """State is orthogonal to the decision flow - a failed item can still be
    approved, discussed or rejected."""
    (board / "review-notes" / "broken.md").write_text(
        "---\nstatus: pending-review\n---\n\n# Note\n")
    r = client.post("/api/backlog/review-note/discuss",
                    json={"file": "broken.md", "feedback": "retry with a longer timeout"})
    assert r.status_code == 200
    note = (board / "review-notes" / "broken.md").read_text()
    assert "status: discussing" in note and "longer timeout" in note
