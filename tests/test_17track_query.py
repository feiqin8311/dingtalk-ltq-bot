import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query


TRACK_HTML = """
<div class="relative">
  <span class="yq-time">2026-06-11 14:20</span>
  <div>Delivered</div>
</div>
"""


class Track17QueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_17track_returns_not_found_error_without_waiting_for_timeout(self):
        tracking_no = "381685128780"
        not_found_html = """
        <div data-state="open">
          <div class="text-sm text-text-primary flex items-center gap-1">Not found</div>
          <p class="text-[var(--yq-red-600)] text-sm overflow-hidden line-clamp-2 px-2">
            The carrier has not updated the information or try switching carrier and then check again.
          </p>
        </div>
        """

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        timeline_root.first = timeline_root
        body_locator = SimpleNamespace(inner_text=mock.AsyncMock(return_value="Not found The carrier has not updated the information"))

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=381685128780",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            content=mock.AsyncMock(return_value=not_found_html),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
        )
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
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
        ):
            result = await logistics_query.query_17track(tracking_no)

        self.assertEqual(result["平台"], "17TRACK")
        self.assertIn("未查询到轨迹信息", result["错误"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertLess(fresh_page.wait_for_timeout.await_count, 10)

    async def test_query_17track_uses_isolated_context_and_closes_page(self):
        tracking_no = "872762992953"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/zh-cn#nums=872762992953",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=lambda selector: timeline_root if selector == "span.yq-time" else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
        )
        stale_page = SimpleNamespace(close=mock.AsyncMock())
        stale_context = SimpleNamespace(pages=[stale_page], close=mock.AsyncMock(), new_page=mock.AsyncMock(return_value=stale_page))
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
        browser = SimpleNamespace(
            contexts=[stale_context],
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
            mock.patch.object(logistics_query, "extract_17track_items_from_html", return_value=parsed_items),
        ):
            result = await logistics_query.query_17track(tracking_no)

        self.assertEqual(result["平台"], "17TRACK")
        self.assertEqual(result["物流轨迹"], parsed_items)
        browser.new_context.assert_awaited_once()
        fresh_context.new_page.assert_awaited_once()
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()
        stale_context.close.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
