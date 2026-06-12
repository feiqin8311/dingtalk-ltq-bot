import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class TrackingProviderDeps:
    normalize_tracking_number: Callable[[Any], str]
    clean_text: Callable[[Any], str]
    begin_local_cdp_session: Callable[[], Any]
    end_local_cdp_session: Callable[[Any], None]
    get_local_cdp_endpoint: Callable[[], str]
    open_cdp_query_page: Callable[..., Any]
    cleanup_cdp_query_page: Callable[..., Any]
    apply_browser_stealth: Callable[..., Any]
    logger: Any
    sort_tracks_newest_first: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None
    extract_17track_items_from_html: Callable[[str], list[dict[str, str]]] | None = None
    build_usps_query_urls: Callable[[str], list[str]] | None = None
    apply_usps_browser_stealth: Callable[..., Any] | None = None
    type_like_human: Callable[..., Any] | None = None
    is_usps_blocked_page_html: Callable[[str], bool] | None = None
    build_usps_debug_dir: Callable[..., Path] | None = None
    extract_usps_tracking_items_from_html: Callable[[str], list[dict[str, str]]] | None = None


async def query_17track_provider(order_no: str, deps: TrackingProviderDeps) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    normalize_tracking_number = deps.normalize_tracking_number
    clean_text = deps.clean_text
    sort_tracks_newest_first = deps.sort_tracks_newest_first
    extract_17track_items_from_html = deps.extract_17track_items_from_html
    begin_local_cdp_session = deps.begin_local_cdp_session
    end_local_cdp_session = deps.end_local_cdp_session
    get_local_cdp_endpoint = deps.get_local_cdp_endpoint
    open_cdp_query_page = deps.open_cdp_query_page
    cleanup_cdp_query_page = deps.cleanup_cdp_query_page
    apply_browser_stealth = deps.apply_browser_stealth
    logger = deps.logger
    if sort_tracks_newest_first is None or extract_17track_items_from_html is None:
        raise RuntimeError('17TRACK provider dependencies are incomplete')

    normalized = normalize_tracking_number(order_no)
    query_url = f'https://t.17track.net/en#nums={normalized}'
    logger.info("17TRACK 查询: order_no=%s", order_no)

    async def dismiss_17track_guide_popup(page) -> bool:
        popup_selectors = ['div.tooltip__body[role="alertdialog"]', 'div.tooltip__body']
        close_selectors = ['button.tooltip__close', 'button:has-text("关闭")', 'button:has-text("知道了")']
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
        selectors = ['iframe[src*="captcha"]', 'iframe[src*="verify"]', '[class*="captcha"]', '[class*="verify"]', '[id*="captcha"]', '[id*="verify"]']
        text_patterns = ['人机验证', '完成验证', '安全验证', '请先验证', '看看右边的图片，找出它的“同类”吧', '看看右边的图片，找出它的"同类"吧', '刷新', '确认', 'Verify you are human', 'Security check', 'CAPTCHA']
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

    async def detect_not_found_result(page) -> str:
        text_patterns = ['Not found', 'Tracking Not Available', 'The carrier has not updated the information', 'try switching carrier and then check again']
        try:
            html = await page.content()
        except Exception:
            html = ''
        normalized_html = clean_text(html)
        if all(pattern.lower() in normalized_html.lower() for pattern in ('not found', 'carrier has not updated the information')):
            return '17TRACK 未查询到轨迹信息，请确认单号或切换承运商后重试'
        if 'Tracking Not Available'.lower() in normalized_html.lower():
            return '17TRACK 未查询到轨迹信息，请确认单号是否有效'
        try:
            body_text = await page.locator('body').inner_text(timeout=1000)
        except Exception:
            body_text = ''
        normalized_body_text = clean_text(body_text).lower()
        for pattern in text_patterns:
            if pattern.lower() in normalized_body_text:
                return '17TRACK 未查询到轨迹信息，请确认单号或切换承运商后重试'
        return ''

    cdp_process = begin_local_cdp_session()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        context, page, owns_context = await open_cdp_query_page(browser, force_new_context=True, viewport={'width': 1440, 'height': 900})
        try:
            await apply_browser_stealth(context, page, platform='17TRACK')
            await page.goto(query_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(1200)
            await dismiss_17track_guide_popup(page)
            captcha_detected = False
            timeline_root = page.locator('span.yq-time').first
            for _ in range(180):
                await dismiss_17track_guide_popup(page)
                if await detect_human_verification(page):
                    if not captcha_detected:
                        captcha_detected = True
                        logger.warning("17TRACK 查询: 检测到人机验证，请先在浏览器中完成验证，程序将继续等待")
                    await page.wait_for_timeout(800)
                    continue
                not_found_error = await detect_not_found_result(page)
                if not_found_error:
                    return {'平台': '17TRACK', '查询值': normalized, '当前页面标题': await page.title(), '当前URL': page.url, '最新轨迹': {}, '物流轨迹': [], '错误': not_found_error}
                try:
                    if await timeline_root.count() > 0 and await timeline_root.is_visible(timeout=300):
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(700)
            else:
                if captcha_detected:
                    raise RuntimeError('17TRACK 人机验证等待超时，请完成验证后重试')
                raise RuntimeError('17TRACK 查询超时，未获取到轨迹结果')
            await page.wait_for_timeout(800)
            timeline_container = page.locator('span.yq-time').locator('xpath=ancestor::div[contains(@class,"relative")][1]').first
            html = await timeline_container.inner_html(timeout=15000)
            track_items = sort_tracks_newest_first(extract_17track_items_from_html(html))
            if not track_items:
                return {'平台': '17TRACK', '查询值': normalized, '当前页面标题': await page.title(), '当前URL': page.url, '最新轨迹': {}, '物流轨迹': [], '错误': '17TRACK 页面未返回轨迹信息'}
            latest_track = track_items[0] if track_items else {'时间': '', '内容': ''}
            logger.info("17TRACK 查询: 轨迹条数=%s", len(track_items))
            return {'平台': '17TRACK', '查询值': normalized, '当前页面标题': await page.title(), '当前URL': page.url, '最新轨迹': latest_track, '物流轨迹': track_items}
        finally:
            await cleanup_cdp_query_page(page, context, owns_context)
            end_local_cdp_session(cdp_process)


async def query_fedex_provider(tracking_no: str, deps: TrackingProviderDeps) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    normalize_tracking_number = deps.normalize_tracking_number
    begin_local_cdp_session = deps.begin_local_cdp_session
    end_local_cdp_session = deps.end_local_cdp_session
    get_local_cdp_endpoint = deps.get_local_cdp_endpoint
    open_cdp_query_page = deps.open_cdp_query_page
    cleanup_cdp_query_page = deps.cleanup_cdp_query_page
    apply_browser_stealth = deps.apply_browser_stealth
    clean_text = deps.clean_text
    logger = deps.logger
    type_like_human = deps.type_like_human

    normalized = normalize_tracking_number(tracking_no)
    query_url = 'https://www.fedex.com/en-us/home.html'
    logger.info("FedEx 查询: tracking_no=%s", normalized)

    cdp_process = begin_local_cdp_session()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        context, page, owns_context = await open_cdp_query_page(browser, force_new_context=True, viewport={'width': 1440, 'height': 900})
        try:
            await apply_browser_stealth(context, page, platform='FEDEX')

            async def _dump_debug_artifacts() -> tuple[str, str, str]:
                title = ''
                url = page.url
                try:
                    title = await page.title()
                except Exception:
                    title = ''
                html = ''
                try:
                    html = await page.content()
                except Exception:
                    html = ''
                debug_dir = Path('tmp') / 'fedex-debug' / datetime.now().strftime('%Y-%m-%d')
                debug_dir.mkdir(parents=True, exist_ok=True)
                html_path = debug_dir / f'{normalized}.html'
                screenshot_path = debug_dir / f'{normalized}.png'
                html_path.write_text(html or '', encoding='utf-8')
                try:
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    pass
                logger.warning("FedEx 查询调试文件已保存 tracking_no=%s title=%s url=%s html=%s screenshot=%s", normalized, title, url, html_path, screenshot_path)
                return title, url, str(html_path)

            goto_error = ''
            for attempt in range(1, 3):
                try:
                    await page.goto(query_url, wait_until='domcontentloaded', timeout=60000)
                    goto_error = ''
                    break
                except Exception as exc:
                    goto_error = str(exc)
                    logger.warning("FedEx 查询: 页面打开失败 tracking_no=%s attempt=%s error=%s", normalized, attempt, exc)
                    if attempt >= 2:
                        title, current_url, html_path = await _dump_debug_artifacts()
                        return {'平台': 'FEDEX', '查询值': normalized, '物流轨迹': [], '最新轨迹': {}, '错误': f'FedEx 查询页面连接失败: {goto_error}', '当前页面标题': title, '当前URL': current_url, '调试HTML': html_path}
                    await page.wait_for_timeout(random.randint(1500, 2800))

            cookie_button = page.locator('#accept').first
            try:
                if await cookie_button.count() > 0 and await cookie_button.is_visible(timeout=1000):
                    await cookie_button.click(timeout=5000)
                    await page.wait_for_timeout(600)
            except Exception:
                pass

            async def _close_fedex_modal() -> bool:
                close_selectors = [
                    'a.fxg-u-modal__close.js-modal-close[title="close"]',
                    'a.fxg-u-modal__close.js-modal-close',
                    '.fxg-u-modal__close.js-modal-close',
                ]
                for close_selector in close_selectors:
                    try:
                        close_button = page.locator(close_selector).first
                        if await close_button.count() > 0 and await close_button.is_visible(timeout=800):
                            await close_button.click(timeout=3000)
                            await page.wait_for_timeout(700)
                            logger.info("FedEx 查询: 已关闭首页弹窗 selector=%s", close_selector)
                            return True
                    except Exception:
                        continue
                return False

            await _close_fedex_modal()

            tracking_input_selector = 'input[type="text"][placeholder="Tracking number"]'
            track_button_selector = 'button.fxp-c-form__button.fxp-c-button--primary.fxp-c-button--primary-condensed'
            tracking_input = page.locator(tracking_input_selector).first
            try:
                await tracking_input.wait_for(timeout=30000)
            except Exception as exc:
                await _close_fedex_modal()
                try:
                    await tracking_input.wait_for(timeout=8000)
                except Exception:
                    title, current_url, html_path = await _dump_debug_artifacts()
                    return {
                        '平台': 'FEDEX',
                        '查询值': normalized,
                        '物流轨迹': [],
                        '最新轨迹': {},
                        '错误': f'FedEx 首页未出现跟踪号输入框: {exc}',
                        '当前页面标题': title,
                        '当前URL': current_url,
                        '调试HTML': html_path,
                    }
            if type_like_human is not None:
                await type_like_human(page, tracking_input_selector, normalized, delay_range=(90, 180))
            else:
                await tracking_input.fill(normalized)
            try:
                current_value = clean_text(await tracking_input.input_value())
            except Exception:
                current_value = ''
            if current_value and current_value != normalized:
                logger.warning("FedEx 查询: 输入框值不一致 tracking_no=%s actual=%s", normalized, current_value)
            track_button = page.locator(track_button_selector).first
            await track_button.wait_for(timeout=12000)
            await page.wait_for_timeout(random.randint(500, 1100))
            await track_button.click(timeout=8000)
            await page.wait_for_timeout(random.randint(1200, 2200))

            if 'system-error' in page.url:
                title, current_url, html_path = await _dump_debug_artifacts()
                return {'平台': 'FEDEX', '查询值': normalized, '物流轨迹': [], '最新轨迹': {}, '错误': 'FedEx 系统错误页，暂时无法查询', '当前页面标题': title, '当前URL': current_url, '调试HTML': html_path}

            progress_container = page.locator('div.shipment-status-progress-container').first
            try:
                await progress_container.wait_for(timeout=30000)
            except Exception:
                if 'system-error' in page.url:
                    title, current_url, html_path = await _dump_debug_artifacts()
                    return {'平台': 'FEDEX', '查询值': normalized, '物流轨迹': [], '最新轨迹': {}, '错误': 'FedEx 系统错误页，暂时无法查询', '当前页面标题': title, '当前URL': current_url, '调试HTML': html_path}
                raise
            active_step = page.locator('div.shipment-status-progress-step.active').first
            await active_step.wait_for(timeout=15000)
            content_nodes = active_step.locator('span.shipment-status-progress-step-label-content')
            content_values: list[str] = []
            try:
                count = await content_nodes.count()
            except Exception:
                count = 0
            for index in range(count):
                try:
                    text = clean_text(await content_nodes.nth(index).inner_text())
                except Exception:
                    text = ''
                if text:
                    content_values.append(text)
            active_text = clean_text(await active_step.inner_text())
            status = content_values[0] if len(content_values) >= 1 else ''
            location = content_values[1] if len(content_values) >= 2 else ''
            time_text = content_values[2] if len(content_values) >= 3 else ''
            if not status:
                lines = [clean_text(line) for line in active_text.splitlines() if clean_text(line)]
                if len(lines) >= 4:
                    status = lines[1]
                    location = lines[2]
                    time_text = lines[3]
                elif len(lines) >= 3:
                    status = lines[0]
                    location = lines[1]
                    time_text = lines[2]
                elif len(lines) >= 1:
                    status = lines[-1]
            latest_track = {'时间': time_text, '地点': location, '内容': status or active_text}
            return {'平台': 'FEDEX', '查询值': normalized, '当前页面标题': await page.title(), '当前URL': page.url, '最新轨迹': latest_track, '物流轨迹': [latest_track] if any(latest_track.values()) else []}
        finally:
            await cleanup_cdp_query_page(page, context, owns_context)
            end_local_cdp_session(cdp_process)


async def query_usps_provider(tracking_no: str, deps: TrackingProviderDeps) -> dict[str, Any]:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    normalize_tracking_number = deps.normalize_tracking_number
    build_usps_query_urls = deps.build_usps_query_urls
    begin_local_cdp_session = deps.begin_local_cdp_session
    end_local_cdp_session = deps.end_local_cdp_session
    get_local_cdp_endpoint = deps.get_local_cdp_endpoint
    open_cdp_query_page = deps.open_cdp_query_page
    cleanup_cdp_query_page = deps.cleanup_cdp_query_page
    apply_usps_browser_stealth = deps.apply_usps_browser_stealth
    type_like_human = deps.type_like_human
    clean_text = deps.clean_text
    is_usps_blocked_page_html = deps.is_usps_blocked_page_html
    build_usps_debug_dir = deps.build_usps_debug_dir
    extract_usps_tracking_items_from_html = deps.extract_usps_tracking_items_from_html
    logger = deps.logger
    if (
        build_usps_query_urls is None
        or apply_usps_browser_stealth is None
        or type_like_human is None
        or is_usps_blocked_page_html is None
        or build_usps_debug_dir is None
        or extract_usps_tracking_items_from_html is None
    ):
        raise RuntimeError('USPS provider dependencies are incomplete')

    normalized = normalize_tracking_number(tracking_no)
    query_urls = build_usps_query_urls(normalized)
    tools_url = 'https://tools.usps.com/tracking/'
    homepage_url = 'https://www.usps.com/'
    logger.info("USPS 查询: tracking_no=%s", normalized)

    cdp_process = begin_local_cdp_session()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        context, page, owns_context = await open_cdp_query_page(
            browser,
            force_new_context=True,
            viewport={'width': 1440, 'height': 900},
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'),
            locale='en-US',
            timezone_id='America/Chicago',
            color_scheme='light',
        )
        try:
            await apply_usps_browser_stealth(context, page)
            try:
                await page.bring_to_front()
            except Exception:
                pass

            class _UspsToolsBlockedError(RuntimeError):
                pass

            async def _wait_for_usps_tracking_input() -> None:
                search_input = page.locator('#tracking-input').first
                try:
                    await search_input.wait_for(timeout=12000)
                    return
                except Exception as exc:
                    html = await page.content()
                    if not is_usps_blocked_page_html(html):
                        raise exc
                    logger.warning("USPS 查询: 检测到 Akamai 挑战页，等待自动恢复 tracking_no=%s", normalized)
                    await page.wait_for_timeout(random.randint(5000, 9000))
                    try:
                        await search_input.wait_for(timeout=8000)
                        return
                    except Exception:
                        logger.warning("USPS 查询: 挑战页未自动恢复，尝试刷新 tracking_no=%s", normalized)
                        await page.reload(wait_until='domcontentloaded', timeout=60000)
                        await page.wait_for_timeout(random.randint(3000, 6000))
                        try:
                            await search_input.wait_for(timeout=12000)
                            return
                        except Exception as refresh_exc:
                            refreshed_html = await page.content()
                            if is_usps_blocked_page_html(refreshed_html):
                                raise _UspsToolsBlockedError('USPS tools tracking page remains blocked') from refresh_exc
                            raise refresh_exc

            async def _submit_via_tools_page() -> None:
                logger.info("USPS 查询: 打开查询页 %s", tools_url)
                await page.goto(tools_url, wait_until='domcontentloaded', timeout=60000)
                search_input = page.locator('#tracking-input').first
                await _wait_for_usps_tracking_input()
                await page.wait_for_timeout(random.randint(600, 1300))
                await type_like_human(page, '#tracking-input', normalized, delay_range=(90, 180))
                await page.wait_for_timeout(random.randint(500, 1100))
                actual_input_value = normalize_tracking_number(await search_input.input_value())
                if actual_input_value != normalized:
                    raise RuntimeError(f'USPS 输入框内容被截断或改写: expected={normalized} actual={actual_input_value or "empty"}')
                search_button = page.locator('#trackBtn').first
                await search_button.wait_for(timeout=10000)
                await page.wait_for_timeout(random.randint(400, 900))
                await search_button.click(timeout=10000)

            async def _submit_via_homepage() -> None:
                logger.info("USPS 查询: 回退首页入口 %s", homepage_url)
                await page.goto(homepage_url, wait_until='domcontentloaded', timeout=60000)
                search_input = page.locator('#home-input').first
                await search_input.wait_for(timeout=20000)
                await page.wait_for_timeout(random.randint(900, 1700))
                await type_like_human(page, '#home-input', normalized, delay_range=(100, 210))
                await page.wait_for_timeout(random.randint(700, 1300))
                actual_input_value = normalize_tracking_number(await search_input.input_value())
                if actual_input_value != normalized:
                    raise RuntimeError(f'USPS 首页输入框内容被截断或改写: expected={normalized} actual={actual_input_value or "empty"}')
                button_selectors = ['button.input--search.btn:visible', 'form#search-site button[type="submit"]', 'button.input--search[type="submit"]']
                last_button_error: Exception | None = None
                for button_selector in button_selectors:
                    search_button = page.locator(button_selector).first
                    try:
                        await search_button.wait_for(timeout=6000)
                        await page.wait_for_timeout(random.randint(500, 1000))
                        await search_button.click(timeout=10000)
                        return
                    except Exception as exc:
                        last_button_error = exc
                try:
                    await page.locator('#home-input').first.press('Enter', timeout=5000)
                    return
                except Exception as exc:
                    if last_button_error is not None:
                        raise last_button_error
                    raise exc

            search_submitted = False
            submit_error = ''
            try:
                try:
                    await _submit_via_tools_page()
                except _UspsToolsBlockedError as blocked_exc:
                    logger.warning("USPS 查询: tools 入口持续被拦截，回退首页入口 tracking_no=%s", normalized)
                    submit_error = str(blocked_exc)
                    await _submit_via_homepage()
                tracking_number = page.locator('#trackingNum').first
                await tracking_number.wait_for(timeout=30000)
                tracking_number_text = clean_text(await tracking_number.inner_text())
                if tracking_number_text != normalized:
                    raise RuntimeError(f'USPS 查询结果页跟踪号不匹配: expected={normalized} actual={tracking_number_text or "empty"}')
                await page.wait_for_timeout(random.randint(900, 1600))
                search_submitted = True
            except Exception as exc:
                submit_error = str(exc)
                logger.warning("USPS 查询: 提交查询失败 tracking_no=%s error=%s", normalized, exc)

            async def _dump_debug_artifacts() -> tuple[str, str, str]:
                title = ''
                url = page.url
                try:
                    title = await page.title()
                except Exception:
                    title = ''
                html = await page.content()
                debug_dir = build_usps_debug_dir()
                debug_dir.mkdir(parents=True, exist_ok=True)
                html_path = debug_dir / f'{normalized}.html'
                screenshot_path = debug_dir / f'{normalized}.png'
                html_path.write_text(html, encoding='utf-8')
                try:
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    pass
                logger.warning("USPS 查询调试文件已保存 tracking_no=%s title=%s url=%s html=%s screenshot=%s", normalized, title, url, html_path, screenshot_path)
                return title, url, str(html_path)

            if not search_submitted:
                title, current_url, html_path = await _dump_debug_artifacts()
                return {'平台': 'USPS', '查询值': normalized, '物流轨迹': [], '最新轨迹': {}, '错误': f'USPS 查询提交失败: {submit_error or "未知错误"}', '当前页面标题': title, '当前URL': current_url, '调试HTML': html_path}

            for query_url in query_urls:
                for attempt in range(1, 4):
                    if attempt == 1:
                        logger.info("USPS 查询: 已提交 tracking_no=%s target=%s", normalized, query_url)
                    else:
                        logger.warning("USPS 查询: 页面未返回轨迹，刷新重试 tracking_no=%s url=%s attempt=%s", normalized, query_url, attempt - 1)
                        await page.reload(wait_until='domcontentloaded', timeout=60000)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=20000)
                    except PlaywrightTimeoutError:
                        pass
                    await page.wait_for_timeout(1800 + attempt * 1200)
                    try:
                        await page.wait_for_selector('div.tb-step, p.tb-status, p.tb-status-detail', timeout=15000)
                    except PlaywrightTimeoutError:
                        await page.wait_for_timeout(1200)
                    html = await page.content()
                    items = extract_usps_tracking_items_from_html(html)
                    if items:
                        return {'平台': 'USPS', '查询值': normalized, '物流轨迹': items, '最新轨迹': items[0]}
                    if is_usps_blocked_page_html(html):
                        logger.warning("USPS 查询: 检测到风控中间页 tracking_no=%s url=%s", normalized, query_url)
                        break

            title, current_url, html_path = await _dump_debug_artifacts()
            return {'平台': 'USPS', '查询值': normalized, '物流轨迹': [], '最新轨迹': {}, '错误': 'USPS 官网触发风控拦截或页面未返回轨迹信息', '当前页面标题': title, '当前URL': current_url, '调试HTML': html_path}
        finally:
            await cleanup_cdp_query_page(page, context, owns_context)
            end_local_cdp_session(cdp_process)
