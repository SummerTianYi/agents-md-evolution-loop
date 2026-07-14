"""Small OS boundary for the Codex-only evolution loop."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def platform_name() -> str:
    return "windows" if os.name == "nt" else "macos" if platform.system() == "Darwin" else "linux"


def find_codex_executable() -> str | None:
    names = ("codex.cmd", "codex.exe", "codex") if os.name == "nt" else ("codex",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def normalize_executable(value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute() or path.parent != Path("."):
        return str(path.resolve())
    return value


def subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def detect_timezone() -> tuple[str | None, str]:
    configured = os.environ.get("TZ", "").strip()
    if configured:
        return configured, "TZ environment variable"
    timezone = datetime.now().astimezone().tzinfo
    key = getattr(timezone, "key", None)
    if key:
        return key, "Python system zoneinfo"
    if os.name == "nt":
        result = subprocess.run(["tzutil", "/g"], text=True, capture_output=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), "Windows tzutil"
    localtime = Path("/etc/localtime")
    try:
        resolved = str(localtime.resolve())
        for marker in ("/zoneinfo/", "/zoneinfo.default/"):
            if marker in resolved:
                return resolved.split(marker, 1)[1], "/etc/localtime"
    except OSError:
        pass
    return (str(timezone) if timezone else None), "system timezone label"
