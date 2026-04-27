import sys
import types
import unittest
from unittest import mock

import logistics_query


class _AsyncLocator:
    def __init__(self, screenshot_bytes=b"fake"):
        self.fill = mock.AsyncMock()
        self.click = mock.AsyncMock()
        self.press = mock.AsyncMock()
        self.type = mock.AsyncMock()
        self.is_checked = mock.AsyncMock(return_value=False)
        self.screenshot = mock.AsyncMock(return_value=screenshot_bytes)
        self.wait_for = mock.AsyncMock()
        self.inner_text = mock.AsyncMock(return_value="")


class _FakePingyiPage:
    def __init__(self):
        self.url = "http://hzpy.rtb56.com/usercenter/index.aspx"
        self.goto = mock.AsyncMock()
        self.wait_for_load_state = mock.AsyncMock()
        self.wait_for_timeout = mock.AsyncMock()
        self.evaluate = mock.AsyncMock()
        self.add_init_script = mock.AsyncMock()
        self.bring_to_front = mock.AsyncMock()
        self._locators = {
            "#txtUserName": _AsyncLocator(),
            "#txtPassword": _AsyncLocator(),
            "#txtVerifyCode": _AsyncLocator(),
            "#verifycode": _AsyncLocator(),
            "#chkRemember": _AsyncLocator(),
            "#btnSubmit": _AsyncLocator(),
        }

    def locator(self, selector):
        return self._locators[selector]


def _install_fake_dingtalk_stream():
    module = types.ModuleType("dingtalk_stream")

    class ChatbotHandler:
        def __init__(self, *args, **kwargs):
            pass

    class CallbackMessage:
        pass

    class AckMessage:
        STATUS_OK = "OK"

    class ChatbotMessage:
        @staticmethod
        def from_dict(data):
            return data

    class Credential:
        def __init__(self, *args, **kwargs):
            pass

    class DingTalkStreamClient:
        def __init__(self, *args, **kwargs):
            pass

    module.ChatbotHandler = ChatbotHandler
    module.CallbackMessage = CallbackMessage
    module.AckMessage = AckMessage
    module.ChatbotMessage = ChatbotMessage
    module.Credential = Credential
    module.DingTalkStreamClient = DingTalkStreamClient
    return module


def _install_fake_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


class PingyiMainFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_tracking_info_awaits_pingyi_coroutine_directly(self):
        fake_stream = _install_fake_dingtalk_stream()
        fake_dotenv = _install_fake_dotenv()
        with mock.patch.dict(sys.modules, {"dingtalk_stream": fake_stream, "dotenv": fake_dotenv}):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main

        handler = main.LogisticsBotHandler()
        expected_result = {
            "平台": "平谊",
            "查询值": "FBA1990CLT0L",
            "最新轨迹": {"时间": "2026-04-07 10:00:00", "内容": "已签收"},
            "物流轨迹": [{"时间": "2026-04-07 10:00:00", "内容": "已签收"}],
        }

        async_query = mock.AsyncMock(return_value=expected_result)

        with mock.patch.object(main, "decide_platform", return_value="pingyi"), \
             mock.patch.object(main, "query_pingyi", async_query):
            reply = await handler._query_tracking_info({"货代公司": "平谊"}, "FBA1990CLT0L")

        self.assertIn("最新物流轨迹(平谊)", reply)
        async_query.assert_awaited_once_with("FBA1990CLT0L")


class PingyiCliTests(unittest.TestCase):
    def test_logistics_query_main_runs_pingyi_with_asyncio_run(self):
        expected_result = {"平台": "平谊", "查询值": "FBA1990CLT0L", "物流轨迹": [], "最新轨迹": {}}

        with mock.patch.object(sys, "argv", ["logistics_query.py", "--fba", "FBA1990CLT0L", "--platform", "pingyi"]), \
             mock.patch.object(logistics_query, "find_order_by_fba", return_value={"货代公司": "平谊"}), \
             mock.patch.object(logistics_query, "decide_platform", return_value="pingyi"), \
             mock.patch.object(logistics_query, "query_pingyi", new=mock.AsyncMock(return_value=expected_result)) as query_pingyi_mock, \
             mock.patch.object(logistics_query.asyncio, "run", return_value=expected_result) as asyncio_run_mock, \
             mock.patch("builtins.print"):
            logistics_query.main()

        query_pingyi_mock.assert_called_once_with("FBA1990CLT0L")
        asyncio_run_mock.assert_called_once()
        asyncio_run_mock.call_args.args[0].close()


class PingyiCdpTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_pingyi_reuses_existing_session_before_login_page(self):
        fake_page = _FakePingyiPage()

        fake_context = mock.Mock()
        fake_context.pages = []
        fake_context.add_init_script = mock.AsyncMock()
        fake_context.new_page = mock.AsyncMock(return_value=fake_page)

        fake_browser = mock.Mock()
        fake_browser.contexts = [fake_context]
        fake_browser.close = mock.AsyncMock()

        fake_chromium = mock.Mock()
        fake_chromium.launch = mock.AsyncMock()
        fake_chromium.connect_over_cdp = mock.AsyncMock(return_value=fake_browser)
        fake_playwright = mock.Mock(chromium=fake_chromium)

        with mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"), \
             mock.patch.object(logistics_query, "_pingyi_requires_login", new=mock.AsyncMock(return_value=False)):
            browser, page = await logistics_query.login_pingyi(fake_playwright)

        fake_chromium.connect_over_cdp.assert_awaited_once_with("ws://127.0.0.1:19444/devtools/browser/demo")
        fake_page.goto.assert_awaited_once_with(
            "http://hzpy.rtb56.com/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        self.assertIs(browser, fake_browser)
        self.assertIs(page, fake_page)

    async def test_login_pingyi_releases_cdp_session_when_root_page_fails(self):
        fake_page = _FakePingyiPage()
        fake_page.goto = mock.AsyncMock(side_effect=RuntimeError("root failed"))

        fake_context = mock.Mock()
        fake_context.pages = []
        fake_context.add_init_script = mock.AsyncMock()
        fake_context.new_page = mock.AsyncMock(return_value=fake_page)

        fake_browser = mock.Mock()
        fake_browser.contexts = [fake_context]
        fake_browser.close = mock.AsyncMock()

        fake_chromium = mock.Mock()
        fake_chromium.connect_over_cdp = mock.AsyncMock(return_value=fake_browser)
        fake_playwright = mock.Mock(chromium=fake_chromium)

        with mock.patch.object(logistics_query, "begin_local_cdp_session", return_value=None), \
             mock.patch.object(logistics_query, "end_local_cdp_session") as end_session_mock, \
             mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"):
            with self.assertRaises(RuntimeError):
                await logistics_query.login_pingyi(fake_playwright)

        fake_browser.close.assert_awaited_once()
        end_session_mock.assert_called_once_with(None)

    async def test_login_pingyi_uses_local_cdp_instead_of_launching_browser(self):
        fake_page = _FakePingyiPage()

        fake_context = mock.Mock()
        fake_context.pages = []
        fake_context.add_init_script = mock.AsyncMock()
        fake_context.new_page = mock.AsyncMock(return_value=fake_page)

        fake_browser = mock.Mock()
        fake_browser.contexts = [fake_context]
        fake_browser.close = mock.AsyncMock()

        fake_chromium = mock.Mock()
        fake_chromium.launch = mock.AsyncMock()
        fake_chromium.connect_over_cdp = mock.AsyncMock(return_value=fake_browser)
        fake_playwright = mock.Mock(chromium=fake_chromium)

        with mock.patch.object(logistics_query, "get_env", side_effect=lambda name: {"PINGYI_USERNAME": "user", "PINGYI_PASSWORD": "pass"}[name]), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"), \
             mock.patch.object(logistics_query, "_recognize_verify_code", return_value="ABCD"):
            browser, page = await logistics_query.login_pingyi(fake_playwright)

        fake_chromium.connect_over_cdp.assert_awaited_once_with("ws://127.0.0.1:19444/devtools/browser/demo")
        fake_chromium.launch.assert_not_called()
        fake_context.new_page.assert_awaited_once()
        self.assertIs(browser, fake_browser)
        self.assertIs(page, fake_page)

    async def test_login_pingyi_retries_on_same_browser_page(self):
        fake_page = _FakePingyiPage()
        fake_page.url = "http://hzpy.rtb56.com/login.aspx"

        async def click_side_effect(*args, **kwargs):
            return None

        fake_page._locators["#btnSubmit"].click.side_effect = click_side_effect

        fake_context = mock.Mock()
        fake_context.pages = []
        fake_context.add_init_script = mock.AsyncMock()
        fake_context.new_page = mock.AsyncMock(return_value=fake_page)

        fake_browser = mock.Mock()
        fake_browser.contexts = [fake_context]
        fake_browser.close = mock.AsyncMock()

        fake_chromium = mock.Mock()
        fake_chromium.launch = mock.AsyncMock()
        fake_chromium.connect_over_cdp = mock.AsyncMock(return_value=fake_browser)
        fake_playwright = mock.Mock(chromium=fake_chromium)

        with mock.patch.object(logistics_query, "get_env", side_effect=lambda name: {"PINGYI_USERNAME": "user", "PINGYI_PASSWORD": "pass"}[name]), \
             mock.patch.object(logistics_query, "ensure_local_cdp_browser", return_value=None), \
             mock.patch.object(logistics_query, "get_local_cdp_endpoint", return_value="ws://127.0.0.1:19444/devtools/browser/demo"), \
             mock.patch.object(logistics_query, "_recognize_verify_code", return_value="ABCD"), \
             mock.patch.object(logistics_query, "_wait_for_pingyi_login_result", side_effect=[False, True]):
            browser, page = await logistics_query.login_pingyi(fake_playwright, max_retries=2)

        fake_chromium.connect_over_cdp.assert_awaited_once_with("ws://127.0.0.1:19444/devtools/browser/demo")
        fake_context.new_page.assert_awaited_once()
        self.assertGreaterEqual(fake_page.goto.await_count, 2)
        fake_browser.close.assert_not_awaited()
        self.assertIs(browser, fake_browser)
        self.assertIs(page, fake_page)


if __name__ == "__main__":
    unittest.main()
