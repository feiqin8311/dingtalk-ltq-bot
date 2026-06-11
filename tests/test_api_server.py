import os
import sys
import types
import unittest
import asyncio
from unittest.mock import AsyncMock, patch


def _install_fake_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


class ApiServerTests(unittest.IsolatedAsyncioTestCase):
    def _load_module(self):
        with patch.dict(sys.modules, {"dotenv": _install_fake_dotenv()}):
            if "api_server" in sys.modules:
                del sys.modules["api_server"]
            import api_server
        return api_server

    async def test_health_endpoint(self):
        api_server = self._load_module()
        result = await api_server.health()
        self.assertEqual(
            result,
            {
                "success": True,
                "data": {"ok": True, "service": "logistics-query-api"},
                "error": None,
            },
        )

    async def test_validate_api_key_accepts_when_not_configured(self):
        api_server = self._load_module()
        with patch.dict(os.environ, {}, clear=False):
            result = await api_server.validate_api_key(None)
        self.assertIsNone(result)

    async def test_query_tracking_endpoint_wraps_success_response(self):
        api_server = self._load_module()
        payload = api_server.TrackingQueryRequest(tracking_no="UUS123456789")
        expected = {
            "平台": "UNIUNI",
            "查询值": "UUS123456789",
            "物流轨迹": [{"时间": "2026-06-09 10:00:00", "内容": "Package arrived"}],
            "最新轨迹": {"时间": "2026-06-09 10:00:00", "内容": "Package arrived"},
            "物流链接": "https://www.uniuni.com//tracking#tracking-detail?no=UUS123456789",
        }

        raw_result = dict(expected)
        raw_result.pop("物流链接")

        with patch.object(api_server, "query_tracking_number", new=AsyncMock(return_value=raw_result)):
            result = await api_server.query_tracking(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], expected)
        self.assertIsNone(result["error"])

    async def test_query_fba_endpoint_without_order_wraps_error(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(fba_code="FBA123456")

        with patch.object(api_server, "find_order_by_fba", return_value=None):
            result = await api_server.query_fba(payload)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "未找到对应FBA记录")
        self.assertEqual(result["data"]["命中平台"], "none")

    async def test_query_fba_endpoint_with_tracking_platform(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(fba_code="FBA123456")
        order = {
            "FBA编码": "FBA123456",
            "货代公司": "大黄蜂",
            "物流编号": "1234567890",
        }
        expected_tracking = {
            "平台": "17TRACK",
            "查询值": "1234567890",
            "物流轨迹": [{"时间": "2026-06-09", "内容": "Delivered"}],
            "最新轨迹": {"时间": "2026-06-09", "内容": "Delivered"},
        }

        with patch.object(api_server, "find_order_by_fba", return_value=order), \
             patch.object(api_server, "query_17track", new=AsyncMock(return_value=expected_tracking)):
            result = await api_server.query_fba(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["FBA编号"], "FBA123456")
        self.assertEqual(result["data"]["命中平台"], "17track")
        self.assertEqual(result["data"]["物流查询结果"], expected_tracking)

    async def test_api_browser_queries_run_serially(self):
        api_server = self._load_module()
        events: list[str] = []

        async def operation(name: str):
            events.append(f"start:{name}")
            await asyncio.sleep(0.05)
            events.append(f"end:{name}")
            return {
                "平台": "USPS",
                "查询值": name,
                "物流轨迹": [{"时间": "2026-06-09 10:00:00", "内容": name}],
                "最新轨迹": {"时间": "2026-06-09 10:00:00", "内容": name},
            }

        with patch.object(api_server, "query_tracking_number", side_effect=lambda tracking_no: operation(tracking_no)):
            first = asyncio.create_task(api_server.query_tracking(api_server.TrackingQueryRequest(tracking_no="A")))
            await asyncio.sleep(0.01)
            second = asyncio.create_task(api_server.query_tracking(api_server.TrackingQueryRequest(tracking_no="B")))
            await asyncio.gather(first, second)

        self.assertEqual(events, ["start:A", "end:A", "start:B", "end:B"])

    async def test_query_tracking_endpoint_wraps_fedex_link(self):
        api_server = self._load_module()
        payload = api_server.TrackingQueryRequest(tracking_no="381685128780")
        expected = {
            "平台": "FEDEX",
            "查询值": "381685128780",
            "物流轨迹": [{"时间": "6/3/26 9:03 AM", "内容": "Departed FedEx location", "地点": "CYPRESS, TX"}],
            "最新轨迹": {"时间": "6/3/26 9:03 AM", "内容": "Departed FedEx location", "地点": "CYPRESS, TX"},
            "物流链接": "https://www.fedex.com/wtrk/track/?trknbr=381685128780",
        }

        raw_result = dict(expected)
        raw_result.pop("物流链接")

        with patch.object(api_server, "query_tracking_number", new=AsyncMock(return_value=raw_result)):
            result = await api_server.query_tracking(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], expected)


if __name__ == "__main__":
    unittest.main()
