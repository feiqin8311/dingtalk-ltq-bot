import sys
import types
import unittest
from unittest import mock

import logistics_query


class _FakeLocator:
    def __init__(self, visible=False, count=0, text="", attribute_value=""):
        self._visible = visible
        self._count = count
        self._text = text
        self._attribute_value = attribute_value

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible

    def count(self):
        return self._count

    def wait_for(self, state=None, timeout=None):
        return None

    def fill(self, value):
        return None

    def click(self):
        return None

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attribute_value

    def nth(self, index):
        return self

    def filter(self, **kwargs):
        return self


class _FakeTextLocator:
    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count


class _FakePage:
    def __init__(
        self,
        url="https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking",
        tracker_text="",
        tracker_texts=None,
    ):
        self.url = url
        self.force_signin_after_goto = False
        self.tracker_text = tracker_text
        self.tracker_texts = list(tracker_texts or [])
        self.tracker_text_index = 0
        self.goto_calls = []
        self.reload_calls = 0
        self.wait_for_timeout_calls = []
        self.wait_for_load_state_calls = []
        self.title_value = "AGL Tracking"
        self.bring_to_front_calls = 0

    def goto(self, url, wait_until=None, timeout=None):
        self.url = "https://signin.amazon.com/ap/signin" if self.force_signin_after_goto else url
        self.goto_calls.append((url, wait_until, timeout))

    def reload(self, wait_until=None, timeout=None):
        self.reload_calls += 1
        if self.force_signin_after_goto:
            self.url = "https://signin.amazon.com/ap/signin"

    def wait_for_timeout(self, value):
        self.wait_for_timeout_calls.append(value)
        if self.tracker_texts and self.tracker_text_index < len(self.tracker_texts) - 1:
            self.tracker_text_index += 1

    def wait_for_load_state(self, state):
        self.wait_for_load_state_calls.append(state)

    def locator(self, selector):
        if selector == ".kat-progress-tracker":
            if self.tracker_texts:
                text = self.tracker_texts[self.tracker_text_index]
            else:
                text = self.tracker_text
            return _FakeLocator(visible=True, count=1, text=text)
        if selector == "#ap_email":
            return _FakeLocator(visible=False, count=0)
        if selector == "#ap_password":
            return _FakeLocator(visible=False, count=0)
        if selector == "body":
            return _FakeLocator(text="body text")
        if selector == "html":
            return _FakeLocator(attribute_value="zh-CN")
        return _FakeLocator(visible=False, count=0)

    def get_by_text(self, text, exact=False):
        return _FakeTextLocator(count=0)

    def title(self):
        return self.title_value

    def bring_to_front(self):
        self.bring_to_front_calls += 1


class _FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.new_page_calls = 0
        self.close_calls = 0
        self.clear_cookies_calls = 0
        self.init_scripts = []

    def new_page(self):
        self.new_page_calls += 1
        page = _FakePage(url="about:blank")
        self.pages.append(page)
        return page

    def close(self):
        self.close_calls += 1

    def clear_cookies(self):
        self.clear_cookies_calls += 1

    def add_init_script(self, script):
        self.init_scripts.append(script)


class _FakeBrowserWithContexts:
    def __init__(self, contexts=None):
        self.contexts = list(contexts or [])
        self.new_context_calls = 0
        self.close_calls = 0

    def new_context(self, **kwargs):
        self.new_context_calls += 1
        context = _FakeContext()
        self.contexts.append(context)
        return context

    def close(self):
        self.close_calls += 1


class _FakeChromium:
    def __init__(self, browser):
        self.browser = browser
        self.endpoint = None

    def connect_over_cdp(self, endpoint):
        self.endpoint = endpoint
        return self.browser


class _FakePlaywrightRoot:
    def __init__(self, browser):
        self.chromium = _FakeChromium(browser)


class _FakeBrowser:
    def close(self):
        return None


