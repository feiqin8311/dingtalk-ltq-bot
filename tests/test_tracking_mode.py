import sys
import types
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace
from unittest.mock import patch


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

    module.ChatbotHandler = ChatbotHandler
    module.CallbackMessage = CallbackMessage
    module.AckMessage = AckMessage
    module.ChatbotMessage = ChatbotMessage
    module.Credential = object
    module.DingTalkStreamClient = object
    module.utils = utils_module
    return module


def _install_fake_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


class TrackingModeMenuTests(unittest.IsolatedAsyncioTestCase):
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

    def _make_message(self, content: str):
        return SimpleNamespace(
            sender_nick="tester",
            sender_staff_id="staff-1",
            sender_id="staff-1",
            conversation_id="cid-1",
            conversation_type="1",
            message_type="text",
            text=SimpleNamespace(content=content),
        )

    async def test_first_message_shows_business_menu(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)

        await handler._handle_text_message(self._make_message("hello"), "hello")

        self.assertEqual(handler._conversation_modes["cid-1"], "menu")
        self.assertEqual(len(replies), 1)
        self.assertIn("请选择要办理的业务", replies[0])

    async def test_reset_replays_business_menu(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "tracking"

        await handler._handle_text_message(self._make_message("重置"), "重置")

        self.assertEqual(handler._conversation_modes["cid-1"], "menu")
        self.assertEqual(len(replies), 1)
        self.assertEqual(
            replies[0],
            "请选择要办理的业务：\n"
            "1. FBA查询\n"
            "2. 跟踪号查询\n\n"
            "回复【重置】➡️ 放弃本次并重新选择业务",
        )

    async def test_reply_one_enters_fba_mode_and_uses_fba_flow(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "menu"

        with patch.object(handler, "_handle_fba_message", create=True) as fba_mock:
            await handler._handle_text_message(self._make_message("1"), "1")
            await handler._handle_text_message(self._make_message("FBA19900H9WP"), "FBA19900H9WP")

        self.assertEqual(handler._conversation_modes["cid-1"], "fba")
        self.assertTrue(any("FBA查询" in reply for reply in replies))
        fba_mock.assert_called_once()

    async def test_reply_two_enters_tracking_mode_and_uses_tracking_flow(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "menu"

        with patch.object(handler, "_handle_tracking_message", create=True) as tracking_mock:
            await handler._handle_text_message(self._make_message("2"), "2")
            await handler._handle_text_message(self._make_message("UUS123456789"), "UUS123456789")

        self.assertEqual(handler._conversation_modes["cid-1"], "tracking")
        self.assertTrue(any("跟踪号查询" in reply for reply in replies))
        tracking_mock.assert_called_once()

    async def test_menu_state_replays_menu_on_unknown_selection(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "menu"

        await handler._handle_text_message(self._make_message("abc"), "abc")

        self.assertEqual(handler._conversation_modes["cid-1"], "menu")
        self.assertEqual(len(replies), 1)
        self.assertIn("请选择要办理的业务", replies[0])

    async def test_tracking_mode_dispatches_tracking_number_query(self):
        handler, main = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "tracking"

        tracking_result = {
            "平台": "UNIUNI",
            "查询值": "UUS123456789",
            "物流轨迹": [{"时间": "2026-06-09 10:00:00", "内容": "Package arrived at station"}],
            "最新轨迹": {"时间": "2026-06-09 10:00:00", "内容": "Package arrived at station"},
        }

        with patch.object(main, "query_tracking_number", return_value=tracking_result):
            await handler._handle_text_message(self._make_message("UUS123456789"), "UUS123456789")

        self.assertEqual(len(replies), 2)
        self.assertIn("开始查询跟踪号 UUS123456789", replies[0])
        self.assertIn("最新物流轨迹", replies[1])
        self.assertIn("https://www.uniuni.com//tracking#tracking-detail?no=UUS123456789", replies[1])

    async def test_tracking_mode_rejects_empty_text(self):
        handler, _ = self._make_handler()
        replies = []
        handler.reply_text = lambda text, incoming_message: replies.append(text)
        handler._conversation_modes["cid-1"] = "tracking"

        await handler._handle_tracking_query(self._make_message("   "), "   ")

        self.assertEqual(replies, ["请发送要查询的跟踪号"])

    async def test_query_tracking_number_routes_to_17track_fallback(self):
        import logistics_query

        expected = {
            "平台": "17TRACK",
            "查询值": "LM123456789CN",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_17track", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("LM123456789CN")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_uniuni_helper(self):
        import logistics_query

        expected = {
            "平台": "UNIUNI",
            "查询值": "UUS123456789",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_uniuni_tracking", new=AsyncMock(return_value=expected), create=True):
            result = await logistics_query.query_tracking_number("UUS123456789")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_gofo_helper(self):
        import logistics_query

        expected = {
            "平台": "GOFO",
            "查询值": "GFUS01055496346945",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_gofo_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("GFUS01055496346945")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_usps_helper(self):
        import logistics_query

        expected = {
            "平台": "USPS",
            "查询值": "9214490411372861932437",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_usps_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("9214490411372861932437")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_ups_helper(self):
        import logistics_query

        expected = {
            "平台": "UPS",
            "查询值": "1Z0VV9660319941066",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_ups_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("1Z0VV9660319941066")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_yuntrack_helper_for_h00rva(self):
        import logistics_query

        expected = {
            "平台": "YUNTRACK",
            "查询值": "H00RVA0498916385",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_yuntrack_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("H00RVA0498916385")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_yuntrack_helper_for_gv(self):
        import logistics_query

        expected = {
            "平台": "YUNTRACK",
            "查询值": "GV123456789US",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_yuntrack_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("GV123456789US")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_swiship_helper_for_tbc(self):
        import logistics_query

        expected = {
            "平台": "SWISHIP_CA",
            "查询值": "TBC906468472009",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("TBC906468472009")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_swiship_helper_for_intl(self):
        import logistics_query

        expected = {
            "平台": "SWISHIP_CA",
            "查询值": "INTL123456789",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("INTL123456789")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_swiship_helper_for_bni(self):
        import logistics_query

        expected = {
            "平台": "SWISHIP_CA",
            "查询值": "BNI123456789",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("BNI123456789")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_amazon_uk_helper_for_uk(self):
        import logistics_query

        expected = {
            "平台": "AMAZON_UK",
            "查询值": "UK4413632304",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_amazon_uk_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("UK4413632304")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_amazon_us_helper_for_tba(self):
        import logistics_query

        expected = {
            "平台": "AMAZON_US",
            "查询值": "TBA331751755675",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_amazon_us_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("TBA331751755675")

        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
