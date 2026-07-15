#!/usr/bin/env python3
"""Record the Codex Automation created for an evolution instance."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--automation-id", required=True)
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    manifest_path = root / "instance.json"
    if not manifest_path.is_file():
        raise SystemExit(f"missing instance manifest: {manifest_path}")
    automation_id = args.automation_id.strip()
    if not automation_id:
        raise SystemExit("automation ID must not be empty")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "automation_created": True,
            "automation_id": automation_id,
            "automation_status": "ACTIVE",
            "automation_recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    print(json.dumps({"automation_created": True, "automation_id": automation_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
