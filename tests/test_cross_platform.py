from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import init_instance
import loop_daemon
import platform_support
import record_delivery
import register_loop


def load_run_loop():
    spec = importlib.util.spec_from_file_location("run_loop", SCRIPTS / "run_loop.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CrossPlatformTests(unittest.TestCase):
    def test_json_template_escapes_windows_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "config.json"
            template.write_text('{"active_agents_path":"{{PATH}}"}', encoding="utf-8")
            rendered = init_instance.render_json_template(template, {"PATH": r"C:\Users\Example\AGENTS.md"})
            self.assertEqual(json.loads(rendered)["active_agents_path"], r"C:\Users\Example\AGENTS.md")

    def test_python_subprocess_environment_is_utf8(self) -> None:
        environment = platform_support.subprocess_environment()
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(environment["PYTHONUTF8"], "1")

    def test_login_status_requires_successful_codex_command(self) -> None:
        logged_in = type("Result", (), {"returncode": 0})()
        logged_out = type("Result", (), {"returncode": 1})()
        with patch.object(platform_support.subprocess, "run", return_value=logged_in):
            self.assertTrue(platform_support.codex_is_authenticated("codex"))
        with patch.object(platform_support.subprocess, "run", return_value=logged_out):
            self.assertFalse(platform_support.codex_is_authenticated("codex"))
        self.assertFalse(platform_support.codex_is_authenticated(None))

    def test_timezone_detection_uses_windows_system_label(self) -> None:
        with patch.dict(os.environ, {"TZ": "Asia/Shanghai"}, clear=False):
            value, source = platform_support.detect_timezone()
        self.assertEqual(value, "Asia/Shanghai")
        self.assertEqual(source, "TZ environment variable")

    def test_windows_cli_discovery_prefers_cmd_shim(self) -> None:
        with patch.object(platform_support, "os") as mocked_os, patch.object(platform_support.shutil, "which") as which:
            mocked_os.name = "nt"
            which.side_effect = [r"C:\\Users\\Example\\AppData\\Roaming\\npm\\codex.cmd"]
            self.assertTrue(platform_support.find_codex_executable().lower().endswith("codex.cmd"))

    def test_codex_exec_sends_prompt_through_stdin(self) -> None:
        run_loop = load_run_loop()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                return type("Result", (), {"stdout": "", "stderr": "", "returncode": 0})()

            with patch.object(run_loop, "run", side_effect=fake_run):
                run_loop.codex_exec("codex", "gpt-test", root, "full prompt", root / "output.md", root / "stdout.log", root / "stderr.log", "high")
            self.assertEqual(calls[0][0][-1], "-")
            self.assertEqual(calls[0][1]["input"], "full prompt")

    def test_windows_startup_entry_starts_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            startup = root / "Startup"
            with patch.object(register_loop, "windows_startup_dir", return_value=startup):
                startup.mkdir()
                entry = register_loop.write_windows_startup(root, ROOT)
            text = entry.read_text(encoding="utf-8")
            self.assertIn("loop_daemon.py", text)
            self.assertIn("--root", text)

    def test_daemon_selects_next_weekday_run(self) -> None:
        now = __import__("datetime").datetime(2026, 7, 17, 18, 0).astimezone()
        expected = now.replace(day=20, hour=10, minute=0)
        self.assertEqual(loop_daemon.next_run(["MO", "TU", "WE", "TH", "FR"], ["10:00", "17:00"], now), expected)

    def test_reasoning_effort_preserves_literal_max(self) -> None:
        run_loop = load_run_loop()
        model = {"slug": "gpt-5.6-sol", "supported_reasoning_levels": [{"effort": "xhigh"}, {"effort": "max"}]}
        self.assertEqual(run_loop.resolve_reasoning_effort(model, "max"), "max")

    def test_reasoning_effort_refuses_max_downgrade(self) -> None:
        run_loop = load_run_loop()
        model = {"slug": "gpt-test", "supported_reasoning_levels": [{"effort": "xhigh"}]}
        with self.assertRaisesRegex(RuntimeError, "refusing silent downgrade"):
            run_loop.resolve_reasoning_effort(model, "max")

    def test_latest_executable_model_uses_catalog_priority(self) -> None:
        run_loop = load_run_loop()
        catalog = {
            "models": [
                {"slug": "gpt-older", "visibility": "list", "priority": 10, "supported_reasoning_levels": [{"effort": "max"}]},
                {"slug": "gpt-newer", "visibility": "list", "priority": 1, "supported_reasoning_levels": [{"effort": "max"}]},
            ]
        }
        result = type("Result", (), {"stdout": json.dumps(catalog), "stderr": "", "returncode": 0})()
        with patch.object(run_loop, "run", return_value=result):
            model, effort = run_loop.latest_executable_model("codex", Path("."), "max")
        self.assertEqual(model["slug"], "gpt-newer")
        self.assertEqual(effort, "max")

    def test_default_delivery_contains_full_approval_material(self) -> None:
        delivery = json.loads((ROOT / "assets" / "instance-template" / "delivery.json").read_text(encoding="utf-8"))
        self.assertTrue(delivery["include_complete_evaluation"])
        self.assertTrue(delivery["include_full_diff"])
        self.assertTrue(delivery["include_full_original"])
        self.assertTrue(delivery["include_full_candidate"])

    def test_daemon_queues_delivery_request_without_sending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "runs" / "run-1" / "email-report.md"
            report.parent.mkdir(parents=True)
            report.write_text("report", encoding="utf-8")
            request = loop_daemon.queue_delivery(root, {"action": "report", "event": "audit_complete", "run_dir": str(report.parent), "report_path": str(report)})
            self.assertIsNotNone(request)
            payload = json.loads(request.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pending_gmail_delivery")
            self.assertEqual(payload["report_path"], str(report.resolve()))

    def test_daemon_run_once_creates_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill_dir = root / "skill"
            script = skill_dir / "scripts" / "run_loop.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")
            completed = type("Result", (), {"stdout": '{"action":"no_change"}\n', "stderr": "", "returncode": 0})()
            with patch.object(loop_daemon.subprocess, "run", return_value=completed):
                outcome = loop_daemon.run_once(root, {"skill_dir": str(skill_dir)})
            self.assertEqual(outcome["action"], "no_change")
            self.assertTrue((root / "logs" / "loop.log").is_file())

    def test_delivery_record_requires_sent_verification_and_updates_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = root / "delivery-requests" / "run-1.json"
            request.parent.mkdir()
            request.write_text(json.dumps({"status": "pending_gmail_delivery"}), encoding="utf-8")
            argv = ["record_delivery.py", "--root", str(root), "--event", "audit_complete", "--run-id", "run-1", "--subject", "subject", "--message-id", "message-1", "--verified"]
            with patch.object(sys, "argv", argv):
                record_delivery.main()
            updated = json.loads(request.read_text(encoding="utf-8"))
            self.assertEqual(updated["status"], "sent_verified")
            self.assertEqual(updated["message_id"], "message-1")

    def test_macos_launch_agent_is_loaded_and_verified(self) -> None:
        completed = type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.object(register_loop.subprocess, "run", return_value=completed) as run:
            register_loop.load_macos_launch_agent(Path("/tmp/com.example.loop.plist"))
        self.assertEqual(run.call_count, 2)
        self.assertIn("bootstrap", run.call_args_list[0].args[0])
        self.assertIn("print", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
