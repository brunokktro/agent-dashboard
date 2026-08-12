"""Backlog decision endpoints (v2 parity): autonomy, approve/discuss/reject, delete.

Real markdown files in the fixture ecosystem - the assertions re-read the file
from disk, never trust the HTTP response alone.
"""

from __future__ import annotations

import pytest

ITEM = """---
autonomy: review
agent: meta-agent
priority: high
created: 2026-08-06
---

# Reclaim stale locks

## Problem

Locks survive SIGKILL.
"""

NOTE = """---
status: pending-review
item: reclaim-stale-locks.md
---

# Review note

## What the agent found

The trap never runs on SIGKILL.

## Proposed plan

Age-based reclaim.
"""


@pytest.fixture()
def backlog(ecosystem):
    base = ecosystem.agents_dir / "backlog"
    (base / "review-notes").mkdir(parents=True)
    (base / "done").mkdir()
    (base / "reclaim-stale-locks.md").write_text(ITEM)
    (base / "review-notes" / "reclaim-stale-locks.md").write_text(NOTE)
    (base / "done" / "shipped-item.md").write_text(ITEM.replace("review", "auto"))
    return base


def test_autonomy_change_rewrites_frontmatter(client, backlog):
    r = client.post("/api/backlog/autonomy",
                    json={"file": "reclaim-stale-locks.md", "autonomy": "blocked"})
    assert r.status_code == 200
    assert "autonomy: blocked" in (backlog / "reclaim-stale-locks.md").read_text()


def test_autonomy_rejects_invalid_value_and_traversal(client, backlog):
    assert client.post("/api/backlog/autonomy",
                       json={"file": "reclaim-stale-locks.md", "autonomy": "yolo"}
                       ).status_code == 422
    assert client.post("/api/backlog/autonomy",
                       json={"file": "../secrets.md", "autonomy": "auto"}
                       ).status_code == 400


def test_approve_flips_item_to_auto(client, backlog):
    r = client.post("/api/backlog/review-note/approve",
                    json={"file": "reclaim-stale-locks.md"})
    assert r.status_code == 200
    text = (backlog / "reclaim-stale-locks.md").read_text()
    assert "autonomy: auto" in text and "autonomy: review" not in text


def test_discuss_sets_status_and_records_feedback(client, backlog):
    r = client.post("/api/backlog/review-note/discuss",
                    json={"file": "reclaim-stale-locks.md", "feedback": "margin too tight"})
    assert r.status_code == 200
    note = (backlog / "review-notes" / "reclaim-stale-locks.md").read_text()
    assert "status: discussing" in note
    assert "## Human feedback" in note and "margin too tight" in note
    # a second discuss REPLACES the feedback section instead of stacking
    client.post("/api/backlog/review-note/discuss",
                json={"file": "reclaim-stale-locks.md", "feedback": "second round"})
    note = (backlog / "review-notes" / "reclaim-stale-locks.md").read_text()
    assert note.count("## Human feedback") == 1 and "second round" in note


def test_discuss_requires_feedback(client, backlog):
    assert client.post("/api/backlog/review-note/discuss",
                       json={"file": "reclaim-stale-locks.md", "feedback": "  "}
                       ).status_code == 422


def test_reject_sets_status_and_optional_reason(client, backlog):
    r = client.post("/api/backlog/review-note/reject",
                    json={"file": "reclaim-stale-locks.md", "reason": "not worth it"})
    assert r.status_code == 200
    note = (backlog / "review-notes" / "reclaim-stale-locks.md").read_text()
    assert "status: rejected" in note and "not worth it" in note


