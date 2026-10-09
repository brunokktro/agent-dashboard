#!/usr/bin/env python3
"""Read active inter-agent discoveries without loading the JSONL into memory."""

import argparse
import json
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_FILE = Path.home() / ".kiro/agents/shared-memory/discoveries.jsonl"
DEFAULT_STATE = (
    Path.home() / ".kiro/agents-state/shared-memory/discovery-watermarks.json"
)


def _load_watermarks(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_watermarks(path, state):
    """Atomic replace: crash never leaves a half-written cursor file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def parse_ts(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def active_rows(
    path, now=None, query="", limit=50, since_hours=168, after=None, consumer=""
):
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=since_hours)
    after_dt = parse_ts(after) if after else None
    query = query.casefold().strip()
    consumer = consumer.casefold().strip()
    rows = deque(maxlen=limit)
    if not Path(path).exists():
        return []
    with Path(path).open(errors="replace") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
                created = parse_ts(row["ts"])
                expires = created + timedelta(days=int(row.get("ttl_days", 30)))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            if created < since or expires < now:
                continue
            if after_dt and created <= after_dt:
                continue
            audience = row.get("to") or []
            if isinstance(audience, str):
                audience = [audience]
            if (
                consumer
                and audience
                and consumer not in {str(x).casefold() for x in audience}
            ):
                continue
            haystack = " ".join(
                str(row.get(k, "")) for k in ("from", "topic", "content")
            ).casefold()
            if query and query not in haystack:
                continue
            rows.append(row)
    return list(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--query", default="")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--since-hours", type=int, default=168)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--consumer",
        default="",
        help="consumer id; filters targeted rows and resumes after its watermark",
    )
    ap.add_argument(
        "--ack",
        action="store_true",
        help="advance this consumer watermark through the newest returned row",
    )
    ap.add_argument("--state-file", default=str(DEFAULT_STATE))
    args = ap.parse_args()
    if args.ack and not args.consumer:
        ap.error("--ack requires --consumer")
    marks = _load_watermarks(args.state_file)
    after = marks.get(args.consumer) if args.consumer else None
    rows = active_rows(
        args.file,
        query=args.query,
        limit=args.limit,
        since_hours=args.since_hours,
        after=after,
        consumer=args.consumer,
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['ts']} | {row.get('from', '?')} | {row.get('topic', '?')}")
            print(f"  {row.get('content', '')}")
    if args.ack and rows:
        newest = max(rows, key=lambda row: parse_ts(row["ts"]))["ts"]
        marks[args.consumer] = newest
        _save_watermarks(args.state_file, marks)
        print(f"ACK {args.consumer} through {newest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
