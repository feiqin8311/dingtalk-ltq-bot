import logging
import os
import time
import re
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QQRouteRule:
    carrier: str
    group_name: str
    mention_name: str
    env_prefix: str


QQ_ROUTE_RULES: dict[str, QQRouteRule] = {
    '金为': QQRouteRule(
        carrier='金为',
        group_name='璧久FBA海运-杭州金为',
        mention_name='李美慧',
        env_prefix='QQ_JINWEI',
    ),
}

DEFAULT_API_BASE_URL = 'http://127.0.0.1:6702'
DEFAULT_API_TIMEOUT_SECONDS = 15
DEFAULT_REPLY_TIMEOUT_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_HISTORY_FETCH_COUNT = 50
DEFAULT_HISTORY_LOOKBACK_COUNT = 5000
DEFAULT_HISTORY_CONTEXT_WINDOW = 20
DEFAULT_HISTORY_FRESHNESS_DAYS = 7
_TRACKING_NUMBER_RE = re.compile(r'(?<!\w)[A-Za-z0-9](?:[A-Za-z0-9.-]{6,}[A-Za-z0-9])?(?!\w)')
_NON_LOGISTICS_NOTICE_KEYWORDS = (
    '关税',
    '罚金',
    '查验',
    '补缴',
    '货值低',
)


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


def get_qq_route_rule(order: dict[str, Any] | None) -> QQRouteRule | None:
    if not order:
        return None
    carrier = clean_text(order.get('货代公司', ''))
    return QQ_ROUTE_RULES.get(carrier)


def build_question_text(route_rule: QQRouteRule, tracking_no: str) -> str:
    return f"@{route_rule.mention_name} {tracking_no} 物流状态"


def _env_str(name: str) -> str:
    return os.environ.get(name, '').strip()


def _env_int(name: str) -> int | None:
    value = _env_str(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f'环境变量 {name} 不是合法整数: {value}') from exc


def _env_float(name: str) -> float | None:
    value = _env_str(name)
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f'环境变量 {name} 不是合法数字: {value}') from exc


def get_qq_api_settings() -> tuple[str, str, int, int, float, int]:
    base_url = _env_str('QQ_API_BASE_URL') or DEFAULT_API_BASE_URL
    token = _env_str('QQ_API_TOKEN')
    timeout_seconds = _env_int('QQ_API_TIMEOUT_SECONDS') or DEFAULT_API_TIMEOUT_SECONDS
    reply_timeout_seconds = _env_int('QQ_REPLY_TIMEOUT_SECONDS') or DEFAULT_REPLY_TIMEOUT_SECONDS
    poll_interval_seconds = _env_float('QQ_POLL_INTERVAL_SECONDS') or DEFAULT_POLL_INTERVAL_SECONDS
    history_fetch_count = _env_int('QQ_HISTORY_FETCH_COUNT') or DEFAULT_HISTORY_FETCH_COUNT
    return (
        base_url,
        token,
        timeout_seconds,
        reply_timeout_seconds,
        poll_interval_seconds,
        history_fetch_count,
    )


def get_qq_history_lookback_count() -> int:
    return _env_int('QQ_HISTORY_LOOKBACK_COUNT') or DEFAULT_HISTORY_LOOKBACK_COUNT


def get_qq_history_context_window() -> int:
    return _env_int('QQ_HISTORY_CONTEXT_WINDOW') or DEFAULT_HISTORY_CONTEXT_WINDOW


class NapCatOneBotClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        if token:
            self.session.headers.update({'Authorization': f'Bearer {token}'})

    def call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        url = f'{self.base_url}/{action.lstrip("/")}'
        try:
            response = self.session.post(url, json=payload or {}, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise RuntimeError(f'调用 QQ API 失败: {exc}') from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:500]
            raise RuntimeError(f'QQ API HTTP 异常: status={response.status_code} body={detail}') from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f'QQ API 返回了非 JSON 内容: {response.text[:500]}') from exc

        if body.get('status') == 'ok' and body.get('retcode') == 0:
            return body.get('data')

        error_message = (
            body.get('message')
            or body.get('wording')
            or body.get('msg')
            or body.get('error')
            or str(body)
        )
        raise RuntimeError(f'QQ API 调用失败: action={action} error={error_message}')

    def get_group_list(self) -> list[dict[str, Any]]:
        data = self.call('get_group_list', {})
        return data if isinstance(data, list) else []

    def get_group_member_list(self, group_id: int) -> list[dict[str, Any]]:
        data = self.call('get_group_member_list', {'group_id': str(group_id)})
        return data if isinstance(data, list) else []

    def send_group_msg(self, group_id: int, user_id: int, tracking_no: str) -> dict[str, Any]:
        payload = {
            'group_id': str(group_id),
            'message': [
                {'type': 'at', 'data': {'qq': str(user_id)}},
                {'type': 'text', 'data': {'text': f' {tracking_no} 物流状态'}},
            ],
        }
        data = self.call('send_group_msg', payload)
        return data if isinstance(data, dict) else {}

    def get_group_msg_history(self, group_id: int, count: int) -> list[dict[str, Any]]:
        data = self.call(
            'get_group_msg_history',
            {
                'group_id': str(group_id),
                'count': count,
                'reverse_order': False,
            },
        )
        messages = data.get('messages') if isinstance(data, dict) else None
        return messages if isinstance(messages, list) else []

    def get_group_msg_history_with_seq(
        self,
        group_id: int,
        message_seq: str,
        count: int,
        reverse_order: bool = True,
    ) -> list[dict[str, Any]]:
        data = self.call(
            'get_group_msg_history',
            {
                'group_id': str(group_id),
                'message_seq': str(message_seq),
                'count': count,
                'reverse_order': reverse_order,
            },
        )
        messages = data.get('messages') if isinstance(data, dict) else None
        return messages if isinstance(messages, list) else []


def _normalize_name_candidates(member: dict[str, Any]) -> list[str]:
    return [
        clean_text(member.get('card', '')),
        clean_text(member.get('nickname', '')),
    ]


def _resolve_group_id(client: NapCatOneBotClient, route_rule: QQRouteRule) -> int:
    env_group_id = _env_int(f'{route_rule.env_prefix}_GROUP_ID')
    if env_group_id is not None:
        return env_group_id

    target_name = clean_text(_env_str(f'{route_rule.env_prefix}_GROUP_NAME') or route_rule.group_name)
    matched = [group for group in client.get_group_list() if clean_text(group.get('group_name', '')) == target_name]
    if not matched:
        raise RuntimeError(f'未找到目标QQ群: {target_name}')
    if len(matched) > 1:
        raise RuntimeError(f'找到多个同名QQ群，请配置 {route_rule.env_prefix}_GROUP_ID')
    return int(matched[0]['group_id'])


def _resolve_user(client: NapCatOneBotClient, route_rule: QQRouteRule, group_id: int) -> tuple[int, str]:
    env_user_id = _env_int(f'{route_rule.env_prefix}_USER_ID')
    target_name = clean_text(_env_str(f'{route_rule.env_prefix}_USER_NAME') or route_rule.mention_name)
    if env_user_id is not None:
        return env_user_id, target_name

    members = client.get_group_member_list(group_id)
    matched: list[dict[str, Any]] = []
    for member in members:
        names = _normalize_name_candidates(member)
        if target_name and target_name in names:
            matched.append(member)

    if not matched:
        raise RuntimeError(f'群 {group_id} 中未找到成员: {target_name}')
    if len(matched) > 1:
        raise RuntimeError(f'群 {group_id} 中存在多个同名成员，请配置 {route_rule.env_prefix}_USER_ID')

    member = matched[0]
    display_name = clean_text(member.get('card') or member.get('nickname') or target_name)
    return int(member['user_id']), display_name


