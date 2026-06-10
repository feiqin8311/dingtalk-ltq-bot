import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import logistics_query


class CdpConfigDefaultsTests(unittest.TestCase):
    def test_defaults_allow_project_to_start_local_cdp(self):
        with mock.patch.dict(
            os.environ,
            {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("LOCAL_CDP_")
            },
            clear=True,
        ):
            module = importlib.reload(logistics_query)

        try:
            self.assertEqual(module.LOCAL_CDP_HOST, "127.0.0.1")
            self.assertEqual(module.LOCAL_CDP_PORT, 19444)
            self.assertFalse(module.LOCAL_CDP_EXTERNAL_ONLY)
        finally:
            importlib.reload(logistics_query)

    def test_resolve_local_cdp_browser_bin_finds_windows_chrome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chrome_path = Path(temp_dir) / "Google" / "Chrome" / "Application" / "chrome.exe"
            chrome_path.parent.mkdir(parents=True)
            chrome_path.write_text("", encoding="utf-8")

            with mock.patch.object(logistics_query, "LOCAL_CDP_BROWSER_BIN", ""), \
                 mock.patch.dict(os.environ, {"ProgramFiles": temp_dir}, clear=False), \
                 mock.patch.object(logistics_query.shutil, "which", return_value=None), \
                 mock.patch.object(logistics_query.glob, "glob", return_value=[]):
                self.assertEqual(logistics_query.resolve_local_cdp_browser_bin(), str(chrome_path))

    def test_resolve_local_cdp_browser_bin_prefers_playwright_windows_chromium(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chromium_path = Path(temp_dir) / "ms-playwright" / "chromium-123" / "chrome-win" / "chrome.exe"
            chromium_path.parent.mkdir(parents=True)
            chromium_path.write_text("", encoding="utf-8")
            chrome_path = Path(temp_dir) / "Google" / "Chrome" / "Application" / "chrome.exe"
            chrome_path.parent.mkdir(parents=True)
            chrome_path.write_text("", encoding="utf-8")

            with mock.patch.object(logistics_query, "LOCAL_CDP_BROWSER_BIN", ""), \
                 mock.patch.dict(os.environ, {"LOCALAPPDATA": temp_dir, "ProgramFiles": temp_dir}, clear=False), \
                 mock.patch.object(logistics_query.shutil, "which", return_value=None), \
                 mock.patch.object(logistics_query.glob, "glob", side_effect=lambda pattern: [str(chromium_path)] if "chrome-win" in pattern else []):
                self.assertEqual(logistics_query.resolve_local_cdp_browser_bin(), str(chromium_path))

    def test_resolve_local_cdp_browser_bin_uses_playwright_executable_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chromium_path = Path(temp_dir) / "chrome.exe"
            chromium_path.write_text("", encoding="utf-8")

            with mock.patch.object(logistics_query, "LOCAL_CDP_BROWSER_BIN", ""), \
                 mock.patch.object(logistics_query.os, "name", "nt"), \
                 mock.patch.object(logistics_query, "_get_playwright_chromium_executable_path", return_value=str(chromium_path)), \
                 mock.patch.object(logistics_query.glob, "glob", return_value=[]):
                self.assertEqual(logistics_query.resolve_local_cdp_browser_bin(), str(chromium_path))

    def test_windows_browser_bin_uses_windows_profile_hint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chrome_path = Path(temp_dir) / "Google" / "Chrome" / "Application" / "chrome.exe"
            chrome_path.parent.mkdir(parents=True)
            chrome_path.write_text("", encoding="utf-8")

            with mock.patch.object(logistics_query, "LOCAL_CDP_BROWSER_BIN", ""), \
                 mock.patch.dict(os.environ, {"ProgramFiles": temp_dir}, clear=False), \
                 mock.patch.object(logistics_query.shutil, "which", return_value=None), \
                 mock.patch.object(logistics_query.glob, "glob", return_value=[]):
                self.assertTrue(logistics_query.resolve_local_cdp_browser_bin().endswith("chrome.exe"))

    def test_windows_without_playwright_chromium_reports_install_hint(self):
        with mock.patch.object(logistics_query, "LOCAL_CDP_BROWSER_BIN", ""), \
             mock.patch.object(logistics_query.os, "name", "nt"), \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": ""}, clear=False), \
             mock.patch.object(logistics_query, "_get_playwright_chromium_executable_path", return_value=""), \
             mock.patch.object(logistics_query.glob, "glob", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "python -m playwright install chromium"):
                logistics_query.resolve_local_cdp_browser_bin()


class CdpSessionLifecycleTests(unittest.TestCase):
    def test_begin_local_cdp_session_increments_active_count(self):
        original_count = logistics_query._LOCAL_CDP_ACTIVE_SESSIONS
        logistics_query._LOCAL_CDP_ACTIVE_SESSIONS = 0
        try:
            with mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None) as ensure_mock:
                logistics_query.begin_local_cdp_session()

            ensure_mock.assert_called_once()
            self.assertEqual(logistics_query._LOCAL_CDP_ACTIVE_SESSIONS, 1)
        finally:
            logistics_query._LOCAL_CDP_ACTIVE_SESSIONS = original_count


