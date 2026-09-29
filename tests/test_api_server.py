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
            with self.assertLogs("api_server", level="INFO") as logs:
                result = await api_server.query_tracking(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], expected)
        self.assertIsNone(result["error"])
        self.assertTrue(any("API跟踪号查询开始" in line for line in logs.output))
        self.assertTrue(any("API跟踪号查询完成" in line for line in logs.output))

    async def test_query_tracking_endpoint_wraps_browser_exception_as_error_response(self):
        api_server = self._load_module()
        payload = api_server.TrackingQueryRequest(tracking_no="UUS6671260344149426")

        with patch.object(api_server, "query_tracking_number", new=AsyncMock(side_effect=RuntimeError("UNIUNI 页面加载超时"))):
            with self.assertLogs("api_server", level="ERROR") as logs:
                result = await api_server.query_tracking(payload)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "UNIUNI 页面加载超时")
        self.assertEqual(result["data"]["查询值"], "UUS6671260344149426")
        self.assertEqual(result["data"]["物流轨迹"], [])
        self.assertEqual(result["data"]["最新轨迹"], {})
        self.assertEqual(result["data"]["错误"], "UNIUNI 页面加载超时")
        self.assertTrue(any("API跟踪号查询异常" in line for line in logs.output))

    async def test_query_fba_endpoint_without_order_wraps_error(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(fba_code="FBA123456")

        with patch.object(api_server, "find_order_by_fba", return_value=None):
            with self.assertLogs("api_server", level="WARNING") as logs:
                result = await api_server.query_fba(payload)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "未找到对应FBA记录")
        self.assertEqual(result["data"]["命中平台"], "none")
        self.assertTrue(any("API FBA查询失败" in line for line in logs.output))

    async def test_query_fba_direct_agl_logistics_number_skips_dingtalk_lookup(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(
            fba_code="FBA123456",
            logistics_no="AL0-UC54XYYFYNEW2",
            brand="YPLUS",
            platform="agl",
        )
        expected_tracking = {
            "平台": "AGL",
            "查询值": "AL0-UC54XYYFYNEW2",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(api_server, "find_order_by_fba") as find_order_mock, \
             patch.object(
                 api_server,
                 "_query_fba_tracking_result",
                 new=AsyncMock(return_value=expected_tracking),
             ) as tracking_mock:
            result = await api_server.query_fba(payload)

        find_order_mock.assert_not_called()
        tracking_mock.assert_awaited_once_with(
            {
                "货代公司": "龙舟",
                "物流编号": "AL0-UC54XYYFYNEW2",
                "品牌": "YPLUS",
            },
            "FBA123456",
            "agl",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["命中平台"], "agl")
        self.assertEqual(result["data"]["线上表匹配结果"], None)
        self.assertEqual(result["data"]["物流查询结果"], expected_tracking)

    async def test_query_fba_direct_yinghe_logistics_number_without_fba(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(
            logistics_no="YHE2605211007",
            platform="yinghe",
        )
        expected_tracking = {
            "平台": "盈和",
            "查询值": "YHE2605211007",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(api_server, "find_order_by_fba") as find_order_mock, \
             patch.object(
                 api_server,
                 "_query_fba_tracking_result",
                 new=AsyncMock(return_value=expected_tracking),
             ) as tracking_mock:
            result = await api_server.query_fba(payload)

        find_order_mock.assert_not_called()
        tracking_mock.assert_awaited_once_with(
            {"货代公司": "盈和", "物流编号": "YHE2605211007", "品牌": ""},
            "YHE2605211007",
            "yinghe",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["命中平台"], "yinghe")
        self.assertEqual(result["data"]["FBA编号"], "")

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

    async def test_query_fba_tracking_queries_each_baosen_logistics_number_separately(self):
        api_server = self._load_module()
        order = {
            "货代公司": "堡森",
            "物流编号": "HZUK26070287\nHZUK26070290",
        }
        expected_results = [
            {
                "平台": "堡森",
                "查询值": "HZUK26070287",
                "物流轨迹": [{"时间": "2026-09-10 10:00:00", "内容": "第一票已开船"}],
            },
            {
                "平台": "堡森",
                "查询值": "HZUK26070290",
                "物流轨迹": [{"时间": "2026-09-11 10:00:00", "内容": "第二票已到港"}],
            },
        ]

        async def run_queued_query(**kwargs):
            return await kwargs["operation"]()

        with patch.object(
            api_server,
            "run_browser_tracking_query_with_queue",
            side_effect=run_queued_query,
        ) as queue_mock, patch.object(
            api_server,
            "query_baosen",
            new=AsyncMock(side_effect=expected_results),
        ) as baosen_mock:
            result = await api_server._query_fba_tracking_result(order, "FBA15M23V82V", "auto")

        self.assertEqual(
            [call.args[0] for call in baosen_mock.await_args_list],
            ["HZUK26070287", "HZUK26070290"],
        )
        self.assertEqual(queue_mock.await_count, 2)
        self.assertEqual(
            [item["物流编号"] for item in result["物流编号查询结果"]],
            ["HZUK26070287", "HZUK26070290"],
        )
        self.assertEqual(result["物流轨迹"][0]["单号"], "HZUK26070290")

    async def test_query_fba_endpoint_uses_pingyi_api_without_browser_queue(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(fba_code="FBA123456")
        order = {
            "FBA编码": "FBA123456",
            "货代公司": "平谊",
            "物流编号": "PY123456789",
        }
        expected_tracking = {
            "平台": "平谊",
            "查询值": "FBA123456",
            "物流轨迹": [{"时间": "2026-06-09", "内容": "Delivered"}],
            "最新轨迹": {"时间": "2026-06-09", "内容": "Delivered"},
        }

        with patch.object(api_server, "find_order_by_fba", return_value=order), \
             patch.object(api_server, "query_pingyi", new=AsyncMock(return_value=expected_tracking)) as query_pingyi_mock, \
             patch.object(api_server, "run_browser_tracking_query_with_queue") as browser_queue_mock:
            result = await api_server.query_fba(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["物流查询结果"], expected_tracking)
        query_pingyi_mock.assert_awaited_once_with("FBA123456")
        browser_queue_mock.assert_not_called()

    async def test_query_fba_agl_reuses_cached_tracking_result(self):
        api_server = self._load_module()
        order = {"品牌": "YPLUS", "物流编号": "AL0-UC54XYYFYNEW2"}
        cached_result = {
            "平台": "AGL",
            "查询值": "AL0-UC54XYYFYNEW2",
            "物流轨迹": [{"时间": "2026-08-04", "内容": "Delivered"}],
            "最新轨迹": {"时间": "2026-08-04", "内容": "Delivered"},
        }

        with patch.object(api_server, "get_tracking_query_cache", return_value=cached_result) as cache_mock, \
             patch.object(api_server, "run_browser_tracking_query_with_queue") as browser_queue_mock:
            result = await api_server._query_fba_tracking_result(order, "FBA123456", "agl")

        cache_mock.assert_called_once_with("agl:YPLUS:AL0-UC54XYYFYNEW2")
        browser_queue_mock.assert_not_called()
        self.assertEqual(result, cached_result)

    def test_agl_tracking_component_error_is_not_retried(self):
        api_server = self._load_module()
        result = {
            "平台": "AGL",
            "物流轨迹": [],
            "错误": "AGL 页面未加载轨迹组件或未返回轨迹信息",
            "阻塞原因": "TRACKING_NOT_RENDERED",
        }

        self.assertFalse(api_server._should_retry_tracking_result("AGL", result))

    def test_ziniao_agl_login_required_is_not_retried(self):
        api_server = self._load_module()
        result = {
            '平台': 'AGL',
            '物流轨迹': [],
            '错误': '紫鸟环境中的 AGL 未登录或免密确认未通过',
            '阻塞原因': 'ZINIAO_AGL_LOGIN_REQUIRED',
        }

        self.assertFalse(api_server._should_retry_tracking_result('AGL', result))

    async def test_query_fba_endpoint_retries_browser_tracking_platform(self):
        api_server = self._load_module()
        payload = api_server.FbaQueryRequest(fba_code="FBA123456")
        order = {
            "FBA编码": "FBA123456",
            "货代公司": "大黄蜂",
            "物流编号": "1234567890",
        }
        attempts = 0

        async def flaky_query(_tracking_no):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return {
                    "平台": "17TRACK",
                    "查询值": "1234567890",
                    "物流轨迹": [],
                    "最新轨迹": {},
                    "错误": "17TRACK 未查询到轨迹信息，请确认单号或切换承运商后重试",
                }
            return {
                "平台": "17TRACK",
                "查询值": "1234567890",
                "物流轨迹": [{"时间": "2026-06-09", "内容": "Delivered"}],
                "最新轨迹": {"时间": "2026-06-09", "内容": "Delivered"},
            }

        with (
            patch.object(api_server, "find_order_by_fba", return_value=order),
            patch.object(api_server, "query_17track", new=AsyncMock(side_effect=flaky_query)),
            patch.object(api_server.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await api_server.query_fba(payload)

        self.assertTrue(result["success"])
        self.assertEqual(attempts, 3)
        self.assertEqual(result["data"]["物流查询结果"]["最新轨迹"]["内容"], "Delivered")

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

    async def test_query_tracking_endpoint_retries_serial_browser_queries(self):
        api_server = self._load_module()
        payload = api_server.TrackingQueryRequest(tracking_no="9214490411372871922107")
        attempts = 0

        async def flaky_query(_tracking_no):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return {
                    "平台": "USPS",
                    "查询值": payload.tracking_no,
                    "物流轨迹": [],
                    "最新轨迹": {},
                    "错误": "USPS 官网触发风控拦截或页面未返回轨迹信息",
                }
            return {
                "平台": "USPS",
                "查询值": payload.tracking_no,
                "物流轨迹": [{"时间": "2026-06-18 20:39:28", "内容": "USPS Awaiting Item"}],
                "最新轨迹": {"时间": "2026-06-18 20:39:28", "内容": "USPS Awaiting Item"},
            }

        with (
            patch.object(api_server, "query_tracking_number", new=AsyncMock(side_effect=flaky_query)),
            patch.object(api_server.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await api_server.query_tracking(payload)

        self.assertTrue(result["success"])
        self.assertEqual(attempts, 3)
        self.assertEqual(result["data"]["平台"], "USPS")
        self.assertEqual(result["data"]["最新轨迹"]["内容"], "USPS Awaiting Item")

    async def test_query_tracking_endpoint_does_not_retry_usps_akamai_block(self):
        api_server = self._load_module()
        payload = api_server.TrackingQueryRequest(tracking_no="9214490407314880398037")
        attempts = 0

        async def blocked_query(_tracking_no):
            nonlocal attempts
            attempts += 1
            return {
                "平台": "USPS",
                "查询值": payload.tracking_no,
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": "USPS Akamai 风控拦截，当前浏览器会话需要人工打开 USPS 后再重试",
            }

        with (
            patch.object(api_server, "query_tracking_number", new=AsyncMock(side_effect=blocked_query)),
            patch.object(api_server.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await api_server.query_tracking(payload)

        self.assertFalse(result["success"])
        self.assertEqual(attempts, 1)
        self.assertIn("Akamai", result["error"])


if __name__ == "__main__":
    unittest.main()
