#!/usr/bin/env python3
"""Read A2A handoff audit history. Latest event per id wins."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT = Path.home() / ".kiro/agents/shared-memory/handoffs.jsonl"


def parse_ts(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def latest_rows(path, now=None, to="", status=""):
    now = now or datetime.now(timezone.utc)
    latest = {}
    metadata = {}
    if not Path(path).exists():
        return []
    with Path(path).open(errors="replace") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
                ident = row["id"]
                created = parse_ts(row["ts"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if ident not in metadata or row.get("timeout_sec") is not None:
                metadata.setdefault(ident, {}).update(
                    {
                        "timeout_sec": row.get("timeout_sec"),
                        "request_ts": row.get("ts"),
                        "from": row.get("from"),
                        "to": row.get("to"),
                        "skill": row.get("skill"),
                        "expected_output": row.get("expected_output"),
                    }
                )
            if ident not in latest or created >= parse_ts(latest[ident]["ts"]):
                latest[ident] = row
    out = []
    for ident, row in latest.items():
        # Request metadata wins for routing fields; latest event wins for status/result.
        # Completion events may be authored by the worker, but the handoff remains FROM the
        # requester TO the target agent.
        merged = {**row, **metadata.get(ident, {})}
        merged["status"] = row.get("status", merged.get("status"))
        if "result" in row:
            merged["result"] = row["result"]
        if merged.get("status") in {"pending", "running"}:
            base = parse_ts(metadata.get(ident, {}).get("request_ts") or merged["ts"])
            timeout = int(metadata.get(ident, {}).get("timeout_sec") or 600)
            if now > base + timedelta(seconds=timeout):
                merged["status"] = "stale"
        if to and str(merged.get("to", "")) != to:
            continue
        if status and merged.get("status") != status:
            continue
        out.append(merged)
    return sorted(out, key=lambda x: parse_ts(x["ts"]), reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--to", default="")
    ap.add_argument("--status", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = latest_rows(args.file, to=args.to, status=args.status)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(
                f"{row['id']} | {row.get('status')} | {row.get('from')} -> {row.get('to')} | {row.get('skill', '')}"
            )
            if row.get("result"):
                print(f"  {row['result']}")
    return 1 if any(row.get("status") == "stale" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
