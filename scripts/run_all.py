#!/usr/bin/env python
import argparse
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


REQUIRED_MODULES = {
    'api': ['fastapi', 'uvicorn'],
    'bot': ['dingtalk_stream', 'dotenv', 'requests'],
}


def _append_runtime_event(project_dir: Path, message: str) -> None:
    log_dir = project_dir / 'runtime'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'run_all-exit.log'
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(f'[{timestamp}] {message}\n')


def _missing_modules() -> list[str]:
    missing: list[str] = []
    for modules in REQUIRED_MODULES.values():
        for module_name in modules:
            try:
                __import__(module_name)
            except ImportError:
                missing.append(module_name)
    return sorted(set(missing))


def _stream_output(prefix: str, stream) -> None:
    try:
        for line in iter(stream.readline, ''):
            if not line:
                break
            print(f'[{prefix}] {line.rstrip()}', flush=True)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(process.pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            process.terminate()
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _wait_before_exit(project_dir: Path) -> None:
    try:
        message = '[run] press Enter to close this window'
        print(message, flush=True)
        _append_runtime_event(project_dir, message)
        input()
    except EOFError:
        pass
    except KeyboardInterrupt:
        pass


def _summarize_remaining_processes(project_dir: Path, processes: dict[str, subprocess.Popen]) -> None:
    for name, process in processes.items():
        try:
            alive = process.poll() is None
        except Exception:
            alive = False
        message = f'[run] remaining process {name}: alive={alive} pid={getattr(process, "pid", "?")}'
        print(message, flush=True)
        _append_runtime_event(project_dir, message)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run API and DingTalk bot in one terminal with prefixed logs.')
    parser.add_argument('--api-host', default=os.environ.get('API_HOST', '0.0.0.0'))
    parser.add_argument('--api-port', default=os.environ.get('API_PORT', '18081'))
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    python_exe = sys.executable
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    startup_messages = [
        f'[run] project directory: {project_dir}',
        f'[run] python executable: {python_exe}',
    ]
    for message in startup_messages:
        print(message, flush=True)
        _append_runtime_event(project_dir, message)

    missing = _missing_modules()
    if missing:
        message = f"[run] missing Python modules: {', '.join(missing)}"
        print(message, flush=True)
        _append_runtime_event(project_dir, message)
        install_message = f"[run] install dependencies with: {python_exe} -m pip install -r {project_dir / 'requirements.txt'}"
        print(install_message, flush=True)
        _append_runtime_event(project_dir, install_message)
        return 1

    commands = {
        'api': [python_exe, '-m', 'uvicorn', 'api_server:app', '--host', str(args.api_host), '--port', str(args.api_port)],
    }
    commands['bot'] = [python_exe, str(project_dir / 'main.py')]
    processes: dict[str, subprocess.Popen] = {}
    threads: list[threading.Thread] = []

    def stop_all(*_args) -> None:
        for process in processes.values():
            _terminate_process(process)

    signal.signal(signal.SIGINT, stop_all)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, stop_all)

    try:
        for name, command in commands.items():
            process = subprocess.Popen(
                command,
                cwd=str(project_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
            )
            processes[name] = process
            thread = threading.Thread(target=_stream_output, args=(name, process.stdout), daemon=True)
            thread.start()
            threads.append(thread)

        while processes:
            for name, process in list(processes.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                message = f'[{name}] exited with code {exit_code}'
                print(message, flush=True)
                _append_runtime_event(project_dir, message)
                processes.pop(name, None)
                _summarize_remaining_processes(project_dir, processes)
                stop_all()
                _wait_before_exit(project_dir)
                return int(exit_code)
            for thread in threads:
                thread.join(timeout=0.1)
    finally:
        stop_all()
        for thread in threads:
            thread.join(timeout=2)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
