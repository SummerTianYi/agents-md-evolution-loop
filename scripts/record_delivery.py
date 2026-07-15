#!/usr/bin/env python3
"""Record non-sensitive Gmail delivery evidence for one loop event."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--verified", action="store_true")
    args = parser.parse_args()
    if not args.verified:
        raise SystemExit("delivery may only be recorded after Sent verification")
    root = args.root.expanduser().resolve()
    path = root / "delivery-log.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    entries.append({"event": args.event, "run_id": args.run_id, "subject": args.subject, "message_id": args.message_id, "sent_verified": args.verified, "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    queued = root / "delivery-requests" / f"{args.run_id}.json"
    if queued.is_file():
        request = json.loads(queued.read_text(encoding="utf-8"))
        request.update({"status": "sent_verified", "sent_verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "message_id": args.message_id})
        queued.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
