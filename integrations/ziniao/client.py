import json
import logging
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests


_CLIENT_START_LOCK = threading.Lock()
_BROWSER_START_LOCK = threading.Lock()
_BROWSER_DEBUGGING_PORTS: dict[str, int] = {}

logger = logging.getLogger(__name__)


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()


def _browser_state_path() -> Path:
    configured_path = _clean_text(os.environ.get('ZINIAO_BROWSER_STATE_PATH', ''))
    if configured_path:
        return Path(configured_path)
    return Path.cwd() / 'tmp' / 'ziniao-browser-ports.json'


def _load_persisted_debugging_ports() -> dict[str, int]:
    path = _browser_state_path()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    ports = payload.get('debugging_ports') if isinstance(payload, dict) else {}
    if not isinstance(ports, dict):
        return {}
    result: dict[str, int] = {}
    for browser_id, port in ports.items():
        try:
            normalized_port = int(port)
        except (TypeError, ValueError):
            continue
        if str(browser_id).strip() and 1 <= normalized_port <= 65535:
            result[str(browser_id).strip()] = normalized_port
    return result


def _save_persisted_debugging_ports(ports: dict[str, int]) -> None:
    path = _browser_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + '.tmp')
        temporary_path.write_text(
            json.dumps({'debugging_ports': ports}, ensure_ascii=True, sort_keys=True),
            encoding='utf-8',
        )
        os.replace(temporary_path, path)
    except OSError as exc:
        logger.warning('紫鸟浏览器: 保存调试端口状态失败 path=%s error=%s', path, exc)


