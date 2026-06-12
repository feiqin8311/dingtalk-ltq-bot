import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


TRACKING_QUERY_CACHE_TTL_SECONDS = 900
TRACKING_QUERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
BROWSER_TRACKING_QUEUE_STATE: dict[int, dict[str, Any]] = {}


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


def normalize_optional_text(value: Any) -> str:
    if value is None:
        return ''
    return clean_text(value)


def normalize_tracking_number(value: Any) -> str:
    return clean_text(value).replace(' ', '').upper()


def build_tracking_result_link(platform: str, query_value: str) -> str:
    normalized_platform = clean_text(platform).upper()
    normalized_query = normalize_tracking_number(query_value)
    if not normalized_platform or not normalized_query:
        return ''
    if normalized_platform in {'17TRACK', '17TRACK_EN'}:
        return f'https://t.17track.net/en#nums={quote(normalized_query)}'
    if normalized_platform == 'UNIUNI':
        return f'https://www.uniuni.com//tracking#tracking-detail?no={quote(normalized_query)}'
    if normalized_platform == 'GOFO':
        return f'https://www.gofo.com/us/track?searchID={quote(normalized_query)}'
    if normalized_platform == 'USPS':
        return f'https://tools.usps.com/tracking/{quote(normalized_query)}'
    if normalized_platform == 'UPS':
        return f'https://www.ups.com/track?tracknum={quote(normalized_query)}'
    if normalized_platform == 'FEDEX':
        return f'https://www.fedex.com/wtrk/track/?trknbr={quote(normalized_query)}'
    if normalized_platform == 'YUNTRACK':
        return f'https://www.yuntrack.com/parcelTracking?id={quote(normalized_query)}'
    if normalized_platform == 'AMAZON_UK':
        return f'https://track.amazon.co.uk/tracking/{quote(normalized_query)}?trackingId={quote(normalized_query)}'
    if normalized_platform == 'SWISHIP_CA':
        return f'https://www.swiship.com/track?loc=en-US&id={quote(normalized_query)}'
    if normalized_platform == 'AMAZON_US':
        return f'https://track.amazon.com/tracking/{quote(normalized_query)}?trackingId={quote(normalized_query)}'
    return ''


def attach_tracking_result_link(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    link = normalize_optional_text(result.get('物流链接') or result.get('当前URL'))
    if not link:
        link = build_tracking_result_link(result.get('平台', ''), result.get('查询值', ''))
    if link:
        result['物流链接'] = link
    return result


def get_tracking_query_cache(cache_key: str) -> dict[str, Any] | None:
    cached = TRACKING_QUERY_CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, cached_result = cached
    if time.time() - cached_at > TRACKING_QUERY_CACHE_TTL_SECONDS:
        TRACKING_QUERY_CACHE.pop(cache_key, None)
        return None
    return dict(cached_result)


def set_tracking_query_cache(cache_key: str, result: dict[str, Any]) -> None:
    error_text = clean_text(result.get('错误', ''))
    if error_text:
        TRACKING_QUERY_CACHE.pop(cache_key, None)
        return
    TRACKING_QUERY_CACHE[cache_key] = (time.time(), dict(result))


def get_browser_tracking_queue_state() -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    state = BROWSER_TRACKING_QUEUE_STATE.get(loop_id)
    if state is None:
        state = {
            'lock': asyncio.Lock(),
            'waiting': 0,
            'thread_id': threading.get_ident(),
        }
        BROWSER_TRACKING_QUEUE_STATE[loop_id] = state
    return state


async def resolve_async_result(result):
    while asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
        result = await result
    return result


async def run_browser_tracking_query_with_queue(logger, platform: str, query_value: str, operation):
    state = get_browser_tracking_queue_state()
    queue_lock = state['lock']
    queued_ahead = 0
    if queue_lock.locked():
        state['waiting'] += 1
        queued_ahead = state['waiting']
        logger.info(
            "浏览器查询队列: 平台=%s 查询值=%s 排队中 queued_ahead=%s",
            platform,
            query_value,
            queued_ahead,
        )

    await queue_lock.acquire()
    if queued_ahead:
        state['waiting'] = max(0, state['waiting'] - 1)

    try:
        logger.info(
            "浏览器查询队列: 平台=%s 查询值=%s 开始执行 waiting=%s",
            platform,
            query_value,
            state['waiting'],
        )
        result = operation()
        result = await resolve_async_result(result)
        return result
    finally:
        queue_lock.release()
        logger.info(
            "浏览器查询队列: 平台=%s 查询值=%s 执行结束 remaining_waiting=%s",
            platform,
            query_value,
            state['waiting'],
        )