def test_delete_moves_item_and_note_with_timestamp(client, backlog):
    r = client.post("/api/backlog/delete",
                    json={"file": "reclaim-stale-locks.md", "bucket": "active"})
    assert r.status_code == 200 and r.json()["note_moved"] is True
    assert not (backlog / "reclaim-stale-locks.md").exists()
    assert not (backlog / "review-notes" / "reclaim-stale-locks.md").exists()
    trashed = list((backlog / "deleted").glob("reclaim-stale-locks-*.md"))
    note_trashed = list((backlog / "review-notes" / "deleted").glob("reclaim-stale-locks-*.md"))
    assert len(trashed) == 1 and len(note_trashed) == 1
    # content preserved (soft delete, reversible)
    assert "Locks survive SIGKILL" in trashed[0].read_text()


def test_delete_from_done_bucket(client, backlog):
    r = client.post("/api/backlog/delete",
                    json={"file": "shipped-item.md", "bucket": "done"})
    assert r.status_code == 200
    assert not (backlog / "done" / "shipped-item.md").exists()


def test_actions_404_on_missing_files(client, backlog):
    for path, body in [
        ("/api/backlog/autonomy", {"file": "ghost.md", "autonomy": "auto"}),
        ("/api/backlog/review-note/approve", {"file": "ghost.md"}),
        ("/api/backlog/review-note/discuss", {"file": "ghost.md", "feedback": "x"}),
        ("/api/backlog/review-note/reject", {"file": "ghost.md"}),
        ("/api/backlog/delete", {"file": "ghost.md"}),
    ]:
        assert client.post(path, json=body).status_code == 404, path


# ── Reorder (kanban drag-and-drop persistence) ──────────────────────


@pytest.fixture()
def board(ecosystem):
    """Three active items, one already carrying an order field."""
    base = ecosystem.agents_dir / "backlog"
    base.mkdir(parents=True, exist_ok=True)
    (base / "alpha.md").write_text("---\nautonomy: review\n---\n\n# Alpha\n")
    (base / "beta.md").write_text("---\nautonomy: review\norder: 7\n---\n\n# Beta\n")
    (base / "gamma.md").write_text("---\nautonomy: review\n---\n\n# Gamma\n")
    return base


def test_reorder_persists_order_in_frontmatter(client, board):
    r = client.post("/api/backlog/reorder",
                    json={"files": ["gamma.md", "alpha.md", "beta.md"]})
    assert r.status_code == 200 and r.json() == {"ok": True, "updated": 3}
    assert "order: 0" in (board / "gamma.md").read_text()
    assert "order: 1" in (board / "alpha.md").read_text()
    assert "order: 2" in (board / "beta.md").read_text()


def test_reorder_overwrites_preexisting_order(client, board):
    client.post("/api/backlog/reorder", json={"files": ["beta.md"]})
    text = (board / "beta.md").read_text()
    assert "order: 0" in text and "order: 7" not in text
    assert text.count("order:") == 1


def test_reorder_skips_missing_files_without_failing(client, board):
    r = client.post("/api/backlog/reorder",
                    json={"files": ["alpha.md", "ghost.md", "beta.md"]})
    assert r.status_code == 200 and r.json()["updated"] == 2


def test_reorder_rejects_path_traversal_before_writing(client, board):
    original = (board / "alpha.md").read_text()
    r = client.post("/api/backlog/reorder",
                    json={"files": ["alpha.md", "../secrets.md"]})
    assert r.status_code == 400
    # atomic rejection: nothing was written, not even the valid first entry
    assert (board / "alpha.md").read_text() == original


def test_reorder_requires_files(client, board):
    assert client.post("/api/backlog/reorder", json={"files": []}).status_code == 422


def test_backlog_listing_respects_order(client, board):
    client.post("/api/backlog/reorder",
                json={"files": ["gamma.md", "beta.md", "alpha.md"]})
    # a fourth item with no order lands at the end, tie-broken by name
    (board / "delta.md").write_text("---\nautonomy: review\n---\n\n# Delta\n")
    files = [i["file"] for i in client.get("/api/backlog").json()["active"]]
    assert files == ["gamma.md", "beta.md", "alpha.md", "delta.md"]
