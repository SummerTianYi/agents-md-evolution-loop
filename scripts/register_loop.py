#!/usr/bin/env python3
"""Register a user-level persistent loop without requiring administrator rights."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
from pathlib import Path

from platform_support import platform_name


def windows_startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def write_windows_startup(root: Path, skill_dir: Path) -> Path:
    path = windows_startup_dir() / f"codex-agents-evolution-{root.name}.cmd"
    if path.exists():
        raise SystemExit(f"startup entry already exists: {path}; refusing to replace it")
    path.write_text(
        "@echo off\r\n"
        f'start "Codex AGENTS Evolution" /b python "{skill_dir / "scripts" / "loop_daemon.py"}" --root "{root}" --once\r\n',
        encoding="utf-8",
    )
    return path


def write_macos_launch_agent(root: Path, skill_dir: Path) -> Path:
    label = f"com.codex.agents-md-evolution.{root.name}"
    path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if path.exists():
        raise SystemExit(f"LaunchAgent already exists: {path}; refusing to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": label,
        "ProgramArguments": ["/usr/bin/env", "python3", str(skill_dir / "scripts" / "loop_daemon.py"), "--root", str(root), "--once"],
        "RunAtLoad": True,
        "StandardOutPath": str(root / "logs" / "loop.log"),
        "StandardErrorPath": str(root / "logs" / "loop-error.log"),
    }
    with path.open("wb") as handle:
        plistlib.dump(plist, handle)
    return path


def load_macos_launch_agent(path: Path) -> None:
    domain = f"gui/{os.getuid()}"
    loaded = subprocess.run(["launchctl", "bootstrap", domain, str(path)], text=True, capture_output=True, check=False)
    if loaded.returncode:
        raise SystemExit(loaded.stderr.strip() or loaded.stdout.strip() or "launchctl bootstrap failed")
    label = path.stem
    verified = subprocess.run(["launchctl", "print", f"{domain}/{label}"], text=True, capture_output=True, check=False)
    if verified.returncode:
        raise SystemExit(verified.stderr.strip() or verified.stdout.strip() or "LaunchAgent was not loaded")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    root.joinpath("logs").mkdir(exist_ok=True)
    platform = platform_name()
    if platform == "windows":
        entry = write_windows_startup(root, Path(config["skill_dir"])) if args.install else None
    elif platform == "macos":
        entry = write_macos_launch_agent(root, Path(config["skill_dir"])) if args.install else None
        if entry:
            load_macos_launch_agent(entry)
    else:
        raise SystemExit(f"unsupported platform: {platform}")
    manifest = {"platform": platform, "entry": str(entry) if entry else None, "installed": bool(args.install), "loaded": bool(entry) if platform == "macos" else None, "schedule": config["schedule"], "delivery": "requires_codex_gmail_task"}
    (root / "scheduler.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
