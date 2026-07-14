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
- Gmail connector when delivery is enabled

## Setup

Read [`SKILL.md`](SKILL.md) and [`references/configuration.md`](references/configuration.md) before creating an instance. Inspect first:

```powershell
python scripts/init_instance.py inspect
```

Then create the persistent loop after confirming Gmail and preference settings:

```powershell
python scripts/bootstrap.py --root <instance-root> --gmail-sender <sender> --gmail-recipient <recipient> --preference-profile neutral --install-schedule --run-once
```

Use `python3` instead of `python` where that is the local macOS convention. `--run-once` produces a candidate and review but never installs it; the controlling Codex task sends the resulting Gmail report and verifies it in Sent.

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
