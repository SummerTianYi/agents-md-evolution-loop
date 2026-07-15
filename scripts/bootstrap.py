#!/usr/bin/env python3
"""Create an instance, register its loop, and run the first safe audit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from platform_support import subprocess_environment


SKILL_DIR = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, encoding="utf-8", capture_output=True, env=subprocess_environment(), check=False)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    print(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gmail-sender", required=True)
    parser.add_argument("--gmail-recipient", required=True)
    parser.add_argument("--preference-profile", choices=("neutral", "michael"), default="neutral")
    parser.add_argument("--install-local-audit-daemon", action="store_true")
    parser.add_argument("--install-schedule", dest="install_local_audit_daemon", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()
    create = [sys.executable, str(SKILL_DIR / "scripts" / "init_instance.py"), "create", "--root", str(args.root), "--gmail-sender", args.gmail_sender, "--gmail-recipient", args.gmail_recipient, "--preference-profile", args.preference_profile, "--confirmed"]
    run(create)
    schedule = [sys.executable, str(SKILL_DIR / "scripts" / "register_loop.py"), "--root", str(args.root)]
    if args.install_local_audit_daemon:
        schedule.append("--install")
    run(schedule)
    if args.run_once:
        run([sys.executable, str(SKILL_DIR / "scripts" / "run_loop.py"), "--root", str(args.root), "--force-audit", "--run-mode", "onboarding_test"])


if __name__ == "__main__":
    main()
