import asyncio
import os
import unittest
from unittest.mock import patch

from main import LogisticsBotHandler
from logistics_query import BaosenLoginError, get_baosen_credentials


class TrackingQueueTests(unittest.IsolatedAsyncioTestCase):
    def test_baosen_credentials_require_non_empty_env(self):
        with patch.dict(os.environ, {"BAOSEN_USERNAME": "", "BAOSEN_PASSWORD": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "缺少环境变量"):
                get_baosen_credentials()

    async def test_browser_queries_run_serially(self):
        handler = LogisticsBotHandler()
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

    async def test_baosen_login_error_is_not_retried(self):
        handler = LogisticsBotHandler()
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            raise BaosenLoginError("堡森登录未成功")

        with self.assertRaises(BaosenLoginError):
            await handler._run_tracking_query_with_retry(
                platform="堡森",
                query_value="HZNL26020133",
                operation=operation,
            )

        self.assertEqual(attempts, 1)

    def test_qq_timeout_formats_as_empty_reply(self):
        handler = LogisticsBotHandler()

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


if __name__ == "__main__":
    unittest.main()
