import asyncio
import os
import sys
import types
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from logistics_query import get_baosen_credentials


def _install_fake_dingtalk_stream():
    module = types.ModuleType("dingtalk_stream")
    utils_module = types.ModuleType("dingtalk_stream.utils")
    utils_module.DINGTALK_OPENAPI_ENDPOINT = "https://oapi.dingtalk.com"

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
    module.utils = utils_module
    return module


def _install_fake_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


class TrackingQueueTests(unittest.IsolatedAsyncioTestCase):
    def _make_handler(self):
        fake_stream = _install_fake_dingtalk_stream()
        fake_dotenv = _install_fake_dotenv()
        with patch.dict(
            sys.modules,
            {
                "dingtalk_stream": fake_stream,
                "dingtalk_stream.utils": fake_stream.utils,
                "dotenv": fake_dotenv,
            },
        ):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main

        return main.LogisticsBotHandler(), main

    def _make_message(self):
        return SimpleNamespace(
            sender_nick="tester",
            sender_staff_id="staff-1",
            sender_id="staff-1",
            conversation_id="cid-1",
            conversation_type="2",
            message_type="text",
            text=SimpleNamespace(content="FBA19900H9WP"),
        )

    def test_baosen_credentials_require_non_empty_env(self):
        with patch.dict(os.environ, {"BAOSEN_USERNAME": "", "BAOSEN_PASSWORD": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "缺少环境变量"):
                get_baosen_credentials()

    async def test_browser_queries_run_serially(self):
        handler, _ = self._make_handler()
        events: list[str] = []

        async def operation(name: str):
            events.append(f"start:{name}")
            await asyncio.sleep(0.05)
            events.append(f"end:{name}")
            return {"平台": "堡森", "查询值": name, "物流轨迹": [{"时间": "2026-04-07 10:00:00", "内容": name}]}

        first = asyncio.create_task(
            handler._run_tracking_query_with_queue(
                platform="堡森",
                platform_key="baosen",
                query_value="A",
                operation=lambda: operation("A"),
            )
        )
        await asyncio.sleep(0.01)
        second = asyncio.create_task(
            handler._run_tracking_query_with_queue(
                platform="堡森",
                platform_key="baosen",
                query_value="B",
                operation=lambda: operation("B"),
            )
        )

        await asyncio.gather(first, second)

        self.assertEqual(events, ["start:A", "end:A", "start:B", "end:B"])

    async def test_usps_queries_run_serially(self):
        handler, _ = self._make_handler()
        events: list[str] = []

        async def operation(name: str):
            events.append(f"start:{name}")
            await asyncio.sleep(0.05)
            events.append(f"end:{name}")
            return {"平台": "USPS", "查询值": name, "物流轨迹": [{"时间": "2026-04-07 10:00:00", "内容": name}]}

        first = asyncio.create_task(
            handler._run_tracking_query_with_queue(
                platform="USPS",
                platform_key="usps",
                query_value="A",
                operation=lambda: operation("A"),
            )
        )
        await asyncio.sleep(0.01)
        second = asyncio.create_task(
            handler._run_tracking_query_with_queue(
                platform="USPS",
                platform_key="usps",
                query_value="B",
                operation=lambda: operation("B"),
            )
        )

        await asyncio.gather(first, second)

        self.assertEqual(events, ["start:A", "end:A", "start:B", "end:B"])

    async def test_baosen_login_error_is_not_retried(self):
        handler, main_module = self._make_handler()
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            raise main_module.BaosenLoginError("堡森登录未成功")

        with self.assertRaises(main_module.BaosenLoginError):
            await handler._run_tracking_query_with_retry(
                platform="堡森",
                query_value="HZNL26020133",
                operation=operation,
            )

        self.assertEqual(attempts, 1)

    async def test_pingyi_not_found_result_is_not_retried(self):
        handler, main_module = self._make_handler()
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            return {
                "平台": "平谊",
                "查询值": "FBA19FDPK8TT",
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "未找到 FBA FBA19FDPK8TT 的记录",
            }

        with patch.object(main_module, "_TRACK_QUERY_RETRY_DELAY_SECONDS", 0):
            result = await handler._run_tracking_query_with_retry(
                platform="平谊",
                query_value="FBA19FDPK8TT",
                operation=operation,
            )

        self.assertEqual(attempts, 1)
        self.assertEqual(result["错误"], "未找到 FBA FBA19FDPK8TT 的记录")

    async def test_usps_akamai_block_result_is_not_retried(self):
        handler, main_module = self._make_handler()
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            return {
                "平台": "USPS",
                "查询值": "9214490407314880398037",
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "USPS Akamai 风控拦截，当前浏览器会话需要人工打开 USPS 后再重试",
            }

        with patch.object(main_module, "_TRACK_QUERY_RETRY_DELAY_SECONDS", 0):
            result = await handler._run_tracking_query_with_retry(
                platform="USPS",
                query_value="9214490407314880398037",
                operation=operation,
            )

        self.assertEqual(attempts, 1)
        self.assertIn("Akamai", result["错误"])

    async def test_agl_manual_login_timeout_is_not_retried(self):
        handler, main_module = self._make_handler()
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            return {
                "平台": "AGL",
                "查询值": "BOOK123",
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "AGL 登录或验证码等待超时",
                "阻塞原因": "MANUAL_LOGIN_TIMEOUT",
            }

        with patch.object(main_module, "_TRACK_QUERY_RETRY_DELAY_SECONDS", 0):
            result = await handler._run_tracking_query_with_retry(
                platform="AGL",
                query_value="BOOK123",
                operation=operation,
            )

        self.assertEqual(attempts, 1)
        self.assertEqual(result["阻塞原因"], "MANUAL_LOGIN_TIMEOUT")

    def test_qq_timeout_formats_as_empty_reply(self):
        handler, _ = self._make_handler()

        text = handler._format_tracking_result(
            {
                "平台": "QQ",
                "查询值": "KMFTORY2600392",
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "等待 QQ 回复超时（120 秒）",
            },
            "qq",
        )

        self.assertEqual(text, "")

    async def test_reply_qq_result_skips_async_push_when_timeout_has_no_tracks(self):
        handler, _ = self._make_handler()
        replies: list[str] = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)

        await handler._reply_qq_result(
            self._make_message(),
            "FBA19900H9WP",
            {
                "平台": "QQ",
                "查询值": "KMFTORY2600392",
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "等待 QQ 回复超时（120 秒）",
            },
        )

        self.assertEqual(replies, [])

    async def test_handle_text_message_returns_recent_qq_history_immediately(self):
        handler, main = self._make_handler()
        replies: list[str] = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "fba"

        order = {"货代公司": "金为", "物流编号": "KMFTORY2600585"}
        qq_result = {
            "平台": "QQ",
            "查询值": "KMFTORY2600585",
            "结果来源": "群历史(按物流编号匹配，展开消息中的多单号)",
            "物流轨迹": [{"时间": "2026-04-07 11:18:50", "内容": "KMFTORY2600585 已离港"}],
            "最新轨迹": {"时间": "2026-04-07 11:18:50", "内容": "KMFTORY2600585 已离港"},
        }

        with (
            patch.object(main, "find_order_by_fba", return_value=order),
            patch.object(main, "decide_platform", return_value="qq"),
            patch.object(handler, "_format_order_info", return_value="📦 FBA编号: FBA19900H9WP"),
            patch.object(handler, "_query_qq_preview", return_value=qq_result),
            patch.object(handler, "_schedule_qq_follow_up") as schedule_mock,
        ):
            await handler._handle_text_message(self._make_message(), "FBA19900H9WP")

        self.assertEqual(len(replies), 2)
        self.assertIn("开始查询 FBA19900H9WP", replies[0])
        self.assertIn("最新物流轨迹(QQ)", replies[1])
        schedule_mock.assert_not_called()

    async def test_handle_text_message_returns_stale_qq_history_with_manual_follow_up_notice(self):
        handler, main = self._make_handler()
        replies: list[str] = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "fba"

        order = {"货代公司": "金为", "物流编号": "KMFTORY2600585"}
        qq_result = {
            "平台": "QQ",
            "查询值": "KMFTORY2600585",
            "结果来源": "群历史已超过7天",
            "提示": "消息已7天未更新，请询问单证",
            "物流轨迹": [{"时间": "2026-04-07 11:18:50", "内容": "KMFTORY2600585 已离港"}],
            "最新轨迹": {"时间": "2026-04-07 11:18:50", "内容": "KMFTORY2600585 已离港"},
        }

        with (
            patch.object(main, "find_order_by_fba", return_value=order),
            patch.object(main, "decide_platform", return_value="qq"),
            patch.object(handler, "_format_order_info", return_value="📦 FBA编号: FBA19900H9WP"),
            patch.object(handler, "_query_qq_preview", return_value=qq_result),
            patch.object(handler, "_schedule_qq_follow_up") as follow_up_mock,
            patch.object(handler, "_schedule_qq_question", create=True) as question_mock,
        ):
            await handler._handle_text_message(self._make_message(), "FBA19900H9WP")

        self.assertEqual(len(replies), 2)
        self.assertIn("最新物流轨迹(QQ)", replies[1])
        self.assertIn("消息已7天未更新，请询问单证", replies[1])
        follow_up_mock.assert_not_called()
        question_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
