import argparse
import asyncio
import glob
import json
import logging
import random
import os
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse, urlunparse
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

import requests
from qq_query import query_qq

ENV_PATH = Path(__file__).with_name('.env')


def _preload_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if not os.environ.get(key, '').strip():
            os.environ[key] = value


_preload_env()

MEITONG_API_BASE = 'https://www.szaaf.com'
DINGTALK_API_BASE = 'https://api.dingtalk.com'
DINGTALK_DOC_ID = 'R1zknDm0WRl1kQwrCZ9rmxxDJBQEx5rG'
DINGTALK_TARGET_SHEET_NAME = os.environ.get('DINGTALK_TARGET_SHEET_NAME', '2025New!')
DINGTALK_OPERATOR_ID = os.environ.get('DINGTALK_OPERATOR_ID', 'UQrqqgBXryxyFbP7kGAfdAiEiE')
AGL_LOGIN_URL = 'https://www.agl.amazon.com/freight-puma'
AGL_TRACKING_URL = 'https://www.agl.amazon.com/freight-puma/shipment/{booking_id}/tracking'
LOCAL_CDP_HOST = os.environ.get('LOCAL_CDP_HOST', '127.0.0.1')
LOCAL_CDP_PORT = int(os.environ.get('LOCAL_CDP_PORT', '19444'))
LOCAL_CDP_URL = os.environ.get('LOCAL_CDP_URL', f'http://{LOCAL_CDP_HOST}:{LOCAL_CDP_PORT}')
LOCAL_CDP_USER_DATA_DIR = os.environ.get(
    'LOCAL_CDP_USER_DATA_DIR',
    str(Path.home() / f'.config/chrome-cdp-{LOCAL_CDP_PORT}'),
)
LOCAL_CDP_BROWSER_BIN = os.environ.get('LOCAL_CDP_BROWSER_BIN', '').strip()
LOCAL_CDP_HEADLESS = os.environ.get('LOCAL_CDP_HEADLESS', '').strip().lower() in {'1', 'true', 'yes', 'on'}
LOCAL_CDP_EXTERNAL_ONLY = os.environ.get('LOCAL_CDP_EXTERNAL_ONLY', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}

logger = logging.getLogger(__name__)

_LOCAL_CDP_SESSION_LOCK = threading.Lock()
_LOCAL_CDP_ACTIVE_SESSIONS = 0

_DINGTALK_TOKEN_CACHE: dict[str, Any] = {
    'token': '',
    'expires_at': 0.0,
}


class BaosenLoginError(RuntimeError):
    """堡森登录失败，且继续重试通常不会改变结果。"""


def get_baosen_credentials() -> tuple[str, str]:
    return get_env('BAOSEN_USERNAME'), get_env('BAOSEN_PASSWORD')


def load_env(path: Path = ENV_PATH) -> None:
    _preload_env(path)


def get_env(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value:
        raise ValueError(f'缺少环境变量: {name}')
    return value


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


def parse_track_time(value: str) -> datetime | None:
    text = (value or '').strip()
    if not text:
        return None

    chinese_match = re.match(
        r'^(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s*GMT[+-]\d+)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$',
        text,
    )
    if chinese_match:
        year, month, day, hour, minute, second = chinese_match.groups()
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second or 0),
        )

    normalized = text.replace('UTC', '').replace('T', ' ').strip()
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue

    english_normalized = re.sub(r'\s*GMT[+-]\d+\s*$', '', text, flags=re.I).strip()
    english_formats = [
        '%b %d, %Y, %I:%M %p',
        '%B %d, %Y, %I:%M %p',
    ]
    for fmt in english_formats:
        try:
            return datetime.strptime(english_normalized, fmt)
        except ValueError:
            continue
    return None


def dedupe_repeated_text(value: Any) -> str:
    text = clean_text(value)
    half = len(text) // 2
    if half > 0 and len(text) % 2 == 0 and text[:half] == text[half:]:
        return text[:half]
    return text


def sort_tracks_newest_first(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(tracks))

    def sort_key(item):
        index, track = item
        parsed = parse_track_time(str(track.get('时间', '')))
        return (parsed is not None, parsed or datetime.min, -index)

    sorted_items = sorted(indexed, key=sort_key, reverse=True)
    return [track for _, track in sorted_items]


def normalize_compare_text(value: Any) -> str:
    return clean_text(value).replace('！', '!').replace('：', ':').lower()


def format_timestamp_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')


def normalize_field_value(value: Any) -> Any:
    if isinstance(value, dict):
        if 'name' in value:
            return value['name']
        if 'value' in value:
            return normalize_field_value(value['value'])
        return {k: normalize_field_value(v) for k, v in value.items()}
    if isinstance(value, list):
        normalized_items = [clean_text(normalize_field_value(item)) for item in value]
        return ', '.join(item for item in normalized_items if item)
    if isinstance(value, int) and value > 1_000_000_000_000:
        return format_timestamp_ms(value)
    return value


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        normalized[key] = normalize_field_value(value)
    return normalized


