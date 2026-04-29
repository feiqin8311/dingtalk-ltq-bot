import sys
import types
import unittest
from unittest import mock


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


class TrackingFormatTests(unittest.TestCase):
    def test_qq_tracking_result_includes_tracking_number_label(self):
        fake_stream = _install_fake_dingtalk_stream()
        fake_dotenv = _install_fake_dotenv()
        with mock.patch.dict(
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

        handler = main.LogisticsBotHandler()
        text = handler._format_tracking_result(
            {
                "平台": "QQ",
                "查询值": "KMFTORY2600585",
                "物流轨迹": [
                    {
                        "时间": "2026-04-07 12:00:00",
                        "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                        "单号": "KMFTORY2600585",
                    },
                    {
                        "时间": "2026-04-07 12:00:00",
                        "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                        "单号": "KMFTORY2600604",
                    },
                ],
                "最新轨迹": {
                    "时间": "2026-04-07 12:00:00",
                    "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                    "单号": "KMFTORY2600585",
                },
            },
            "qq",
        )

        self.assertIn("[KMFTORY2600585]", text)
        self.assertNotIn("[KMFTORY2600604]", text)

    def test_qq_tracking_result_deduplicates_expanded_history_entries(self):
        fake_stream = _install_fake_dingtalk_stream()
        fake_dotenv = _install_fake_dotenv()
        with mock.patch.dict(
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

        handler = main.LogisticsBotHandler()
        text = handler._format_tracking_result(
            {
                "平台": "QQ",
                "查询值": "KMFTORY2600585",
                "结果来源": "群历史(按物流编号匹配，展开消息中的多单号)",
                "物流轨迹": [
                    {
                        "时间": "2026-04-07 12:00:00",
                        "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                        "单号": "KMFTORY2600585",
                    },
                    {
                        "时间": "2026-04-07 12:00:00",
                        "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                        "单号": "KMFTORY2600604",
                    },
                ],
                "最新轨迹": {
                    "时间": "2026-04-07 12:00:00",
                    "内容": "船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
                    "单号": "KMFTORY2600585",
                },
            },
            "qq",
        )

        self.assertEqual(text.count("• "), 1)
        self.assertIn("[KMFTORY2600585]", text)
        self.assertNotIn("[KMFTORY2600604]", text)


if __name__ == "__main__":
    unittest.main()
