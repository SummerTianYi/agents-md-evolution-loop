#!/usr/bin/env python3
"""Run local audits on a schedule and queue, but never perform, email delivery."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from platform_support import subprocess_environment


WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def next_run(weekdays: list[str], times: list[str], now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    candidates = []
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in {WEEKDAYS[value] for value in weekdays}:
            continue
        for value in times:
            hour, minute = (int(part) for part in value.split(":"))
            candidate = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
            if candidate > now:
                candidates.append(candidate)
    return min(candidates)


def result_from_stdout(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "action" in value:
            return value
    raise RuntimeError("run_loop did not return a JSON result")


def delivery_request_id(result: dict) -> str:
    if result.get("run_dir"):
        return Path(result["run_dir"]).name
    checked_at = str(result.get("checked_at", "unknown")).replace(":", "").replace("+", "_")
    return f"{result.get('action', 'event')}-{result.get('model_id', 'unknown')}-{checked_at}"


def queue_delivery(root: Path, result: dict) -> Path | None:
    root = root.resolve()
    if result.get("action") not in {"baseline", "report", "failure"}:
        return None
    report_path = result.get("report_path")
    if not report_path:
        return None
    report = Path(report_path).expanduser().resolve()
    if not report.is_relative_to(root) or not report.is_file():
        raise RuntimeError("delivery report must be an existing file inside the instance root")
    queue = root / "delivery-requests"
    queue.mkdir(parents=True, exist_ok=True)
    request_path = queue / f"{delivery_request_id(result)}.json"
    if request_path.exists():
        return request_path
    request = {
        "schema_version": 1,
        "status": "pending_gmail_delivery",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": result.get("event", result["action"]),
        "run_id": delivery_request_id(result),
        "report_path": str(report),
        "result": result,
    }
    temporary = request_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(request_path)
    return request_path


def run_once(root: Path, config: dict) -> dict:
    log = root / "logs" / "loop.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(config["skill_dir"]) / "scripts" / "run_loop.py"), "--root", str(root)]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=subprocess_environment(), check=False)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] exit={result.returncode}\n")
        handle.write(result.stdout)
        handle.write(result.stderr)
    outcome = result_from_stdout(result.stdout)
    request = queue_delivery(root, outcome)
    if request:
        outcome["delivery_request_path"] = str(request)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    root.joinpath("logs").mkdir(exist_ok=True)
    run_once(root, config)
    if args.once:
        return
    while True:
        delay = max(1, int((next_run(config["schedule"]["weekdays"], config["schedule"]["times"]) - datetime.now().astimezone()).total_seconds()))
        time.sleep(delay)
        run_once(root, config)


if __name__ == "__main__":
    main()