class CdpProfileCleanupTests(unittest.TestCase):
    def test_benign_windows_singleton_lock_error_is_ignored(self):
        exc = PermissionError("[WinError 1920] 系统无法访问此文件。")
        exc.winerror = 1920

        self.assertTrue(
            logistics_query._is_benign_cdp_lock_cleanup_error(Path("SingletonLock"), exc)
        )
        self.assertTrue(
            logistics_query._is_benign_cdp_lock_cleanup_error(Path("SingletonCookie"), exc)
        )
        self.assertTrue(
            logistics_query._is_benign_cdp_lock_cleanup_error(Path("SingletonSocket"), exc)
        )

    def test_non_singleton_cleanup_error_is_not_ignored(self):
        exc = PermissionError("[WinError 1920] 系统无法访问此文件。")
        exc.winerror = 1920

        self.assertFalse(
            logistics_query._is_benign_cdp_lock_cleanup_error(Path("Preferences"), exc)
        )

    def test_ensure_local_cdp_browser_binds_debugging_address(self):
        calls = [False, True]
        popen_mock = mock.Mock()
        popen_mock.poll.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(logistics_query, "is_local_cdp_listening", side_effect=lambda: calls.pop(0)), \
             mock.patch.object(logistics_query, "is_local_port_in_use", return_value=False), \
             mock.patch.object(logistics_query, "resolve_local_cdp_browser_bin", return_value="/chrome"), \
             mock.patch.object(logistics_query, "LOCAL_CDP_USER_DATA_DIR", str(Path(temp_dir) / "profile")), \
             mock.patch.object(logistics_query.subprocess, "Popen", return_value=popen_mock) as popen_call:
            logistics_query.ensure_local_cdp_browser()

        launch_args = popen_call.call_args.args[0]
        self.assertIn("--remote-debugging-address=127.0.0.1", launch_args)

    def test_ensure_local_cdp_browser_writes_pid_file_for_started_process(self):
        calls = [False, True]
        popen_mock = mock.Mock()
        popen_mock.poll.return_value = None
        popen_mock.pid = 43210
        pid_file = Path(f"/tmp/dingtalk-ltq-cdp-{logistics_query.LOCAL_CDP_PORT}.pid")
        if pid_file.exists():
            pid_file.unlink()

        try:
            with tempfile.TemporaryDirectory() as temp_dir, \
                 mock.patch.object(logistics_query, "is_local_cdp_listening", side_effect=lambda: calls.pop(0)), \
                 mock.patch.object(logistics_query, "is_local_port_in_use", return_value=False), \
                 mock.patch.object(logistics_query, "resolve_local_cdp_browser_bin", return_value="/chrome"), \
                 mock.patch.object(logistics_query, "LOCAL_CDP_USER_DATA_DIR", str(Path(temp_dir) / "profile")), \
                 mock.patch.object(logistics_query.subprocess, "Popen", return_value=popen_mock):
                logistics_query.ensure_local_cdp_browser()

            self.assertTrue(pid_file.exists())
            self.assertEqual(pid_file.read_text(encoding="utf-8").strip(), "43210")
        finally:
            if pid_file.exists():
                pid_file.unlink()

    def test_end_local_cdp_session_only_stops_browser_for_last_session(self):
        original_count = logistics_query._LOCAL_CDP_ACTIVE_SESSIONS
        logistics_query._LOCAL_CDP_ACTIVE_SESSIONS = 2
        try:
            with mock.patch.object(logistics_query, "stop_local_cdp_browser") as stop_mock:
                logistics_query.end_local_cdp_session(None)
                stop_mock.assert_not_called()
                self.assertEqual(logistics_query._LOCAL_CDP_ACTIVE_SESSIONS, 1)

                logistics_query.end_local_cdp_session(None)
                stop_mock.assert_called_once_with(None)
                self.assertEqual(logistics_query._LOCAL_CDP_ACTIVE_SESSIONS, 0)
        finally:
            logistics_query._LOCAL_CDP_ACTIVE_SESSIONS = original_count

    def test_stop_local_cdp_browser_uses_windows_taskkill_tree(self):
        process = mock.Mock()
        process.pid = 43210
        process.wait.side_effect = logistics_query.subprocess.TimeoutExpired(cmd="chrome", timeout=5)
        process.kill = mock.Mock()

        with mock.patch.object(logistics_query.os, "name", "nt"), \
             mock.patch.object(logistics_query, "LOCAL_CDP_HOST", "127.0.0.1"), \
             mock.patch.object(logistics_query, "_find_local_cdp_pids_by_port", return_value=[]), \
             mock.patch.object(logistics_query.subprocess, "run") as run_mock:
            logistics_query.stop_local_cdp_browser(process)

        run_mock.assert_any_call(
            ["taskkill", "/F", "/T", "/PID", "43210"],
            check=False,
            stdout=logistics_query.subprocess.DEVNULL,
            stderr=logistics_query.subprocess.DEVNULL,
        )


if __name__ == "__main__":
    unittest.main()
