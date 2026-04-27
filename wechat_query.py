import argparse
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from gewechat_client import GEWECHAT_CALLBACK_EVENTS_PATH, get_gewechat_client


logger = logging.getLogger(__name__)

def clean_text(value: str) -> str:
    return ' '.join(str(value).split()).strip()


def shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def env_flag(name: str, default: bool = False) -> bool:
    value = clean_text(os.environ.get(name, ''))
    if not value:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int


REFERENCE_WINDOW_WIDTH = 2494
REFERENCE_WINDOW_HEIGHT = 1568


SEARCH_CATEGORIES = {'function', 'group'}
WECHAT_GUI_OPEN_MODES = {'search', 'sidebar_recent'}
SEARCH_RESULT_POPUP_POINTS: dict[str, tuple[int, int]] = {
    'function': (70, 160),
    'group': (70, 160),
}
SIDEBAR_RECENT_CHAT_POINTS: dict[str, tuple[int, int]] = {}
TITLE_REGION = (120, 0, 360, 60)
SIDEBAR_CHAT_LIST_REGION = (28, 28, 220, 560)
CHAT_HISTORY_REGION = (130, 70, 2390, 1210)
CHAT_RECENT_LEFT_REPLY_REGION = (130, 760, 1220, 1240)
OCR_SCALE_FACTOR = 3

WECHAT_REPLY_TIMEOUT_SECONDS = int(os.environ.get('WECHAT_REPLY_TIMEOUT_SECONDS', '120'))
WECHAT_REPLY_POLL_INTERVAL_SECONDS = float(os.environ.get('WECHAT_REPLY_POLL_INTERVAL_SECONDS', '2'))
GEWECHAT_REPLY_TIMEOUT_SECONDS = int(os.environ.get('GEWECHAT_REPLY_TIMEOUT_SECONDS', '120'))
GEWECHAT_REPLY_POLL_INTERVAL_SECONDS = float(os.environ.get('GEWECHAT_REPLY_POLL_INTERVAL_SECONDS', '2'))


def get_wechat_group_name() -> str:
    return clean_text(os.environ.get('WECHAT_GROUP_NAME', '易达-平谊物流信息推送群')) or '易达-平谊物流信息推送群'


def get_wechat_mention_name() -> str:
    if env_flag('WECHAT_DISABLE_MENTION', default=False):
        return ''
    return clean_text(os.environ.get('WECHAT_MENTION_NAME', '伍林慧')) or '伍林慧'


def get_wechat_provider() -> str:
    return clean_text(os.environ.get('WECHAT_PROVIDER', 'gui')).lower() or 'gui'


def get_wechat_debug_dir() -> Path:
    return Path(os.environ.get('WECHAT_DEBUG_DIR', 'tmp')).expanduser()


def get_gewechat_username() -> str:
    return clean_text(os.environ.get('GEWECHAT_USERNAME', 'dingtalk_ltq_bot')) or 'dingtalk_ltq_bot'


def get_wechat_gui_auto_send() -> bool:
    return env_flag('WECHAT_GUI_AUTO_SEND', default=False)


def get_wechat_gui_wait_for_reply() -> bool:
    return env_flag('WECHAT_GUI_WAIT_FOR_REPLY', default=False)


def get_wechat_gui_open_mode() -> str:
    mode = clean_text(os.environ.get('WECHAT_GUI_OPEN_MODE', 'search')).lower() or 'search'
    return mode if mode in WECHAT_GUI_OPEN_MODES else 'search'


def get_wechat_gui_allowed_groups() -> set[str]:
    raw_value = os.environ.get('WECHAT_GUI_ALLOWED_GROUPS', '')
    groups = {
        clean_text(item)
        for item in raw_value.replace('\n', ',').split(',')
        if clean_text(item)
    }
    return groups or {'测试'}


def get_wechat_gui_recent_chat_points() -> dict[str, tuple[int, int]]:
    raw_value = os.environ.get('WECHAT_GUI_RECENT_CHAT_POINTS', '')
    if not clean_text(raw_value):
        return {}

    points: dict[str, tuple[int, int]] = {}
    for item in raw_value.split(';'):
        entry = clean_text(item)
        if not entry or '=' not in entry:
            continue
        name, point = entry.split('=', 1)
        group_name = clean_text(name)
        if not group_name or ',' not in point:
            continue
        x_text, y_text = point.split(',', 1)
        try:
            points[group_name] = (int(x_text.strip()), int(y_text.strip()))
        except ValueError:
            continue
    return points


