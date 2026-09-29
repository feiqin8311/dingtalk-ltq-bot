import sys
import types
import unittest
import os
from pathlib import Path
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
        tracker_exists=True,
    ):
        self.url = url
        self.force_signin_after_goto = False
        self.tracker_text = tracker_text
        self.tracker_texts = list(tracker_texts or [])
        self.tracker_text_index = 0
        self.tracker_exists = tracker_exists
        self.goto_calls = []
        self.reload_calls = 0
        self.wait_for_timeout_calls = []
        self.wait_for_load_state_calls = []
        self.title_value = "AGL Tracking"
        self.bring_to_front_calls = 0
        self.close_calls = 0
        self.continue_visible = False
        self.continue_clicks = 0
        self.passkey_visible = False
        self.passkey_clicks = 0

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
            return _FakeLocator(visible=self.tracker_exists, count=1 if self.tracker_exists else 0, text=text)
        if selector == "#ap_email":
            return _FakeLocator(visible=False, count=0)
        if selector == "#ap_password":
            return _FakeLocator(visible=False, count=0)
        if selector in {
            '#continue',
            'input#continue',
            'input#continue[aria-describedby="legalTextRow"]',
        }:
            locator = _FakeLocator(visible=self.continue_visible, count=1 if self.continue_visible else 0)
            original_click = locator.click

            def click_continue():
                original_click()
                self.continue_clicks += 1
                self.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

            locator.click = click_continue
            return locator
        if selector == 'button#dialog-btn-0':
            locator = _FakeLocator(visible=self.passkey_visible, count=1 if self.passkey_visible else 0)

            def click_passkey():
                self.passkey_clicks += 1
                self.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

            locator.click = click_passkey
            return locator
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

    def close(self):
        self.close_calls += 1