def get_dingtalk_access_token() -> str:
    now = time.time()
    cached_token = _DINGTALK_TOKEN_CACHE.get('token', '')
    expires_at = float(_DINGTALK_TOKEN_CACHE.get('expires_at', 0.0) or 0.0)
    if cached_token and now < expires_at:
        logger.info("钉钉 access token: 使用缓存")
        return cached_token

    logger.info("钉钉 access token: 开始请求")
    response = requests.post(
        f'{DINGTALK_API_BASE}/v1.0/oauth2/accessToken',
        json={
            'appKey': get_env('DINGTALK_APP_KEY'),
            'appSecret': get_env('DINGTALK_APP_SECRET'),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get('accessToken') or payload.get('access_token')
    if not token:
        raise ValueError(f'钉钉 access token 获取失败: {payload}')
    expires_in = int(payload.get('expireIn') or payload.get('expiresIn') or payload.get('expires_in') or 7200)
    _DINGTALK_TOKEN_CACHE['token'] = token
    _DINGTALK_TOKEN_CACHE['expires_at'] = now + max(expires_in - 300, 60)
    logger.info("钉钉 access token: 获取成功")
    return token


def dingtalk_headers() -> dict[str, str]:
    return {
        'x-acs-dingtalk-access-token': get_dingtalk_access_token(),
        'Content-Type': 'application/json',
    }


def _dingtalk_get_json(url: str, params: dict[str, Any], *, label: str, max_attempts: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    last_status: int | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                url,
                headers=dingtalk_headers(),
                params=params,
                timeout=30,
            )
            last_status = response.status_code
            if response.status_code >= 500:
                logger.warning(
                    "%s: 服务端错误 status=%s attempt=%s body=%s",
                    label,
                    response.status_code,
                    attempt,
                    response.text[:500],
                )
                time.sleep(1.5 * attempt)
                continue
            if response.status_code >= 400:
                logger.warning(
                    "%s: 客户端错误 status=%s attempt=%s body=%s",
                    label,
                    response.status_code,
                    attempt,
                    response.text[:500],
                )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("%s: 请求异常 attempt=%s error=%s", label, attempt, exc)
            time.sleep(1.5 * attempt)

    if last_error is not None:
        raise RuntimeError(f'{label} 失败 status={last_status} error={last_error}') from last_error
    raise RuntimeError(f'{label} 失败 status={last_status}')


def get_all_sheets(document_id: str) -> list[dict[str, Any]]:
    logger.info("钉钉表格: 获取 sheet 列表")
    payload = _dingtalk_get_json(
        f'{DINGTALK_API_BASE}/v1.0/notable/bases/{document_id}/sheets',
        {'operatorId': DINGTALK_OPERATOR_ID},
        label='钉钉表格: 获取 sheet 列表',
    )
    sheets = payload.get('value') or payload.get('sheets') or payload.get('items') or payload.get('data') or []
    if not isinstance(sheets, list):
        raise ValueError(f'钉钉数据表列表返回格式异常: {payload}')
    logger.info("钉钉表格: sheet 数量 %s", len(sheets))
    return sheets


def pick_sheet(document_id: str, sheets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sheets = sheets or get_all_sheets(document_id)
    if not sheets:
        raise ValueError('当前文档下未查询到任何数据表')

    target_name = normalize_compare_text(os.environ.get('DINGTALK_TARGET_SHEET_NAME', DINGTALK_TARGET_SHEET_NAME))
    for sheet in sheets:
        title = normalize_compare_text(sheet.get('name') or sheet.get('title') or sheet.get('sheetName') or '')
        if title == target_name:
            logger.info("钉钉表格: 命中目标 sheet %s", title)
            return sheet

    logger.info("钉钉表格: 未命中目标 sheet，回退到第一个 sheet")
    return sheets[0]


def get_sheet_records(document_id: str, sheet_id: str) -> list[dict[str, Any]]:
    all_records = []
    next_token = None

    while True:
        logger.info("钉钉表格: 拉取记录 sheet_id=%s nextToken=%s", sheet_id, next_token or "")
        params = {'operatorId': DINGTALK_OPERATOR_ID}
        if next_token:
            params['nextToken'] = next_token

        try:
            payload = _dingtalk_get_json(
                f'{DINGTALK_API_BASE}/v1.0/notable/bases/{document_id}/sheets/{sheet_id}/records',
                params,
                label='钉钉表格: 拉取记录',
            )
        except Exception as exc:
            logger.error("钉钉表格: 拉取失败，返回部分数据 error=%s", exc)
            break
        records = payload.get('records') or payload.get('items') or payload.get('data') or []
        if not isinstance(records, list):
            raise ValueError(f'钉钉数据表记录返回格式异常: {payload}')

        all_records.extend(records)

        if not payload.get('hasMore'):
            break
        next_token = payload.get('nextToken')

    logger.info("钉钉表格: sheet_id=%s 记录数=%s", sheet_id, len(all_records))
    return all_records


def iter_search_sheets(document_id: str) -> list[dict[str, Any]]:
    sheets = get_all_sheets(document_id)
    preferred_sheet = pick_sheet(document_id, sheets=sheets)
    preferred_id = str(preferred_sheet.get('id') or preferred_sheet.get('sheetId') or preferred_sheet.get('sheet_id') or '')
    ordered: list[dict[str, Any]] = [preferred_sheet]
    for sheet in sheets:
        sheet_id = str(sheet.get('id') or sheet.get('sheetId') or sheet.get('sheet_id') or '')
        if sheet_id and sheet_id != preferred_id:
            ordered.append(sheet)
    return ordered


def record_matches_target(normalized: dict[str, Any], target: str) -> bool:
    if not target:
        return False
    candidates = [
        clean_text(normalized.get('FBA编码', '')),
        clean_text(normalized.get('物流编号', '')),
    ]
    for candidate in candidates:
        if candidate and (target in candidate or candidate in target):
            return True

    blob = '\n'.join(clean_text(value) for value in normalized.values())
    return target in blob


def get_primary_logistics_no(order: dict[str, Any] | None) -> str:
    if not order:
        return ''

    raw_source = str(order.get('物流编号', '') or '')
    raw_value = clean_text(raw_source)
    if not raw_value or raw_value == '/':
        return ''

    matched_codes = re.findall(r'[A-Za-z]{2,}\d{6,}', raw_source)
    if matched_codes:
        return clean_text(matched_codes[0])

    parts = [
        clean_text(item)
        for item in re.split(r'[\s,，;；|｜/]+', raw_source)
        if clean_text(item) and clean_text(item) != '/'
    ]
    if parts:
        return parts[0]
    return raw_value


def find_order_by_fba(fba_code: str) -> dict[str, Any] | None:
    target = clean_text(fba_code)
    logger.info("查询订单: FBA=%s", target)
    for sheet in iter_search_sheets(DINGTALK_DOC_ID):
        sheet_id = str(sheet.get('id') or sheet.get('sheetId') or sheet.get('sheet_id') or '')
        if not sheet_id:
            continue
        records = get_sheet_records(DINGTALK_DOC_ID, sheet_id)
        for record in records:
            fields = record.get('fields', record)
            normalized = normalize_record(fields)
            if record_matches_target(normalized, target):
                logger.info("查询订单: 命中 sheet=%s record_id=%s", sheet.get('name') or sheet.get('title') or '', record.get('id', ''))
                normalized['__record_id__'] = record.get('id', '')
                normalized['__sheet_id__'] = sheet_id
                normalized['__sheet_name__'] = sheet.get('name') or sheet.get('title') or sheet.get('sheetName') or ''
                return normalized
    logger.info("查询订单: 未命中 FBA=%s", target)
    return None


def normalize_agl_username(username: str) -> str:
    username = clean_text(username)
    phone_match = re.fullmatch(r'(\+\d+)[A-Za-z]+', username)
    if phone_match:
        return phone_match.group(1)
    return username


def click_if_visible(page, selectors: list[str], timeout: int = 2000) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state='visible', timeout=timeout)
            locator.click()
            return True
        except Exception:
            continue
    return False


def click_first_visible(locator, timeout: int = 2000) -> bool:
    try:
        if locator.count() == 0:
            return False
    except Exception:
        return False

    for index in range(locator.count()):
        item = locator.nth(index)
        try:
            item.wait_for(state='visible', timeout=timeout)
            item.click()
            return True
        except Exception:
            continue
    return False


def maybe_select_agl_account(page) -> bool:
    direct_selectors = [
        "button:has-text('选择账户')",
        "button:has-text('Select account')",
        "text='选择账户'",
        "text='Select account'",
    ]
    if click_if_visible(page, direct_selectors, timeout=1500):
        return True

    account_candidates = [
        page.locator("button:has-text('Select account')"),
        page.locator("button:has-text('选择账户')"),
        page.locator("button").filter(has_text=re.compile(r'^A[0-9A-Z]+$')),
    ]
    for locator in account_candidates:
        if click_first_visible(locator, timeout=1500):
            return True
    return False


def set_agl_language_to_zh(page) -> str:
    current_language_selectors = [
        "button:has-text('简体中文')",
        "kat-button:has-text('简体中文')",
        "text='简体中文'",
    ]
    if any(page.locator(selector).count() > 0 for selector in current_language_selectors):
        return '简体中文'

    menu_selectors = [
        "button[aria-label*='language' i]",
        "button:has-text('English')",
        "button:has-text('EN')",
        "div:has-text('English') >> button",
        "div[role='button']:has-text('English')",
    ]
    option_selectors = [
        "text=简体中文",
        "text='Chinese (Simplified)'",
        "[role='option']:has-text('简体中文')",
        "[role='option']:has-text('Chinese (Simplified)')",
        "li:has-text('简体中文')",
        "li:has-text('Chinese (Simplified)')",
        "button:has-text('简体中文')",
        "button:has-text('Chinese (Simplified)')",
    ]
    if click_if_visible(page, menu_selectors):
        page.wait_for_timeout(800)
        if click_if_visible(page, option_selectors, timeout=3000):
            page.wait_for_load_state('networkidle')
            return '简体中文'
    if any(page.locator(selector).count() > 0 for selector in current_language_selectors):
        return '简体中文'
    return clean_text(page.locator('html').get_attribute('lang') or '')


def extract_agl_tracking(page) -> list[dict[str, str]]:
    tracker_root = page.locator('.kat-progress-tracker').first
    try:
        if tracker_root.count() > 0:
            raw_lines = [dedupe_repeated_text(line) for line in tracker_root.first.inner_text().splitlines()]
            lines = [line for line in raw_lines if line]
            section_headers = {
                '已预订', '装货港口', '运输途中', '卸货港口', '正在配送', '已配送至亚马逊运营中心'
            }
            tracker_items: list[dict[str, str]] = []

            def is_time_line(text: str) -> bool:
                return parse_track_time(text) is not None or text == '—'

            def is_noise_line(text: str) -> bool:
                if text in section_headers:
                    return True
                if text.startswith('POC') or text.startswith('原配送目的地：'):
                    return True
                if len(text) <= 2 and all(ord(ch) > 0xE000 for ch in text):
                    return True
                return False

            i = 0
            while i < len(lines):
                line = lines[i]
                if not is_time_line(line):
                    i += 1
                    continue

                content_lines: list[str] = []
                j = i + 1
                while j < len(lines):
                    candidate = lines[j]
                    if is_noise_line(candidate):
                        j += 1
                        continue
                    if is_time_line(candidate):
                        break
                    content_lines.append(candidate)
                    j += 1

                if content_lines:
                    tracker_items.append({'时间': line, '内容': ' | '.join(content_lines)})
                i = max(j, i + 1)

            if tracker_items:
                return tracker_items
    except Exception:
        pass

    timeline_buttons = page.locator("button").filter(
        has_text=re.compile(r'(GMT|Booking|Cargo|Departed|Arrived|Customs|Delivered|Port of|Loaded|Unloaded)', re.I)
    )
    items: list[dict[str, str]] = []
    if timeline_buttons.count() > 0:
        for index in range(timeline_buttons.count()):
            text = clean_text(timeline_buttons.nth(index).inner_text())
            if not text:
                continue
            match = re.match(
                r'^(?P<time>.*?(?:GMT[+-]\d+)?)(?P<content>(Booking|Cargo|Departed|Arrived|Customs|Delivered|Port of|Loaded|Unloaded).*)$',
                text,
                re.I,
            )
            if match:
                items.append({
                    '时间': clean_text(match.group('time')),
                    '内容': clean_text(match.group('content')),
                })
            else:
                items.append({'时间': '', '内容': text})
        if items:
            return items

    selectors = [
        'table tbody tr',
        '[role="table"] [role="row"]',
        '.ant-timeline-item',
        '[class*="timeline"] [class*="item"]',
    ]
    items: list[dict[str, str]] = []
    for selector in selectors:
        rows = page.locator(selector)
        count = rows.count()
        if count == 0:
            continue
        for index in range(count):
            text = clean_text(rows.nth(index).inner_text())
            if not text:
                continue
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) >= 2:
                items.append({'时间': lines[0], '内容': ' | '.join(lines[1:])})
            else:
                items.append({'时间': '', '内容': lines[0]})
        if items:
            return items

    tracker_text = clean_text(page.locator('.kat-progress-tracker').first.inner_text())
    if tracker_text:
        return [{'时间': '', '内容': tracker_text[:2000]}]
    return []


def wait_for_agl_tracking_stability(page, wait_ms: int = 1500, max_checks: int = 4) -> list[dict[str, str]]:
    previous_snapshot = ''
    latest_tracks: list[dict[str, str]] = []

    for index in range(max_checks):
        latest_tracks = sort_tracks_newest_first(extract_agl_tracking(page))
        snapshot = clean_text(page.locator('.kat-progress-tracker').first.inner_text())

        if latest_tracks and not snapshot:
            return latest_tracks

        if snapshot and snapshot == previous_snapshot:
            return latest_tracks

        previous_snapshot = snapshot
        if index < max_checks - 1:
            page.wait_for_timeout(wait_ms)

    return latest_tracks


def get_agl_credentials(order: dict[str, Any]) -> tuple[str, str, str]:
    brand = clean_text(order.get('品牌', ''))
    if brand.upper() in {'TOLESA', 'EZARC'}:
        return (
            normalize_agl_username(get_env('AGL_EASYCAN_USERNAME')),
            get_env('AGL_EASYCAN_PASSWORD'),
            'AGL_EASYCAN',
        )
    return (
        normalize_agl_username(get_env('AGL_USERNAME')),
        get_env('AGL_PASSWORD'),
        'AGL_DEFAULT',
    )


def create_agl_page(playwright, credential_source: str, headless: bool):
    browser = playwright.chromium.connect_over_cdp(get_local_cdp_endpoint())
    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context(
        viewport={'width': 1440, 'height': 960},
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
    )
    try:
        context.clear_cookies()
    except Exception:
        pass
    try:
        context.add_init_script(
            """
            (() => {
              const credentials = navigator.credentials;
              if (!credentials) {
                return;
              }
              const originalGet = credentials.get ? credentials.get.bind(credentials) : null;
              const originalCreate = credentials.create ? credentials.create.bind(credentials) : null;
              if (originalGet) {
                credentials.get = (options) => {
                  if (options && options.publicKey) {
                    return Promise.reject(new DOMException('Passkey disabled by automation', 'NotSupportedError'));
                  }
                  return originalGet(options);
                };
              }
              if (originalCreate) {
                credentials.create = (options) => {
                  if (options && options.publicKey) {
                    return Promise.reject(new DOMException('Passkey disabled by automation', 'NotSupportedError'));
                  }
                  return originalCreate(options);
                };
              }
            })();
            """
        )
    except Exception:
        pass
    _ = credential_source, headless
    page = context.new_page()
    try:
        page.bring_to_front()
    except Exception:
        pass

    def cleanup():
        browser.close()

    return browser, context, page, cleanup


def _fetch_local_cdp_metadata() -> dict[str, Any] | None:
    try:
        response = requests.get(f'{LOCAL_CDP_URL}/json/version/', timeout=2)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get('webSocketDebuggerUrl'):
            return payload
    except (requests.RequestException, ValueError):
        return None
    return None


def get_local_cdp_endpoint() -> str:
    metadata = _fetch_local_cdp_metadata()
    if not metadata:
        raise RuntimeError(
            f'本地 CDP 服务不可用: {LOCAL_CDP_URL}/json/version/ 未返回有效的 webSocketDebuggerUrl'
        )
    endpoint = str(metadata['webSocketDebuggerUrl'])
    parsed = urlparse(endpoint)
    if parsed.hostname in {'127.0.0.1', 'localhost'} and LOCAL_CDP_HOST not in {'127.0.0.1', 'localhost'}:
        host = LOCAL_CDP_HOST
        if parsed.port:
            host = f'{host}:{parsed.port}'
        endpoint = urlunparse(parsed._replace(netloc=host))
    return endpoint


def is_local_cdp_listening(host: str = LOCAL_CDP_HOST, port: int = LOCAL_CDP_PORT) -> bool:
    _ = host, port
    return _fetch_local_cdp_metadata() is not None


def is_local_port_in_use(host: str = LOCAL_CDP_HOST, port: int = LOCAL_CDP_PORT) -> bool:
    try:
        response = requests.get(LOCAL_CDP_URL, timeout=2)
        return response is not None
    except requests.RequestException:
        return False


def cleanup_stale_cdp_profile_locks(user_data_dir: str) -> None:
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
            logger.warning("清理 CDP 用户目录锁文件失败: path=%s error=%s", entry, exc)


def ensure_local_cdp_browser():
    if is_local_cdp_listening():
        logger.info("本地 CDP: 复用现有服务 %s", f'{LOCAL_CDP_URL}/json/version/')
        return None

    if LOCAL_CDP_EXTERNAL_ONLY:
        raise RuntimeError(
            f'项目配置为仅使用外部 CDP，但当前不可访问: {LOCAL_CDP_URL}/json/version/。'
            '请先在宿主机启动项目专用 Chrome/CDP，再重试查询'
        )

    if LOCAL_CDP_HOST not in {'127.0.0.1', 'localhost'}:
        raise RuntimeError(
            f'宿主机 CDP 服务不可用: {LOCAL_CDP_URL}/json/version/ 未响应。'
            '请先在宿主机启动项目专用 Chrome，再重试查询'
        )

    if is_local_port_in_use():
        raise RuntimeError(
            f'本地端口 {LOCAL_CDP_PORT} 已被占用，但不是 Chrome DevTools 服务；'
            '请更换 LOCAL_CDP_PORT，或停止当前占用该端口的服务'
        )

    Path(LOCAL_CDP_USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
    cleanup_stale_cdp_profile_locks(LOCAL_CDP_USER_DATA_DIR)
    browser_bin = resolve_local_cdp_browser_bin()
    launch_args = [
        browser_bin,
        '--new-window',
        f'--remote-debugging-address={LOCAL_CDP_HOST}',
        f'--remote-debugging-port={LOCAL_CDP_PORT}',
        f'--user-data-dir={LOCAL_CDP_USER_DATA_DIR}',
        '--no-first-run',
        '--no-default-browser-check',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-blink-features=AutomationControlled',
        '--lang=zh-CN',
    ]
    if LOCAL_CDP_HEADLESS:
        launch_args.append('--headless=new')
    launch_args.append('about:blank')

    logger.info(
        "本地 CDP: 启动浏览器 bin=%s host=%s port=%s headless=%s user_data_dir=%s",
        browser_bin,
        LOCAL_CDP_HOST,
        LOCAL_CDP_PORT,
        LOCAL_CDP_HEADLESS,
        LOCAL_CDP_USER_DATA_DIR,
    )

    process = subprocess.Popen(
        launch_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    if LOCAL_CDP_HOST in {'127.0.0.1', 'localhost'}:
        pid_file = Path(f'/tmp/dingtalk-ltq-cdp-{LOCAL_CDP_PORT}.pid')
        try:
            pid_file.write_text(str(process.pid), encoding='utf-8')
        except OSError as exc:
            logger.warning("记录本地 CDP 进程 PID 失败: path=%s error=%s", pid_file, exc)

    for _ in range(20):
        if is_local_cdp_listening():
            logger.info("本地 CDP: 启动成功 %s", f'{LOCAL_CDP_URL}/json/version/')
            return process
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                '本地CDP浏览器进程已退出: '
                f'exit_code={exit_code} bin={browser_bin} host={LOCAL_CDP_HOST} '
                f'port={LOCAL_CDP_PORT} user_data_dir={LOCAL_CDP_USER_DATA_DIR}'
            )
        time.sleep(0.5)

    process.terminate()
    raise RuntimeError(
        '无法启动本地CDP浏览器，请检查浏览器是否可用: '
        f'{browser_bin} host={LOCAL_CDP_HOST} port={LOCAL_CDP_PORT} '
        f'headless={LOCAL_CDP_HEADLESS} user_data_dir={LOCAL_CDP_USER_DATA_DIR}'
    )


def begin_local_cdp_session() -> subprocess.Popen | None:
    global _LOCAL_CDP_ACTIVE_SESSIONS
    with _LOCAL_CDP_SESSION_LOCK:
        process = ensure_local_cdp_browser()
        _LOCAL_CDP_ACTIVE_SESSIONS += 1
        logger.info("本地 CDP: 会话开始 active_sessions=%s", _LOCAL_CDP_ACTIVE_SESSIONS)
        return process


def end_local_cdp_session(process: subprocess.Popen | None = None) -> None:
    global _LOCAL_CDP_ACTIVE_SESSIONS
    with _LOCAL_CDP_SESSION_LOCK:
        if _LOCAL_CDP_ACTIVE_SESSIONS > 0:
            _LOCAL_CDP_ACTIVE_SESSIONS -= 1
        active_sessions = _LOCAL_CDP_ACTIVE_SESSIONS

    if active_sessions > 0:
        logger.info("本地 CDP: 保持浏览器运行 active_sessions=%s", active_sessions)
        return

    stop_local_cdp_browser(process)


def stop_local_cdp_browser(process: subprocess.Popen | None = None) -> None:
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception as exc:
            logger.warning("停止本地 CDP 进程失败: %s", exc)

    if LOCAL_CDP_HOST not in {'127.0.0.1', 'localhost'}:
        return

    pid_file = Path(f'/tmp/dingtalk-ltq-cdp-{LOCAL_CDP_PORT}.pid')
    pid = ''
    if pid_file.exists():
        try:
            pid = pid_file.read_text(encoding='utf-8').strip()
        except OSError:
            pid = ''
        try:
            pid_file.unlink()
        except OSError:
            pass

    if pid:
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(['kill', pid], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    try:
        if os.name == 'nt':
            # pkill is not available on Windows
            pass
        else:
            subprocess.run(
                ['pkill', '-f', f'remote-debugging-port={LOCAL_CDP_PORT}'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as exc:
        logger.warning("按端口停止本地 CDP 进程失败: %s", exc)


def _get_playwright_chromium_executable_path() -> str:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            return str(getattr(playwright.chromium, 'executable_path', '') or '').strip()
    except Exception as exc:
        logger.debug("读取 Playwright Chromium 路径失败: %s", exc)
        return ''


def resolve_local_cdp_browser_bin() -> str:
    if LOCAL_CDP_BROWSER_BIN:
        return LOCAL_CDP_BROWSER_BIN

    local_app_data = os.environ.get('LOCALAPPDATA', '')
    program_files = os.environ.get('ProgramFiles', '')
    program_files_x86 = os.environ.get('ProgramFiles(x86)', '')

    if os.name == 'nt':
        executable_path = _get_playwright_chromium_executable_path()
        if executable_path and os.path.exists(executable_path):
            return executable_path
    candidates = []
    candidates.extend(sorted(glob.glob('/ms-playwright/chromium-*/chrome-linux/chrome')))
    if local_app_data:
        candidates.extend(sorted(glob.glob(str(Path(local_app_data) / 'ms-playwright' / 'chromium-*' / 'chrome-win' / 'chrome.exe'))))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    if os.name == 'nt':
        raise RuntimeError(
            'Windows 下需要使用 Playwright Chromium 启动本地 CDP；'
            '请先执行 python -m playwright install chromium，'
            '或手动设置 LOCAL_CDP_BROWSER_BIN 指向 chrome-win\\chrome.exe'
        )

    candidates.extend([
        shutil.which('google-chrome'),
        shutil.which('google-chrome-stable'),
        shutil.which('chromium'),
        shutil.which('chromium-browser'),
        shutil.which('chrome'),
        shutil.which('msedge'),
    ])
    for base_dir in (local_app_data, program_files, program_files_x86):
        if not base_dir:
            continue
        candidates.extend([
            str(Path(base_dir) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'),
            str(Path(base_dir) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'),
        ])
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    raise RuntimeError(
        '未找到可用浏览器，请安装 Chrome/Edge/chromium，或设置 LOCAL_CDP_BROWSER_BIN'
    )


def logout_agl(page) -> bool:
    menu_selectors = [
        'kat-icon[name="person"]',
        'kat-button:has(kat-icon[name="person"])',
        'button:has(kat-icon[name="person"])',
        'button[aria-label*="account" i]',
        'button[aria-label*="profile" i]',
        'button[aria-label*="user" i]',
        'text="用户信息"',
        'text="User info"',
        'text="Account"',
        'text="账户"',
    ]
    logout_selectors = [
        'kat-link[label="退出"]',
        '.kat-row.menu-padding kat-link[label="退出"]',
        '.kat-row.menu-padding:has-text("退出")',
        'text="退出登录"',
        'text="退出"',
        'text="Sign out"',
        'text="Log out"',
        'a:has-text("退出")',
        'button:has-text("退出登录")',
        'button:has-text("Sign out")',
        'button:has-text("Log out")',
    ]

    click_if_visible(page, menu_selectors, timeout=1500)
    page.wait_for_timeout(800)
    if click_if_visible(page, logout_selectors, timeout=2000):
        page.wait_for_timeout(1500)
        return True
    return False


def _is_agl_signin_page(page) -> bool:
    return 'signin' in page.url.lower()


def _retry_agl_tracking_fetch(page, tracking_url: str) -> list[dict[str, str]]:
    logger.info("AGL 查询: 首次未抓到轨迹，尝试页内刷新后重试")
    try:
        page.reload(wait_until='domcontentloaded', timeout=60000)
    except Exception as reload_exc:
        logger.warning("AGL 查询: 刷新追踪页失败，改为重新打开 tracking URL: %s", reload_exc)
        page.goto(tracking_url, wait_until='domcontentloaded', timeout=60000)

    page.wait_for_timeout(1500)
    maybe_select_agl_account(page)
    page.wait_for_load_state('networkidle')
    return wait_for_agl_tracking_stability(page)


def query_agl(booking_id: str, order: dict[str, Any], headless: bool = False) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    username, password, credential_source = get_agl_credentials(order)
    logger.info("AGL 查询: booking_id=%s 账号来源=%s headless=%s", booking_id, credential_source, False)
    cdp_process = begin_local_cdp_session()

    with sync_playwright() as p:
        browser, context, page, cleanup = create_agl_page(p, credential_source, False)

        try:
            tracking_url = AGL_TRACKING_URL.format(booking_id=booking_id)
            logger.info("AGL 查询: 打开追踪页 %s", tracking_url)
            page.goto(tracking_url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(1500)

            logger.info("AGL 查询: 尝试选择账户")
            maybe_select_agl_account(page)

            if page.locator('#ap_email').first.is_visible():
                logger.info("AGL 查询: 填写账号")
                page.locator('#ap_email').fill(username)
                page.wait_for_timeout(600)
                page.locator('input#continue').click()
                page.wait_for_timeout(1500)
                invalid_account = page.get_by_text('Wrong or Invalid email address', exact=False).count() > 0
                if invalid_account:
                    raise RuntimeError(f'AGL 账号格式无效: {username}')

            if page.locator('#ap_password').first.count() > 0:
                logger.info("AGL 查询: 填写密码")
                password_locator = page.locator('#ap_password').first
                password_locator.wait_for(state='visible', timeout=15000)
                password_locator.fill(password)
                page.wait_for_timeout(600)
                page.locator('input#signInSubmit').click()
                page.wait_for_timeout(2500)

            if page.get_by_text('Your password is incorrect', exact=False).count() > 0:
                raise RuntimeError('AGL 登录失败: 密码错误')

            if 'ap/mfa' in page.url.lower() or page.get_by_text('Two-Step Verification', exact=False).count() > 0:
                logger.warning("AGL 查询: 触发 MFA")
                return {
                    '平台': 'AGL',
                    '查询值': booking_id,
                    '账号来源': credential_source,
                    '错误': 'AGL 登录需要二次验证',
                    '阻塞原因': 'MFA_REQUIRED',
                    '当前URL': page.url,
                    '当前页面标题': page.title(),
                    '页面文本': clean_text(page.locator('body').inner_text())[:2000],
                }

            maybe_select_agl_account(page)
            page.wait_for_timeout(1500)

            page.goto(tracking_url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(1500)

            maybe_select_agl_account(page)
            page.wait_for_timeout(1500)
            logger.info("AGL 查询: 切换语言")
            language = set_agl_language_to_zh(page)
            page.wait_for_timeout(2000)

            if 'global-picker' in page.url.lower():
                maybe_select_agl_account(page)
                page.wait_for_timeout(2500)

            if _is_agl_signin_page(page):
                return {
                    '平台': 'AGL',
                    '查询值': booking_id,
                    '账号来源': credential_source,
                    '错误': 'AGL 登录后仍停留在登录页',
                    '阻塞原因': 'LOGIN_NOT_COMPLETED',
                    '当前URL': page.url,
                    '当前页面标题': page.title(),
                    '页面文本': clean_text(page.locator('body').inner_text())[:2000],
                }

            page.wait_for_load_state('networkidle')
            tracks = wait_for_agl_tracking_stability(page)
            if not tracks and not _is_agl_signin_page(page):
                tracks = _retry_agl_tracking_fetch(page, tracking_url)
            logger.info("AGL 查询: 轨迹条数=%s", len(tracks))
            latest_track = tracks[0] if tracks else {}
            return {
                '平台': 'AGL',
                '查询值': booking_id,
                '账号来源': credential_source,
                '语言': language,
                '当前URL': page.url,
                '当前页面标题': page.title(),
                '最新轨迹': latest_track,
                '物流轨迹': tracks,
            }
        except PlaywrightTimeoutError as exc:
            tracks = wait_for_agl_tracking_stability(page, wait_ms=800, max_checks=2)
            if not tracks and not _is_agl_signin_page(page):
                try:
                    tracks = _retry_agl_tracking_fetch(page, tracking_url)
                except Exception as retry_exc:
                    logger.warning("AGL 查询: 超时后页内重试失败: %s", retry_exc)
            if tracks and not _is_agl_signin_page(page):
                return {
                    '平台': 'AGL',
                    '查询值': booking_id,
                    '账号来源': credential_source,
                    '语言': set_agl_language_to_zh(page),
                    '当前URL': page.url,
                    '当前页面标题': page.title(),
                    '最新轨迹': tracks[0],
                    '物流轨迹': tracks,
                    '警告': f'AGL 页面等待超时，但已抓取到轨迹内容: {exc}',
                }
            return {
                '平台': 'AGL',
                '查询值': booking_id,
                '账号来源': credential_source,
                '错误': f'AGL 页面等待超时: {exc}',
                '当前URL': page.url,
                '当前页面标题': page.title(),
                '页面文本': clean_text(page.locator('body').inner_text())[:2000],
            }
        except Exception as exc:
            return {
                '平台': 'AGL',
                '查询值': booking_id,
                '账号来源': credential_source,
                '错误': str(exc),
                '当前URL': page.url,
                '当前页面标题': page.title(),
                '页面文本': clean_text(page.locator('body').inner_text())[:2000],
            }
        finally:
            try:
                logger.info("AGL 查询: 尝试退出登录")
                logout_agl(page)
            except Exception as logout_exc:
                logger.warning("AGL 查询: 退出登录失败: %s", logout_exc)
            cleanup()
            end_local_cdp_session(cdp_process)


def extract_baosen_track_items_from_html(html: str) -> list[dict[str, str]]:
    parts = re.split(r'<li[^>]*class="[^"]*el-timeline-item[^"]*"[^>]*>', html)
    items: list[dict[str, str]] = []

    for part in parts:
        if 'operation-time' not in part or 'class="operation"' not in part:
            continue

        time_match = re.search(r'<div[^>]*class="operation-time[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>', part, re.S)
        content_match = re.search(r'<div[^>]*class="operation"[^>]*>.*?<span[^>]*>(.*?)</span>', part, re.S)
        if not time_match or not content_match:
            continue

        time_text = clean_text(unescape(re.sub(r'<[^>]+>', '', time_match.group(1))))
        content_text = clean_text(unescape(re.sub(r'<[^>]+>', '', content_match.group(1))))
        if not time_text or not content_text:
            continue

        items.append({'时间': time_text, '内容': content_text})

    return items


def extract_17track_items_from_html(html: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(
        r'<span[^>]*class="[^"]*yq-time[^"]*"[^>]*>(.*?)</span>\s*'
        r'<span[^>]*class="[^"]*flex-1[^"]*"[^>]*>(.*?)</span>',
        re.S,
    )
    for time_text, content_text in pattern.findall(html):
        time_clean = clean_text(re.sub(r'<[^>]+>', '', unescape(time_text)))
        content_clean = clean_text(re.sub(r'<[^>]+>', '', unescape(content_text)))
        if time_clean and content_clean:
            items.append({'时间': time_clean, '内容': content_clean})
    return items


async def query_17track(order_no: str) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    query_url = 'https://www.17track.net/zh-cn'
    logger.info("17TRACK 查询: order_no=%s", order_no)

    async def dismiss_17track_guide_popup(page) -> bool:
        popup_selectors = [
            'div.tooltip__body[role="alertdialog"]',
            'div.tooltip__body',
        ]
        close_selectors = [
            'button.tooltip__close',
            'button:has-text("关闭")',
            'button:has-text("知道了")',
        ]

        for popup_selector in popup_selectors:
            popup = page.locator(popup_selector).first
            try:
                if await popup.count() == 0 or not await popup.is_visible(timeout=300):
                    continue
            except Exception:
                continue

            logger.info("17TRACK 查询: 检测到引导弹窗，尝试关闭")
            for close_selector in close_selectors:
                try:
                    button = page.locator(close_selector).first
                    if await button.count() > 0 and await button.is_visible(timeout=500):
                        await button.click(timeout=2000)
                        await page.wait_for_timeout(800)
                        return True
                except Exception:
                    continue
        return False

    async def detect_human_verification(page) -> bool:
        selectors = [
            'iframe[src*="captcha"]',
            'iframe[src*="verify"]',
            '[class*="captcha"]',
            '[class*="verify"]',
            '[id*="captcha"]',
            '[id*="verify"]',
        ]
        text_patterns = [
            '人机验证',
            '完成验证',
            '安全验证',
            '请先验证',
            '看看右边的图片，找出它的“同类”吧',
            '看看右边的图片，找出它的"同类"吧',
            '刷新',
            '确认',
            'Verify you are human',
            'Security check',
            'CAPTCHA',
        ]

        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=300):
                    return True
            except Exception:
                continue

        for pattern in text_patterns:
            try:
                locator = page.get_by_text(pattern, exact=False).first
                if await locator.count() > 0 and await locator.is_visible(timeout=300):
                    return True
            except Exception:
                continue

        try:
            body_text = await page.locator('body').inner_text(timeout=1000)
        except Exception:
            body_text = ''
        body_text = clean_text(body_text)
        return any(pattern in body_text for pattern in text_patterns)

    cdp_process = begin_local_cdp_session()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(query_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(2500)
            await dismiss_17track_guide_popup(page)

            textarea = page.locator('textarea#auto-size-textarea').first
            await textarea.wait_for(state='visible', timeout=30000)
            await textarea.click()
            await textarea.fill(clean_text(order_no))
            await page.wait_for_timeout(1500)
            await dismiss_17track_guide_popup(page)

            search_button = page.locator('div.batch_track_search-area__9BaOs').first
            await search_button.wait_for(state='visible', timeout=15000)
            await search_button.click()
            await page.wait_for_timeout(1500)
            await dismiss_17track_guide_popup(page)

            captcha_detected = False
            timeline_root = page.locator('span.yq-time').first
            for _ in range(300):
                await dismiss_17track_guide_popup(page)
                if await detect_human_verification(page):
                    if not captcha_detected:
                        captcha_detected = True
                        logger.warning("17TRACK 查询: 检测到人机验证，请先在浏览器中完成验证，程序将继续等待")
                    await page.wait_for_timeout(1000)
                    continue

                try:
                    if await timeline_root.count() > 0 and await timeline_root.is_visible(timeout=300):
                        body_text = clean_text(await page.locator('body').inner_text(timeout=2000))
                        if 'TestNumber00017' in body_text and order_no not in body_text:
                            logger.warning("17TRACK 查询: 页面仍显示测试/旧结果，继续等待刷新")
                            await page.wait_for_timeout(1000)
                            continue
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
            else:
                if captcha_detected:
                    raise RuntimeError('17TRACK 人机验证等待超时，请完成验证后重试')
                raise RuntimeError('17TRACK 查询超时，未获取到轨迹结果')

            await page.wait_for_timeout(1500)

            timeline_container = page.locator('span.yq-time').locator('xpath=ancestor::div[contains(@class,"relative")][1]').first
            html = await timeline_container.inner_html(timeout=15000)
            track_items = sort_tracks_newest_first(extract_17track_items_from_html(html))
            latest_track = track_items[0] if track_items else {'时间': '', '内容': ''}
            logger.info("17TRACK 查询: 轨迹条数=%s", len(track_items))
            return {
                '平台': '17TRACK',
                '查询值': order_no,
                '当前页面标题': await page.title(),
                '当前URL': page.url,
                '最新轨迹': latest_track,
                '物流轨迹': track_items,
            }
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            end_local_cdp_session(cdp_process)


async def query_baosen(order_no: str) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    baosen_url = get_env('BAOSEN_URL') if os.environ.get('BAOSEN_URL') else 'https://www.baosencloud.com/orderManage/eCommerce/firstTransportDetails?type=2'
    baosen_username, baosen_password = get_baosen_credentials()

    logger.info("堡森查询: order_no=%s", order_no)

    async def dismiss_baosen_system_dialog() -> bool:
        dialog_selectors = [
            'div[role="dialog"][aria-label="系统提示"]',
            '.el-message-box__wrapper',
        ]
        confirm_selectors = [
            'button:has-text("确定")',
            'button:has-text("确认")',
            '.el-message-box__btns .el-button--primary',
        ]

        for selector in dialog_selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() > 0 and await locator.is_visible(timeout=1500):
                    logger.info("堡森查询: 检测到系统提示弹窗，尝试关闭")
                    for confirm_selector in confirm_selectors:
                        try:
                            confirm = page.locator(confirm_selector).first
                            await confirm.wait_for(state='visible', timeout=3000)
                            await confirm.click()
                            await page.wait_for_timeout(1000)
                            return True
                        except Exception:
                            continue
                    if False:
                        return True
            except Exception:
                continue
        return False

    async def click_baosen_login_button() -> None:
        selectors = [
            'button.el-button.btn',
            'form.login-form button[type="button"]',
        ]
        candidates = [page.locator(selector).first for selector in selectors]
        candidates.append(page.get_by_role('button', name=re.compile(r'登\s*录')).first)

        last_error: Exception | None = None
        for login_button in candidates:
            try:
                await login_button.wait_for(state='visible', timeout=3000)
            except Exception as exc:
                last_error = exc
                continue
            try:
                await login_button.click(timeout=5000)
                return
            except Exception:
                logger.info("堡森查询: 常规登录点击被遮挡，改用强制点击")
            await dismiss_baosen_system_dialog()
            try:
                await login_button.click(force=True, timeout=5000)
                return
            except Exception:
                logger.info("堡森查询: 强制点击失败，改用 DOM click")
            try:
                await login_button.evaluate('(node) => node.click()')
                return
            except Exception as exc:
                last_error = exc
                continue

        raise BaosenLoginError(f'堡森登录按钮不可用，无法触发登录: {last_error}')

    async def collect_baosen_login_diagnostics() -> str:
        text_candidates: list[str] = []
        selectors = [
            '.el-message--error',
            '.el-message-box__message',
            '.el-form-item__error',
            '.el-alert__content',
            '.error-msg',
            '.error-message',
            '.ant-message-error',
            '.ant-form-item-explain-error',
        ]

        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = min(await locator.count(), 5)
                for index in range(count):
                    item = locator.nth(index)
                    try:
                        if not await item.is_visible(timeout=500):
                            continue
                    except Exception:
                        continue
                    try:
                        text = clean_text(await item.inner_text(timeout=1000))
                    except Exception:
                        try:
                            text = clean_text(await item.text_content(timeout=1000))
                        except Exception:
                            text = ''
                    if text and text not in text_candidates:
                        text_candidates.append(text)
            except Exception:
                continue

        try:
            page_text = clean_text(await page.locator('body').inner_text(timeout=1500))
            for pattern in (
                r'(账号[^。；\n]{0,30}(?:错误|不存在|异常))',
                r'(密码[^。；\n]{0,30}(?:错误|不正确|异常))',
                r'(验证码[^。；\n]{0,30})',
                r'(登录[^。；\n]{0,30}(?:失败|异常|过期))',
                r'(请[^。；\n]{0,30}(?:登录|输入|验证))',
            ):
                match = re.search(pattern, page_text, flags=re.I)
                if match:
                    text = clean_text(match.group(1))
                    if text and text not in text_candidates:
                        text_candidates.append(text)
        except Exception:
            pass

        return ' | '.join(text_candidates[:3])

    async def baosen_requires_login() -> bool:
        selectors = (
            'input[placeholder="请输入账号"]',
            'input[placeholder="请输入密码"]',
        )
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=800):
                    return True
            except Exception:
                continue

        try:
            login_button = page.get_by_role('button', name=re.compile(r'登\s*录')).first
            if await login_button.count() > 0 and await login_button.is_visible(timeout=800):
                return True
        except Exception:
            pass

        return 'login' in page.url.lower()

    async def baosen_login_completed() -> bool:
        if 'login' not in page.url.lower():
            return True

        success_selectors = (
            'input[placeholder="请选择跳转订单"]',
            'text=电商订单详情',
            'text=头程订单管理',
        )
        for selector in success_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=800):
                    return True
            except Exception:
                continue

        return not await baosen_requires_login()

    async def ensure_baosen_logged_in() -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=2000)
            except Exception:
                pass
            await dismiss_baosen_system_dialog()
            if await baosen_login_completed():
                return
            await page.wait_for_timeout(500)

        if await baosen_requires_login():
            diagnostics = await collect_baosen_login_diagnostics()
            message = f'堡森登录未成功，当前仍停留在登录页: {page.url}'
            if diagnostics:
                logger.warning("堡森查询: 登录失败诊断=%s", diagnostics)
                message += f'。页面提示: {diagnostics}'
            message += '。请检查账号密码，或先在当前 CDP 用户目录中完成一次登录。'
            raise BaosenLoginError(message)

    cdp_process = begin_local_cdp_session()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context(viewport={'width': 1440, 'height': 900})
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Linux x86_64' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            window.chrome = window.chrome || { runtime: {} };
            if (!navigator.plugins || navigator.plugins.length === 0) {
              Object.defineProperty(navigator, 'plugins', {
                get: () => [
                  { name: 'Chrome PDF Plugin' },
                  { name: 'Chrome PDF Viewer' },
                  { name: 'Native Client' },
                ],
              });
            }
            """
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            logger.info("堡森查询: 打开目标页")
            await page.goto(baosen_url, wait_until='networkidle')
            await page.wait_for_timeout(1200)
            await dismiss_baosen_system_dialog()

            if await baosen_requires_login():
                logger.info("堡森查询: 检测到未登录状态，执行登录")
                await dismiss_baosen_system_dialog()
                await page.locator('input[placeholder="请输入账号"]').fill(baosen_username)
                await page.wait_for_timeout(500)
                await page.locator('input[placeholder="请输入密码"]').fill(baosen_password)
                await page.wait_for_timeout(500)
                if await page.locator('span.el-checkbox__inner').count() > 0:
                    await dismiss_baosen_system_dialog()
                    await page.locator('span.el-checkbox__inner').first.click()
                    await page.wait_for_timeout(500)
                await dismiss_baosen_system_dialog()
                await click_baosen_login_button()
                await ensure_baosen_logged_in()
            else:
                logger.info("堡森查询: 复用已有登录态，无需重复登录")

            logger.info("堡森查询: 输入订单并选择下拉项")
            jump_input = page.locator('input[placeholder="请选择跳转订单"]')
            await jump_input.click()
            await page.wait_for_timeout(500)
            await jump_input.press('Control+a')
            await jump_input.press('Backspace')
            await jump_input.type(clean_text(order_no), delay=180)
            await page.wait_for_timeout(1500)

            options = page.locator('li.el-select-dropdown__item')
            matched_option = options.filter(has_text=clean_text(order_no)).first
            await matched_option.wait_for(state='visible', timeout=15000)
            await matched_option.click()

            trajectory_box = page.locator('.trajectory-box')
            await trajectory_box.wait_for(state='visible', timeout=15000)
            await page.wait_for_timeout(1500)

            html = await page.locator('.trajectory-box').first.inner_html(timeout=15000)
            track_items = sort_tracks_newest_first(extract_baosen_track_items_from_html(html))
            logger.info("堡森查询: 轨迹条数=%s", len(track_items))
            latest_track = track_items[0] if track_items else {'时间': '', '内容': ''}
            return {
                '平台': '堡森',
                '查询值': order_no,
                '当前页面标题': await page.title(),
                '当前URL': page.url,
                '最新轨迹': latest_track,
                '物流轨迹': track_items,
            }
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            end_local_cdp_session(cdp_process)


def get_meitong_access_token() -> str:
    logger.info("美通: 获取 token")
    response = requests.post(
        f'{MEITONG_API_BASE}/v1/user/oauth/token',
        files={
            'grant_type': (None, 'password'),
            'client_id': (None, 'aaf'),
            'client_secret': (None, 'aaf88888888'),
            'login_type': (None, 'api_key'),
            'user_type': (None, '1'),
            'username': (None, get_env('MEITONG_API_USERNAME')),
            'password': (None, get_env('MEITONG_API_PASSWORD')),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get('access_token')
    if not token:
        raise ValueError(f'美通 token 获取失败: {payload.get("message", "未知错误")}')
    logger.info("美通: token 获取成功")
    return token


def query_meitong(fba_code: str) -> dict[str, Any]:
    logger.info("美通查询: orderNo=%s", fba_code)
    token = get_meitong_access_token()
    response = requests.get(
        f'{MEITONG_API_BASE}/v1/track/aafOrderTrack/getTrackInfo',
        params={'orderNo': fba_code},
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    raw_tracks = payload.get('data') or []

    def _extract_field(track: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in track and track.get(key) not in (None, '', '/'):
                return track.get(key)
        return ''

    def _normalize_track_items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
        time_keys = [
            '时间', 'time', 'Time', 'createTime', 'create_time', 'operationTime', 'operateTime',
            'trackingTime', 'trackTime', 'eventTime', 'opTime', 'acceptTime', 'date',
        ]
        content_keys = [
            '内容', 'content', 'desc', 'description', 'remark', 'status', 'statusDesc',
            'trackStatus', 'operation', 'operationName', 'node', 'event', 'eventDesc',
            'detail', 'message', 'info', 'log',
        ]
        location_keys = ['地点', 'location', 'place', 'city', 'port', 'site', 'position', 'address']

        normalized_items: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                normalized_items.append({'时间': '', '地点': '', '内容': clean_text(item)})
                continue

            raw_time = _extract_field(item, time_keys)
            raw_content = _extract_field(item, content_keys)
            raw_location = _extract_field(item, location_keys)

            if isinstance(raw_time, int) and raw_time > 1_000_000_000_000:
                time_text = format_timestamp_ms(raw_time)
            else:
                time_text = clean_text(raw_time)

            content_text = clean_text(raw_content)
            location_text = clean_text(raw_location)

            if not content_text:
                fallback = clean_text(json.dumps(item, ensure_ascii=False))
                content_text = fallback[:500] if fallback else ''

            normalized_items.append({
                '时间': time_text,
                '地点': location_text,
                '内容': content_text,
            })
        return normalized_items

    tracks = _normalize_track_items(raw_tracks)
    logger.info("美通查询: 轨迹条数=%s", len(tracks))
    latest_track = tracks[0] if tracks else {}
    return {
        '平台': '美通',
        '查询值': fba_code,
        '接口响应': {
            'success': payload.get('success'),
            'message': payload.get('message'),
            'code': payload.get('code'),
            'timestamp': payload.get('timestamp'),
        },
        '最新轨迹': latest_track,
        '物流轨迹': tracks,
    }


# ============ 平谊订单系统 ============
PINGYI_ROOT_URL = 'http://hzpy.rtb56.com/'
PINGYI_URL = 'http://hzpy.rtb56.com/login.aspx'
PINGYI_USERCENTER_URL = 'http://hzpy.rtb56.com/usercenter/index.aspx'


def _recognize_verify_code(img_bytes: bytes) -> str:
    """使用 ddddocr 识别验证码"""
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)
    return ocr.classification(img_bytes)


async def _type_like_human(page, selector: str, value: str, delay_range: tuple[int, int] = (80, 160)) -> None:
    locator = page.locator(selector)
    await locator.wait_for(state='visible', timeout=15000)
    await locator.click()
    await page.wait_for_timeout(random.randint(120, 280))
    try:
        await locator.press('Control+a')
        await page.wait_for_timeout(random.randint(80, 180))
        await locator.press('Backspace')
    except Exception:
        try:
            await locator.fill('')
        except Exception:
            pass
    await page.wait_for_timeout(random.randint(120, 260))
    await locator.type(str(value), delay=random.randint(*delay_range))
    await page.wait_for_timeout(random.randint(180, 360))


async def _open_pingyi_order_query_page(page) -> None:
    logger.info("平谊查询: 打开 mainframe 运单查询页")
    await page.locator('iframe[name="mainframe"]').first.wait_for(state='attached', timeout=15000)
    await page.evaluate(
        """
        () => {
            const frame = document.querySelector('iframe[name="mainframe"]');
            if (!frame) {
                throw new Error('mainframe iframe not found');
            }
            frame.src = 'order/order_list.aspx';
        }
        """
    )
    await page.wait_for_timeout(3000)


async def _get_pingyi_mainframe(page, timeout_ms: int = 20000):
    deadline = time.time() + timeout_ms / 1000
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            frame = page.frame(name='mainframe')
            if frame is None:
                await page.wait_for_timeout(500)
                continue

            frame_url = ''
            try:
                frame_url = frame.url or ''
            except Exception:
                frame_url = ''

            if 'order/order_list.aspx' in frame_url.lower():
                await frame.locator('#txtNo').wait_for(state='visible', timeout=1500)
                return frame

            try:
                await frame.locator('#txtNo').wait_for(state='visible', timeout=1000)
                return frame
            except Exception as exc:
                last_error = exc
        except Exception as exc:
            last_error = exc

        await page.wait_for_timeout(500)

    if last_error is not None:
        raise RuntimeError(f'平谊 mainframe 未进入运单查询页: {last_error}')
    raise RuntimeError('平谊 mainframe 未进入运单查询页')


async def _wait_for_pingyi_search_result(frame, fba_code: str, timeout_ms: int = 12000) -> str:
    deadline = time.time() + timeout_ms / 1000
    pattern = rf"showtrackdialog\('(\d+)','([^']*{re.escape(fba_code)}[^']*)'\)"
    last_html = ''

    while time.time() < deadline:
        html = await frame.locator('body').inner_html()
        last_html = html
        if re.search(pattern, html, re.IGNORECASE):
            return html

        body_text = clean_text(re.sub(r'<[^>]+>', ' ', html))
        if any(keyword in body_text for keyword in ('没有记录', '暂无数据', '未查询到', '没有查询到')):
            return html

        await frame.wait_for_timeout(800)

    return last_html


async def _goto_pingyi_page(page, url: str, timeout: int = 30000) -> None:
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        return
    except Exception as exc:
        if 'ERR_HTTP_RESPONSE_CODE_FAILURE' not in str(exc):
            raise
        logger.warning("平谊导航: 页面返回异常状态码，继续检查页面可用性 url=%s error=%s", url, exc)
        await page.wait_for_timeout(2000)
        if page.is_closed():
            raise
        try:
            await page.locator('body').wait_for(state='attached', timeout=5000)
            return
        except Exception:
            raise


async def _wait_for_pingyi_login_result(page, timeout_ms: int = 15000) -> bool:
    deadline = time.time() + timeout_ms / 1000
    known_error_keywords = (
        '验证码错误',
        '验证码不正确',
        '用户名或密码错误',
        '登录失败',
    )

    while time.time() < deadline:
        if 'usercenter' in page.url.lower():
            return True

        try:
            body_text = clean_text(await page.locator('body').inner_text())
        except Exception:
            body_text = ''

        if any(keyword in body_text for keyword in known_error_keywords):
            logger.warning("平谊登录: 页面提示登录失败: %s", body_text[:200])
            return False

        await page.wait_for_timeout(500)

    return 'usercenter' in page.url.lower()


async def _pingyi_requires_login(page) -> bool:
    try:
        if 'login.aspx' in page.url.lower():
            return True
    except Exception:
        pass

    selectors = (
        '#txtUserName',
        '#txtPassword',
        '#txtVerifyCode',
        '#btnSubmit',
    )
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state='attached', timeout=800)
            return True
        except Exception:
            continue
    return False


async def login_pingyi(playwright, max_retries: int = 3) -> tuple:
    """登录平谊系统，返回 (playwright_browser, page) 元组。"""
    username = get_env('PINGYI_USERNAME')
    password = get_env('PINGYI_PASSWORD')
    cdp_process = begin_local_cdp_session()
    browser = await playwright.chromium.connect_over_cdp(get_local_cdp_endpoint())
    contexts = browser.contexts
    context = contexts[0] if contexts else await browser.new_context(viewport={'width': 1280, 'height': 900})

    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
    """)
    page = await context.new_page()
    try:
        await page.bring_to_front()
    except Exception:
        pass

    try:
        logger.info("平谊登录: 先检查是否已有登录态")
        try:
            await _goto_pingyi_page(page, PINGYI_ROOT_URL, timeout=30000)
            await page.wait_for_timeout(2500)
        except Exception as root_exc:
            logger.warning("平谊登录: 根地址访问失败，改走登录页: %s", root_exc)
            await _goto_pingyi_page(page, PINGYI_URL, timeout=30000)
            await page.wait_for_timeout(2000)

        if not await _pingyi_requires_login(page):
            logger.info("平谊登录: 复用已有登录态")
            return browser, page

        for attempt in range(1, max_retries + 1):
            logger.info("平谊登录: 尝试 %s/%s", attempt, max_retries)
            try:
                logger.info("平谊登录: 打开登录页")
                await _goto_pingyi_page(page, PINGYI_URL, timeout=30000)
                await page.locator('#txtUserName').wait_for(state='visible', timeout=20000)
                await page.locator('#txtPassword').wait_for(state='visible', timeout=20000)
                await page.locator('#verifycode').wait_for(state='visible', timeout=20000)
                await page.wait_for_timeout(2500)

                # 随机滚动一下模拟真人
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(800)

                logger.info("平谊登录: 输入账号密码")
                await _type_like_human(page, '#txtUserName', username, delay_range=(90, 170))
                await _type_like_human(page, '#txtPassword', password, delay_range=(90, 170))

                logger.info("平谊登录: 识别验证码")
                img_bytes = await page.locator('#verifycode').screenshot()
                code = _recognize_verify_code(img_bytes).strip().upper()
                await _type_like_human(page, '#txtVerifyCode', code, delay_range=(120, 220))

                try:
                    remember_checkbox = page.locator('#chkRemember').first
                    await remember_checkbox.wait_for(state='attached', timeout=5000)
                    is_checked = await remember_checkbox.is_checked()
                    if not is_checked:
                        logger.info("平谊登录: 勾选记住登录")
                        await remember_checkbox.click()
                        await page.wait_for_timeout(500)
                except Exception as exc:
                    logger.info("平谊登录: 记住登录勾选失败，继续登录: %s", exc)

                logger.info("平谊登录: 提交登录")
                await page.locator('#btnSubmit').wait_for(state='visible', timeout=10000)
                await page.locator('#btnSubmit').click()
                await page.wait_for_timeout(2500)
                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception:
                    logger.info("平谊登录: 登录后页面 load_state 等待超时，继续按页面结果判断")
                login_ok = await _wait_for_pingyi_login_result(page, timeout_ms=20000)
                if login_ok:
                    logger.info("平谊登录: 成功")
                    return (browser, page)
                logger.warning("平谊登录: 提交后未成功进入 usercenter，准备重试")
            except Exception as e:
                logger.warning("平谊登录: 第 %s 次失败: %s", attempt, e)
                if attempt == max_retries:
                    break

            if attempt < max_retries and 'usercenter' not in page.url.lower():
                try:
                    logger.info("平谊登录: 刷新登录页后重试")
                    await _goto_pingyi_page(page, PINGYI_URL, timeout=30000)
                    await page.wait_for_timeout(1500)
                except Exception as refresh_exc:
                    logger.warning("平谊登录: 重试前刷新失败: %s", refresh_exc)

        raise RuntimeError(f'平谊系统登录失败，已尝试 {max_retries} 次')
    except Exception:
        await browser.close()
        end_local_cdp_session(cdp_process)
        raise


async def query_pingyi(fba_code: str) -> dict[str, Any]:
    """查询平谊系统订单物流轨迹"""
    from playwright.async_api import async_playwright

    browser = None
    async with async_playwright() as p:
        try:
            logger.info("平谊查询: 开始 fba_code=%s", fba_code)
            browser, page = await login_pingyi(p)
        except Exception as e:
            return {'平台': '平谊', '查询值': fba_code, '最新轨迹': {}, '物流轨迹': [], '错误': str(e)}

        try:
            await _open_pingyi_order_query_page(page)
            if page.is_closed():
                raise RuntimeError('平谊查询页面已被意外关闭')

            frame = await _get_pingyi_mainframe(page, timeout_ms=20000)

            logger.info("平谊查询: 输入运单号")
            txt_no = frame.locator('#txtNo')
            await txt_no.wait_for(state='visible', timeout=10000)
            await txt_no.click()
            await txt_no.press('Control+a')
            await txt_no.press('Backspace')
            await txt_no.fill(fba_code)
            await page.wait_for_timeout(300)

            logger.info("平谊查询: 触发搜索")
            search_button = frame.locator('#btnSearch').first
            await search_button.wait_for(state='visible', timeout=15000)
            try:
                await search_button.click(timeout=5000)
            except Exception:
                await frame.evaluate(
                    """
                    () => {
                        const node = document.querySelector('#btnSearch');
                        if (!node) {
                            throw new Error('mainframe #btnSearch not found');
                        }
                        node.click();
                    }
                    """
                )
            await page.wait_for_timeout(2000)

            logger.info("平谊查询: 解析搜索结果")
            html = await _wait_for_pingyi_search_result(frame, fba_code, timeout_ms=12000)
            pattern = rf"showtrackdialog\('(\d+)','([^']*{re.escape(fba_code)}[^']*)'\)"
            match = re.search(pattern, html, re.IGNORECASE)
            if not match:
                return {'平台': '平谊', '查询值': fba_code, '最新轨迹': {}, '物流轨迹': [], '错误': f'未找到 FBA {fba_code} 的记录'}

            bs_id = match.group(1)

            logger.info("平谊查询: 打开轨迹详情页")
            track_url = f'http://hzpy.rtb56.com/usercenter/dialog/dialog_trackdetails.aspx?bs_id={bs_id}'
            await page.goto(track_url)
            await page.wait_for_timeout(5000)

            logger.info("平谊查询: 提取轨迹表格")
            tracks = []
            rows = page.locator('table tbody tr')
            for ri in range(await rows.count()):
                cells = rows.nth(ri).locator('td')
                if await cells.count() >= 3:
                    time_text = (await cells.nth(0).inner_text()).strip()
                    location = (await cells.nth(1).inner_text()).strip()
                    content = (await cells.nth(2).inner_text()).strip()
                    if time_text and time_text != '发生时间':
                        tracks.append({'时间': time_text, '地点': location, '内容': content})

            logger.info("平谊查询: 轨迹条数=%s", len(tracks))
            return {
                '平台': '平谊',
                '查询值': fba_code,
                '物流轨迹': tracks,
                '最新轨迹': tracks[0] if tracks else {},
            }

        except Exception as e:
            return {'平台': '平谊', '查询值': fba_code, '最新轨迹': {}, '物流轨迹': [], '错误': str(e)}
        finally:
            if browser:
                await browser.close()
            end_local_cdp_session(None)


def decide_platform(order: dict[str, Any] | None, explicit_platform: str) -> str:
    if explicit_platform != 'auto':
        return explicit_platform
    if not order:
        return 'none'

    carrier = clean_text(order.get('货代公司', ''))
    if carrier == '龙舟':
        return 'agl'
    if carrier == '平谊':
        return 'pingyi'
    if carrier == '堡森':
        return 'baosen'
    if carrier == '金为':
        return 'qq'
    if carrier == '大黄蜂':
        return '17track'
    return 'meitong'


def main() -> None:
    load_env()

    parser = argparse.ArgumentParser()
    parser.add_argument('--fba', required=True, help='FBA 编号')
    parser.add_argument(
        '--platform',
        choices=['auto', 'agl', 'meitong', 'pingyi', 'baosen', 'qq', '17track', 'none'],
        default='auto',
        help='查询平台，默认按货代公司自动选择',
    )
    parser.add_argument('--headless', action='store_true', help='浏览器无头模式，仅对 Playwright 查询生效')
    args = parser.parse_args()

    order = find_order_by_fba(args.fba)
    result: dict[str, Any] = {
        'FBA编号': args.fba,
        '线上表匹配结果': order,
    }

    platform = decide_platform(order, args.platform)
    result['命中平台'] = platform

    if platform == 'agl' and order:
        booking_id = get_primary_logistics_no(order)
        if not booking_id:
            result['AGL查询'] = {'错误': '钉钉表格中未找到物流编号，无法作为 BookingID 查询'}
        else:
            result['AGL查询'] = query_agl(booking_id, order, headless=args.headless)

    if platform == 'meitong' and order:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            result['美通查询'] = {'错误': '钉钉表格中未找到物流编号，无法查询美通轨迹'}
        else:
            result['美通查询'] = query_meitong(tracking_no)

    if platform == 'pingyi':
        # 平谊直接使用用户传入的单号查询，不依赖钉钉表里的物流编号
        result['平谊查询'] = asyncio.run(query_pingyi(args.fba))

    if platform == 'baosen' and order:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            result['堡森查询'] = {'错误': '钉钉表格中未找到物流编号，无法查询堡森轨迹'}
        else:
            result['堡森查询'] = asyncio.run(query_baosen(tracking_no))

    if platform == 'qq' and order:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            result['QQ查询'] = {'错误': '钉钉表格中未找到物流编号，无法通过 QQ 询问物流状态'}
        else:
            result['QQ查询'] = query_qq(order, tracking_no)

    if platform == '17track' and order:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            result['17TRACK查询'] = {'错误': '钉钉表格中未找到物流编号，无法通过 17TRACK 查询物流状态'}
        else:
            result['17TRACK查询'] = asyncio.run(query_17track(tracking_no))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
