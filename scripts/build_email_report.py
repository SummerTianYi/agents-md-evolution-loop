#!/usr/bin/env python3
"""Build a complete Simplified Chinese Gmail report with deterministic secret protection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "bearer_token": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "assigned_secret": re.compile(r"(?im)^\s*(?:api[_-]?key|app[_-]?secret|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*[\"']?[^\s\"']{12,}"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan(texts: dict[str, str]) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    for filename, text in texts.items():
        matches = [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
        if matches:
            findings[filename] = matches
    return findings


def fenced(label: str, value: str) -> str:
    fence = "````"
    return f"{fence}{label}\n{value.rstrip()}\n{fence}\n"


def approval_summary(run_dir: Path, run: dict, execution: dict, reviewer: dict) -> str:
    summary = {
        "run_id": run_dir.name,
        "model": {
            "detected": execution.get("detected_model"),
            "author": execution.get("author_model"),
            "reviewer": execution.get("reviewer_model"),
            "reasoning_effort": execution.get("reviewer_reasoning_effort"),
        },
        "review": {
            "verdict": reviewer["verdict"],
            "critical_regressions": reviewer["critical_regressions"],
            "risk_summary": reviewer["risk_summary"],
            "approval_recommendation": reviewer["approval_recommendation"],
        },
        "installation": {"active_agents_modified": False, "requires_named_run_approval": True},
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    root = run_dir.parent.parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    delivery = json.loads((root / "delivery.json").read_text(encoding="utf-8"))
    if delivery.get("provider") != "gmail" or delivery.get("language") != "zh-CN":
        raise SystemExit("the packaged report builder currently requires Gmail and zh-CN")
    if delivery.get("secret_scan_required") is not True or delivery.get("verify_sent") is not True:
        raise SystemExit("secret scanning and Sent verification must remain enabled")
    if delivery.get("attach_files") is not False:
        raise SystemExit("file attachments are not permitted")

    output = args.output or run_dir / "email-report.md"
    required = {name: run_dir / name for name in ("evaluation.md", "changes.diff", "original.md", "candidate.md", "execution.json", "run.json", "reviewer-result.json")}
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise SystemExit("missing required files: " + ", ".join(missing))
    texts = {name: path.read_text(encoding="utf-8") for name, path in required.items() if path.suffix in {".md", ".diff"}}
    findings = scan({name: texts[name] for name in ("original.md", "candidate.md", "changes.diff")})
    execution = json.loads(required["execution.json"].read_text(encoding="utf-8"))
    run = json.loads(required["run.json"].read_text(encoding="utf-8"))
    reviewer = json.loads(required["reviewer-result.json"].read_text(encoding="utf-8"))

    lines = [
        "# AGENTS.md 完整改版与对比报告",
        "",
        "> 本邮件用于审批。活动 `AGENTS.md` 尚未修改；只有在 Codex 中明确批准本 Run 后，候选才可能进入安装流程。邮件回复不构成批准。",
        "",
        "## 风险与审批建议",
        "",
        fenced("json", approval_summary(run_dir, run, execution, reviewer)).rstrip(),
        "",
        "## 执行信息",
        "",
        f"- Run ID：`{run_dir.name}`",
        f"- 候选作者：`{execution.get('author_model')}` / `{execution.get('author_reasoning_effort')}`",
        f"- 独立复核：`{execution.get('reviewer_model')}` / `{execution.get('reviewer_reasoning_effort')}`",
        f"- 复核结论：`{run.get('reviewer_verdict')}`",
        f"- 原版 SHA-256：`{sha256(required['original.md'])}`",
        f"- 改版 SHA-256：`{sha256(required['candidate.md'])}`",
        "",
    ]
    if delivery.get("include_complete_evaluation", True):
        lines.extend(["## 完整审计结论", "", texts["evaluation.md"].rstrip(), ""])
    else:
        lines.extend(["> 使用者配置为不在邮件中加入完整审计正文；本地 `evaluation.md` 仍保留。", ""])

    if findings:
        lines.extend([
            "## 秘密扫描保护",
            "",
            "> 检测到疑似凭据模式。为避免邮件泄密，完整 diff、修改前全文和修改后全文已自动省略；不得绕过此保护。",
            "",
            *[f"- `{name}`：{', '.join(kinds)}" for name, kinds in sorted(findings.items())],
            "",
        ])
    else:
        if delivery.get("include_full_diff", True):
            lines.extend(["## 完整统一差异（diff）", "", fenced("diff", texts["changes.diff"]).rstrip(), ""])
        if delivery.get("include_full_original", True):
            lines.extend(["## 修改前完整原文", "", fenced("markdown", texts["original.md"]).rstrip(), ""])
        if delivery.get("include_full_candidate", True):
            lines.extend(["## 修改后完整原文", "", fenced("markdown", texts["candidate.md"]).rstrip(), ""])

    approval_phrase = config.get("approval_phrase", "批准安装 run <Run ID>").replace("<Run ID>", run_dir.name)
    lines.extend([
        "## 审批方式",
        "",
        f"在 Codex 中回复：`{approval_phrase}`，或明确提出拒绝及修改意见。邮件回复不构成批准。",
        "",
        "## 邮件内容安全检查",
        "",
        f"- 秘密扫描：{'发现疑似秘密，已省略相关完整章节' if findings else '通过，未发现已知秘密模式'}",
        "- 邮件附件：无",
        "- 活动全局文件：未修改",
        "- Gmail Sent：发送后仍须独立核验，未核验不得声称成功",
        "",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"email_report": str(output), "secret_scan": "blocked" if findings else "passed", "findings": findings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
