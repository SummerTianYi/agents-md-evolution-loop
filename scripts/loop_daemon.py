#!/usr/bin/env python3
"""Run one Codex loop immediately and at configured local weekday times."""

from __future__ import annotations

import argparse
import json
import subprocess
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


def run_once(root: Path, config: dict) -> None:
    prompt = (root / "automation-prompt.md").read_text(encoding="utf-8")
    log = root / "logs" / "loop.log"
    command = [config["codex_executable"], "exec", "--cd", str(root), "--skip-git-repo-check", "--sandbox", "workspace-write", "--ephemeral", "-"]
    result = subprocess.run(command, input=prompt, text=True, encoding="utf-8", errors="replace", capture_output=True, env=subprocess_environment(), check=False)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] exit={result.returncode}\n")
        handle.write(result.stdout)
        handle.write(result.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    root.joinpath("logs").mkdir(exist_ok=True)
    run_once(root, config)
    while True:
        delay = max(1, int((next_run(config["schedule"]["weekdays"], config["schedule"]["times"]) - datetime.now().astimezone()).total_seconds()))
        time.sleep(delay)
        run_once(root, config)


if __name__ == "__main__":
    main()
