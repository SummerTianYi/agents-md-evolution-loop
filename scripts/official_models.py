"""Resolve the current Codex target from an OpenAI-owned model catalog."""

from __future__ import annotations

import re
from urllib.request import Request, urlopen


SOL_PATTERN = re.compile(r"GPT-(\d+(?:\.\d+)*)\s+Sol", re.IGNORECASE)


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def target_from_official_text(text: str) -> str:
    versions = [match.group(1) for match in SOL_PATTERN.finditer(text)]
    if not versions:
        raise RuntimeError("official model catalog did not identify a GPT Sol target")
    return f"gpt-{max(versions, key=version_key)}-sol"


def fetch_target(url: str) -> str:
    request = Request(url, headers={"User-Agent": "agents-md-evolution/1.0"})
    with urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
    return target_from_official_text(text)
