---
name: agents-md-evolution
description: Initialize and operate a reusable Codex-only loop that detects newly available local Codex models, audits a global AGENTS.md with the newest model at maximum reasoning, independently reviews the candidate, and delivers a Chinese Gmail approval report without unattended installation. Use when setting up, configuring, scheduling, running, approving, installing, or packaging an AGENTS.md evolution loop.
---

# AGENTS.md Evolution

Keep the reusable skill separate from each user's runtime instance. Never copy bundled example values into a live configuration without presenting them to the user.

## First-time setup and persistent loop

1. Read `references/configuration.md` completely.
2. Run `python scripts/init_instance.py inspect` to detect the local Codex home, active global `AGENTS.md`, local time zone, Codex executable, and recommended instance root. On macOS, use `python3` when that is the local command.
3. Present every setting printed by the inspection, including defaults, purpose, safety classification, and whether it came from Michael's author preferences. Do not hide unchanged defaults.
4. Ask the user to supply or confirm the Gmail sender and recipient. Gmail is the default and currently supported report path; never retain another person's address. Confirm the connected Gmail account before scheduling delivery.
5. Keep Simplified Chinese reports and the weekday 10:00 and 17:00 schedule as recommended defaults. Detect the host time zone automatically; do not ask the user to enter it unless they explicitly request an override.
6. Ask whether to use the neutral preference profile or Michael's optional author-preference profile. Explain each Michael preference individually; never imply it is a universal Codex rule.
7. After confirmation, run `python scripts/bootstrap.py --root <instance-root> --gmail-sender <sender> --gmail-recipient <recipient> --preference-profile <profile> --install-schedule --run-once`.
8. The bootstrap creates persistent platform scheduling: a login/startup check plus weekday checks. The first run is an onboarding test and must not install a candidate.
9. After a report is produced, use the connected Gmail account to send and verify the test message in Sent. Record the result without storing credentials.

## Scheduled check

1. The registered loop runs `python scripts/run_loop.py --root <instance-root>` at startup and at the configured schedule. Manual execution is only for diagnosis or the first onboarding test.
2. Parse its single JSON result:
   - `baseline`: save and deliver the Chinese baseline report if configured.
   - `no_change`: return `NO_UPDATE`; do not create or send a report.
   - `pending`: identify the existing pending Run; do not create or resend it.
   - `report`: send only the returned `email-report.md` through the configured Gmail account.
   - failure: create a Chinese local failure report and deliver it when possible.
3. Before sending, search Gmail Sent using the unique Chinese subject and Run ID. Send the full Markdown as the message body without attachments, then verify the message in Sent. Never claim success without verification.

## Audit rules

- Detect availability from the local `codex debug models` catalog and use official OpenAI Codex model and changelog pages as supporting evidence. Do not infer local availability from the API catalog alone.
- Launch the candidate author in a fresh `codex exec` session using the highest-priority visible local model and the configured maximum reasoning effort. Launch an independent reviewer in a second fresh session with the same model and effort.
- Preserve `original.md`, record execution evidence, verify candidate checksums before and after review, and evaluate every enabled case under the instance `evals/` directory.
- Produce the smallest justified candidate. Reject safety, authorization, stable-intent, or critical-case regressions.
- Build a Simplified Chinese approval report containing the full evaluation, full diff, original text, candidate text, and approval command when the deterministic secret scan passes. Omit affected full-text sections when it fails.

## Approval and installation

Never install during an unattended run. Install only after the user explicitly approves a named Run ID in Codex. Recompute the active file SHA-256, invalidate stale candidates, create a timestamped backup, replace the active file, verify final content and checksum, update instance state, and produce a Chinese installation report. Email replies are not approvals.

## Guardrails

- Never modify another user's Gmail, paths, time zone, intent, or personal preferences during setup.
- Never weaken `auto_install=false`, named-Run approval, SHA validation, backup creation, secret scanning, recipient restriction, or Sent verification without explicit user acknowledgement of the safety impact.
- Do not bundle runtime state, reports, runs, backups, email addresses, absolute user paths, credentials, or active `AGENTS.md` content when sharing this skill.
- Stop after one author pass and one reviewer pass. Persist evidence instead of retrying the same failure without new evidence.
