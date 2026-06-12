import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query


class FedexQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_fedex_tracking_accepts_cookie_and_extracts_active_status(self):
        tracking_no = "381685128780"

        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        tracking_input.first = tracking_input
        track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        track_button.first = track_button
        cookie_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        cookie_button.first = cookie_button
        modal_close_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        modal_close_button.first = modal_close_button
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
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
                    tracking_input
                    if selector == 'input[type="text"][placeholder="Tracking number"]'
                    else track_button
                    if selector == "button.fxp-c-form__button.fxp-c-button--primary.fxp-c-button--primary-condensed"
                    else cookie_button
                    if selector == "#accept"
                    else modal_close_button
                    if selector == 'a.fxg-u-modal__close.js-modal-close[title="close"]'
                    else progress_container
                    if selector == "div.shipment-status-progress-container"
                    else active_step
                    if selector == "div.shipment-status-progress-step.active"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
        )
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
        browser = SimpleNamespace(contexts=[], new_context=mock.AsyncMock(return_value=fresh_context))
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
            mock.patch.dict(sys.modules, {"playwright": fake_playwright, "playwright.async_api": fake_playwright_async_api}),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "_type_like_human", new=mock.AsyncMock()) as type_like_human_mock,
        ):
            result = await logistics_query.query_fedex_tracking(tracking_no)

        self.assertEqual(result["平台"], "FEDEX")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertEqual(result["最新轨迹"]["内容"], "Departed FedEx location")
        self.assertEqual(result["最新轨迹"]["地点"], "CYPRESS, TX")
        self.assertEqual(result["最新轨迹"]["时间"], "6/3/26 9:03 AM")
        fresh_page.goto.assert_awaited_once_with("https://www.fedex.com/en-us/home.html", wait_until="domcontentloaded", timeout=60000)
        type_like_human_mock.assert_awaited_once_with(
            fresh_page,
            'input[type="text"][placeholder="Tracking number"]',
            tracking_no,
            delay_range=(90, 180),
        )
        track_button.click.assert_awaited_once()
        cookie_button.click.assert_awaited_once()
        modal_close_button.click.assert_awaited_once()
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_fedex_tracking_returns_error_when_home_input_missing(self):
        tracking_no = "381685128780"

        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=TimeoutError("input missing")),
            first=None,
        )
        tracking_input.first = tracking_input
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        hidden_locator.first = hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Home"),
            content=mock.AsyncMock(return_value="<html><body>modal</body></html>"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    tracking_input
                    if selector == 'input[type="text"][placeholder="Tracking number"]'
                    else hidden_locator
                )
            ),
        )
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
        browser = SimpleNamespace(contexts=[], new_context=mock.AsyncMock(return_value=fresh_context))
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
            mock.patch.dict(sys.modules, {"playwright": fake_playwright, "playwright.async_api": fake_playwright_async_api}),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
        ):
            result = await logistics_query.query_fedex_tracking(tracking_no)

        self.assertEqual(result["平台"], "FEDEX")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertIn("首页未出现跟踪号输入框", result["错误"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(result["最新轨迹"], {})
        self.assertGreaterEqual(tracking_input.wait_for.await_count, 2)
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_fedex_tracking_returns_error_when_goto_connection_closed(self):
        tracking_no = "381685128780"

        fresh_page = SimpleNamespace(
            url="about:blank",
            goto=mock.AsyncMock(side_effect=Exception("Page.goto: net::ERR_CONNECTION_CLOSED at https://www.fedex.com/en-us/home.html")),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value=""),
            content=mock.AsyncMock(return_value="<html></html>"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace())),
        )
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
        browser = SimpleNamespace(contexts=[], new_context=mock.AsyncMock(return_value=fresh_context))
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
            mock.patch.dict(sys.modules, {"playwright": fake_playwright, "playwright.async_api": fake_playwright_async_api}),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
        ):
            result = await logistics_query.query_fedex_tracking(tracking_no)

        self.assertEqual(result["平台"], "FEDEX")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertIn("连接失败", result["错误"])
        self.assertIn("ERR_CONNECTION_CLOSED", result["错误"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(result["最新轨迹"], {})
        self.assertEqual(fresh_page.goto.await_count, 2)
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_fedex_tracking_returns_error_when_redirected_to_system_error_page(self):
        tracking_no = "381685128780"

        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        tracking_input.first = tracking_input
        track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        track_button.first = track_button
        cookie_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        cookie_button.first = cookie_button
        progress_container = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=TimeoutError("progress missing")),
            first=None,
        )
        progress_container.first = progress_container

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/fedextrack/system-error?trknbr=381685128780",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Error"),
            content=mock.AsyncMock(return_value="<html><body>system error</body></html>"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    tracking_input
                    if selector == 'input[type="text"][placeholder="Tracking number"]'
                    else track_button
                    if selector == "button.fxp-c-form__button.fxp-c-button--primary.fxp-c-button--primary-condensed"
                    else cookie_button
                    if selector == "#accept"
                    else progress_container
                    if selector == "div.shipment-status-progress-container"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
        )
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=fresh_page), close=mock.AsyncMock())
        browser = SimpleNamespace(contexts=[], new_context=mock.AsyncMock(return_value=fresh_context))
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
            mock.patch.dict(sys.modules, {"playwright": fake_playwright, "playwright.async_api": fake_playwright_async_api}),
            mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None),
            mock.patch.object(logistics_query, "end_local_cdp_session"),
            mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"),
            mock.patch.object(logistics_query, "_type_like_human", new=mock.AsyncMock()),
        ):
            result = await logistics_query.query_fedex_tracking(tracking_no)

        self.assertEqual(result["平台"], "FEDEX")
        self.assertEqual(result["查询值"], tracking_no)
        self.assertIn("系统错误页", result["错误"])
        self.assertIn("system-error", result["当前URL"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(result["最新轨迹"], {})
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
