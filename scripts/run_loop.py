#!/usr/bin/env python3
"""Detect the latest local Codex model and run one two-pass AGENTS.md audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from platform_support import subprocess_environment


SKILL_DIR = Path(__file__).resolve().parents[1]
PREPARE = SKILL_DIR / "scripts" / "prepare_run.py"
BUILD_EMAIL_REPORT = SKILL_DIR / "scripts" / "build_email_report.py"
SOURCE_READ_LIMIT = 131_072
SOURCE_TIMEOUT_SECONDS = 20
MODEL_ID_PATTERN = re.compile(r"\b(?:gpt|codex|o)[a-z0-9_.-]*(?:-[a-z0-9_.-]+)*\b", re.IGNORECASE)
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(
    command: list[str], *, cwd: Path, timeout: int = 2400, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=subprocess_environment(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        input=input,
        timeout=timeout,
        check=False,
    )


def resolve_from_root(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def resolve_reasoning_effort(model: dict, requested_effort: str) -> str:
    levels = {item["effort"] for item in model.get("supported_reasoning_levels", [])}
    if requested_effort not in levels:
        raise RuntimeError(f"{model['slug']} does not advertise {requested_effort} reasoning; refusing silent downgrade")
    return requested_effort


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def fetch_official_source(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "User-Agent": "codex-agents-evolve/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=SOURCE_TIMEOUT_SECONDS) as response:
            raw = response.read(SOURCE_READ_LIMIT)
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            title_match = TITLE_PATTERN.search(text)
            model_mentions = sorted({match.group(0) for match in MODEL_ID_PATTERN.finditer(text.lower())})
            return {
                "url": url,
                "final_url": response.geturl(),
                "status": getattr(response, "status", None),
                "content_type": response.headers.get("content-type"),
                "bytes_sampled": len(raw),
                "title": compact_text(title_match.group(1)) if title_match else None,
                "model_mentions": model_mentions[:30],
                "ok": True,
            }
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as error:
        return {
            "url": url,
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
        }


def collect_official_source_evidence(sources: list[str], required: bool) -> list[dict]:
    evidence = [fetch_official_source(source) for source in sources]
    if required and not any(item.get("ok") for item in evidence):
        errors = "; ".join(f"{item['url']} -> {item.get('error', 'unknown error')}" for item in evidence)
        raise RuntimeError(f"official source check failed for all configured sources: {errors}")
    return evidence


def latest_executable_model(codex: str, cwd: Path, reasoning_effort: str) -> tuple[dict, str]:
    result = run([codex, "debug", "models"], cwd=cwd, timeout=60)
    if result.returncode:
        raise RuntimeError(f"model catalog failed: {result.stderr.strip()}")
    catalog = json.loads(result.stdout)
    visible = [model for model in catalog.get("models", []) if model.get("visibility") == "list"]
    visible.sort(key=lambda item: item.get("priority", 1_000_000))
    if not visible:
        raise RuntimeError("local Codex catalog has no visible model")
    model = visible[0]
    return model, resolve_reasoning_effort(model, reasoning_effort)


def codex_exec(
    codex: str,
    model: str,
    root: Path,
    prompt: str,
    output: Path,
    stdout_log: Path,
    stderr_log: Path,
    reasoning_effort: str,
    schema: Path | None = None,
) -> None:
    command = [
        codex,
        "exec",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--cd",
        str(root),
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "--output-last-message",
        str(output),
    ]
    if schema:
        command.extend(["--output-schema", str(schema)])
    command.append("-")
    result = run(command, cwd=root, input=prompt)
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"codex exec failed with exit code {result.returncode}; see {stderr_log}")


def update_run_status(run_path: Path, **values: object) -> dict:
    data = json.loads(run_path.read_text(encoding="utf-8"))
    data.update(values)
    write_json(run_path, data)
    return data


def normalize_reviewer_report(root: Path, run_dir: Path, result: dict) -> None:
    evaluation = run_dir / "evaluation.md"
    if not evaluation.is_file():
        reported = Path(result.get("report_path", "")).expanduser().resolve()
        if not reported.is_relative_to(root) or not reported.is_file() or reported.suffix != ".md":
            raise RuntimeError("reviewer did not create a usable final report")
        evaluation.write_bytes(reported.read_bytes())
    latest = root / "reports" / "latest.md"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_bytes(evaluation.read_bytes())


def enabled_eval_files(root: Path) -> list[Path]:
    files = sorted((root / "evals").glob("*.yaml"))
    if not files:
        raise RuntimeError("no enabled YAML evaluation cases found")
    return files


def write_baseline_report(root: Path, action: dict, source_url: str, effort: str) -> Path:
    path = root / "reports" / "baseline.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# AGENTS.md Evolution 基线报告\n\n"
        f"- 检测模型：`{action['model_id']}`\n"
        f"- 检查时间：`{action['checked_at']}`\n"
        f"- 配置推理强度：`{effort}`\n"
        f"- 官方来源：{source_url}\n\n"
        "这是首次基线记录，未生成候选，也未修改活动 `AGENTS.md`。后续检测到不同的真实本地可用模型时才启动完整审计。\n",
        encoding="utf-8",
    )
    return path


def due_trigger(path: Path) -> dict | None:
    if not path.is_file():
        return None
    trigger = json.loads(path.read_text(encoding="utf-8"))
    scheduled = trigger.get("scheduled_for")
    if trigger.get("status") != "scheduled" or not scheduled:
        return None
    scheduled_for = datetime.fromisoformat(scheduled)
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.astimezone()
    return trigger if datetime.now().astimezone() >= scheduled_for else None


def execute(args: argparse.Namespace) -> dict:
    root = args.root.expanduser().resolve()
    config_path = root / "config.json"
    if not config_path.is_file():
        raise RuntimeError(f"missing instance config: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("auto_install") is not False:
        raise RuntimeError("auto_install must remain false")
    if config.get("report_language") != "zh-CN":
        raise RuntimeError("this package currently requires zh-CN report templates")
    author_effort = config["author_reasoning_effort"]
    reviewer_effort = config["reviewer_reasoning_effort"]
    if author_effort != reviewer_effort:
        raise RuntimeError("author and reviewer reasoning effort must match")
    codex = args.codex or config.get("codex_executable") or "codex"
    active_file = resolve_from_root(root, args.active_file or config["active_agents_path"])
    sources = config.get("official_sources", [])
    if not sources:
        raise RuntimeError("at least one official OpenAI Codex source is required")
    source_url = args.source_url or sources[0]
    source_evidence = collect_official_source_evidence(sources, bool(config.get("official_source_check_required", True)))
    model, effective_effort = latest_executable_model(codex, root, author_effort)
    model_id = model["slug"]
    trigger_path = resolve_from_root(root, config.get("test_trigger_path", "test-trigger.json"))
    trigger = due_trigger(trigger_path)
    force_audit = args.force_audit or trigger is not None

    prepare_command = [
        sys.executable,
        str(PREPARE),
        "--model-id",
        model_id,
        "--source-url",
        source_url,
        "--root",
        str(root),
        "--active-file",
        str(active_file),
    ]
    if force_audit:
        prepare_command.append("--force-audit")
    prepared = run(prepare_command, cwd=root, timeout=60)
    if prepared.returncode:
        raise RuntimeError(prepared.stderr.strip() or "prepare_run failed")
    action = json.loads(prepared.stdout.strip())
    if action["action"] == "baseline":
        report = write_baseline_report(root, action, source_url, effective_effort)
        return {**action, "report_path": str(report)}
    if action["action"] == "no_change":
        return action

    run_dir = Path(action["run_dir"])
    run_path = run_dir / "run.json"
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    if trigger is not None:
        trigger.update({
            "status": "consumed",
            "consumed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "run_dir": str(run_dir),
            "executor_model": model_id,
        })
        write_json(trigger_path, trigger)
        run_data = update_run_status(run_path, trigger_mode=trigger["mode"], simulated_event=True)
    if action["action"] == "pending" and run_data.get("status") not in {"candidate_required", "author_failed", "review_failed"}:
        return action

    run_mode = trigger["mode"] if trigger is not None else args.run_mode
    simulated_event = run_mode == "simulated_model_update"
    eval_files = enabled_eval_files(root)
    execution = {
        "schema_version": 2,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "detected_model": model_id,
        "catalog_priority": model.get("priority"),
        "catalog_description": model.get("description"),
        "author_model": model_id,
        "author_reasoning_effort": effective_effort,
        "configured_author_reasoning_effort": author_effort,
        "reviewer_model": model_id,
        "reviewer_reasoning_effort": effective_effort,
        "configured_reviewer_reasoning_effort": reviewer_effort,
        "official_sources": sources,
        "detector": {
            "mode": "deterministic_official_source_probe_plus_local_catalog",
            "uses_codex_exec": False,
            "model_used": None,
            "official_source_required": bool(config.get("official_source_check_required", True)),
            "official_source_evidence": source_evidence,
            "local_catalog_selection": {
                "slug": model_id,
                "priority": model.get("priority"),
                "description": model.get("description"),
                "supported_reasoning_levels": model.get("supported_reasoning_levels", []),
            },
        },
        "detector_evidence": "deterministic official-source HTTP probe plus local codex debug models; no model is used for detection",
        "trigger_mode": run_mode,
        "simulated_event": simulated_event,
        "enabled_evals": [str(path) for path in eval_files],
    }
    write_json(run_dir / "execution.json", execution)

    candidate = run_dir / "candidate.md"
    evaluation_draft = run_dir / "evaluation-draft.md"
    eval_list = ", ".join(str(path) for path in eval_files)
    event_note = ""
    if simulated_event:
        event_note = "This is a simulated model-update test. Label every artifact as a simulation and never claim OpenAI released a nonexistent model."
    elif run_mode != "actual_model_detection":
        event_note = f"This is a manual re-audit with run mode {run_mode}; do not present it as an OpenAI release announcement."
    if not candidate.exists() or run_data.get("status") == "author_failed":
        author_prompt = f"""You are the sole candidate author for an AGENTS.md evolution audit.
