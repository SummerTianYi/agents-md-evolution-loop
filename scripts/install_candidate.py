#!/usr/bin/env python3
"""Install one explicitly approved candidate with stale-run and rollback protection."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    if not args.approved:
        raise SystemExit("installation requires explicit named-Run approval and --approved")

    root = args.root.expanduser().resolve()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if config.get("auto_install") is not False:
        raise SystemExit("auto_install must remain false")
    run_dir = (root / "runs" / args.run_id).resolve()
    if run_dir.parent != (root / "runs").resolve() or not run_dir.is_dir():
        raise SystemExit("invalid or missing Run ID")
    run_path = run_dir / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("status") != "candidate_pending" or run.get("reviewer_verdict") != "approve":
        raise SystemExit("run is not in an installable reviewed state")
    candidate = run_dir / "candidate.md"
    active = Path(config["active_agents_path"]).expanduser().resolve()
    if not candidate.is_file() or not active.is_file():
        raise SystemExit("candidate or active AGENTS.md is missing")
    active_before = sha256(active)
    if active_before != run.get("original_sha256"):
        run.update({"status": "stale_candidate", "stale_active_sha256": active_before})
        write_json(run_path, run)
        raise SystemExit("active AGENTS.md changed since the audit; candidate invalidated")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / "backups" / f"AGENTS.md.{timestamp}.before-{args.run_id}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(active, backup)
    temporary = active.with_name(active.name + f".tmp-{timestamp}")
    try:
        shutil.copy2(candidate, temporary)
        temporary.replace(active)
        expected = sha256(candidate)
        installed = sha256(active)
        if installed != expected or active.read_bytes() != candidate.read_bytes():
            raise RuntimeError("post-install content verification failed")
    except Exception:
        if temporary.exists():
            failed_temporary = root / "backups" / f"AGENTS.md.{timestamp}.failed-install-temp-{args.run_id}"
            temporary.replace(failed_temporary)
        shutil.copy2(backup, active)
        raise

    installed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run.update({"status": "installed", "installed_at": installed_at, "backup_path": str(backup), "installed_sha256": installed})
    write_json(run_path, run)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "last_installed_model": run.get("model_id"),
        "last_installed_run": args.run_id,
        "active_agents_sha256": installed,
        "pending_run": None,
        "status": "installed",
    })
    write_json(state_path, state)
    report = run_dir / "installation-report.md"
    report.write_text(
        "# AGENTS.md 安装完成报告\n\n"
        f"- Run ID：`{args.run_id}`\n"
        f"- 安装时间：`{installed_at}`\n"
        f"- 活动文件：`{active}`\n"
        f"- 安装后 SHA-256：`{installed}`\n"
        f"- 备份文件：`{backup}`\n\n"
        "已核对安装后内容与获批候选完全一致。\n",
        encoding="utf-8",
    )
    print(json.dumps({"action": "installed", "run_id": args.run_id, "active_file": str(active), "backup": str(backup), "sha256": installed, "report_path": str(report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
