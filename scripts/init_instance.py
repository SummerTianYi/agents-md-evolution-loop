#!/usr/bin/env python3
"""Inspect the host and create a user-specific AGENTS.md evolution instance."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from platform_support import detect_timezone, find_codex_executable, normalize_executable, platform_name


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_DIR / "assets" / "instance-template"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def detected_environment() -> dict[str, object]:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    active_file = codex_home / "AGENTS.md"
    timezone, timezone_source = detect_timezone()
    codex = find_codex_executable()
    return {
        "platform": platform_name(),
        "codex_home": str(codex_home),
        "active_agents_path": str(active_file),
        "active_agents_exists": active_file.is_file(),
        "recommended_instance_root": str(codex_home / "agents-md-evolution-instance"),
        "timezone": timezone,
        "timezone_source": timezone_source,
        "timezone_requires_confirmation": False,
        "codex_executable": codex,
    }


def print_inspection() -> None:
    env = detected_environment()
    print("# AGENTS.md Evolution 首次配置检查\n")
    print("以下项目必须全部展示给使用者并由其确认；标为 Michael 的项目只是原作者个人偏好。\n")
    print(f"- Codex 主目录：`{env['codex_home']}`")
    print(f"- 运行平台：`{env['platform']}`")
    print(f"- 活动 AGENTS.md：`{env['active_agents_path']}`（存在：{env['active_agents_exists']}）")
    print(f"- 推荐实例目录：`{env['recommended_instance_root']}`")
    print(f"- 检测时区：`{env['timezone']}`（来源：{env['timezone_source']}）")
    print(f"- Codex CLI：`{env['codex_executable']}`")
    print("- Gmail 发件账号：必须由当前使用者填写并核对连接账号")
    print("- Gmail 收件地址：必须由当前使用者填写，不静默假设与发件人相同")
    print("- 报告语言：简体中文（推荐默认，可在同步修改模板后调整）")
    print("- 运行时间：工作日 10:00、17:00（推荐默认，可调整）")
    print("- 作者/复核推理强度：max，且必须一致（可明确调整，不可静默降级）")
    print("- 报告范围：完整审计、完整 diff、修改前全文、修改后全文（Michael 推荐，可调整）")
    print("- 偏好配置：neutral 或 michael；选择 michael 前必须逐项说明其个人偏好")
    print("- 安全底线：禁止自动安装、指定 Run ID 审批、SHA 校验、时间戳备份、秘密扫描、Sent 核验")
    print(f"\n完整清单：`{SKILL_DIR / 'references/configuration.md'}`")


def render_text(path: Path, replacements: dict[str, str]) -> str:
    value = path.read_text(encoding="utf-8")
    for token, replacement in replacements.items():
        value = value.replace("{{" + token + "}}", replacement)
    return value


def render_json_template(path: Path, replacements: dict[str, str]) -> str:
    escaped = {key: json.dumps(value, ensure_ascii=False)[1:-1] for key, value in replacements.items()}
    return render_text(path, escaped)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def create_instance(args: argparse.Namespace) -> None:
    if not args.confirmed:
        raise SystemExit("refusing to initialize: pass --confirmed only after presenting every configurable setting")
    if not EMAIL_RE.match(args.gmail_sender) or not EMAIL_RE.match(args.gmail_recipient):
        raise SystemExit("valid Gmail sender and recipient addresses are required")
    if args.provider != "gmail":
        raise SystemExit("this package currently supports Gmail as its official delivery path")

    env = detected_environment()
    root = args.root.expanduser().resolve()
    active_file = (args.active_file or Path(str(env["active_agents_path"]))).expanduser().resolve()
    timezone = args.timezone or str(env["timezone"] or "")
    if not timezone:
        raise SystemExit("system timezone detection failed")
    codex = args.codex or str(env["codex_executable"] or "")
    if not codex:
        raise SystemExit("Codex CLI was not detected; pass --codex with its executable path")
    if not active_file.is_file():
        raise SystemExit(f"active AGENTS.md does not exist: {active_file}")
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"instance root is not empty: {root}")

    times = [item.strip() for item in args.times.split(",") if item.strip()]
    if not times or any(not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", item) for item in times):
        raise SystemExit("--times must be a comma-separated list such as 10:00,17:00")
    weekdays = [item.strip().upper() for item in args.weekdays.split(",") if item.strip()]
    if not weekdays or any(item not in {"MO", "TU", "WE", "TH", "FR", "SA", "SU"} for item in weekdays):
        raise SystemExit("--weekdays contains an invalid weekday code")

    replacements = {
        "ACTIVE_AGENTS_PATH": str(active_file),
        "TIMEZONE": timezone,
        "PREFERENCE_PROFILE": args.preference_profile,
        "GMAIL_SENDER": args.gmail_sender,
        "GMAIL_RECIPIENT": args.gmail_recipient,
    }
    root.mkdir(parents=True, exist_ok=True)
    config = json.loads(render_json_template(TEMPLATE_DIR / "config.json", replacements))
    config["schedule"] = {"weekdays": weekdays, "times": times}
    config["author_reasoning_effort"] = args.reasoning_effort
    config["reviewer_reasoning_effort"] = args.reasoning_effort
    config["codex_executable"] = normalize_executable(codex)
    config["skill_dir"] = str(SKILL_DIR)
    write_text(root / "config.json", json.dumps(config, ensure_ascii=False, indent=2))
    write_text(root / "delivery.json", render_json_template(TEMPLATE_DIR / "delivery.json", replacements))

    intent = (TEMPLATE_DIR / "INTENT.base.md").read_text(encoding="utf-8").rstrip()
    if args.preference_profile == "michael":
        intent += "\n" + (TEMPLATE_DIR / "INTENT.michael.md").read_text(encoding="utf-8").rstrip()
    write_text(root / "INTENT.md", intent)
    write_text(root / "state.json", (TEMPLATE_DIR / "state.json").read_text(encoding="utf-8"))
    write_text(root / "test-trigger.json", (TEMPLATE_DIR / "test-trigger.json").read_text(encoding="utf-8"))
    write_text(root / "evals" / "base-cases.yaml", (TEMPLATE_DIR / "evals/base-cases.yaml").read_text(encoding="utf-8"))
    write_text(root / "evals" / "reviewer-result.schema.json", (TEMPLATE_DIR / "evals/reviewer-result.schema.json").read_text(encoding="utf-8"))
    if args.preference_profile == "michael":
        write_text(root / "evals" / "michael-preferences.yaml", (TEMPLATE_DIR / "evals/michael-preferences.yaml").read_text(encoding="utf-8"))
    for directory in ("runs", "reports", "backups"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    automation_prompt = render_text(
        SKILL_DIR / "assets" / "automation-prompt.md",
        {"SKILL_DIR": str(SKILL_DIR), "INSTANCE_ROOT": str(root)},
    )
    write_text(root / "automation-prompt.md", automation_prompt)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "instance_root": str(root),
        "skill_dir": str(SKILL_DIR),
        "preference_profile": args.preference_profile,
        "timezone_detection": {"value": env["timezone"], "source": env["timezone_source"]},
        "detected_timezone": timezone,
        "schedule": config["schedule"],
        "gmail_configured": True,
        "automation_created": False,
    }
    write_text(root / "instance.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"action": "created", "instance_root": str(root), "config": str(root / "config.json"), "automation_created": False}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--active-file", type=Path)
    create.add_argument("--provider", default="gmail")
    create.add_argument("--gmail-sender", required=True)
    create.add_argument("--gmail-recipient", required=True)
    create.add_argument("--timezone", help="optional override; normally detected from the host")
    create.add_argument("--times", default="10:00,17:00")
    create.add_argument("--weekdays", default="MO,TU,WE,TH,FR")
    create.add_argument("--reasoning-effort", default="max")
    create.add_argument("--preference-profile", choices=("neutral", "michael"), required=True)
    create.add_argument("--codex")
    create.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        print_inspection()
    else:
        create_instance(args)


if __name__ == "__main__":
    main()
