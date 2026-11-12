from types import SimpleNamespace
import sys
import types
import unittest
from unittest import mock

import logistics_query
from logistics_query import (
    extract_uniuni_tracking_items_from_html,
)


class UniUniQueryHelperTests(unittest.TestCase):
    def test_extract_uniuni_tracking_items_reads_current_tracking_history_markup(self):
        html = """
        <div class="mt-10">
          <div class="text-xl font-semibold mb-6 text-uni-black">Tracking History</div>
          <div class="grid grid-cols-[120px_40px_1fr] gap-5 mob:grid-cols-[76px_28px_1fr] mob:gap-2 py-4">
            <div class="text-[14px] mob:text-[11px] text-uni-muted leading-relaxed text-right">
              <span class="block">2026-06-21</span>
              <span class="block">07:25:25</span>
            </div>
            <div class="flex justify-center relative"><svg></svg></div>
            <div class="h-full flex flex-col justify-between">
              <div class="text-[16px] mob:text-sm text-uni-black leading-[1.45] font-semibold">Order received</div>
              <div class="text-xs text-uni-muted mt-1.5">UNI DATA CENTER</div>
            </div>
          </div>
        </div>
        """

        self.assertEqual(
            extract_uniuni_tracking_items_from_html(html),
            [{"时间": "2026-06-21 07:25:25", "内容": "Order received", "地点": "UNI DATA CENTER"}],
        )


class UniUniQueryExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_uniuni_tracking_reads_current_tracking_history_markup(self):
        tracking_no = "UUS65K2370395621872"
        html = f"""
        <html>
          <body>
            <span>{tracking_no}</span>
            <div class="mt-10">
              <div class="text-xl font-semibold mb-6 text-uni-black">Tracking History</div>
              <div class="grid grid-cols-[120px_40px_1fr] gap-5 mob:grid-cols-[76px_28px_1fr] mob:gap-2 py-4">
                <div class="text-[14px] mob:text-[11px] text-uni-muted leading-relaxed text-right">
                  <span class="block">2026-06-21</span>
                  <span class="block">07:25:25</span>
                </div>
                <div class="flex justify-center relative"><svg></svg></div>
                <div class="h-full flex flex-col justify-between">
                  <div class="text-[16px] mob:text-sm text-uni-black leading-[1.45] font-semibold">Order received</div>
                  <div class="text-xs text-uni-muted mt-1.5">UNI DATA CENTER</div>
                </div>
              </div>
            </div>
          </body>
        </html>
        """

        class FakeLocator:
            def __init__(self, count_values=None):
                self._count_values = list(count_values or [1])
                self.wait_for = mock.AsyncMock()
                self.click = mock.AsyncMock()

            @property
            def first(self):
                return self

            async def count(self):
                if len(self._count_values) > 1:
                    return self._count_values.pop(0)
                return self._count_values[0]

        tracking_locator = FakeLocator([1])

        page = SimpleNamespace(
            url=f"https://www.uniuni.com//tracking#tracking-detail?no={tracking_no}",
            goto=mock.AsyncMock(),
            reload=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            content=mock.AsyncMock(return_value=html),
            bring_to_front=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="UNIUNI"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            expect_download=mock.Mock(),
        )

        def locator_side_effect(selector):
            if selector == f'div:has-text("{tracking_no}")':
                return tracking_locator
            return FakeLocator([0])

        page.locator = mock.Mock(side_effect=locator_side_effect)
        page.get_by_text = mock.Mock(return_value=FakeLocator([0]))

        context = SimpleNamespace(
            pages=[],
            new_page=mock.AsyncMock(return_value=page),
            close=mock.AsyncMock(),
        )
        browser = SimpleNamespace(
            contexts=[],
            new_context=mock.AsyncMock(return_value=context),
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
        ):
            result = await logistics_query.query_uniuni_tracking(tracking_no)

        self.assertEqual(result["平台"], "UNIUNI")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertEqual(len(result["物流轨迹"]), 1)
        self.assertEqual(result["最新轨迹"]["时间"], "2026-06-21 07:25:25")
        self.assertEqual(result["最新轨迹"]["内容"], "Order received")
        self.assertEqual(result["最新轨迹"]["地点"], "UNI DATA CENTER")
        page.expect_download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
