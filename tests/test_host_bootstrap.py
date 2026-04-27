import tempfile
import unittest
from pathlib import Path
from unittest import mock

import host_bootstrap


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
             mock.patch("host_bootstrap.time.sleep") as sleep_mock:
            host_bootstrap.ensure_host_cdp(Path("/tmp/project"), port=19444, mode="visible", wait_seconds=2)

        script_call = run_mock.call_args.args[0]
        self.assertEqual(script_call[0], "/tmp/project/start_host_cdp.sh")
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
        self.assertIn('exec python3 "$PROJECT_DIR/main.py"', script_text)

    def test_windows_start_bot_runs_main_from_project_dir(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_bot.ps1").read_text(encoding="utf-8")

        self.assertIn("Set-Location $ProjectDir", script_text)
        self.assertIn("Resolve-PlaywrightChromium", script_text)
        self.assertIn("$env:LOCAL_CDP_BROWSER_BIN = $ResolvedCdpBrowser", script_text)
        self.assertIn("& $PythonExe (Join-Path $ProjectDir 'main.py')", script_text)

    def test_windows_start_all_uses_project_napcat_before_bot(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_all.ps1").read_text(encoding="utf-8")

        self.assertIn("NapCat.Shell\\launcher.bat", script_text)
        self.assertIn("Wait-NapCatHttp", script_text)
        self.assertIn('$QQApiToken = $EnvValues["QQ_API_TOKEN"]', script_text)
        self.assertIn("'Authorization' = \"Bearer $Token\"", script_text)
        self.assertIn("Resolve-PlaywrightChromium", script_text)
        self.assertIn("$env:LOCAL_CDP_BROWSER_BIN = $ResolvedCdpBrowser", script_text)
        self.assertIn("& $PythonExe (Join-Path $ProjectDir 'main.py')", script_text)


if __name__ == "__main__":
    unittest.main()