class _FakeSyncPlaywright:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class QueryAglTests(unittest.TestCase):
    def setUp(self):
        self.page = _FakePage()
        self.browser = _FakeBrowser()
        self.cleanup = mock.Mock()

        self.sync_api_module = types.ModuleType("playwright.sync_api")

        class FakeTimeoutError(Exception):
            pass

        self.sync_api_module.TimeoutError = FakeTimeoutError
        self.sync_api_module.sync_playwright = lambda: _FakeSyncPlaywright()
        self.playwright_module = types.ModuleType("playwright")
        self.playwright_module.sync_api = self.sync_api_module

        self.module_patcher = mock.patch.dict(
            sys.modules,
            {
                "playwright": self.playwright_module,
                "playwright.sync_api": self.sync_api_module,
            },
        )
        self.module_patcher.start()

    def tearDown(self):
        self.module_patcher.stop()

    def test_query_agl_waits_for_tracking_to_stabilize_before_refreshing(self):
        extract_results = [
            [],
            [{"时间": "2026-04-03 12:00:00", "内容": "已装船"}],
        ]

        with mock.patch.object(logistics_query, "get_agl_credentials", return_value=("user", "pass", "AGL_DEFAULT")), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, object(), self.page, self.cleanup)), \
             mock.patch.object(logistics_query, "maybe_select_agl_account", return_value=False), \
             mock.patch.object(logistics_query, "set_agl_language_to_zh", return_value="简体中文"), \
             mock.patch.object(logistics_query, "extract_agl_tracking", side_effect=extract_results), \
             mock.patch.object(logistics_query, "sort_tracks_newest_first", side_effect=lambda items: items), \
             mock.patch.object(logistics_query, "logout_agl", return_value=True):
            result = logistics_query.query_agl("BOOK123", {"品牌": "OTHER"})

        self.assertEqual(result.get("最新轨迹", {}).get("内容"), "已装船")
        self.assertEqual(self.page.reload_calls, 0)

    def test_query_agl_refreshes_tracking_page_after_stability_wait_still_empty(self):
        extract_results = [
            [],
            [],
            [],
            [],
            [{"时间": "2026-04-03 12:00:00", "内容": "已装船"}],
        ]

        with mock.patch.object(logistics_query, "get_agl_credentials", return_value=("user", "pass", "AGL_DEFAULT")), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, object(), self.page, self.cleanup)), \
             mock.patch.object(logistics_query, "maybe_select_agl_account", return_value=False), \
             mock.patch.object(logistics_query, "set_agl_language_to_zh", return_value="简体中文"), \
             mock.patch.object(logistics_query, "extract_agl_tracking", side_effect=extract_results), \
             mock.patch.object(logistics_query, "sort_tracks_newest_first", side_effect=lambda items: items), \
             mock.patch.object(logistics_query, "logout_agl", return_value=True):
            result = logistics_query.query_agl("BOOK123", {"品牌": "OTHER"})

        self.assertEqual(result.get("最新轨迹", {}).get("内容"), "已装船")
        self.assertEqual(self.page.reload_calls, 1)

    def test_query_agl_returns_login_error_without_refresh_retry(self):
        self.page.force_signin_after_goto = True

        with mock.patch.object(logistics_query, "get_agl_credentials", return_value=("user", "pass", "AGL_DEFAULT")), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, object(), self.page, self.cleanup)), \
             mock.patch.object(logistics_query, "maybe_select_agl_account", return_value=False), \
             mock.patch.object(logistics_query, "set_agl_language_to_zh", return_value="简体中文"), \
             mock.patch.object(logistics_query, "extract_agl_tracking", return_value=[]), \
             mock.patch.object(logistics_query, "sort_tracks_newest_first", side_effect=lambda items: items), \
             mock.patch.object(logistics_query, "logout_agl", return_value=True):
            result = logistics_query.query_agl("BOOK123", {"品牌": "OTHER"})

        self.assertIn("登录后仍停留在登录页", result.get("错误", ""))
        self.assertEqual(self.page.reload_calls, 0)

    def test_parse_track_time_supports_agl_english_time_format(self):
        parsed = logistics_query.parse_track_time("Mar 18, 2026, 5:52 PM GMT+8")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 18)
        self.assertEqual(parsed.hour, 17)
        self.assertEqual(parsed.minute, 52)

    def test_extract_agl_tracking_parses_english_timeline_lines(self):
        tracker_text = "\n".join([
            "Mar 18, 2026, 5:52 PM GMT+8",
            "Booking receivedBooking received",
            "Mar 26, 2026, 8:00 AM GMT+8",
            "Space confirmedSpace confirmed",
            "CNNGB Ningbo, ChinaCNNGB Ningbo, China",
            "Mar 31, 2026, 6:38 PM GMT+8",
            "Loaded on vesselLoaded on vessel",
        ])
        page = _FakePage(tracker_text=tracker_text)

        tracks = logistics_query.extract_agl_tracking(page)

        self.assertEqual(len(tracks), 3)
        self.assertEqual(tracks[0]["时间"], "Mar 18, 2026, 5:52 PM GMT+8")
        self.assertEqual(tracks[0]["内容"], "Booking received")
        self.assertEqual(tracks[1]["内容"], "Space confirmed | CNNGB Ningbo, China")
        self.assertEqual(tracks[2]["内容"], "Loaded on vessel")

    def test_wait_for_agl_tracking_stability_uses_latest_stable_snapshot(self):
        partial_text = "\n".join([
            "Mar 18, 2026, 5:52 PM GMT+8",
            "Booking receivedBooking received",
        ])
        full_text = "\n".join([
            "Mar 18, 2026, 5:52 PM GMT+8",
            "Booking receivedBooking received",
            "Mar 26, 2026, 8:00 AM GMT+8",
            "Space confirmedSpace confirmed",
        ])
        page = _FakePage(tracker_texts=[partial_text, full_text, full_text])

        tracks = logistics_query.wait_for_agl_tracking_stability(page, wait_ms=200, max_checks=3)

        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["内容"], "Space confirmed")
        self.assertEqual(page.wait_for_timeout_calls, [200, 200])

    def test_create_agl_page_reuses_existing_context_and_clears_cookies(self):
        old_page = _FakePage(url="https://example.com/old")
        existing_context = _FakeContext(pages=[old_page])
        browser = _FakeBrowserWithContexts(contexts=[existing_context])
        playwright = _FakePlaywrightRoot(browser)

        with mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://fake-cdp"):
            created_browser, created_context, page, cleanup = logistics_query.create_agl_page(
                playwright,
                "AGL_DEFAULT",
                False,
            )

        self.assertIs(created_browser, browser)
        self.assertIs(created_context, existing_context)
        self.assertEqual(browser.new_context_calls, 0)
        self.assertEqual(created_context.clear_cookies_calls, 1)
        self.assertEqual(len(created_context.init_scripts), 1)
        self.assertIn("navigator.credentials", created_context.init_scripts[0])
        self.assertIsNot(page, old_page)
        self.assertEqual(created_context.new_page_calls, 1)
        self.assertEqual(page.bring_to_front_calls, 1)
        self.assertEqual(playwright.chromium.endpoint, "ws://fake-cdp")
        cleanup()
        self.assertEqual(browser.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
