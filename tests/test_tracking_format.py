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
    def test_baosen_multiple_logistics_numbers_are_formatted_in_separate_sections(self):
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
                "平台": "堡森",
                "物流编号查询结果": [
                    {
                        "物流编号": "HZUK26070287",
                        "平台": "堡森",
                        "物流轨迹": [{"时间": "2026-09-10 10:00:00", "内容": "第一票已开船"}],
                    },
                    {
                        "物流编号": "HZUK26070290",
                        "平台": "堡森",
                        "物流轨迹": [{"时间": "2026-09-11 10:00:00", "内容": "第二票已到港"}],
                    },
                ],
            },
            "baosen",
        )

        self.assertIn("堡森物流轨迹（按物流编号）", text)
        self.assertIn("物流编号: HZUK26070287", text)
        self.assertIn("物流编号: HZUK26070290", text)
        self.assertIn("第一票已开船", text)
        self.assertIn("第二票已到港", text)

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

    def test_qq_tax_notice_result_summarizes_customs_clearance_content(self):
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
                "查询值": "KMFMTLY2600197",
                "物流轨迹": [
                    {
                        "时间": "2026-06-18 12:00:00",
                        "内容": "到港，清关中",
                        "单号": "KMFMTLY2600197",
                    },
                ],
                "最新轨迹": {
                    "时间": "2026-06-18 12:00:00",
                    "内容": "到港，清关中",
                    "单号": "KMFMTLY2600197",
                },
            },
            "qq",
        )

        self.assertIn("到港，清关中", text)
        self.assertIn("清关中", text)
        self.assertNotIn("关税", text)


if __name__ == "__main__":
    unittest.main()
