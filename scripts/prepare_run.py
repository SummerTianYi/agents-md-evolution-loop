#!/usr/bin/env python3
"""Prepare a baseline or new-model AGENTS.md audit run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "codex-model"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--active-file", type=Path, required=True)
    parser.add_argument("--force-audit", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    state_path = root / "state.json"
    active_file = args.active_file.expanduser().resolve()
    if not state_path.is_file():
        raise SystemExit(f"missing state file: {state_path}")
    if not active_file.is_file():
        raise SystemExit(f"missing active AGENTS.md: {active_file}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    model_id = args.model_id.strip()
    if not model_id:
        raise SystemExit("model ID must not be empty")

    now = datetime.now(timezone.utc)
    checked_at = now.isoformat(timespec="seconds")
    active_sha = sha256(active_file)
    previous_model = state.get("last_seen_model")
    pending_run = state.get("pending_run")
    state.update({"last_checked_at": checked_at, "active_agents_sha256": active_sha, "last_source_url": args.source_url})

    if previous_model is None and not args.force_audit:
        state.update({"last_seen_model": model_id, "status": "baseline"})
        write_json_atomic(state_path, state)
        print(json.dumps({"action": "baseline", "model_id": model_id, "checked_at": checked_at}))
        return
    if model_id == previous_model and pending_run and not args.force_audit:
        state["status"] = "candidate_pending"
        write_json_atomic(state_path, state)
        print(json.dumps({"action": "pending", "model_id": model_id, "run_dir": pending_run}))
        return
    if model_id == previous_model and not args.force_audit:
        state["status"] = "no_change"
        write_json_atomic(state_path, state)
        print(json.dumps({"action": "no_change", "model_id": model_id, "checked_at": checked_at}))
        return

    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / "runs" / f"{timestamp}-{slugify(model_id)}"
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(active_file, run_dir / "original.md")
    run = {
        "schema_version": 2,
        "created_at": checked_at,
        "previous_model": previous_model,
        "model_id": model_id,
        "source_url": args.source_url,
        "active_file": str(active_file),
        "original_sha256": active_sha,
        "status": "candidate_required",
    }
    write_json_atomic(run_dir / "run.json", run)
    state.update({"last_seen_model": model_id, "pending_run": str(run_dir), "status": "candidate_required"})
    write_json_atomic(state_path, state)
    print(json.dumps({"action": "new_model", "model_id": model_id, "run_dir": str(run_dir)}))


if __name__ == "__main__":
    main()