def resolve_ziniao_client_path(configured_path: str = '') -> str:
    configured = _clean_text(configured_path)
    candidates = [configured] if configured else []
    if os.name == 'nt':
        program_files = os.environ.get('ProgramFiles', r'C:\\Program Files')
        program_files_x86 = os.environ.get('ProgramFiles(x86)', r'C:\\Program Files (x86)')
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        candidates.extend([
            r'D:\\ziniao\\ziniao.exe',
            str(Path(program_files) / 'Ziniao' / 'ziniao.exe'),
            str(Path(program_files_x86) / 'Ziniao' / 'ziniao.exe'),
            str(Path(program_files) / 'SuperBrowser' / 'ziniao.exe'),
            str(Path(program_files_x86) / 'SuperBrowser' / 'ziniao.exe'),
            str(Path(local_app_data) / 'Ziniao' / 'ziniao.exe') if local_app_data else '',
        ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return ''


class ZiniaoWebDriverClient:
    """Client for Ziniao's local WebDriver HTTP service."""

    def __init__(self, company: str, username: str, password: str, port: int, client_path: str = '') -> None:
        self.company = _clean_text(company)
        self.username = _clean_text(username)
        self.password = str(password or '').strip()
        self.port = port
        self.client_path = _clean_text(client_path)

    @property
    def base_url(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    def _credentials(self) -> dict[str, str]:
        values = {
            'ZINIAO_COMPANY': self.company,
            'ZINIAO_USERNAME': self.username,
            'ZINIAO_PASSWORD': self.password,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(f'缺少紫鸟 WebDriver 配置: {", ".join(missing)}')
        return {'company': self.company, 'username': self.username, 'password': self.password}

    def _request(self, action: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
        data = {
            'action': action,
            'requestId': str(uuid.uuid4()),
            **self._credentials(),
            **(payload or {}),
        }
        try:
            response = requests.post(self.base_url, data=json.dumps(data).encode('utf-8'), timeout=timeout)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f'紫鸟 WebDriver 服务不可用: {self.base_url}; {exc}') from exc
        if not isinstance(result, dict):
            raise RuntimeError(f'紫鸟 WebDriver 返回格式异常: {result!r}')
        return result

    def _is_available(self) -> bool:
        try:
            self._request('getBrowserList', timeout=3)
            return True
        except RuntimeError:
            return False

    def ensure_running(self) -> None:
        if self._is_available():
            return
        executable_path = resolve_ziniao_client_path(self.client_path)
        if not executable_path:
            raise RuntimeError(
                '紫鸟 WebDriver 服务未启动，且未找到 ziniao.exe。请设置 ZINIAO_CLIENT_PATH 指向 ziniao.exe，'
                '或手动以 --run_type=web_driver --ipc_type=http --port=<端口> 启动紫鸟客户端'
            )
        executable = Path(executable_path)
        with _CLIENT_START_LOCK:
            if self._is_available():
                return
            subprocess.Popen(
                [str(executable), '--run_type=web_driver', '--ipc_type=http', f'--port={self.port}'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if self._is_available():
                    return
                time.sleep(1)
        raise RuntimeError(f'紫鸟 WebDriver 启动超时: {self.base_url}')

    def update_core(self) -> None:
        deadline = time.monotonic() + 120
        while True:
            result = self._request('updateCore')
            status = str(result.get('statusCode', ''))
            if status == '0':
                return
            if status == '-10003':
                raise RuntimeError(f'紫鸟 WebDriver 企业登录失败: {result}')
            if time.monotonic() >= deadline:
                raise RuntimeError(f'紫鸟内核准备超时: {result}')
            time.sleep(2)

    def start_browser(self, browser_id: str) -> dict[str, Any]:
        browser_id = _clean_text(browser_id)
        if not browser_id:
            raise RuntimeError('缺少紫鸟浏览器环境 ID: AGL_EASYCAN_ZINIAO_BROWSER_ID')
        self.ensure_running()
        self.update_core()
        result = self._request('startBrowser', {
            'isWaitPluginUpdate': 0,
            'isHeadless': 0,
            'isWebDriverReadOnlyMode': 0,
            'cookieTypeLoad': 0,
            'cookieTypeSave': 0,
            'runMode': '1',
            'isLoadUserPlugin': False,
            'pluginIdType': 1,
            'privacyMode': 0,
            'browserId': browser_id,
        })
        if str(result.get('statusCode', '')) != '0':
            raise RuntimeError(f'紫鸟启动浏览器环境失败: {result}')
        if not result.get('debuggingPort'):
            raise RuntimeError(f'紫鸟未返回 debuggingPort: {result}')
        return result

    @staticmethod
    def _debugging_port_is_available(port: int) -> bool:
        try:
            response = requests.get(f'http://127.0.0.1:{port}/json/version', timeout=2)
            response.raise_for_status()
            return bool(response.json().get('webSocketDebuggerUrl'))
        except (requests.RequestException, ValueError, AttributeError):
            return False

    @staticmethod
    def _cached_debugging_port(browser_id: str) -> int | None:
        cached_port = _BROWSER_DEBUGGING_PORTS.get(browser_id)
        if cached_port:
            return cached_port
        persisted_port = _load_persisted_debugging_ports().get(browser_id)
        if persisted_port:
            _BROWSER_DEBUGGING_PORTS[browser_id] = persisted_port
            return persisted_port
        return None

    @staticmethod
    def _remember_debugging_port(browser_id: str, port: int) -> None:
        _BROWSER_DEBUGGING_PORTS[browser_id] = port
        ports = _load_persisted_debugging_ports()
        ports[browser_id] = port
        _save_persisted_debugging_ports(ports)

    @staticmethod
    def _forget_debugging_port(browser_id: str) -> None:
        _BROWSER_DEBUGGING_PORTS.pop(browser_id, None)
        ports = _load_persisted_debugging_ports()
        if browser_id in ports:
            ports.pop(browser_id, None)
            _save_persisted_debugging_ports(ports)

    def get_or_start_browser(self, browser_id: str) -> dict[str, Any]:
        """Reuse a reachable open environment before requesting another start."""
        browser_id = _clean_text(browser_id)
        if not browser_id:
            raise RuntimeError('缺少紫鸟浏览器环境 ID: AGL_EASYCAN_ZINIAO_BROWSER_ID')

        with _BROWSER_START_LOCK:
            cached_port = self._cached_debugging_port(browser_id)
            if cached_port and self._debugging_port_is_available(cached_port):
                logger.info('紫鸟浏览器: 复用已打开环境 browser_id=%s debugging_port=%s', browser_id, cached_port)
                return {'statusCode': 0, 'browserId': browser_id, 'debuggingPort': cached_port, 'reused': True}
            if cached_port:
                logger.warning(
                    '紫鸟浏览器: 缓存调试端口不可达，才会重新打开环境 browser_id=%s debugging_port=%s',
                    browser_id,
                    cached_port,
                )
                self._forget_debugging_port(browser_id)

            result = self.start_browser(browser_id)
            debugging_port = int(result['debuggingPort'])
            self._remember_debugging_port(browser_id, debugging_port)
            logger.info('紫鸟浏览器: 已打开环境 browser_id=%s debugging_port=%s', browser_id, debugging_port)
            return result


def get_ziniao_webdriver_client() -> ZiniaoWebDriverClient:
    raw_port = _clean_text(os.environ.get('ZINIAO_WEBDRIVER_PORT', '16851')) or '16851'
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError(f'ZINIAO_WEBDRIVER_PORT 必须是端口号: {raw_port}') from exc
    return ZiniaoWebDriverClient(
        company=os.environ.get('ZINIAO_COMPANY', ''),
        username=os.environ.get('ZINIAO_USERNAME', ''),
        password=os.environ.get('ZINIAO_PASSWORD', ''),
        port=port,
        client_path=os.environ.get('ZINIAO_CLIENT_PATH', ''),
    )