def _extract_message_text(message: dict[str, Any]) -> str:
    payload = message.get('message')
    if isinstance(payload, str):
        return clean_text(payload)
    if not isinstance(payload, list):
        return clean_text(message.get('raw_message', ''))

    parts: list[str] = []
    for segment in payload:
        if not isinstance(segment, dict):
            continue
        segment_type = segment.get('type')
        data = segment.get('data', {})
        if segment_type == 'text':
            parts.append(str(data.get('text', '')))
        elif segment_type == 'at':
            qq = clean_text(data.get('qq', ''))
            parts.append('@全体成员' if qq == 'all' else f'@{qq}')
    text = clean_text(' '.join(parts))
    if text:
        return text
    return clean_text(message.get('raw_message', ''))


def _extract_message_assets(message: dict[str, Any]) -> list[dict[str, str]]:
    payload = message.get('message')
    if not isinstance(payload, list):
        return []

    assets: list[dict[str, str]] = []
    for segment in payload:
        if not isinstance(segment, dict):
            continue
        segment_type = clean_text(segment.get('type', '')).lower()
        data = segment.get('data', {})
        if not isinstance(data, dict):
            data = {}

        if segment_type == 'image':
            url = clean_text(data.get('url') or data.get('file') or '')
            summary = clean_text(data.get('summary') or '') or '[图片]'
            assets.append({'类型': '图片', '名称': summary, '链接': url})
        elif segment_type == 'file':
            name = clean_text(data.get('file_name') or data.get('name') or '') or '[文件]'
            url = clean_text(data.get('url') or data.get('file') or '')
            assets.append({'类型': '文件', '名称': name, '链接': url})
        elif segment_type == 'video':
            url = clean_text(data.get('url') or data.get('file') or '')
            assets.append({'类型': '视频', '名称': '[视频]', '链接': url})
        elif segment_type == 'record':
            url = clean_text(data.get('url') or data.get('file') or '')
            assets.append({'类型': '语音', '名称': '[语音]', '链接': url})

    return assets


def _build_track(message: dict[str, Any]) -> dict[str, str]:
    timestamp = int(message.get('time') or 0)
    if timestamp > 0:
        time_text = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
    else:
        time_text = time.strftime('%Y-%m-%d %H:%M:%S')
    content = _extract_message_text(message)
    assets = _extract_message_assets(message)
    track = {
        '时间': time_text,
        '内容': content,
    }
    if assets:
        labels = []
        for asset in assets:
            asset_type = asset.get('类型', '')
            asset_name = asset.get('名称', '')
            if asset_name and asset_name.startswith('['):
                labels.append(asset_name)
            elif asset_type and asset_name:
                labels.append(f'[{asset_type}] {asset_name}')
            elif asset_type:
                labels.append(f'[{asset_type}]')
        if labels:
            asset_text = ' '.join(labels)
            track['内容'] = f'{content}\n{asset_text}'.strip() if content else asset_text
        track['消息类型'] = '附件'
        track['附件'] = assets
    else:
        track['消息类型'] = '文本'
    return track


def _extract_tracking_numbers_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for match in _TRACKING_NUMBER_RE.finditer(text):
        token = clean_text(match.group(0))
        start = match.start()
        end = match.end()
        if len(token) < 8:
            continue
        if not re.search(r'[A-Za-z]', token):
            continue
        if not re.search(r'\d', token):
            continue
        token_key = token.upper()
        if token_key in seen:
            continue
        seen.add(token_key)
        candidates.append(token)

    return candidates


