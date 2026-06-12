import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import host_bootstrap


class HostBootstrapTests(unittest.TestCase):
    def test_ensure_host_cdp_reuses_existing_service(self):
        with mock.patch.object(host_bootstrap, "is_cdp_ready", return_value=True) as is_ready_mock, \
             mock.patch.object(host_bootstrap.subprocess, "run") as run_mock:
            host_bootstrap.ensure_host_cdp(Path("/tmp/project"), port=19444, mode="visible")

        is_ready_mock.assert_called_once()
        run_mock.assert_not_called()

    def test_ensure_host_cdp_starts_script_when_missing(self):
        with mock.patch.object(host_bootstrap, "is_cdp_ready", side_effect=[False, False, True]) as is_ready_mock, \
             mock.patch.object(host_bootstrap.subprocess, "run") as run_mock, \
             mock.patch("services.host_bootstrap.time.sleep") as sleep_mock:
            host_bootstrap.ensure_host_cdp(Path("/tmp/project"), port=19444, mode="visible", wait_seconds=2)

        script_call = run_mock.call_args.args[0]
        self.assertEqual(script_call[0], "/tmp/project/scripts/linux/start_host_cdp.sh")
        self.assertEqual(script_call[1:], ["19444", "visible"])
        self.assertEqual(is_ready_mock.call_count, 3)
        sleep_mock.assert_called()

    def test_main_only_ensures_host_cdp(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(host_bootstrap, "__file__", str(Path(temp_dir) / "host_bootstrap.py")), \
             mock.patch.object(host_bootstrap, "ensure_host_cdp") as ensure_host_cdp_mock:
            host_bootstrap.main()

        ensure_host_cdp_mock.assert_called_once()


class StartScriptTests(unittest.TestCase):
    def test_start_bot_runs_main_directly(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_bot.sh").read_text(encoding="utf-8")
        self.assertIn('exec bash "$PROJECT_DIR/scripts/linux/start_bot.sh" "$@"', script_text)

    def test_windows_start_bot_runs_main_from_project_dir(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_bot.ps1").read_text(encoding="utf-8")

        self.assertIn('scripts\\windows\\start_bot.ps1', script_text)
        self.assertIn("& $ScriptPath @args", script_text)

    def test_windows_start_all_uses_project_napcat_before_bot(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_all.ps1").read_text(encoding="utf-8")

        self.assertIn('scripts\\windows\\start_all.ps1', script_text)
        self.assertIn("& $ScriptPath @args", script_text)

    def test_windows_start_all_uses_log_aggregator(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "scripts" / "windows" / "start_all.ps1").read_text(encoding="utf-8")

        self.assertIn("scripts\\run_all.py", script_text)
        self.assertNotIn("Start-Process `\n    -FilePath $PythonExe `\n    -ArgumentList @(\"-m\", \"uvicorn\"", script_text)


if __name__ == "__main__":
    unittest.main()
