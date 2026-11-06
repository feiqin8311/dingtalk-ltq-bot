import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import launcher.run_all as run_all


class _FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        return None

    def join(self, timeout=None):
        return None


class _FakeProcess:
    def __init__(self, exit_code):
        self._exit_code = exit_code
        self.pid = 12345
        self.stdout = io.StringIO("")

    def poll(self):
        return self._exit_code


class RunAllTests(unittest.TestCase):
    @patch.object(run_all, "_missing_modules", return_value=[])
    @patch("launcher.run_all.signal.signal")
    @patch("launcher.run_all.threading.Thread", side_effect=lambda *args, **kwargs: _FakeThread(*args, **kwargs))
    @patch("launcher.run_all._terminate_process")
    @patch("builtins.input", return_value="")
    @patch("launcher.run_all.subprocess.Popen")
    def test_main_waits_for_enter_after_child_failure(
        self,
        popen_mock,
        input_mock,
        terminate_mock,
        _thread_mock,
        _signal_mock,
        _missing_modules_mock,
    ):
        popen_mock.side_effect = [_FakeProcess(1), _FakeProcess(None)]

        stdout = io.StringIO()
        with patch("sys.stdout", new=stdout):
            with patch("sys.argv", ["run_all.py"]):
                exit_code = run_all.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("[api] exited with code 1", stdout.getvalue())
        self.assertIn("[run] press Enter to close this window", stdout.getvalue())
        input_mock.assert_called_once()
        self.assertTrue(terminate_mock.called)

    @patch.object(run_all, "_missing_modules", return_value=[])
    @patch("launcher.run_all.signal.signal")
    @patch("launcher.run_all.threading.Thread", side_effect=lambda *args, **kwargs: _FakeThread(*args, **kwargs))
    @patch("launcher.run_all._terminate_process")
    @patch("builtins.input", return_value="")
    @patch("launcher.run_all.subprocess.Popen")
    def test_main_waits_for_enter_after_child_clean_exit(
        self,
        popen_mock,
        input_mock,
        terminate_mock,
        _thread_mock,
        _signal_mock,
        _missing_modules_mock,
    ):
        popen_mock.side_effect = [_FakeProcess(0), _FakeProcess(None)]

        stdout = io.StringIO()
        with patch("sys.stdout", new=stdout):
            with patch("sys.argv", ["run_all.py"]):
                exit_code = run_all.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("[api] exited with code 0", stdout.getvalue())
        self.assertIn("[run] press Enter to close this window", stdout.getvalue())
        input_mock.assert_called_once()
        self.assertTrue(terminate_mock.called)

    def test_append_runtime_event_writes_log_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)

            run_all._append_runtime_event(project_dir, "first line")
            run_all._append_runtime_event(project_dir, "second line")

            log_path = project_dir / "tmp" / "runtime" / "run_all-exit.log"
            content = log_path.read_text(encoding="utf-8")

        self.assertIn("first line", content)
        self.assertIn("second line", content)

    @patch.object(run_all, "_missing_modules", return_value=["fastapi"])
    @patch("sys.argv", ["run_all.py"])
    def test_main_logs_python_executable_when_modules_missing(self, _missing_modules_mock):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_python = str(Path(tmp_dir) / "python.exe")
            with patch("launcher.run_all.Path.resolve", return_value=Path(tmp_dir) / "launcher" / "run_all.py"):
                with patch("sys.executable", fake_python):
                    with patch("sys.stdout", new=stdout):
                        exit_code = run_all.main()

            log_path = Path(tmp_dir) / "tmp" / "runtime" / "run_all-exit.log"
            content = log_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertIn(f"[run] python executable: {fake_python}", stdout.getvalue())
        self.assertIn(f"[run] python executable: {fake_python}", content)

    def test_cleanup_runtime_artifacts_removes_old_tmp_children(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            recent_dir = project_dir / "tmp" / "17track-debug" / "recent"
            old_dir = project_dir / "tmp" / "17track-debug" / "old"
            recent_dir.mkdir(parents=True)
            old_dir.mkdir(parents=True)

            old_time = (datetime.now() - timedelta(days=10)).timestamp()
            recent_time = (datetime.now() - timedelta(days=1)).timestamp()
            for path, timestamp in ((old_dir, old_time), (recent_dir, recent_time)):
                path.touch(exist_ok=True)
                os.utime(path, (timestamp, timestamp))

            run_all.cleanup_runtime_artifacts(project_dir, retention_days=7)

            self.assertFalse(old_dir.exists())
            self.assertTrue(recent_dir.exists())


if __name__ == "__main__":
    unittest.main()
