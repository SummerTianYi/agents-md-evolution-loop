# AGENTS.md Evolution for Codex

A Codex-only Skill that detects the newest locally available Codex model, prepares an `AGENTS.md` candidate, requests an independent review, and produces a Simplified Chinese approval report. It never installs a candidate without explicit approval for a named Run ID.

## Platforms

One package supports Windows and macOS. The audit state machine is shared; `scripts/platform_support.py` contains the small operating-system boundary for CLI discovery, local time-zone detection, and subprocess encoding.

| Concern | Windows | macOS |
| --- | --- | --- |
| Codex CLI discovery | `codex.cmd`, `codex.exe`, then `codex` | `codex` |
| Long `codex exec` prompts | UTF-8 stdin | UTF-8 stdin |
| Python helper protocol | Forced UTF-8 | Forced UTF-8 |
| Persistent startup check | user Startup folder | LaunchAgent `RunAtLoad` |
| Weekday checks | shared local loop daemon | shared local loop daemon |
| Time zone | detected from the host | detected from the host |

## Requirements

- Python 3.10+
- Codex CLI authenticated locally
- A local global `AGENTS.md`
- A Gmail-capable Codex scheduled task when delivery is enabled

## Setup

Read [`SKILL.md`](SKILL.md) and [`references/configuration.md`](references/configuration.md) before creating an instance. Inspect first:

```powershell
python scripts/init_instance.py inspect
```

If inspection says the Codex CLI is not logged in, run `codex login` before creating the instance.

Then create the instance and run a safe onboarding audit after confirming Gmail and preference settings:

```powershell
python scripts/bootstrap.py --root <instance-root> --gmail-sender <sender> --gmail-recipient <recipient> --preference-profile neutral --run-once
```

Use `python3` instead of `python` where that is the local macOS convention. `--run-once` produces a candidate and review but never installs it.

For automatic Gmail delivery, create a Codex scheduled task with the generated `<instance-root>/automation-prompt.md`. That task must have access to the configured Gmail connector; it sends only the generated report, verifies Gmail Sent, and records delivery evidence. The package deliberately does not attempt to impersonate Gmail from a generic Python process.

`--install-local-audit-daemon` is optional. It installs a login/startup worker that runs local audits and writes structured `delivery-requests/*.json` files, but it never sends mail or claims delivery. Use it only when a separate Gmail-capable Codex task will consume those requests.

## Safety

- `auto_install` must remain `false`.
- A candidate is installed only with explicit named-Run approval and `--approved`.
- Installation verifies the active file hash, creates a backup, and verifies installed bytes.
- Reports scan for common secret patterns before including full text.
- Do not commit generated runtime instances, reports, backups, addresses, or active `AGENTS.md` content.

## Verification

The included tests are offline and run without a Codex account:

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions runs these tests on Windows and macOS. Live `codex exec` remains a local integration check because it requires an authenticated account and a real model catalog.
