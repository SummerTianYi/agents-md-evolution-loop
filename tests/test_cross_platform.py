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
import official_models
import platform_support
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

    def test_official_catalog_selects_highest_sol_generation(self) -> None:
        text = "Use GPT-5.5 Sol today. GPT-5.6 Sol is the flagship model."
        self.assertEqual(official_models.target_from_official_text(text), "gpt-5.6-sol")

    def test_reasoning_effort_preserves_literal_max(self) -> None:
        run_loop = load_run_loop()
        model = {"slug": "gpt-5.6-sol", "supported_reasoning_levels": [{"effort": "xhigh"}, {"effort": "max"}]}
        self.assertEqual(run_loop.resolve_reasoning_effort(model, "max"), "max")


if __name__ == "__main__":
    unittest.main()