def normalize_mention_name(value: str) -> str:
    return clean_text(value).lstrip('@').strip()


def build_debug_screenshot_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return get_wechat_debug_dir() / f'{prefix}-{timestamp}.png'


class WeChatUIClient:
    def __init__(self) -> None:
        self.display = os.environ.get('WECHAT_DISPLAY', ':1').strip() or ':1'
        self.window_id = self._resolve_window_id()
        self.geometry = self._get_window_geometry()

    def _run(self, command: str, check: bool = True) -> str:
        env = os.environ.copy()
        env['DISPLAY'] = self.display
        completed = subprocess.run(
            ['/bin/bash', '-lc', command],
            check=check,
            capture_output=True,
            text=True,
            env=env,
        )
        if check and completed.returncode != 0:
            stderr = clean_text(completed.stderr)
            raise RuntimeError(f'微信 GUI 命令执行失败: {command}; stderr={stderr}')
        return completed.stdout.strip()

    def _resolve_window_id(self) -> str:
        output = self._run("wmctrl -lx | awk '/wechat\\.wechat/ && /微信$/ {print $1; exit}'", check=False)
        window_id = clean_text(output)
        if not window_id:
            raise RuntimeError('未找到微信主窗口，请先在本机登录并打开微信')
        return window_id

    def _get_window_geometry(self) -> WindowGeometry:
        output = self._run(f'xwininfo -id {shell_quote(self.window_id)}')
        width = height = 0
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith('Absolute upper-left X:'):
                x = int(line.split(':', 1)[1].strip())
            elif line.startswith('Absolute upper-left Y:'):
                y = int(line.split(':', 1)[1].strip())
            elif line.startswith('Width:'):
                width = int(line.split(':', 1)[1].strip())
            elif line.startswith('Height:'):
                height = int(line.split(':', 1)[1].strip())
        if width <= 0 or height <= 0:
            raise RuntimeError(f'无法读取微信窗口尺寸: {output}')
        return WindowGeometry(x=x, y=y, width=width, height=height)

    def _refresh_geometry(self) -> None:
        self.geometry = self._get_window_geometry()

    def _scale_x(self, value: int) -> int:
        return max(0, round(value * self.geometry.width / REFERENCE_WINDOW_WIDTH))

    def _scale_y(self, value: int) -> int:
        return max(0, round(value * self.geometry.height / REFERENCE_WINDOW_HEIGHT))

    def _scaled_point(self, x: int, y: int) -> tuple[int, int]:
        return self._scale_x(x), self._scale_y(y)

    def activate(self) -> None:
        self._run(f'wmctrl -ia {shell_quote(self.window_id)}')
        time.sleep(0.8)
        self._refresh_geometry()

    def click(self, x: int, y: int, sleep_seconds: float = 0.5) -> None:
        scaled_x, scaled_y = self._scaled_point(x, y)
        self._run(
            f'xdotool mousemove --window {shell_quote(self.window_id)} {scaled_x} {scaled_y} click 1'
        )
        time.sleep(sleep_seconds)

    def key(self, sequence: str, sleep_seconds: float = 0.2) -> None:
        self._run(f'xdotool key --window {shell_quote(self.window_id)} --clearmodifiers {sequence}')
        time.sleep(sleep_seconds)

    def paste_text(self, text: str, sleep_seconds: float = 0.3) -> None:
        escaped = shell_quote(text)
        self._run(
            'bash -lc '
            + shell_quote(
                f"printf %s {escaped} | xclip -selection clipboard -quiet >/dev/null 2>&1 & "
                f"printf %s {escaped} | xclip -selection primary -quiet >/dev/null 2>&1 & "
                "sleep 0.4"
            )
        )
        self.key('Shift+Insert', sleep_seconds=sleep_seconds)

    def type_text(self, text: str) -> None:
        # Prefer clipboard paste for CJK content and @-mentions; xdotool type
        # is unreliable here with the current desktop/input method setup.
        self.paste_text(text)

    def capture_debug(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        png_path = shell_quote(str(output_path))
        self.activate()
        self._run(
            'import -window root '
            f'-crop {self.geometry.width}x{self.geometry.height}+{self.geometry.x}+{self.geometry.y} '
            f'{png_path}'
        )

    def capture_region(self, output_path: Path, region: tuple[int, int, int, int]) -> None:
        self.capture_debug(output_path)
        left, top, right, bottom = region
        crop_x = self._scale_x(left)
        crop_y = self._scale_y(top)
        crop_width = max(1, self._scale_x(right - left))
        crop_height = max(1, self._scale_y(bottom - top))
        png_path = shell_quote(str(output_path))
        self._run(
            f'convert {png_path} -crop {crop_width}x{crop_height}+{crop_x}+{crop_y} +repage {png_path}'
        )

    def preprocess_for_ocr(
        self,
        image_path: Path,
        scale_factor: int = OCR_SCALE_FACTOR,
        threshold: int = 70,
    ) -> None:
        png_path = shell_quote(str(image_path))
        self._run(
            f'convert {png_path} -colorspace Gray -resize {scale_factor * 100}% -threshold {threshold}% {png_path}'
        )

    def recognize_text(
        self,
        image_path: Path,
        languages: str = 'chi_sim+eng',
        psm: int = 7,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix='wechat-ocr-') as temp_dir:
            output_base = Path(temp_dir) / 'ocr'
            command = (
                f'tesseract {shell_quote(str(image_path))} {shell_quote(str(output_base))} '
                f'-l {shell_quote(languages)} --psm {psm}'
            )
            self._run(command)
            txt_path = output_base.with_suffix('.txt')
            if not txt_path.exists():
                return ''
            return clean_text(txt_path.read_text(encoding='utf-8', errors='ignore'))

    def recognize_multiline_text(
        self,
        image_path: Path,
        languages: str = 'chi_sim+eng',
        psm: int = 6,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix='wechat-ocr-multi-') as temp_dir:
            output_base = Path(temp_dir) / 'ocr'
            command = (
                f'tesseract {shell_quote(str(image_path))} {shell_quote(str(output_base))} '
                f'-l {shell_quote(languages)} --psm {psm}'
            )
            self._run(command)
            txt_path = output_base.with_suffix('.txt')
            if not txt_path.exists():
                return ''
            lines = [
                clean_text(line)
                for line in txt_path.read_text(encoding='utf-8', errors='ignore').splitlines()
            ]
            return '\n'.join(line for line in lines if line)

    def recognize_tsv(self, image_path: Path, languages: str = 'chi_sim+eng', psm: int = 6) -> list[dict[str, str]]:
        with tempfile.TemporaryDirectory(prefix='wechat-ocr-tsv-') as temp_dir:
            output_base = Path(temp_dir) / 'ocr'
            command = (
                f'tesseract {shell_quote(str(image_path))} {shell_quote(str(output_base))} '
                f'-l {shell_quote(languages)} --psm {psm} tsv'
            )
            self._run(command)
            tsv_path = output_base.with_suffix('.tsv')
            if not tsv_path.exists():
                return []
            with tsv_path.open('r', encoding='utf-8', errors='ignore') as fh:
                return list(csv.DictReader(fh, delimiter='\t'))

    def find_sidebar_chat_center(self, target_name: str) -> tuple[int, int] | None:
        sidebar_path = build_debug_screenshot_path('wechat-sidebar-ocr')
        self.capture_region(sidebar_path, SIDEBAR_CHAT_LIST_REGION)
        self.preprocess_for_ocr(sidebar_path)
        entries = self.recognize_tsv(sidebar_path)
        left, top, _, _ = SIDEBAR_CHAT_LIST_REGION
        for entry in entries:
            text = clean_text(entry.get('text', ''))
            if not text or target_name not in text:
                continue
            try:
                x = int(entry.get('left', '0'))
                y = int(entry.get('top', '0'))
                width = int(entry.get('width', '0'))
                height = int(entry.get('height', '0'))
            except ValueError:
                continue
            center_x = left + round((x + max(1, width) / 2) / OCR_SCALE_FACTOR)
            center_y = top + round((y + max(1, height) / 2) / OCR_SCALE_FACTOR)
            return center_x, center_y
        return None

    def get_current_chat_title(self, debug_prefix: str = 'wechat-title') -> dict[str, str]:
        title_path = build_debug_screenshot_path(debug_prefix)
        self.capture_region(title_path, TITLE_REGION)
        self.preprocess_for_ocr(title_path)
        title_text = self.recognize_text(title_path)
        return {
            'title_text': title_text,
            'title_screenshot': str(title_path),
        }

    def wait_for_chat_title(self, expected_name: str, timeout_seconds: float = 6.0) -> dict[str, str]:
        deadline = time.time() + timeout_seconds
        last_info = {'title_text': '', 'title_screenshot': ''}
        while time.time() < deadline:
            last_info = self.get_current_chat_title()
            if expected_name in clean_text(last_info.get('title_text', '')):
                return last_info
            time.sleep(0.8)
        return last_info

    def open_search_and_fill(self, target_name: str) -> None:
        self.activate()
        self.key('ctrl+f', sleep_seconds=0.3)
        self.key('ctrl+a', sleep_seconds=0.1)
        self.key('BackSpace', sleep_seconds=0.2)
        self.type_text(target_name)
        time.sleep(1.0)

    def open_chat_via_search(self, target_name: str, category: str) -> None:
        if category not in SEARCH_CATEGORIES:
            raise RuntimeError(f'不支持的微信搜索分类: {category}')
        open_mode = get_wechat_gui_open_mode()
        if open_mode == 'sidebar_recent':
            sidebar_point = self.find_sidebar_chat_center(target_name)
            if sidebar_point is None:
                sidebar_point = get_wechat_gui_recent_chat_points().get(target_name)
            if sidebar_point is None:
                sidebar_point = SIDEBAR_RECENT_CHAT_POINTS.get(target_name)
            if sidebar_point is not None:
                self.activate()
                self.click(*sidebar_point, sleep_seconds=1.5)
                return
        self.open_search_and_fill(target_name)
        result_x, result_y = SEARCH_RESULT_POPUP_POINTS[category]
        self.click(result_x, result_y, sleep_seconds=1.0)
        self.key('Escape', sleep_seconds=0.2)

    def open_file_transfer_assistant_from_sidebar(self) -> None:
        self.activate()
        self.click(90, 220, sleep_seconds=1.2)

    def focus_input_box(self) -> None:
        self.click(356, 1326, sleep_seconds=0.4)

    def clear_input_box(self) -> None:
        self.key('ctrl+a', sleep_seconds=0.1)
        self.key('BackSpace', sleep_seconds=0.2)

    def send_text(self, text: str, clear_before_send: bool = False) -> None:
        self.focus_input_box()
        if clear_before_send:
            self.clear_input_box()
        self.type_text(text)
        time.sleep(0.3)
        self.key('Return', sleep_seconds=0.8)

    def select_recent_left_messages(self) -> None:
        self.activate()
        start_x, start_y = self._scaled_point(145, 1180)
        end_x, end_y = self._scaled_point(920, 120)
        self._run(
            f'xdotool mousemove --window {shell_quote(self.window_id)} {start_x} {start_y} '
            f'mousedown 1 mousemove --window {shell_quote(self.window_id)} {end_x} {end_y} mouseup 1'
        )
        time.sleep(0.3)

    def read_selected_text(self) -> str:
        self.select_recent_left_messages()
        self.key('ctrl+c', sleep_seconds=0.3)
        return clean_text(self._run('xclip -selection clipboard -o', check=False))

    def read_chat_history_via_ocr(self) -> dict[str, str]:
        history_path = build_debug_screenshot_path('wechat-history')
        self.capture_region(history_path, CHAT_HISTORY_REGION)
        self.preprocess_for_ocr(history_path, scale_factor=2, threshold=78)
        return {
            'history_text': self.recognize_multiline_text(history_path, psm=6),
            'history_screenshot': str(history_path),
        }

    def read_recent_left_reply_via_ocr(self) -> dict[str, str]:
        history_path = build_debug_screenshot_path('wechat-recent-left-reply')
        self.capture_region(history_path, CHAT_RECENT_LEFT_REPLY_REGION)
        self.preprocess_for_ocr(history_path, scale_factor=3, threshold=72)
        return {
            'text': self.recognize_multiline_text(history_path, psm=6),
            'ocr_screenshot': str(history_path),
            'source': 'ocr-left-recent',
        }

    def read_chat_history_text(self) -> dict[str, str]:
        clipboard_text = self.read_selected_text()
        ocr_payload = self.read_chat_history_via_ocr()
        ocr_text = clean_text(ocr_payload.get('history_text', ''))
        selected_text = clipboard_text if len(clipboard_text) >= len(ocr_text) else ocr_text
        source = 'clipboard' if selected_text == clipboard_text else 'ocr'
        return {
            'text': selected_text,
            'clipboard_text': clipboard_text,
            'ocr_text': ocr_payload.get('history_text', ''),
            'ocr_screenshot': ocr_payload.get('history_screenshot', ''),
            'source': source,
        }


def _extract_new_reply_text(before: str, after: str) -> str:
    before_lines = [line.strip() for line in str(before).splitlines() if line.strip()]
    after_lines = [line.strip() for line in str(after).splitlines() if line.strip()]
    prefix_length = 0
    for before_line, after_line in zip(before_lines, after_lines):
        if before_line != after_line:
            break
        prefix_length += 1
    new_lines = after_lines[prefix_length:]
    if new_lines:
        return '\n'.join(new_lines).strip()
    if after.strip() != before.strip():
        return after.strip()
    return ''


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_gewechat_raw_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ('string', 'String', 'value', 'Value', 'content', 'Content'):
            if key in value:
                return _extract_gewechat_raw_text(value.get(key))
        return ''
    if value is None:
        return ''
    return str(value)


def _read_gewechat_callback_records(start_offset: int) -> tuple[list[dict[str, Any]], int]:
    path = GEWECHAT_CALLBACK_EVENTS_PATH
    if not path.exists():
        return [], 0

    with path.open('r', encoding='utf-8', errors='ignore') as fh:
        file_size = path.stat().st_size
        offset = start_offset if 0 <= start_offset <= file_size else file_size
        fh.seek(offset)
        raw_lines = fh.readlines()
        new_offset = fh.tell()

    records: list[dict[str, Any]] = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Gewechat 回调文件存在非法 JSON 行，已跳过: %s", line[:200])
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records, new_offset


def _parse_gewechat_callback_message(record: dict[str, Any]) -> dict[str, Any] | None:
    event = record.get('event')
    if not isinstance(event, dict):
        return None

    type_name = clean_text(event.get('TypeName', ''))
    if type_name != 'AddMsg':
        return None

    data = event.get('Data')
    if not isinstance(data, dict):
        return None

    if _safe_int(data.get('MsgType')) != 1:
        return None

    own_wxid = clean_text(_extract_gewechat_raw_text(event.get('Wxid')))
    from_wxid = clean_text(_extract_gewechat_raw_text(data.get('FromUserName')))
    to_wxid = clean_text(_extract_gewechat_raw_text(data.get('ToUserName')))
    raw_content = _extract_gewechat_raw_text(data.get('Content'))
    push_content = clean_text(_extract_gewechat_raw_text(data.get('PushContent')))
    chat_wxid = from_wxid if from_wxid.endswith('@chatroom') else to_wxid if to_wxid.endswith('@chatroom') else ''
    sender_wxid = from_wxid
    content = raw_content
    is_self_message = False

    if chat_wxid:
        if from_wxid == own_wxid and to_wxid == chat_wxid:
            is_self_message = True
            sender_wxid = own_wxid
        elif from_wxid == chat_wxid and ':\n' in raw_content:
            possible_sender, possible_text = raw_content.split(':\n', 1)
            sender_wxid = clean_text(possible_sender)
            content = clean_text(possible_text)
        elif from_wxid == chat_wxid:
            sender_wxid = ''
            content = raw_content
    else:
        is_self_message = from_wxid == own_wxid

    content = clean_text(content)
    if not content:
        return None

    return {
        'event_id': f"{clean_text(event.get('Appid', ''))}:{clean_text(data.get('NewMsgId', ''))}",
        'received_at': _safe_int(record.get('received_at')),
        'create_time': _safe_int(data.get('CreateTime')),
        'chat_wxid': chat_wxid,
        'sender_wxid': clean_text(sender_wxid),
        'self_wxid': own_wxid,
        'is_self_message': is_self_message,
        'content': content,
        'push_content': push_content,
        'msg_id': clean_text(data.get('MsgId', '')),
        'new_msg_id': clean_text(data.get('NewMsgId', '')),
        'msg_seq': _safe_int(data.get('MsgSeq')),
        'raw_event': event,
    }


def wait_for_gewechat_reply(
    group_wxid: str,
    expected_sender_wxid: str = '',
    not_before: int = 0,
    start_offset: int = 0,
    sent_new_msg_id: str = '',
    timeout_seconds: int = GEWECHAT_REPLY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = GEWECHAT_REPLY_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    expected_group_wxid = clean_text(group_wxid)
    expected_sender = clean_text(expected_sender_wxid)
    deadline = time.time() + timeout_seconds
    offset = start_offset
    seen_event_ids: set[str] = set()

    while time.time() < deadline:
        records, offset = _read_gewechat_callback_records(offset)
        for record in records:
            message = _parse_gewechat_callback_message(record)
            if message is None:
                continue

            event_id = clean_text(message.get('event_id', ''))
            if event_id:
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)

            if clean_text(message.get('chat_wxid', '')) != expected_group_wxid:
                continue
            if message.get('is_self_message'):
                continue
            if sent_new_msg_id and clean_text(message.get('new_msg_id', '')) == sent_new_msg_id:
                continue

            message_time = max(
                _safe_int(message.get('received_at')),
                _safe_int(message.get('create_time')),
            )
            if not_before and message_time and message_time < not_before:
                continue

            sender_wxid = clean_text(message.get('sender_wxid', ''))
            if expected_sender and sender_wxid != expected_sender:
                continue

            timestamp = time.strftime(
                '%Y-%m-%d %H:%M:%S',
                time.localtime(_safe_int(message.get('create_time')) or int(time.time())),
            )
            track = {
                '时间': timestamp,
                '内容': clean_text(message.get('content', '')),
            }
            return {
                '物流轨迹': [track],
                '最新轨迹': track,
                '回复消息ID': clean_text(message.get('msg_id', '')),
                '回复消息序号': _safe_int(message.get('msg_seq')),
                '回复人wxid': sender_wxid,
                '原始PushContent': clean_text(message.get('push_content', '')),
            }

        time.sleep(poll_interval_seconds)

    return {
        '物流轨迹': [],
        '最新轨迹': {},
        '错误': f'等待 Gewechat 回复超时（{timeout_seconds} 秒）',
    }


def wait_for_first_reply(
    client: WeChatUIClient,
    baseline_text: str,
    timeout_seconds: int = WECHAT_REPLY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = WECHAT_REPLY_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, str] = {'text': baseline_text, 'source': '', 'ocr_screenshot': ''}
    while time.time() < deadline:
        last_payload = client.read_recent_left_reply_via_ocr()
        current_text = str(last_payload.get('text', '') or '')
        reply_text = _extract_new_reply_text(baseline_text, current_text)
        if reply_text:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            track = {'时间': timestamp, '内容': reply_text}
            return {
                '物流轨迹': [track],
                '最新轨迹': track,
                '原始聊天文本': current_text,
                '读取来源': last_payload.get('source', ''),
                'OCR截图': last_payload.get('ocr_screenshot', ''),
            }
        time.sleep(poll_interval_seconds)

    return {
        '物流轨迹': [],
        '最新轨迹': {},
        '读取来源': last_payload.get('source', ''),
        'OCR截图': last_payload.get('ocr_screenshot', ''),
        '错误': f'等待微信回复超时（{timeout_seconds} 秒）',
    }


def send_to_file_transfer_assistant(message: str) -> dict[str, str]:
    client = WeChatUIClient()
    client.open_file_transfer_assistant_from_sidebar()
    client.send_text(message, clear_before_send=True)
    return {
        'chat': '文件传输助手',
        'message': message,
        'window_id': client.window_id,
    }


def send_via_search(chat_name: str, category: str, message: str) -> dict[str, str]:
    client = WeChatUIClient()
    client.open_chat_via_search(chat_name, category)
    client.send_text(message)
    return {
        'chat': chat_name,
        'category': category,
        'message': message,
        'window_id': client.window_id,
    }


def build_wechat_question(tracking_no: str) -> str:
    mention_name = normalize_mention_name(get_wechat_mention_name())
    tracking_text = clean_text(tracking_no)
    if mention_name:
        return f'@{mention_name} {tracking_text}'
    return tracking_text


def query_wechat_gui(
    tracking_no: str,
    wait_for_reply: bool = True,
    allow_unverified_send: bool = False,
) -> dict[str, Any]:
    cleaned_tracking_no = clean_text(tracking_no)
    mention_name = normalize_mention_name(get_wechat_mention_name())
    group_name = get_wechat_group_name()
    if not cleaned_tracking_no:
        return {
            '平台': '微信',
            '查询值': '',
            '群名': group_name,
            '询问对象': mention_name,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '未提供要发送到微信的单号',
        }

    message = build_wechat_question(cleaned_tracking_no)
    client = WeChatUIClient()
    title_info: dict[str, str] = {'title_text': '', 'title_screenshot': ''}
    for _ in range(2):
        client.open_chat_via_search(group_name, 'group')
        title_info = client.wait_for_chat_title(group_name)
        if group_name in clean_text(title_info.get('title_text', '')):
            break
        time.sleep(1.0)

    preflight_screenshot = build_debug_screenshot_path('wechat-preflight')
    client.capture_debug(preflight_screenshot)
    result: dict[str, Any] = {
        '平台': '微信',
        'Provider': 'gui',
        '查询值': cleaned_tracking_no,
        '群名': group_name,
        '询问对象': mention_name,
        '提问内容': message,
        '物流轨迹': [],
        '最新轨迹': {},
        '窗口ID': client.window_id,
        '发送前截图': str(preflight_screenshot),
    }
    allowed_groups = get_wechat_gui_allowed_groups()
    if group_name not in allowed_groups:
        result['错误'] = f'当前仅允许发送到白名单群: {", ".join(sorted(allowed_groups))}'
        return result

    result['识别标题'] = title_info.get('title_text', '')
    result['标题截图'] = title_info.get('title_screenshot', '')
    recognized_title = clean_text(title_info.get('title_text', ''))
    if group_name not in recognized_title:
        result['标题校验警告'] = (
            f'发送前标题 OCR 未命中目标群，期望包含 `{group_name}`，'
            f'实际识别为 `{recognized_title or "空"}`；已按白名单配置继续发送。'
        )

    should_send = allow_unverified_send or get_wechat_gui_auto_send()
    if not should_send:
        result['错误'] = (
            '已停止发送。请先人工确认发送前截图中的当前会话是否为目标群，'
            '确认后再使用 allow_unverified_send=True 或设置 WECHAT_GUI_AUTO_SEND=true 执行发送。'
        )
        return result

    client.send_text(message)
    post_send_screenshot = build_debug_screenshot_path('wechat-postsend')
    client.capture_debug(post_send_screenshot)
    result['发送后截图'] = str(post_send_screenshot)
    if wait_for_reply:
        baseline_payload = client.read_recent_left_reply_via_ocr()
        result.update(wait_for_first_reply(client, str(baseline_payload.get('text', '') or '')))
    return result


def query_wechat_gewechat(
    tracking_no: str,
    wait_for_reply: bool = True,
) -> dict[str, Any]:
    cleaned_tracking_no = clean_text(tracking_no)
    mention_name = normalize_mention_name(get_wechat_mention_name())
    group_name = get_wechat_group_name()
    gewechat_username = get_gewechat_username()
    group_wxid = clean_text(os.environ.get('GEWECHAT_CHAT_WXID', ''))
    mention_wxid = clean_text(os.environ.get('GEWECHAT_AT_WXID', ''))
    callback_url = clean_text(os.environ.get('GEWECHAT_CALLBACK_URL', ''))
    if not cleaned_tracking_no:
        return {
            '平台': '微信',
            'Provider': 'gewechat',
            '查询值': '',
            '群名': group_name,
            '询问对象': mention_name,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '未提供要发送到微信的单号',
        }
    if not group_wxid:
        return {
            '平台': '微信',
            'Provider': 'gewechat',
            '查询值': cleaned_tracking_no,
            '群名': group_name,
            '询问对象': mention_name,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '缺少环境变量: GEWECHAT_CHAT_WXID',
        }
    if not clean_text(os.environ.get('GEWECHAT_APP_ID', '')):
        return {
            '平台': '微信',
            'Provider': 'gewechat',
            '查询值': cleaned_tracking_no,
            '群名': group_name,
            '询问对象': mention_name,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '缺少环境变量: GEWECHAT_APP_ID，请先执行 python3 gewechat_bootstrap.py 完成登录',
        }

    message = build_wechat_question(cleaned_tracking_no)
    at_user_list = [mention_wxid] if mention_wxid else []
    result: dict[str, Any] = {
        '平台': '微信',
        'Provider': 'gewechat',
        '查询值': cleaned_tracking_no,
        '群名': group_name,
        '群wxid': group_wxid,
        '询问对象': mention_name,
        '询问对象wxid': mention_wxid,
        'Gewechat用户名': gewechat_username,
        '提问内容': message,
        '物流轨迹': [],
        '最新轨迹': {},
        'Webhook': callback_url,
    }

    client = get_gewechat_client()
    token = clean_text(os.environ.get('GEWECHAT_TOKEN', ''))
    if callback_url:
        result['回调注册结果'] = client.set_callback_url(token, callback_url)
    elif wait_for_reply:
        result['错误'] = '缺少环境变量: GEWECHAT_CALLBACK_URL，无法等待微信回复'
        return result

    start_offset = GEWECHAT_CALLBACK_EVENTS_PATH.stat().st_size if GEWECHAT_CALLBACK_EVENTS_PATH.exists() else 0
    send_started_at = int(time.time()) - 1
    result['发送结果'] = client.send_text(
        chat_wxid=group_wxid,
        content=message,
        at_user_list=at_user_list,
    )
    send_data = result.get('发送结果')
    send_result_data = send_data.get('data') if isinstance(send_data, dict) else {}
    sent_new_msg_id = clean_text(send_result_data.get('newMsgId', '')) if isinstance(send_result_data, dict) else ''
    result['发送消息ID'] = sent_new_msg_id
    if wait_for_reply:
        result.update(
            wait_for_gewechat_reply(
                group_wxid=group_wxid,
                expected_sender_wxid=mention_wxid,
                not_before=send_started_at,
                start_offset=start_offset,
                sent_new_msg_id=sent_new_msg_id,
            )
        )
    return result


def query_wechat(
    tracking_no: str,
    wait_for_reply: bool = True,
    allow_unverified_send: bool = False,
) -> dict[str, Any]:
    provider = get_wechat_provider()
    if provider == 'gewechat':
        return query_wechat_gewechat(
            tracking_no=tracking_no,
            wait_for_reply=wait_for_reply,
        )
    return query_wechat_gui(
        tracking_no=tracking_no,
        wait_for_reply=wait_for_reply and get_wechat_gui_wait_for_reply(),
        allow_unverified_send=allow_unverified_send,
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)-8s %(message)s',
    )

    parser = argparse.ArgumentParser()
    parser.add_argument('--message', required=True, help='要发送的消息文本')
    parser.add_argument('--chat', default='文件传输助手', help='目标会话名称')
    parser.add_argument(
        '--category',
        choices=sorted(SEARCH_CATEGORIES),
        default='function',
        help='搜索结果分类，文件传输助手用 function，群聊用 group',
    )
    parser.add_argument(
        '--mode',
        choices=['sidebar-file-helper', 'search'],
        default='sidebar-file-helper',
        help='sidebar-file-helper 直接点左侧文件传输助手，search 通过微信搜索结果打开',
    )
    parser.add_argument(
        '--allow-unverified-send',
        action='store_true',
        help='允许在未完成人工校验前直接发送，仅建议手动确认发送前截图后使用',
    )
    parser.add_argument('--debug-screenshot', default='', help='可选，发送后保存微信窗口截图')
    args = parser.parse_args()

    if args.mode == 'sidebar-file-helper':
        result = send_to_file_transfer_assistant(args.message)
    else:
        result = send_via_search(args.chat, args.category, args.message)

    screenshot_path = clean_text(args.debug_screenshot)
    if screenshot_path:
        WeChatUIClient().capture_debug(Path(screenshot_path))
        result['debug_screenshot'] = screenshot_path

    print(result)


if __name__ == '__main__':
    main()