class _FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.new_page_calls = 0
        self.close_calls = 0
        self.clear_cookies_calls = 0
        self.init_scripts = []
        self.storage_state_calls = []

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

    def storage_state(self, path=None):
        self.storage_state_calls.append(path)
        return {}


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
        self.context = _FakeContext()
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

    def test_get_agl_credentials_selects_account_by_brand(self):
        credentials = {
            "AGL_USERNAME": "+8619065440811",
            "AGL_PASSWORD": "default-password",
            "AGL_YPLUS_USERNAME": "8613858064738",
            "AGL_YPLUS_PASSWORD": "yplus-password",
            "AGL_EASYCAN_USERNAME": "logistic@easycantools.com",
            "AGL_EASYCAN_PASSWORD": "easycan-password",
        }

        with mock.patch.dict(os.environ, {'AGL_EASYCAN_ZINIAO_BROWSER_ID': ''}, clear=False), \
             mock.patch.object(logistics_query, "get_env", side_effect=credentials.__getitem__):
            self.assertEqual(
                logistics_query.get_agl_credentials({"品牌": "LIBRATON"}),
                ("+8619065440811", "default-password", "AGL_DEFAULT"),
            )
            self.assertEqual(
                logistics_query.get_agl_credentials({"品牌": "PACMANN"}),
                ("+8619065440811", "default-password", "AGL_DEFAULT"),
            )
            self.assertEqual(
                logistics_query.get_agl_credentials({"品牌": "YPLUS"}),
                ("8613858064738", "yplus-password", "AGL_YPLUS"),
            )
            self.assertEqual(
                logistics_query.get_agl_credentials({"品牌": "EZARC"}),
                ("logistic@easycantools.com", "easycan-password", "AGL_EASYCAN"),
            )
            self.assertEqual(
                logistics_query.get_agl_credentials({"品牌": "TOLESA"}),
                ("logistic@easycantools.com", "easycan-password", "AGL_EASYCAN"),
            )

    def test_get_agl_credentials_uses_ziniao_for_easycan_brands_when_configured(self):
        with mock.patch.dict(os.environ, {'AGL_EASYCAN_ZINIAO_BROWSER_ID': '27864375894927'}, clear=False):
            self.assertEqual(
                logistics_query.get_agl_credentials({'品牌': 'EZARC'}),
                ('', '', 'AGL_EASYCAN_ZINIAO'),
            )
            self.assertEqual(
                logistics_query.get_agl_credentials({'品牌': 'TOLESA'}),
                ('', '', 'AGL_EASYCAN_ZINIAO'),
            )

    def test_wait_for_agl_manual_verification_waits_for_any_signin_page(self):
        page = _FakePage(url="https://signin.amazon.com/ap/signin")

        def complete_login(_milliseconds):
            page.url = "https://www.agl.amazon.com/freight-puma"

        page.wait_for_timeout = complete_login

        self.assertTrue(logistics_query.wait_for_agl_manual_verification(page, 30))

    def test_continue_ziniao_agl_session_clicks_passwordless_continue_page(self):
        page = _FakePage(url='https://signin.amazon.com/ap/signin')
        page.continue_visible = True

        self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))
        self.assertEqual(page.continue_clicks, 1)
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_clicks_passkey_confirmation_first(self):
        page = _FakePage(url='https://signin.amazon.com/ap/signin')
        page.passkey_visible = True
        page.continue_visible = True

        self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))
        self.assertEqual(page.passkey_clicks, 1)
        self.assertEqual(page.continue_clicks, 0)
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_waits_for_passkey_after_continue(self):
        page = _FakePage(url='https://www.agl.amazon.com/ap/signin')
        passkey_visible = False
        passkey_locator = _FakeLocator(visible=True, count=0)
        continue_locator = _FakeLocator(visible=True, count=1)

        def passkey_count():
            return 1 if passkey_visible else 0

        def click_continue():
            nonlocal passkey_visible
            page.continue_clicks += 1
            passkey_visible = True

        def click_passkey():
            page.passkey_clicks += 1
            page.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

        passkey_locator.count = passkey_count
        passkey_locator.click = click_passkey
        continue_locator.click = click_continue
        original_locator = page.locator

        with mock.patch.object(
            page,
            'locator',
            side_effect=lambda selector: (
                passkey_locator if selector == 'button#dialog-btn-0'
                else continue_locator if selector == 'input#continue[aria-describedby="legalTextRow"]'
                else original_locator(selector)
            ),
        ):
            self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(page.continue_clicks, 1)
        self.assertEqual(page.passkey_clicks, 1)
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_clicks_passkey_in_another_context_page(self):
        page = _FakePage(url='https://www.agl.amazon.com/ap/signin')
        passkey_page = _FakePage(url='chrome-extension://ziniao-passkey/dialog.html')
        context = _FakeContext(pages=[page, passkey_page])
        passkey_locator = _FakeLocator(visible=True, count=1)

        def click_passkey():
            passkey_page.passkey_clicks += 1
            page.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

        passkey_locator.click = click_passkey
        original_locator = passkey_page.locator
        with mock.patch.object(
            passkey_page,
            'locator',
            side_effect=lambda selector: passkey_locator if selector == 'button#dialog-btn-0' else original_locator(selector),
        ):
            self.assertTrue(
                logistics_query.continue_ziniao_agl_session(
                    page,
                    'https://www.agl.amazon.com/tracking',
                    context=context,
                )
            )

        self.assertEqual(passkey_page.passkey_clicks, 1)
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_clicks_passkey_in_child_frame(self):
        page = _FakePage(url='https://www.agl.amazon.com/ap/signin')
        passkey_frame = mock.Mock()
        passkey_frame.url = 'https://passkey.ziniao.local/dialog'
        passkey_locator = _FakeLocator(visible=True, count=1)
        passkey_clicks = []

        def click_passkey():
            passkey_clicks.append(True)
            page.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

        passkey_locator.click = click_passkey
        passkey_frame.locator.side_effect = (
            lambda selector: passkey_locator if selector == 'button#dialog-btn-0' else _FakeLocator()
        )
        page.frames = [passkey_frame]

        self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))
        self.assertEqual(passkey_clicks, [True])
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_uses_windows_ui_for_browser_level_passkey(self):
        page = _FakePage(url='https://www.agl.amazon.com/ap/signin')
        continue_locator = _FakeLocator(visible=True, count=1)

        def click_continue():
            page.continue_clicks += 1

        def click_native_passkey():
            page.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'
            return True

        continue_locator.click = click_continue
        original_locator = page.locator
        with mock.patch.object(
            page,
            'locator',
            side_effect=lambda selector: (
                continue_locator if selector == 'input#continue[aria-describedby="legalTextRow"]'
                else original_locator(selector)
            ),
        ), mock.patch.object(
            logistics_query,
            '_click_ziniao_passkey_button_via_windows_ui',
            side_effect=click_native_passkey,
        ) as native_click_mock:
            self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(page.continue_clicks, 1)
        native_click_mock.assert_called_once_with()

    def test_continue_ziniao_agl_session_clicks_continue_on_non_signin_amazon_page(self):
        page = _FakePage(url='https://www.amazon.com/ap/cvf')
        page.continue_visible = True

        self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))
        self.assertEqual(page.continue_clicks, 1)
        self.assertIn('agl.amazon.com', page.url)

    def test_continue_ziniao_agl_session_clicks_continue_when_login_fields_are_hidden(self):
        page = _FakePage(url='https://www.amazon.com/ap/cvf')
        page.continue_visible = True
        hidden_login_field = _FakeLocator(visible=False, count=1)
        original_locator = page.locator

        with mock.patch.object(
            page,
            'locator',
            side_effect=lambda selector: hidden_login_field if selector in {'#ap_email', '#ap_password'} else original_locator(selector),
        ):
            self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(page.continue_clicks, 1)

    def test_continue_ziniao_agl_session_clicks_legal_continue_even_when_email_is_visible(self):
        page = _FakePage(url='https://signin.amazon.com/ap/signin')
        page.continue_visible = True
        email_locator = _FakeLocator(visible=True, count=1)
        original_locator = page.locator

        with mock.patch.object(
            page,
            'locator',
            side_effect=lambda selector: email_locator if selector == '#ap_email' else original_locator(selector),
        ):
            self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(page.continue_clicks, 1)

    def test_continue_ziniao_agl_session_force_clicks_continue_when_normal_click_is_intercepted(self):
        page = _FakePage(url='https://www.amazon.com/ap/cvf')
        continue_locator = mock.Mock()
        continue_locator.first = continue_locator
        continue_locator.count.return_value = 1
        click_calls = []

        def click_continue(*_args, **kwargs):
            click_calls.append(kwargs)
            if not kwargs.get('force'):
                raise RuntimeError('pointer events intercepted')
            page.url = 'https://www.agl.amazon.com/freight-puma/shipment/BOOK123/tracking'

        continue_locator.click.side_effect = click_continue
        original_locator = page.locator

        with mock.patch.object(page, 'locator', side_effect=lambda selector: continue_locator if selector == 'input#continue' else original_locator(selector)):
            self.assertTrue(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(click_calls, [{'timeout': 5000}, {'timeout': 5000, 'force': True}])

    def test_continue_ziniao_agl_session_does_not_click_real_login_page(self):
        page = _FakePage(url='https://signin.amazon.com/ap/signin')
        original_locator = page.locator

        with mock.patch.object(page, 'locator', wraps=original_locator) as locator:
            email_locator = _FakeLocator(visible=True, count=1)

            def locator_with_login_field(selector):
                return email_locator if selector == '#ap_email' else original_locator(selector)

            locator.side_effect = locator_with_login_field
            self.assertFalse(logistics_query.continue_ziniao_agl_session(page, 'https://www.agl.amazon.com/tracking'))

        self.assertEqual(page.continue_clicks, 0)

    def test_agl_tracking_render_wait_seconds_uses_bounded_environment_value(self):
        with mock.patch.dict(os.environ, {'AGL_TRACKING_RENDER_WAIT_SECONDS': '45'}, clear=False):
            self.assertEqual(logistics_query.get_agl_tracking_render_wait_seconds(), 45)
        with mock.patch.dict(os.environ, {'AGL_TRACKING_RENDER_WAIT_SECONDS': '300'}, clear=False):
            self.assertEqual(logistics_query.get_agl_tracking_render_wait_seconds(), 60)

    def test_query_agl_waits_for_tracking_to_stabilize_before_refreshing(self):
        extract_results = [
            [],
            [{"时间": "2026-04-03 12:00:00", "内容": "已装船"}],
        ]

        with mock.patch.object(logistics_query, "get_agl_credentials", return_value=("user", "pass", "AGL_DEFAULT")), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, self.context, self.page, self.cleanup)), \
             mock.patch.object(logistics_query, "maybe_select_agl_account", return_value=False), \
             mock.patch.object(logistics_query, "set_agl_language_to_zh", return_value="简体中文"), \
             mock.patch.object(logistics_query, "extract_agl_tracking", side_effect=extract_results), \
             mock.patch.object(logistics_query, "sort_tracks_newest_first", side_effect=lambda items: items), \
             mock.patch.object(logistics_query, "logout_agl", return_value=True):
            result = logistics_query.query_agl("BOOK123", {"品牌": "OTHER"})

        self.assertEqual(result.get("最新轨迹", {}).get("内容"), "已装船")
        self.assertEqual(self.page.reload_calls, 0)

    def test_query_agl_refreshes_tracking_page_after_stability_wait_still_empty(self):
        extract_results = ([[]] * 20) + [
            [{"时间": "2026-04-03 12:00:00", "内容": "已装船"}],
        ]

        with mock.patch.object(logistics_query, "get_agl_credentials", return_value=("user", "pass", "AGL_DEFAULT")), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, self.context, self.page, self.cleanup)), \
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
             mock.patch.object(logistics_query, "create_agl_page", return_value=(self.browser, self.context, self.page, self.cleanup)), \
             mock.patch.object(logistics_query, "maybe_select_agl_account", return_value=False), \
             mock.patch.object(logistics_query, "set_agl_language_to_zh", return_value="简体中文"), \
             mock.patch.object(logistics_query, "extract_agl_tracking", return_value=[]), \
             mock.patch.object(logistics_query, "sort_tracks_newest_first", side_effect=lambda items: items), \
             mock.patch.object(logistics_query, "wait_for_agl_manual_verification", return_value=False), \
             mock.patch.object(logistics_query, "logout_agl", return_value=True):
            result = logistics_query.query_agl("BOOK123", {"品牌": "OTHER"})

        self.assertIn("登录或验证码等待超时", result.get("错误", ""))
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

    def test_extract_agl_tracking_returns_empty_when_tracker_is_absent(self):
        page = _FakePage(tracker_exists=False)

        self.assertEqual(logistics_query.extract_agl_tracking(page), [])
        self.assertEqual(logistics_query.wait_for_agl_tracking_stability(page, wait_ms=1, max_checks=2), [])

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

    def test_create_agl_page_uses_isolated_context_without_clearing_cookies(self):
        old_page = _FakePage(url="https://example.com/old")
        existing_context = _FakeContext(pages=[old_page])
        browser = _FakeBrowserWithContexts(contexts=[existing_context])
        playwright = _FakePlaywrightRoot(browser)

        with mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://fake-cdp"), \
             mock.patch.object(logistics_query, "get_agl_session_state_path", return_value=Path("/tmp/missing-agl-session.json")):
            created_browser, created_context, page, cleanup = logistics_query.create_agl_page(
                playwright,
                "AGL_DEFAULT",
                False,
            )

        self.assertIs(created_browser, browser)
        self.assertIsNot(created_context, existing_context)
        self.assertEqual(browser.new_context_calls, 1)
        self.assertEqual(created_context.clear_cookies_calls, 0)
        self.assertEqual(len(created_context.init_scripts), 1)
        self.assertIn("navigator.credentials", created_context.init_scripts[0])
        self.assertIsNot(page, old_page)
        self.assertEqual(created_context.new_page_calls, 1)
        self.assertEqual(page.bring_to_front_calls, 1)
        self.assertEqual(playwright.chromium.endpoint, "ws://fake-cdp")
        cleanup()
        self.assertEqual(page.close_calls, 1)
        self.assertEqual(created_context.close_calls, 1)
        self.assertEqual(browser.close_calls, 1)

    def test_create_ziniao_agl_page_reuses_existing_page_without_closing_it(self):
        existing_page = _FakePage(url='https://www.agl.amazon.com/freight-puma')
        existing_context = _FakeContext(pages=[existing_page])
        browser = _FakeBrowserWithContexts(contexts=[existing_context])
        playwright = _FakePlaywrightRoot(browser)

        created_browser, context, page, cleanup = logistics_query.create_ziniao_agl_page(playwright, 24567)

        self.assertIs(created_browser, browser)
        self.assertIs(context, existing_context)
        self.assertEqual(browser.new_context_calls, 0)
        self.assertIs(page, existing_page)
        self.assertEqual(existing_context.new_page_calls, 0)
        self.assertEqual(existing_page.bring_to_front_calls, 1)
        self.assertEqual(playwright.chromium.endpoint, 'http://127.0.0.1:24567')
        cleanup()
        self.assertEqual(page.close_calls, 0)
        self.assertEqual(existing_context.close_calls, 0)
        self.assertEqual(browser.close_calls, 0)

    def test_query_agl_ziniao_skips_local_cdp_login_and_session_save(self):
        ziniao_client = mock.Mock()
        ziniao_client.get_or_start_browser.return_value = {'debuggingPort': 24567}
        expected_tracks = [{'时间': '2026-04-03 12:00:00', '内容': '已装船'}]

        with mock.patch.object(logistics_query, 'get_agl_credentials', return_value=('', '', 'AGL_EASYCAN_ZINIAO')), \
             mock.patch.object(logistics_query, 'begin_local_cdp_session') as local_cdp_mock, \
             mock.patch.object(logistics_query, 'get_ziniao_webdriver_client', return_value=ziniao_client), \
             mock.patch.object(logistics_query, 'create_ziniao_agl_page', return_value=(self.browser, self.context, self.page, self.cleanup)), \
             mock.patch.object(logistics_query, 'maybe_select_agl_account') as select_account_mock, \
             mock.patch.object(logistics_query, 'continue_ziniao_agl_session', return_value=True) as continue_mock, \
             mock.patch.object(logistics_query, 'save_agl_session_state') as save_session_mock, \
             mock.patch.object(logistics_query, 'wait_for_agl_tracking_render', return_value=expected_tracks):
            result = logistics_query.query_agl('BOOK123', {'品牌': 'EZARC'})

        local_cdp_mock.assert_not_called()
        ziniao_client.get_or_start_browser.assert_called_once_with(mock.ANY)
        select_account_mock.assert_not_called()
        continue_mock.assert_called_once()
        save_session_mock.assert_not_called()
        self.cleanup.assert_called_once()
        self.assertEqual(result['物流轨迹'], expected_tracks)


if __name__ == "__main__":
    unittest.main()
