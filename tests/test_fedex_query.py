import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query


class FedexQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_fedex_tracking_reuses_existing_cdp_context(self):
        tracking_no = "382046572780"

        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        def _locator(selector: str):
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
        )
        existing_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=page), close=mock.AsyncMock())
        fresh_context = SimpleNamespace(pages=[], new_page=mock.AsyncMock(return_value=page), close=mock.AsyncMock())
        browser = SimpleNamespace(contexts=[existing_context], new_context=mock.AsyncMock(return_value=fresh_context))
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
        existing_context.new_page.assert_awaited_once()
        browser.new_context.assert_not_awaited()
        existing_context.close.assert_not_awaited()

    async def test_query_fedex_tracking_uses_direct_url_first(self):
        tracking_no = "382046572780"

        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        def _locator(selector: str):
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/wtrk/track/?trknbr=382046572780",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        fresh_page.goto.assert_awaited_once_with(
            "https://www.fedex.com/wtrk/track/?trknbr=382046572780",
            wait_until="domcontentloaded",
            timeout=60000,
        )

    async def test_query_fedex_tracking_force_hides_cookie_banner_when_accept_button_remains_visible(self):
        tracking_no = "382046572780"

        accept_cookies_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        accept_cookies_button.first = accept_cookies_button
        visible_tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        visible_tracking_input.first = visible_tracking_input
        visible_track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        visible_track_button.first = visible_track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        def _locator(selector: str):
            if selector == '#accept':
                return accept_cookies_button
            if selector == '#trackingModuleTrackingNum:visible':
                return visible_tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return visible_track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertGreaterEqual(accept_cookies_button.click.await_count, 1)
        fresh_page.evaluate.assert_awaited()

    async def test_query_fedex_tracking_removes_still_open_geo_dialog_before_typing(self):
        tracking_no = "382046572780"

        geo_title = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            first=None,
        )
        geo_title.first = geo_title
        geo_us_english_link = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        geo_us_english_link.first = geo_us_english_link
        visible_tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        visible_tracking_input.first = visible_tracking_input
        visible_track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        visible_track_button.first = visible_track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        def _locator(selector: str):
            if selector == '.fxg-u-modal__content .fxg-geo-locator__title':
                return geo_title
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-analytics="link|GEO-EN-US"]':
                return geo_us_english_link
            if selector == '#trackingModuleTrackingNum:visible':
                return visible_tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return visible_track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        fresh_page.evaluate.assert_awaited()

    async def test_query_fedex_tracking_prefers_visible_tracking_input_when_hidden_duplicate_exists(self):
        tracking_no = "382046572780"

        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        visible_tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        visible_tracking_input.first = visible_tracking_input
        visible_track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        visible_track_button.first = visible_track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == 'input[name="trackingNumber"]':
                return hidden_locator
            if selector == 'input[name="trackingNumber"]:visible':
                return visible_tracking_input
            if selector == '#trackingModuleTrackingNum':
                return hidden_locator
            if selector == '#trackingModuleTrackingNum:visible':
                return visible_tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary':
                return hidden_locator
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return visible_track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        type_like_human_mock.assert_awaited_once_with(
            fresh_page,
            '#trackingModuleTrackingNum:visible',
            tracking_no,
            delay_range=(90, 180),
        )
        visible_track_button.click.assert_awaited_once()

    async def test_query_fedex_tracking_clicks_geo_english_and_accepts_accept_all_cookies_button(self):
        tracking_no = "382046572780"

        geo_title = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            first=None,
        )
        geo_title.first = geo_title
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        geo_us_english_link = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        geo_us_english_link.first = geo_us_english_link

        accept_cookies_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        accept_cookies_button.first = accept_cookies_button

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
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="AT LOCAL FACILITY\nAt local facility\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["At local facility", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '.fxg-u-modal__content .fxg-geo-locator__title':
                return geo_title
            if selector == 'a.fxg-u-modal__close.js-modal-close[title="close"]':
                return hidden_locator
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[href="https://www.fedex.com/en-us/home.html"]':
                return geo_us_english_link
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-analytics="link|GEO-EN-US"]':
                return geo_us_english_link
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-country-code="us"][aria-label="English"]':
                return geo_us_english_link
            if selector == '#accept':
                return accept_cookies_button
            if selector == 'input[type="text"][placeholder="Tracking number"]':
                return hidden_locator
            if selector == '#trackingModuleTrackingNum':
                return tracking_input
            if selector == "button.cc-aem-c-button.cc-aem-c-button--primary":
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertGreaterEqual(geo_us_english_link.click.await_count, 1)
        self.assertGreaterEqual(accept_cookies_button.click.await_count, 1)

    async def test_query_fedex_tracking_prefers_geo_english_over_close_button_when_both_are_visible(self):
        tracking_no = "382046572780"

        geo_title = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            first=None,
        )
        geo_title.first = geo_title
        geo_close_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        geo_close_button.first = geo_close_button
        geo_us_english_link = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        geo_us_english_link.first = geo_us_english_link
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        tracking_input.first = tracking_input
        track_button = SimpleNamespace(wait_for=mock.AsyncMock(), click=mock.AsyncMock(), first=None)
        track_button.first = track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="AT LOCAL FACILITY\nAt local facility\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["At local facility", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '.fxg-u-modal__content .fxg-geo-locator__title':
                return geo_title
            if selector == 'a.fxg-u-modal__close.js-modal-close[title="close"]':
                return geo_close_button
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[href="https://www.fedex.com/en-us/home.html"]':
                return geo_us_english_link
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-analytics="link|GEO-EN-US"]':
                return geo_us_english_link
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-country-code="us"][aria-label="English"]':
                return geo_us_english_link
            if selector == '#trackingModuleTrackingNum':
                return tracking_input
            if selector == "button.cc-aem-c-button.cc-aem-c-button--primary":
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertGreaterEqual(geo_us_english_link.click.await_count, 1)
        geo_close_button.click.assert_not_awaited()

    async def test_query_fedex_tracking_navigates_via_plain_en_us_link_when_geo_locator_uses_dropdown_markup(self):
        tracking_no = "382046572780"

        geo_title = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            first=None,
        )
        geo_title.first = geo_title
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            get_attribute=mock.AsyncMock(return_value=None),
            first=None,
        )
        hidden_locator.first = hidden_locator
        plain_english_link = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            get_attribute=mock.AsyncMock(return_value="https://www.fedex.com/en-us/home.html"),
            first=None,
        )
        plain_english_link.first = plain_english_link
        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        tracking_input.first = tracking_input
        track_button = SimpleNamespace(wait_for=mock.AsyncMock(), click=mock.AsyncMock(), first=None)
        track_button.first = track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="AT LOCAL FACILITY\nAt local facility\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["At local facility", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '.fxg-u-modal__content .fxg-geo-locator__title':
                return geo_title
            if selector == '.fxg-u-modal__content a[href="https://www.fedex.com/en-us/home.html"]':
                return plain_english_link
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[href="https://www.fedex.com/en-us/home.html"]':
                return hidden_locator
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-analytics="link|GEO-EN-US"]':
                return hidden_locator
            if selector == '.fxg-u-modal__content a.fxg-geo-locator__country-url[data-country-code="us"][aria-label="English"]':
                return hidden_locator
            if selector == '#trackingModuleTrackingNum':
                return tracking_input
            if selector == "button.cc-aem-c-button.cc-aem-c-button--primary":
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        plain_english_link.click.assert_not_awaited()
        self.assertGreaterEqual(plain_english_link.get_attribute.await_count, 1)
        self.assertGreaterEqual(fresh_page.goto.await_count, 2)

    async def test_query_fedex_tracking_ignores_plain_en_us_link_outside_geo_modal(self):
        tracking_no = "382046572780"

        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            get_attribute=mock.AsyncMock(return_value=None),
            first=None,
        )
        hidden_locator.first = hidden_locator
        page_level_english_link = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            get_attribute=mock.AsyncMock(return_value="https://www.fedex.com/en-us/home.html"),
            first=None,
        )
        page_level_english_link.first = page_level_english_link
        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            first=None,
        )
        tracking_input.first = tracking_input
        track_button = SimpleNamespace(wait_for=mock.AsyncMock(), click=mock.AsyncMock(), first=None)
        track_button.first = track_button
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="AT LOCAL FACILITY\nAt local facility\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["At local facility", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '.fxg-u-modal__content .fxg-geo-locator__title':
                return hidden_locator
            if selector == '.fxg-u-modal__content a[href="https://www.fedex.com/en-us/home.html"]':
                return hidden_locator
            if selector == 'a[href="https://www.fedex.com/en-us/home.html"]':
                return page_level_english_link
            if selector == '#trackingModuleTrackingNum':
                return tracking_input
            if selector == "button.cc-aem-c-button.cc-aem-c-button--primary":
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        page_level_english_link.get_attribute.assert_not_awaited()
        self.assertEqual(fresh_page.goto.await_count, 2)
        fresh_page.goto.assert_any_await("https://www.fedex.com/en-us/home.html", wait_until="domcontentloaded", timeout=60000)

    async def test_query_fedex_tracking_supports_tracking_id_input_and_new_cookie_banner(self):
        tracking_no = "382046572780"

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
        accept_cookies_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        accept_cookies_button.first = accept_cookies_button
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        hidden_locator.first = hidden_locator
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
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

        def _locator(selector: str):
            if selector == 'input[type="text"][placeholder="Tracking number"]:visible':
                return hidden_locator
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == 'input[type="text"][placeholder="Tracking ID"]:visible':
                return tracking_input
            if selector == "button.cc-aem-c-button.cc-aem-c-button--primary:visible":
                return track_button
            if selector == "button.uc-accept-button":
                return accept_cookies_button
            if selector == "#accept":
                return hidden_locator
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertEqual(result["最新轨迹"]["内容"], "On the way")
        self.assertEqual(result["最新轨迹"]["地点"], "MEMPHIS, TN")
        self.assertEqual(result["最新轨迹"]["时间"], "6/23/26 8:12 AM")
        type_like_human_mock.assert_awaited_once_with(
            fresh_page,
            '#trackingModuleTrackingNum:visible',
            tracking_no,
            delay_range=(90, 180),
        )
        self.assertGreaterEqual(accept_cookies_button.click.await_count, 1)
        track_button.click.assert_awaited_once()

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
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    tracking_input
                    if selector == 'input[type="text"][placeholder="Tracking number"]:visible'
                    else track_button
                    if selector == "button.fxp-c-form__button.fxp-c-button--primary.fxp-c-button--primary-condensed:visible"
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
        self.assertEqual(fresh_page.goto.await_count, 2)
        fresh_page.goto.assert_any_await("https://www.fedex.com/en-us/home.html", wait_until="domcontentloaded", timeout=60000)
        type_like_human_mock.assert_awaited_once_with(
            fresh_page,
            'input[type="text"][placeholder="Tracking number"]:visible',
            tracking_no,
            delay_range=(90, 180),
        )
        track_button.click.assert_awaited_once()
        self.assertGreaterEqual(cookie_button.click.await_count, 1)
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
                    if selector == 'input[type="text"][placeholder="Tracking number"]:visible'
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
        self.assertEqual(fresh_page.goto.await_count, 4)
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_fedex_tracking_force_clicks_cookie_button_when_normal_click_is_blocked(self):
        tracking_no = "382046572780"

        cookie_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(side_effect=TimeoutError("cookie blocked")),
            first=None,
        )
        cookie_button.first = cookie_button
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
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator

        def _locator(selector: str):
            if selector == '#accept':
                return cookie_button
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="Track & Ship Online or Find Nearby Locations | FedEx"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(return_value=True),
            locator=mock.Mock(side_effect=_locator),
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
        cookie_button.click.assert_awaited()
        fresh_page.evaluate.assert_awaited()

    async def test_type_like_human_force_clicks_when_cookie_overlay_intercepts_pointer_events(self):
        locator = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            press=mock.AsyncMock(),
            fill=mock.AsyncMock(),
            type=mock.AsyncMock(),
        )
        click_attempts: list[dict] = []

        async def _click(**kwargs):
            click_attempts.append(dict(kwargs))
            if not kwargs.get("force"):
                raise TimeoutError("usercentrics overlay intercepts pointer events")

        locator.click = mock.AsyncMock(side_effect=_click)

        page = SimpleNamespace(
            locator=mock.Mock(return_value=locator),
            wait_for_timeout=mock.AsyncMock(),
        )

        await logistics_query._type_like_human(page, "#trackingModuleTrackingNum:visible", "382046572780")

        self.assertEqual(click_attempts, [{}, {"force": True}])
        locator.type.assert_awaited_once()

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
                    if selector == 'input[type="text"][placeholder="Tracking number"]:visible'
                    else track_button
                    if selector == "button.fxp-c-form__button.fxp-c-button--primary.fxp-c-button--primary-condensed:visible"
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
        fresh_page.goto.assert_any_await(
            "https://www.fedex.com/wtrk/track/?trknbr=381685128780",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self.assertEqual(fresh_page.goto.await_count, 1)
        fresh_page.close.assert_awaited_once()
        fresh_context.close.assert_awaited_once()

    async def test_query_fedex_tracking_returns_not_found_when_result_page_shows_tracking_number_missing_message(self):
        tracking_no = "382046572780"

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
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        progress_container = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=TimeoutError("progress missing")),
            first=None,
        )
        progress_container.first = progress_container
        body_locator = SimpleNamespace(
            inner_text=mock.AsyncMock(return_value="FedEx Tracking\nWe can't find that tracking number. Please check with the shipper to make sure it's the correct one."),
            first=None,
        )
        body_locator.first = body_locator

        def _locator(selector: str):
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "body":
                return body_locator
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/wtrk/track/?action=track&tracknumbers=382046572780&locale=en_US&cntry_code=us",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            content=mock.AsyncMock(return_value="<html></html>"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertIn("未查到", result["错误"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(result["最新轨迹"], {})

    async def test_query_fedex_tracking_returns_error_when_result_progress_never_appears(self):
        tracking_no = "382046572780"

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
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        progress_container = SimpleNamespace(
            wait_for=mock.AsyncMock(side_effect=TimeoutError("progress missing")),
            first=None,
        )
        progress_container.first = progress_container
        body_locator = SimpleNamespace(
            inner_text=mock.AsyncMock(return_value="FedEx Tracking\nTrack Another Shipment\nLocal Scan Time"),
            first=None,
        )
        body_locator.first = body_locator

        def _locator(selector: str):
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "body":
                return body_locator
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/wtrk/track/?action=track&tracknumbers=382046572780&locale=en_US&cntry_code=us",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            content=mock.AsyncMock(return_value="<html><body>FedEx Tracking</body></html>"),
            screenshot=mock.AsyncMock(),
            close=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertIn("结果页未返回轨迹", result["错误"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(result["最新轨迹"], {})

    async def test_query_fedex_tracking_presses_enter_when_track_button_is_not_visible(self):
        tracking_no = "382046572780"

        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            press=mock.AsyncMock(),
            first=None,
        )
        tracking_input.first = tracking_input
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        tracking_input.press.assert_awaited_once_with('Enter')

    async def test_query_fedex_tracking_force_clicks_track_button_when_cookie_overlay_intercepts_pointer_events(self):
        tracking_no = "382046572780"

        tracking_input = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            input_value=mock.AsyncMock(return_value=tracking_no),
            press=mock.AsyncMock(),
            first=None,
        )
        tracking_input.first = tracking_input
        click_attempts: list[dict] = []

        async def _click_track_button(**kwargs):
            click_attempts.append(dict(kwargs))
            if not kwargs.get("force"):
                raise TimeoutError("usercentrics overlay intercepts pointer events")

        track_button = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            click=mock.AsyncMock(side_effect=_click_track_button),
            first=None,
        )
        track_button.first = track_button
        hidden_locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        hidden_locator.first = hidden_locator
        progress_container = SimpleNamespace(wait_for=mock.AsyncMock(), first=None)
        progress_container.first = progress_container
        active_step = SimpleNamespace(
            wait_for=mock.AsyncMock(),
            inner_text=mock.AsyncMock(return_value="IN TRANSIT\nOn the way\nMEMPHIS, TN\n6/23/26 8:12 AM"),
            locator=mock.Mock(
                return_value=SimpleNamespace(
                    count=mock.AsyncMock(return_value=3),
                    nth=lambda index: SimpleNamespace(
                        inner_text=mock.AsyncMock(
                            return_value=["On the way", "MEMPHIS, TN", "6/23/26 8:12 AM"][index]
                        )
                    ),
                )
            ),
            first=None,
        )
        active_step.first = active_step

        def _locator(selector: str):
            if selector == '#trackingModuleTrackingNum:visible':
                return tracking_input
            if selector == 'button.cc-aem-c-button.cc-aem-c-button--primary:visible':
                return track_button
            if selector == "div.shipment-status-progress-container":
                return progress_container
            if selector == "div.shipment-status-progress-step.active":
                return active_step
            return hidden_locator

        fresh_page = SimpleNamespace(
            url="https://www.fedex.com/en-us/home.html",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="FedEx Tracking"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(side_effect=_locator),
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
        self.assertEqual(click_attempts, [{"timeout": 8000}, {"timeout": 8000, "force": True}])
        tracking_input.press.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