This task is fully specified and authorized: choose the "audit and produce a revised draft without changing the active file" path. Do not ask the user questions or wait for confirmation. Your deliverables are the three required files below, not a chat response.
Your runtime was explicitly launched as {model_id} with {effective_effort} reasoning. Work only inside {root}.
{event_note}
Read {SKILL_DIR / 'SKILL.md'}, {root / 'INTENT.md'}, every enabled evaluation file ({eval_list}), {run_dir / 'original.md'}, and {SKILL_DIR / 'references/report-template.md'}.
Write exactly {candidate}, {run_dir / 'changes.diff'}, and {evaluation_draft}. Write the evaluation in Simplified Chinese; preserve model IDs, filenames, commands, and technical identifiers.
Treat sections explicitly marked as author preferences as user-configurable intent, not universal truth. Produce the smallest justified improvement, preserve all enabled intent, and never modify the active global AGENTS.md. Evaluate original and candidate against every enabled case. Do not install or send anything."""
        try:
            update_run_status(run_path, status="author_running")
            codex_exec(codex, model_id, root, author_prompt, run_dir / "author-message.md", run_dir / "author-stdout.log", run_dir / "author-stderr.log", effective_effort)
            for required in (candidate, run_dir / "changes.diff", evaluation_draft):
                if not required.is_file():
                    raise RuntimeError(f"author did not create {required}")
            update_run_status(run_path, status="review_required")
        except Exception as error:
            update_run_status(run_path, status="author_failed", error=str(error))
            raise

    candidate_before = sha256(candidate)
    reviewer_prompt = f"""You are the independent reviewer for an AGENTS.md evolution audit. You did not author the candidate.