def _extract_message_tracking_numbers(message: dict[str, Any], tracking_no: str = '') -> list[str]:
    fragments: list[str] = []
    raw_message = clean_text(message.get('raw_message', ''))
    if raw_message:
        fragments.append(raw_message)

    payload = message.get('message')
    if isinstance(payload, str):
        payload_text = clean_text(payload)
        if payload_text:
            fragments.append(payload_text)
    elif isinstance(payload, list):
        for segment in payload:
            if not isinstance(segment, dict):
                continue
            segment_type = clean_text(segment.get('type', '')).lower()
            if segment_type != 'text':
                continue
            data = segment.get('data', {})
            if not isinstance(data, dict):
                continue
            for value in data.values():
                value_text = clean_text(value)
                if value_text:
                    fragments.append(value_text)

    candidates: list[str] = []
    seen: set[str] = set()
    preferred = clean_text(tracking_no)
    preferred_key = preferred.upper() if preferred else ''

    for fragment in fragments:
        for candidate in _extract_tracking_numbers_from_text(fragment):
            candidate_key = candidate.upper()
            if preferred_key and candidate_key == preferred_key and preferred_key not in seen:
                candidates.append(preferred)
                seen.add(preferred_key)
                continue
            candidate_start = fragment.find(candidate)
            candidate_end = candidate_start + len(candidate) if candidate_start >= 0 else -1
            if candidate_start > 0 and fragment[candidate_start - 1] == '=':
                continue
            if candidate_end >= 0 and candidate_end < len(fragment) and fragment[candidate_end:candidate_end + 1] == '=':
                continue
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            candidates.append(candidate)

    return candidates


def _build_track_entry(message: dict[str, Any], tracking_no: str | None = None) -> dict[str, str]:
    track = _build_track(message)
    if tracking_no:
        track['单号'] = tracking_no
    return track


def _expand_history_matches(messages: list[dict[str, Any]], tracking_no: str) -> list[dict[str, str]]:
    expanded: list[dict[str, str]] = []
    seen_message_ids: set[str] = set()

    for message in sorted(messages, key=_message_sort_key, reverse=True):
        if not _message_contains_tracking_no(message, tracking_no):
            continue
        if not _message_has_content(message):
            continue

        message_id = str(message.get('message_id') or '')
        if message_id and message_id in seen_message_ids:
            continue

        tracking_numbers = _extract_message_tracking_numbers(message, tracking_no)
        if not tracking_numbers:
            tracking_numbers = [tracking_no]

        for number in tracking_numbers:
            expanded.append(_build_track_entry(message, number))

        if message_id:
            seen_message_ids.add(message_id)

    return expanded


def _message_sort_key(message: dict[str, Any]) -> tuple[int, int]:
    return int(message.get('time') or 0), int(message.get('message_seq') or 0)


def _is_message_older_than(message: dict[str, Any], now_ts: int, max_age_seconds: int) -> bool:
    message_ts = int(message.get('time') or 0)
    if message_ts <= 0:
        return False
    return now_ts - message_ts > max(max_age_seconds, 0)


def _message_contains_tracking_no(message: dict[str, Any], tracking_no: str) -> bool:
    needle = clean_text(tracking_no).lower()
    if not needle:
        return False

    haystacks = [clean_text(message.get('raw_message', ''))]
    payload = message.get('message')
    if isinstance(payload, str):
        haystacks.append(clean_text(payload))
    elif isinstance(payload, list):
        for segment in payload:
            if not isinstance(segment, dict):
                continue
            data = segment.get('data', {})
            if not isinstance(data, dict):
                continue
            for value in data.values():
                haystacks.append(clean_text(value))

    for asset in _extract_message_assets(message):
        haystacks.append(clean_text(asset.get('名称', '')))
        haystacks.append(clean_text(asset.get('链接', '')))

    return any(needle in haystack.lower() for haystack in haystacks if haystack)


def _message_sender_id(message: dict[str, Any]) -> str:
    sender = message.get('sender', {}) if isinstance(message.get('sender'), dict) else {}
    return str(message.get('user_id') or sender.get('user_id') or '')


def _message_has_content(message: dict[str, Any]) -> bool:
    return bool(
        _extract_message_text(message)
        or _extract_message_assets(message)
        or clean_text(message.get('raw_message', ''))
    )


def _message_has_meaningful_text(message: dict[str, Any]) -> bool:
    text = _extract_message_text(message)
    if text and '[CQ:' not in text:
        return True
    raw_message = clean_text(message.get('raw_message', ''))
    return bool(raw_message and '[CQ:' not in raw_message)


def _is_non_logistics_notice_message(message: dict[str, Any]) -> bool:
    text = _extract_message_text(message)
    if not text:
        text = clean_text(message.get('raw_message', ''))
    return any(keyword in text for keyword in _NON_LOGISTICS_NOTICE_KEYWORDS)


