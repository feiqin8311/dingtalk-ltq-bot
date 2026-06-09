import sys
import types
import unittest
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
        self.assertIn("已重置当前选择", replies[0])

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


if __name__ == "__main__":
    unittest.main()
