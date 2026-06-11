import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query


class FedexQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_fedex_tracking_accepts_cookie_and_extracts_active_status(self):
        tracking_no = "381685128780"

        cookie_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        cookie_button.first = cookie_button
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            inner_text=mock.AsyncMock(return_value="ON THE WAY\nDeparted FedEx location\nCYPRESS, TX\n6/3/26 9:03 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["Departed FedEx location", "CYPRESS, TX", "6/3/26 9:03 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        progress_container = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            first=None,
        )
        progress_container.first = progress_container

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/wtrk/track/?trknbr=381685128780",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    cookie_button
                    if selector == "#accept"
                    else progress_container
                    if selector == "div.shipment-status-progress-container"
                    else active_step
                    if selector == "div.shipment-status-progress-step.active"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
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
        ):
            result = await logistics_query.query_fedex_tracking(tracking_no)

        self.assertEqual(result["平台"], "FEDEX")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertEqual(result["最新轨迹"]["内容"], "Departed FedEx location")
        self.assertEqual(result["最新轨迹"]["地点"], "CYPRESS, TX")
        self.assertEqual(result["最新轨迹"]["时间"], "6/3/26 9:03 AM")
        cookie_button.click.assert_awaited_once()
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