Your runtime was explicitly launched as {model_id} with {effective_effort} reasoning.
{event_note}
Read {root / 'INTENT.md'}, every enabled evaluation file ({eval_list}), {run_dir / 'original.md'}, {candidate}, {run_dir / 'changes.diff'}, {evaluation_draft}, {run_dir / 'execution.json'}, and {SKILL_DIR / 'references/report-template.md'}.
Do not edit original.md, candidate.md, changes.diff, or evaluation-draft.md. Independently test all enabled critical requirements. Write {run_dir / 'review.md'}, final {run_dir / 'evaluation.md'}, and copy the final report to {root / 'reports/latest.md'}. Use Simplified Chinese except for technical identifiers.
Reject if any critical case regresses, model evidence is inconsistent, reasoning effort is not recorded, authorization or safety weakens, or enabled stable intent changes. Return JSON matching the supplied schema with report_path={run_dir / 'evaluation.md'}."""
    try:
        update_run_status(run_path, status="review_running")
        codex_exec(
            codex,
            model_id,
            root,
            reviewer_prompt,
            run_dir / "reviewer-result.json",
            run_dir / "reviewer-stdout.log",
            run_dir / "reviewer-stderr.log",
            effective_effort,
            SKILL_DIR / "assets" / "instance-template" / "evals" / "reviewer-result.schema.json",
        )
        if sha256(candidate) != candidate_before:
            raise RuntimeError("reviewer modified candidate.md")
        result = json.loads((run_dir / "reviewer-result.json").read_text(encoding="utf-8"))
        normalize_reviewer_report(root, run_dir, result)
        verdict = result["verdict"]
        if result["critical_regressions"] and verdict == "approve":
            verdict = "reject"
        status = "candidate_pending" if verdict == "approve" else "candidate_revision_required" if verdict == "revise" else "audit_rejected"
        update_run_status(run_path, status=status, reviewer_verdict=verdict)
        built = run([sys.executable, str(BUILD_EMAIL_REPORT), "--run-dir", str(run_dir)], cwd=root, timeout=60)
        if built.returncode:
            raise RuntimeError(f"email report build failed: {built.stderr.strip()}")
        email_report = json.loads(built.stdout.strip())
        state_path = root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"last_audited_model": model_id, "status": status})
        if status == "audit_rejected":
            state["pending_run"] = None
        write_json(state_path, state)
        return {
            "action": "report",
            "event": ("simulated_audit_complete" if simulated_event else "audit_complete") if status == "candidate_pending" else "audit_revision_required" if status == "candidate_revision_required" else "audit_rejected",
            "model_id": model_id,
            "reasoning_effort": effective_effort,
            "run_dir": str(run_dir),
            "report_path": email_report["email_report"],
            "evaluation_path": str(run_dir / "evaluation.md"),
            "secret_scan": email_report["secret_scan"],
            "verdict": verdict,
        }
    except Exception as error:
        update_run_status(run_path, status="review_failed", error=str(error))
        raise


def write_failure_report(root: Path, error: Exception) -> Path | None:
    try:
        reports = root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = reports / f"failure-{timestamp}.md"
        path.write_text(
            "# AGENTS.md Evolution 失败报告\n\n"
            f"- 时间：`{datetime.now(timezone.utc).isoformat(timespec='seconds')}`\n"
            f"- 错误：`{type(error).__name__}`\n\n"
            f"{str(error)}\n\n"
            "活动 `AGENTS.md` 未被自动修改。请在修复根因后重新运行。\n",
            encoding="utf-8",
        )
        return path
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    default_root = os.environ.get("AGENTS_MD_EVOLUTION_ROOT")
    parser.add_argument("--root", type=Path, required=not bool(default_root), default=Path(default_root) if default_root else None)
    parser.add_argument("--active-file", type=Path)
    parser.add_argument("--codex")
    parser.add_argument("--source-url")
    parser.add_argument("--force-audit", action="store_true")
    parser.add_argument("--run-mode", default="actual_model_detection")
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args), ensure_ascii=False))
    except Exception as error:
        root = args.root.expanduser().resolve()
        report = write_failure_report(root, error)
        print(json.dumps({"action": "failure", "error": str(error), "report_path": str(report) if report else None}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
