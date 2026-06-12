import errno
import json
import os
import time
from pathlib import Path
from typing import Any, Callable


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


def local_cdp_state_dir(os_name: str, port: int) -> Path:
    _ = port
    if os_name != 'nt':
        return Path('/tmp')
    return Path(os.environ.get('TEMP') or os.environ.get('TMP') or '.')


def local_cdp_state_path(os_name: str, port: int) -> Path:
    return local_cdp_state_dir(os_name, port) / f'dingtalk-ltq-cdp-{port}.json'


def local_cdp_lock_path(os_name: str, port: int) -> Path:
    return local_cdp_state_dir(os_name, port) / f'dingtalk-ltq-cdp-{port}.lock'


def load_local_cdp_state(os_name: str, port: int) -> dict[str, Any]:
    path = local_cdp_state_path(os_name, port)
    if not path.exists():
        return {'owner_pid': 0, 'browser_pid': 0, 'sessions': {}, 'updated_at': 0.0}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'owner_pid': 0, 'browser_pid': 0, 'sessions': {}, 'updated_at': 0.0}
    return {
        'owner_pid': int(payload.get('owner_pid') or 0),
        'browser_pid': int(payload.get('browser_pid') or 0),
        'sessions': {
            str(pid): int(count)
            for pid, count in dict(payload.get('sessions') or {}).items()
            if str(pid).strip() and int(count or 0) > 0
        },
        'updated_at': float(payload.get('updated_at') or 0.0),
    }


def save_local_cdp_state(os_name: str, port: int, state: dict[str, Any]) -> None:
    path = local_cdp_state_path(os_name, port)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'owner_pid': int(state.get('owner_pid') or 0),
        'browser_pid': int(state.get('browser_pid') or 0),
        'sessions': dict(state.get('sessions') or {}),
        'updated_at': float(state.get('updated_at') or time.time()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding='utf-8')


def with_local_cdp_file_lock(os_name: str, port: int, callback: Callable[[], Any]) -> Any:
    lock_path = local_cdp_lock_path(os_name, port)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(120):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            time.sleep(0.1)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                time.sleep(0.1)
                continue
            raise
    else:
        raise RuntimeError(f'获取本地 CDP 共享锁超时: {lock_path}')

    try:
        return callback()
    finally:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass


def register_local_cdp_session(
    os_name: str,
    port: int,
    current_pid: int,
    owner_pid: int | None = None,
    browser_pid: int | None = None,
) -> int:
    def _register() -> int:
        state = load_local_cdp_state(os_name, port)
        sessions = dict(state.get('sessions') or {})
        pid_key = str(current_pid)
        sessions[pid_key] = int(sessions.get(pid_key) or 0) + 1
        if owner_pid:
            state['owner_pid'] = int(owner_pid)
        if browser_pid:
            state['browser_pid'] = int(browser_pid)
        state['sessions'] = sessions
        state['updated_at'] = time.time()
        save_local_cdp_state(os_name, port, state)
        return sum(int(value or 0) for value in sessions.values())

    return with_local_cdp_file_lock(os_name, port, _register)


def unregister_local_cdp_session(os_name: str, port: int, current_pid: int) -> tuple[int, bool]:
    def _unregister() -> tuple[int, bool]:
        state = load_local_cdp_state(os_name, port)
        sessions = dict(state.get('sessions') or {})
        pid_key = str(current_pid)
        current_count = int(sessions.get(pid_key) or 0)
        if current_count <= 1:
            sessions.pop(pid_key, None)
        else:
            sessions[pid_key] = current_count - 1
        state['sessions'] = sessions
        state['updated_at'] = time.time()
        total = sum(int(value or 0) for value in sessions.values())
        should_stop = total == 0 and int(state.get('owner_pid') or 0) == current_pid
        if total == 0:
            state['sessions'] = {}
            if should_stop:
                state['owner_pid'] = 0
                state['browser_pid'] = 0
        save_local_cdp_state(os_name, port, state)
        return total, should_stop

    return with_local_cdp_file_lock(os_name, port, _unregister)


def is_benign_cdp_lock_cleanup_error(entry: Path, exc: OSError) -> bool:
    if entry.name not in {'SingletonLock', 'SingletonCookie', 'SingletonSocket'}:
        return False
    winerror = getattr(exc, 'winerror', None)
    if winerror in {5, 32, 33, 1920}:
        return True
    text = clean_text(exc)
    return any(keyword in text for keyword in ['WinError 5', 'WinError 32', 'WinError 33', 'WinError 1920'])


def cleanup_stale_cdp_profile_locks(logger, user_data_dir: str) -> None:
    profile_dir = Path(user_data_dir)
    stale_entries = [
        profile_dir / 'SingletonLock',
        profile_dir / 'SingletonCookie',
        profile_dir / 'SingletonSocket',
    ]
    stale_entries.extend(profile_dir.glob('.org.chromium.Chromium.*'))

    for entry in stale_entries:
        try:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if is_benign_cdp_lock_cleanup_error(entry, exc):
                logger.info("清理 CDP 用户目录锁文件跳过: path=%s error=%s", entry, exc)
                continue
            logger.warning("清理 CDP 用户目录锁文件失败: path=%s error=%s", entry, exc)
