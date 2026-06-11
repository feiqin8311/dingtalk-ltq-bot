import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query
from logistics_query import build_usps_query_urls, extract_usps_tracking_items_from_html, is_usps_blocked_page_html


USPS_HTML = """
<div>
  <div class="tb-step current-step">
    <span class="bar-fill-animation"></span>
    <p class="tb-status">USPS 等待物品</p>
    <p class="tb-status-detail">寄件标签已创建</p>
    <p class="tb-location">HOUSTON, TX 77041 </p>
    <p class="tb-date">2026 年 06 月 08 日 3:40 下午</p>
  </div>
  <div class="tb-step"><div>
    <p class="tb-status-detail">发送给 USPS 的寄件前信息 </p>
    <p class="tb-location"></p>
    <p class="tb-date">2026 年 06 月 08 日</p>
  </div></div>
</div>
"""

USPS_BLOCKED_HTML = """
<!DOCTYPE html><html><head>
  <title></title>
</head>
<body>
  <script>
    var vendor = "akamai";
    var note = "bot detection";
  </script>
</body>
</html>
"""


class UspsQueryParsingTests(unittest.TestCase):
    def test_build_usps_query_urls_uses_tools_tracking_page(self):
        urls = build_usps_query_urls("9214490411372848389407")

        self.assertEqual(
            urls,
            [
                "https://tools.usps.com/tracking/9214490411372848389407",
            ],
        )

    def test_detects_usps_blocked_blank_page(self):
        self.assertTrue(is_usps_blocked_page_html(USPS_BLOCKED_HTML))

    def test_extract_usps_tracking_items_reads_current_and_history_steps(self):
        items = extract_usps_tracking_items_from_html(USPS_HTML)

        self.assertEqual(
            items,
            [
                {
                    "时间": "2026 年 06 月 08 日 3:40 下午",
                    "内容": "USPS 等待物品 - 寄件标签已创建",
                    "地点": "HOUSTON, TX 77041",
                },
                {
                    "时间": "2026 年 06 月 08 日",
                    "内容": "发送给 USPS 的寄件前信息",
                    "地点": "",
                },
            ],
        )


class UspsQueryExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_usps_tracking_waits_for_akamai_challenge_then_recovers(self):
        tracking_no = "9214490411372848389407"
        parsed_items = [{"时间": "2026-06-08", "内容": "Delivered", "地点": "TX"}]

        search_input = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=[TimeoutError("blocked"), None]),
            input_value=mock.AsyncMock(return_value=tracking_no),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_input.first = search_input
        search_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_button.first = search_button
        tracking_number = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value=tracking_no),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        tracking_number.first = tracking_number

        fresh_page = SimpleNamespace(
            url="https://tools.usps.com/tracking/",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_selector=mock.AsyncMock(),
            wait_for_url=mock.AsyncMock(),
            content=mock.AsyncMock(side_effect=[USPS_BLOCKED_HTML, USPS_HTML]),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value=""),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    search_input
                    if selector == "#tracking-input"
                    else search_button
                    if selector == "#trackBtn"
                    else tracking_number
                )
            ),
        )
        fresh_context = SimpleNamespace(
            pages=[],
            new_page=mock.AsyncMock(return_value=fresh_page),
            close=mock.AsyncMock(),
        )
        browser = SimpleNamespace(
            contexts=[],
            new_context=mock.AsyncMock(return_value=fresh_context),
        )
        chromium = SimpleNamespace(connect_over_cdp=mock.AsyncMock(return_value=browser))

        class _FakePlaywright:
            def __init__(self, chromium):
                self.chromium = chromium

        class _FakeAsyncPlaywright:
            async def __aenter__(self):
                return _FakePlaywright(chromium)

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_playwright_async_api = types.ModuleType("playwright.async_api")
        fake_playwright_async_api.async_playwright = lambda: _FakeAsyncPlaywright()
        fake_playwright_async_api.TimeoutError = TimeoutError

        fake_playwright = types.ModuleType("playwright")
        fake_playwright.async_api = fake_playwright_async_api

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "playwright": fake_playwright,
                    "playwright.async_api": fake_playwright_async_api,
                },
            ),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "apply_usps_browser_stealth", new=mock.AsyncMock()),
            mock.patch.object(logistics_query, "extract_usps_tracking_items_from_html", return_value=parsed_items),
            mock.patch.object(logistics_query, "_type_like_human", new=mock.AsyncMock()),
        ):
            result = await logistics_query.query_usps_tracking(tracking_no)

        self.assertEqual(result["平台"], "USPS")
        self.assertEqual(result["物流轨迹"], parsed_items)
        self.assertGreaterEqual(search_input.wait_for.await_count, 2)

    async def test_query_usps_tracking_uses_new_page_from_new_context(self):
        tracking_no = "9214490411372848389407"
        parsed_items = [{"时间": "2026-06-08", "内容": "Delivered", "地点": "TX"}]
        home_url = "https://tools.usps.com/tracking/"

        search_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            fill=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_input.first = search_input
        search_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_button.first = search_button
        tracking_number = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value=tracking_no),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        tracking_number.first = tracking_number

        stale_page = SimpleNamespace(
            url="",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_selector=mock.AsyncMock(),
            wait_for_url=mock.AsyncMock(),
            content=mock.AsyncMock(return_value=USPS_HTML),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value=""),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
        )
        stale_context = SimpleNamespace(
            pages=[stale_page],
            close=mock.AsyncMock(),
        )

        fresh_page = SimpleNamespace(
            url="about:blank",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_selector=mock.AsyncMock(),
            wait_for_url=mock.AsyncMock(),
            content=mock.AsyncMock(return_value=USPS_HTML),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value=""),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    search_input
                    if selector == "#tracking-input"
                    else search_button
                    if selector == "#trackBtn"
                    else tracking_number
                )
            ),
        )
        fresh_context = SimpleNamespace(
            pages=[],
            new_page=mock.AsyncMock(return_value=fresh_page),
            close=mock.AsyncMock(),
        )
        browser = SimpleNamespace(
            contexts=[stale_context, fresh_context],
            new_context=mock.AsyncMock(return_value=fresh_context),
        )
        chromium = SimpleNamespace(connect_over_cdp=mock.AsyncMock(return_value=browser))

        class _FakePlaywright:
            def __init__(self, chromium):
                self.chromium = chromium

        class _FakeAsyncPlaywright:
            async def __aenter__(self):
                return _FakePlaywright(chromium)

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_playwright_async_api = types.ModuleType("playwright.async_api")
        fake_playwright_async_api.async_playwright = lambda: _FakeAsyncPlaywright()
        fake_playwright_async_api.TimeoutError = TimeoutError

        fake_playwright = types.ModuleType("playwright")
        fake_playwright.async_api = fake_playwright_async_api

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "playwright": fake_playwright,
                    "playwright.async_api": fake_playwright_async_api,
                },
            ),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "apply_usps_browser_stealth", new=mock.AsyncMock()),
            mock.patch.object(logistics_query, "extract_usps_tracking_items_from_html", return_value=parsed_items),
            mock.patch.object(logistics_query, "_type_like_human", new=mock.AsyncMock()) as type_like_human_mock,
        ):
            result = await logistics_query.query_usps_tracking(tracking_no)

        self.assertEqual(result["平台"], "USPS")
        self.assertEqual(result["物流轨迹"], parsed_items)
        fresh_context.new_page.assert_awaited_once()
        fresh_page.goto.assert_awaited_once_with(home_url, wait_until="domcontentloaded", timeout=60000)
        search_input.wait_for.assert_awaited_once()
        type_like_human_mock.assert_awaited_once_with(fresh_page, "#tracking-input", tracking_no, delay_range=(90, 180))
        search_button.wait_for.assert_awaited_once()
        search_button.click.assert_awaited_once()
        tracking_number.wait_for.assert_awaited_once()
        tracking_number.inner_text.assert_awaited_once()
        fresh_page.wait_for_url.assert_not_awaited()
        stale_page.goto.assert_not_awaited()
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()
        stale_context.close.assert_not_awaited()

    async def test_query_usps_tracking_returns_submit_error_when_tools_search_fails(self):
        tracking_no = "9214490411372848389407"

        search_input = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=TimeoutError("missing input")),
            click=mock.AsyncMock(),
            fill=mock.AsyncMock(),
            first=None,
        )
        search_input.first = search_input

        fresh_page = SimpleNamespace(
            url="https://www.usps.com/",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_selector=mock.AsyncMock(),
            wait_for_url=mock.AsyncMock(),
            content=mock.AsyncMock(return_value="<html></html>"),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="USPS"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(return_value=search_input),
        )
        fresh_context = SimpleNamespace(
            pages=[],
            new_page=mock.AsyncMock(return_value=fresh_page),
            close=mock.AsyncMock(),
        )
        browser = SimpleNamespace(
            contexts=[],
            new_context=mock.AsyncMock(return_value=fresh_context),
        )
        chromium = SimpleNamespace(connect_over_cdp=mock.AsyncMock(return_value=browser))

        class _FakePlaywright:
            def __init__(self, chromium):
                self.chromium = chromium

        class _FakeAsyncPlaywright:
            async def __aenter__(self):
                return _FakePlaywright(chromium)

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_playwright_async_api = types.ModuleType("playwright.async_api")
        fake_playwright_async_api.async_playwright = lambda: _FakeAsyncPlaywright()
        fake_playwright_async_api.TimeoutError = TimeoutError

        fake_playwright = types.ModuleType("playwright")
        fake_playwright.async_api = fake_playwright_async_api

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "playwright": fake_playwright,
                    "playwright.async_api": fake_playwright_async_api,
                },
            ),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "apply_usps_browser_stealth", new=mock.AsyncMock()),
            mock.patch.object(logistics_query, "build_usps_debug_dir", return_value=mock.Mock(mkdir=mock.Mock(), __truediv__=lambda self, name: self)),
        ):
            result = await logistics_query.query_usps_tracking(tracking_no)

        self.assertEqual(result["平台"], "USPS")
        self.assertIn("USPS 查询提交失败", result["错误"])
        fresh_page.wait_for_selector.assert_not_awaited()
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_usps_tracking_returns_error_when_input_is_truncated(self):
        tracking_no = "9361289741064766954915"

        search_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            fill=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value="936128974106476695491"),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_input.first = search_input
        search_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            count=mock.AsyncMock(return_value=1),
            first=None,
        )
        search_button.first = search_button

        fresh_page = SimpleNamespace(
            url="https://tools.usps.com/tracking/",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_selector=mock.AsyncMock(),
            wait_for_url=mock.AsyncMock(),
            content=mock.AsyncMock(return_value="<html></html>"),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="USPS Tracking"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=lambda selector: search_input if selector == "#tracking-input" else search_button),
        )
        fresh_context = SimpleNamespace(
            pages=[],
            new_page=mock.AsyncMock(return_value=fresh_page),
            close=mock.AsyncMock(),
        )
        browser = SimpleNamespace(
            contexts=[],
            new_context=mock.AsyncMock(return_value=fresh_context),
        )
        chromium = SimpleNamespace(connect_over_cdp=mock.AsyncMock(return_value=browser))

        class _FakePlaywright:
            def __init__(self, chromium):
                self.chromium = chromium

        class _FakeAsyncPlaywright:
            async def __aenter__(self):
                return _FakePlaywright(chromium)

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_playwright_async_api = types.ModuleType("playwright.async_api")
        fake_playwright_async_api.async_playwright = lambda: _FakeAsyncPlaywright()
        fake_playwright_async_api.TimeoutError = TimeoutError

        fake_playwright = types.ModuleType("playwright")
        fake_playwright.async_api = fake_playwright_async_api

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "playwright": fake_playwright,
                    "playwright.async_api": fake_playwright_async_api,
                },
            ),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "apply_usps_browser_stealth", new=mock.AsyncMock()),
            mock.patch.object(logistics_query, "_type_like_human", new=mock.AsyncMock()),
            mock.patch.object(logistics_query, "build_usps_debug_dir", return_value=mock.Mock(mkdir=mock.Mock(), __truediv__=lambda self, name: self)),
        ):
            result = await logistics_query.query_usps_tracking(tracking_no)

        self.assertEqual(result["平台"], "USPS")
        self.assertIn("输入框内容被截断", result["错误"])
        search_button.click.assert_not_awaited()


class TrackingCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_cache = dict(logistics_query._TRACKING_QUERY_CACHE)
        logistics_query._TRACKING_QUERY_CACHE.clear()

    async def asyncTearDown(self):
        logistics_query._TRACKING_QUERY_CACHE.clear()
        logistics_query._TRACKING_QUERY_CACHE.update(self.original_cache)

    async def test_query_tracking_number_reuses_cached_success_result(self):
        expected = {
            "平台": "USPS",
            "查询值": "9214490411372848389407",
            "物流轨迹": [{"时间": "2026-06-08", "内容": "Delivered", "地点": "TX"}],
            "最新轨迹": {"时间": "2026-06-08", "内容": "Delivered", "地点": "TX"},
        }

        with mock.patch.object(logistics_query, "query_usps_tracking", new=mock.AsyncMock(return_value=expected)) as query_mock:
            first = await logistics_query.query_tracking_number("9214490411372848389407")
            second = await logistics_query.query_tracking_number("9214490411372848389407")

        self.assertEqual(first["物流轨迹"], expected["物流轨迹"])
        self.assertEqual(second["物流轨迹"], expected["物流轨迹"])
        query_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
