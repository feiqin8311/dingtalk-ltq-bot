import time
from pathlib import Path


def project_tmp_dir(project_dir: Path) -> Path:
    return project_dir / 'tmp'


def debug_dir(project_dir: Path, platform: str, day: str) -> Path:
    normalized_platform = str(platform).strip().lower()
    normalized_day = str(day).strip()
    return project_tmp_dir(project_dir) / f'{normalized_platform}-debug' / normalized_day


def download_dir(project_dir: Path, platform: str, day: str) -> Path:
    normalized_platform = str(platform).strip().lower()
    normalized_day = str(day).strip()
    return project_tmp_dir(project_dir) / 'tracking-downloads' / normalized_day / normalized_platform


def runtime_log_path(project_dir: Path) -> Path:
    return project_tmp_dir(project_dir) / 'runtime' / 'run_all-exit.log'


def cdp_pid_path(project_dir: Path, port: int) -> Path:
    return project_tmp_dir(project_dir) / 'cdp' / f'dingtalk-ltq-cdp-{port}.pid'


def cleanup_tmp_artifacts(project_dir: Path, retention_days: int = 7) -> int:
    tmp_dir = project_tmp_dir(project_dir)
    if retention_days <= 0 or not tmp_dir.exists():
        return 0

    cutoff = time.time() - (retention_days * 86400)
    removed = 0
    paths = sorted(tmp_dir.rglob('*'), key=lambda path: len(path.parts), reverse=True)

    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime >= cutoff:
            continue
        try:
            if path.is_dir():
                if any(path.iterdir()):
                    continue
                path.rmdir()
            else:
                path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            continue

    for path in sorted(tmp_dir.rglob('*'), key=lambda item: len(item.parts), reverse=True):
        try:
            if path.is_dir() and not any(path.iterdir()) and path.stat().st_mtime < cutoff:
                path.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return removed