def _find_history_matches(
    messages: list[dict[str, Any]],
    tracking_no: str,
    target_user_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()
    target = str(target_user_id)

    for message in sorted(messages, key=_message_sort_key, reverse=True):
        if _message_sender_id(message) != target:
            continue
        if not _message_contains_tracking_no(message, tracking_no):
            continue
        if _is_non_logistics_notice_message(message):
            continue
        if not _message_has_meaningful_text(message):
            continue
        if not _message_has_content(message):
            continue
        message_id = str(message.get('message_id') or '')
        if message_id and message_id in seen_message_ids:
            continue
        if message_id:
            seen_message_ids.add(message_id)
        matched.append(message)
        if limit is not None and len(matched) >= max(limit, 1):
            break

    return matched


def _is_query_prompt_message(message: dict[str, Any], tracking_no: str, target_user_id: int) -> bool:
    payload = message.get('message')
    if not isinstance(payload, list):
        return False

    has_tracking_text = False
    has_target_at = False
    for segment in payload:
        if not isinstance(segment, dict):
            continue
        segment_type = clean_text(segment.get('type', '')).lower()
        data = segment.get('data', {})
        if not isinstance(data, dict):
            continue
        if segment_type == 'text':
            text = clean_text(data.get('text', ''))
            if tracking_no in text and '物流状态' in text:
                has_tracking_text = True
        elif segment_type == 'at':
            qq = clean_text(data.get('qq', ''))
            if qq == str(target_user_id):
                has_target_at = True
    return has_tracking_text and has_target_at


def _find_any_tracking_messages(
    messages: list[dict[str, Any]],
    tracking_no: str,
    target_user_id: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()

    for message in sorted(messages, key=_message_sort_key, reverse=True):
        if not _message_contains_tracking_no(message, tracking_no):
            continue
        if _is_query_prompt_message(message, tracking_no, target_user_id):
            continue
        if _is_non_logistics_notice_message(message):
            continue
        if not _message_has_meaningful_text(message):
            continue
        if not _message_has_content(message):
            continue
        message_id = str(message.get('message_id') or '')
        if message_id and message_id in seen_message_ids:
            continue
        if message_id:
            seen_message_ids.add(message_id)
        matched.append(message)

    return matched


def _scan_history_messages(
    client: NapCatOneBotClient,
    group_id: int,
    page_size: int,
    max_messages: int,
) -> list[dict[str, Any]]:
    scanned = 0
    next_anchor_seq: str | None = None
    seen_message_ids: set[str] = set()
    collected: list[dict[str, Any]] = []

    while scanned < max_messages:
        count = min(page_size, max_messages - scanned)
        if next_anchor_seq is None:
            page = client.get_group_msg_history(group_id, count)
        else:
            page = client.get_group_msg_history_with_seq(group_id, next_anchor_seq, count, reverse_order=True)

        if not page:
            break

        raw_page_size = len(page)
        deduped_page: list[dict[str, Any]] = []
        for message in page:
            message_id = str(message.get('message_id') or '')
            if message_id and message_id in seen_message_ids:
                continue
            if message_id:
                seen_message_ids.add(message_id)
            deduped_page.append(message)

        if not deduped_page:
            break

        collected.extend(deduped_page)
        scanned += len(deduped_page)
        oldest = page[0]
        oldest_seq = str(oldest.get('message_seq') or '').strip()
        if not oldest_seq or raw_page_size < count:
            break
        next_anchor_seq = oldest_seq

    return collected


def _history_debug_summary(messages: list[dict[str, Any]], tracking_no: str) -> str:
    if not messages:
        return f'总数=0 tracking={tracking_no} 命中=0'

    ordered = sorted(messages, key=_message_sort_key)
    newest = ordered[-1]
    oldest = ordered[0]
    matched = [message for message in ordered if _message_contains_tracking_no(message, tracking_no)]
    return (
        f'总数={len(ordered)} '
        f'最早={oldest.get("time")}#{oldest.get("message_seq")} '
        f'最新={newest.get("time")}#{newest.get("message_seq")} '
        f'tracking={tracking_no} 命中={len(matched)}'
    )


def _find_reply_messages(
    messages: list[dict[str, Any]],
    target_user_id: int,
    not_before: int,
    min_message_seq: int,
) -> list[dict[str, Any]]:
    target = str(target_user_id)
    collected: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()

    for message in sorted(messages, key=_message_sort_key):
        sender = message.get('sender', {}) if isinstance(message.get('sender'), dict) else {}
        sender_id = str(message.get('user_id') or sender.get('user_id') or '')
        if sender_id != target:
            continue
        message_time = int(message.get('time') or 0)
        if message_time and message_time < not_before:
            continue
        message_seq = int(message.get('message_seq') or 0)
        if message_seq and message_seq <= min_message_seq:
            continue
        message_id = str(message.get('message_id') or '')
        if message_id and message_id in seen_message_ids:
            continue
        text = _extract_message_text(message)
        assets = _extract_message_assets(message)
        if not text and not assets:
            continue
        if message_id:
            seen_message_ids.add(message_id)
        collected.append(message)
    return collected


def query_qq(order: dict[str, Any], tracking_no: str, defer_if_stale: bool = False) -> dict[str, Any]:
    route_rule = get_qq_route_rule(order)
    if route_rule is None:
        return {
            '平台': 'QQ',
            '查询值': tracking_no,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '当前货代公司未配置 QQ 查询规则',
        }

    if not tracking_no:
        return {
            '平台': 'QQ',
            '查询值': tracking_no,
            '群名': route_rule.group_name,
            '询问对象': route_rule.mention_name,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': '钉钉表格中未找到物流编号，无法通过 QQ 询问物流状态',
        }

    question_text = build_question_text(route_rule, tracking_no)
    (
        api_base_url,
        api_token,
        api_timeout_seconds,
        reply_timeout_seconds,
        poll_interval_seconds,
        history_fetch_count,
    ) = get_qq_api_settings()
    client = NapCatOneBotClient(
        base_url=api_base_url,
        token=api_token,
        timeout_seconds=api_timeout_seconds,
    )

    try:
        group_id = _resolve_group_id(client, route_rule)
        user_id, display_name = _resolve_user(client, route_rule, group_id)
        history_lookback_count = max(history_fetch_count, get_qq_history_lookback_count())
        history_messages = _scan_history_messages(
            client=client,
            group_id=group_id,
            page_size=history_fetch_count,
            max_messages=history_lookback_count,
        )
        logger.info(
            "QQ历史扫描: 群号=%s %s",
            group_id,
            _history_debug_summary(history_messages, tracking_no),
        )
        any_tracking_matches = _find_any_tracking_messages(
            history_messages,
            tracking_no=tracking_no,
            target_user_id=user_id,
        )
        history_matches = _find_history_matches(
            history_messages,
            tracking_no=tracking_no,
            target_user_id=user_id,
        )
        any_tracking_tracks = _expand_history_matches(any_tracking_matches, tracking_no)
        history_tracks = _expand_history_matches(history_matches, tracking_no)
        logger.info(
            "QQ历史过滤: tracking=%s 全群命中=%s 李美慧命中=%s",
            tracking_no,
            len(any_tracking_tracks),
            len(history_tracks),
        )
        if not any_tracking_matches:
            raw_matches = [
                message
                for message in sorted(history_messages, key=_message_sort_key, reverse=True)
                if _message_contains_tracking_no(message, tracking_no)
            ]
            if raw_matches:
                latest_raw = raw_matches[0]
                logger.info(
                    "QQ历史原始命中但被过滤: tracking=%s sender=%s time=%s raw=%s",
                    tracking_no,
                    _message_sender_id(latest_raw),
                    latest_raw.get('time'),
                    clean_text(latest_raw.get('raw_message', '')),
                )
        if any_tracking_matches:
            latest_any = any_tracking_matches[0]
            logger.info(
                "QQ历史全群最新: tracking=%s sender=%s time=%s | %s",
                tracking_no,
                _message_sender_id(latest_any),
                latest_any.get('time'),
                _extract_message_text(latest_any),
            )
        if history_tracks:
            logger.info(
                "QQ历史命中: tracking=%s 条数=%s 最新=%s | %s",
                tracking_no,
                len(history_tracks),
                history_tracks[0].get('时间'),
                history_tracks[0].get('内容'),
            )
        latest_history_message = history_matches[0] if history_matches else None
        history_is_stale = bool(
            latest_history_message
            and _is_message_older_than(
                latest_history_message,
                now_ts=int(time.time()),
                max_age_seconds=DEFAULT_HISTORY_FRESHNESS_DAYS * 24 * 60 * 60,
            )
        )
        if history_tracks and not history_is_stale:
            return {
                '平台': 'QQ',
                '查询值': tracking_no,
                '群名': route_rule.group_name,
                '群号': str(group_id),
                '询问对象': display_name,
                '询问对象QQ': str(user_id),
                '提问内容': '',
                '发送消息ID': '',
                '回复消息ID': str(history_matches[0].get('message_id') or ''),
                '结果来源': '群历史(按物流编号匹配，展开消息中的多单号)',
                '物流轨迹': history_tracks,
                '最新轨迹': history_tracks[0],
            }
        if history_tracks and history_is_stale:
            logger.info(
                "QQ历史已过期: tracking=%s 最新时间=%s 超过%s天，转为主动询问",
                tracking_no,
                history_tracks[0].get('时间'),
                DEFAULT_HISTORY_FRESHNESS_DAYS,
            )
            if defer_if_stale:
                return {
                    '平台': 'QQ',
                    '查询值': tracking_no,
                    '群名': route_rule.group_name,
                    '群号': str(group_id),
                    '询问对象': display_name,
                    '询问对象QQ': str(user_id),
                    '结果来源': '群历史已过期，转为异步人工询问',
                    '需要异步跟进': True,
                    '物流轨迹': history_tracks,
                    '最新轨迹': history_tracks[0],
                }

        baseline_history = client.get_group_msg_history(group_id, history_fetch_count)
        baseline_message_seq = max((int(item.get('message_seq') or 0) for item in baseline_history), default=0)
        send_started_at = int(time.time()) - 1
        send_result = client.send_group_msg(group_id, user_id, tracking_no)
        sent_message_id = send_result.get('message_id', '')

        deadline = time.time() + reply_timeout_seconds
        while time.time() < deadline:
            history = client.get_group_msg_history(group_id, history_fetch_count)
            replies = _find_reply_messages(history, user_id, send_started_at, baseline_message_seq)
            if replies:
                first_reply = sorted(replies, key=_message_sort_key)[0]
                tracks = [_build_track(first_reply)]
                return {
                    '平台': 'QQ',
                    '查询值': tracking_no,
                    '群名': route_rule.group_name,
                    '群号': str(group_id),
                    '询问对象': display_name,
                    '询问对象QQ': str(user_id),
                    '提问内容': question_text,
                    '发送消息ID': str(sent_message_id),
                    '回复消息ID': str(first_reply.get('message_id') or ''),
                    '物流轨迹': tracks,
                    '最新轨迹': tracks[0],
                }
            time.sleep(poll_interval_seconds)

        return {
            '平台': 'QQ',
            '查询值': tracking_no,
            '群名': route_rule.group_name,
            '群号': str(group_id),
            '询问对象': display_name,
            '询问对象QQ': str(user_id),
            '提问内容': question_text,
            '发送消息ID': str(sent_message_id),
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': f'等待 QQ 回复超时（{reply_timeout_seconds} 秒）',
        }
    except Exception as exc:
        logger.warning("QQ 查询失败: tracking_no=%s error=%s", tracking_no, exc)
        return {
            '平台': 'QQ',
            '查询值': tracking_no,
            '群名': route_rule.group_name,
            '询问对象': route_rule.mention_name,
            '提问内容': question_text,
            '物流轨迹': [],
            '最新轨迹': {},
            '错误': str(exc),
        }
