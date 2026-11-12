import sys
import types
import unittest
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import logistics_query


TRACK_HTML = """
<div class="relative">
  <span class="yq-time">2026-06-11 14:20</span>
  <div>Delivered</div>
</div>
"""

NOT_FOUND_HTML = """
<div class="gap-4 flex items-center">
  <div class="flex items-center gap-2 w-[310px]">
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2">
        <span title="CRIN26061521261065" class="text-sm font-medium truncate">CRIN26061521261065</span>
      </div>
      <div class="text-sm text-text-primary flex items-center gap-1">Not found</div>
    </div>
  </div>
  <div title="If auto-detection is incorrect or unknown, please designate carrier manually." class="flex items-center gap-3">
    <p class="w-full">Select carrier</p>
  </div>
  <div class="flex items-center gap-2">
    <p class="text-[var(--yq-red-600)] text-sm overflow-hidden line-clamp-2 px-2">Please check if the tracking number is correct or try switching carrier and then check again.</p>
  </div>
</div>
"""


class Track17QueryTests(unittest.IsolatedAsyncioTestCase):
    def test_17track_result_wait_seconds_uses_bounded_environment_value(self):
        with mock.patch.dict(os.environ, {'TRACKING_17TRACK_MAX_WAIT_SECONDS': '3'}, clear=False):
            self.assertEqual(logistics_query.tracking_providers_service.get_17track_result_wait_seconds(), 10)
        with mock.patch.dict(os.environ, {'TRACKING_17TRACK_MAX_WAIT_SECONDS': '120'}, clear=False):
            self.assertEqual(logistics_query.tracking_providers_service.get_17track_result_wait_seconds(), 90)
        with mock.patch.dict(os.environ, {'TRACKING_17TRACK_MAX_WAIT_SECONDS': 'bad'}, clear=False):
            self.assertEqual(logistics_query.tracking_providers_service.get_17track_result_wait_seconds(), 25)

    def _build_search_input(self):
        locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            fill=mock.AsyncMock(),
            press_sequentially=mock.AsyncMock(),
            press=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            first=None,
        )
        locator.first = locator
        return locator

    def _build_search_trigger(self):
        locator = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            hover=mock.AsyncMock(),
            click=mock.AsyncMock(),
            first=None,
        )
        locator.first = locator
        return locator

    async def test_query_17track_does_not_use_homepage_track_button(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        search_trigger.click = mock.AsyncMock(side_effect=RuntimeError("click blocked"))

        fresh_page = SimpleNamespace(
            url="https://www.17track.net/en",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {
                        'div[title="Track the entered order number."]',
                        "div:has-text(\"TRACK\")",
                        "div[title*=\"Track\"]",
                    }
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
        fresh_page.goto.assert_awaited_once_with(
            f"https://t.17track.net/en#nums={tracking_no}",
            wait_until="domcontentloaded",
            timeout=25000,
        )
        search_trigger.click.assert_not_awaited()
        fresh_page.evaluate.assert_not_awaited()

    async def test_query_17track_opens_direct_tracking_page(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()

        fresh_page = SimpleNamespace(
            url="https://www.17track.net/en",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
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
            mock.patch.object(logistics_query, "extract_17track_items_from_html", return_value=parsed_items),
        ):
            result = await logistics_query.query_17track(tracking_no)

        self.assertEqual(result["平台"], "17TRACK")
        self.assertEqual(result["物流轨迹"], parsed_items)
        fresh_page.goto.assert_awaited_once_with(
            f"https://t.17track.net/en#nums={tracking_no}",
            wait_until="domcontentloaded",
            timeout=25000,
        )
        search_input.press_sequentially.assert_not_awaited()
        search_trigger.click.assert_not_awaited()

    async def test_query_17track_does_not_treat_loading_page_as_not_found(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[0, 0, 1]),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        body_locator = SimpleNamespace(
            inner_text=mock.AsyncMock(
                side_effect=[
                    "Loading results Not found",
                    "Loading results Not found",
                    "",
                ]
            )
        )

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=UL228444795YP",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            content=mock.AsyncMock(
                side_effect=[
                    "<html><body>Loading results Not found</body></html>",
                    "<html><body>Loading results Not found</body></html>",
                    "<html><body>loaded</body></html>",
                ]
            ),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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

    async def test_query_17track_returns_not_found_quickly_for_new_result_card(self):
        tracking_no = "CRIN26061521261065"

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        body_locator = SimpleNamespace(inner_text=mock.AsyncMock(return_value="Not found Select carrier Please check if the tracking number is correct or try switching carrier and then check again."))

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=CRIN26061521261065",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            content=mock.AsyncMock(return_value=NOT_FOUND_HTML),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', 'div:has-text("TRACK")', 'div[title*="Track"]'}
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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

    async def test_query_17track_does_not_require_role_textbox_input(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        role_textbox = self._build_search_input()
        hidden_textarea = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        hidden_textarea.first = hidden_textarea
        search_trigger = self._build_search_trigger()

        fresh_page = SimpleNamespace(
            url="https://www.17track.net/en",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else hidden_textarea
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else role_textbox
                    if selector in {"[role=\"textbox\"]", "[contenteditable=\"true\"]"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
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
            mock.patch.object(logistics_query, "extract_17track_items_from_html", return_value=parsed_items),
        ):
            result = await logistics_query.query_17track(tracking_no)

        self.assertEqual(result["平台"], "17TRACK")
        fresh_page.goto.assert_awaited_once_with(
            f"https://t.17track.net/en#nums={tracking_no}",
            wait_until="domcontentloaded",
            timeout=25000,
        )
        role_textbox.press_sequentially.assert_not_awaited()
        search_trigger.click.assert_not_awaited()

    async def test_query_17track_clicks_next_and_finish_guides_until_gone(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        next_button = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[1, 1, 0]),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        next_button.first = next_button
        finish_button = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[0, 1, 0]),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        finish_button.first = finish_button

        fresh_page = SimpleNamespace(
            url="https://www.17track.net/en",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else next_button
                    if selector in {'button[title="Next"]', 'button[aria-label="Next"]'}
                    else finish_button
                    if selector in {'button[title="Finish"]', 'button[aria-label="Finish"]'}
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
        self.assertGreaterEqual(next_button.click.await_count, 1)
        self.assertGreaterEqual(finish_button.click.await_count, 1)

    async def test_query_17track_falls_back_to_js_click_for_walkthrough_buttons(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        next_button = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[1, 0, 0]),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(side_effect=RuntimeError("click blocked")),
            first=None,
        )
        next_button.first = next_button
        finish_button = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            click=mock.AsyncMock(),
            first=None,
        )
        finish_button.first = finish_button

        fresh_page = SimpleNamespace(
            url="https://www.17track.net/en",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(return_value=True),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else next_button
                    if selector in {'button[title="Next"]', 'button[aria-label="Next"]'}
                    else finish_button
                    if selector in {'button[title="Finish"]', 'button[aria-label="Finish"]'}
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
        fresh_page.evaluate.assert_awaited()

    async def test_query_17track_waits_for_walkthrough_to_clear_before_not_found_detection(self):
        tracking_no = "UL228444795YP"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[0, 1]),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        next_button = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[1, 0, 0]),
            is_visible=mock.AsyncMock(return_value=True),
            click=mock.AsyncMock(),
            first=None,
        )
        next_button.first = next_button
        body_locator = SimpleNamespace(inner_text=mock.AsyncMock(side_effect=["Not found", ""]))

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=UL228444795YP",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            content=mock.AsyncMock(side_effect=[
                "<div>Not found</div>",
                "<div>loaded</div>",
            ]),
            evaluate=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else next_button
                    if selector in {'button[title="Next"]', 'button[aria-label="Next"]'}
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
        next_button.click.assert_awaited()

    async def test_query_17track_does_not_close_result_page_before_timeline_finishes_loading(self):
        tracking_no = "JJD0002234334887751"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(side_effect=[0, 0, 0, 0, 0, 0, 1]),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        body_locator = SimpleNamespace(inner_text=mock.AsyncMock(return_value="Loading results"))

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=JJD0002234334887751",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            wait_for_load_state=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="ALL-IN-ONE PACKAGE TRACKING | 17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            content=mock.AsyncMock(return_value="<html><body>Loading results</body></html>"),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
        self.assertNotIn("错误", result)

    async def test_query_17track_stops_at_result_wait_deadline_and_dumps_debug_files(self):
        tracking_no = "UL228444795YP"

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=0),
            is_visible=mock.AsyncMock(return_value=False),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()
        body_locator = SimpleNamespace(inner_text=mock.AsyncMock(return_value=""))

        debug_dir = mock.Mock()
        debug_dir.mkdir = mock.Mock()
        debug_dir.__truediv__ = lambda self, name: self

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/en#nums=UL228444795YP",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="ALL-IN-ONE PACKAGE TRACKING | 17TRACK"),
            close=mock.AsyncMock(),
            evaluate=mock.AsyncMock(),
            content=mock.AsyncMock(return_value="<html><body>empty result</body></html>"),
            screenshot=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"#auto-size-textarea", "textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else body_locator
                    if selector == "body"
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
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
            mock.patch("services.tracking_providers.Path", return_value=debug_dir),
            mock.patch("services.tracking_providers.time.monotonic", side_effect=[0, 26]),
        ):
            result = await logistics_query.query_17track(tracking_no)

        self.assertEqual(result["平台"], "17TRACK")
        self.assertIn("页面加载超过 25 秒", result["错误"])
        debug_dir.mkdir.assert_called()
        fresh_page.screenshot.assert_awaited()
        self.assertTrue(result["调试HTML"])

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
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()

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
                    else search_input
                    if selector in {"textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
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

    async def test_query_17track_reuses_shared_context_and_closes_page(self):
        tracking_no = "872762992953"
        parsed_items = [{"时间": "2026-06-11 14:20", "内容": "Delivered", "地点": ""}]

        timeline_root = SimpleNamespace(
            count=mock.AsyncMock(return_value=1),
            is_visible=mock.AsyncMock(return_value=True),
            locator=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(inner_html=mock.AsyncMock(return_value=TRACK_HTML)))),
            first=None,
        )
        timeline_root.first = timeline_root
        search_input = self._build_search_input()
        search_trigger = self._build_search_trigger()

        fresh_page = SimpleNamespace(
            url="https://t.17track.net/zh-cn#nums=872762992953",
            goto=mock.AsyncMock(),
            wait_for_timeout=mock.AsyncMock(),
            title=mock.AsyncMock(return_value="17TRACK"),
            close=mock.AsyncMock(),
            locator=mock.Mock(
                side_effect=lambda selector: (
                    timeline_root
                    if selector == "span.yq-time"
                    else search_input
                    if selector in {"textarea", "input[placeholder*=\"tracking\"]", "input[type=\"text\"]", "input"}
                    else search_trigger
                    if selector in {'div[title="Track the entered order number."]', "div:has-text(\"TRACK\")", "div[title*=\"Track\"]"}
                    else SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))
                )
            ),
            get_by_text=mock.Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=mock.AsyncMock(return_value=0), is_visible=mock.AsyncMock(return_value=False)))),
        )
        shared_context = SimpleNamespace(pages=[], close=mock.AsyncMock(), new_page=mock.AsyncMock(return_value=fresh_page))
        browser = SimpleNamespace(
            contexts=[shared_context],
            new_context=mock.AsyncMock(),
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
        browser.new_context.assert_not_awaited()
        shared_context.new_page.assert_awaited_once()
        fresh_page.close.assert_awaited_once()
        shared_context.close.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
