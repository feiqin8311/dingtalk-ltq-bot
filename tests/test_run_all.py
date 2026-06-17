import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.run_all as run_all


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
    @patch("scripts.run_all.signal.signal")
    @patch("scripts.run_all.threading.Thread", side_effect=lambda *args, **kwargs: _FakeThread(*args, **kwargs))
    @patch("scripts.run_all._terminate_process")
    @patch("builtins.input", return_value="")
    @patch("scripts.run_all.subprocess.Popen")
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
    @patch("scripts.run_all.signal.signal")
    @patch("scripts.run_all.threading.Thread", side_effect=lambda *args, **kwargs: _FakeThread(*args, **kwargs))
    @patch("scripts.run_all._terminate_process")
    @patch("builtins.input", return_value="")
    @patch("scripts.run_all.subprocess.Popen")
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

            log_path = project_dir / "runtime" / "run_all-exit.log"
            content = log_path.read_text(encoding="utf-8")

        self.assertIn("first line", content)
        self.assertIn("second line", content)

    @patch.object(run_all, "_missing_modules", return_value=["fastapi"])
    @patch("sys.argv", ["run_all.py"])
    def test_main_logs_python_executable_when_modules_missing(self, _missing_modules_mock):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_python = str(Path(tmp_dir) / "python.exe")
            with patch("scripts.run_all.Path.resolve", return_value=Path(tmp_dir) / "scripts" / "run_all.py"):
                with patch("sys.executable", fake_python):
                    with patch("sys.stdout", new=stdout):
                        exit_code = run_all.main()

            log_path = Path(tmp_dir) / "runtime" / "run_all-exit.log"
            content = log_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertIn(f"[run] python executable: {fake_python}", stdout.getvalue())
        self.assertIn(f"[run] python executable: {fake_python}", content)


if __name__ == "__main__":
    unittest.main()
