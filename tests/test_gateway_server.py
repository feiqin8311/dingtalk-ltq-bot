import os
import sys
import unittest
from unittest.mock import patch


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status = status_code
        self._payload = payload or {}
        self.text = text

    def read(self):
        return self.text.encode("utf-8") if self.text else __import__("json").dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        return None


class GatewayServerTests(unittest.IsolatedAsyncioTestCase):
    def _load_module(self):
        if "gateway_server" in sys.modules:
            del sys.modules["gateway_server"]
        import gateway_server

        return gateway_server

    async def test_health_endpoint(self):
        gateway_server = self._load_module()
        result = await gateway_server.health()
        self.assertEqual(
            result,
            {
                "success": True,
                "data": {"ok": True, "service": "logistics-query-gateway"},
                "error": None,
            },
        )

    async def test_validate_gateway_key_accepts_when_not_configured(self):
        gateway_server = self._load_module()
        with patch.dict(os.environ, {}, clear=False):
            result = await gateway_server.validate_gateway_key(None)
        self.assertIsNone(result)

    async def test_query_tracking_proxies_success_response(self):
        gateway_server = self._load_module()
        payload = gateway_server.TrackingQueryRequest(tracking_no="UUS123456789")
        upstream_payload = {
            "success": True,
            "data": {"平台": "UNIUNI", "查询值": "UUS123456789"},
            "error": None,
        }

        with patch.object(
            gateway_server.urllib.request,
            "urlopen",
            return_value=_FakeResponse(payload=upstream_payload),
        ) as mock_post:
            result = await gateway_server.query_tracking(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], upstream_payload["data"])
        self.assertIsNone(result["error"])
        mock_post.assert_called_once()

    async def test_query_fba_returns_upstream_error(self):
        gateway_server = self._load_module()
        payload = gateway_server.FbaQueryRequest(fba_code="FBA123456")
        upstream_payload = {
            "success": False,
            "data": {"FBA编号": "FBA123456"},
            "error": "未找到对应FBA记录",
        }

        with patch.object(
            gateway_server.urllib.request,
            "urlopen",
            side_effect=gateway_server.urllib.error.HTTPError(
                url="http://127.0.0.1:18081/api/fba/query",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=_FakeResponse(status_code=404, payload=upstream_payload),
            ),
        ):
            result = await gateway_server.query_fba(payload)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "未找到对应FBA记录")
        self.assertEqual(result["data"], upstream_payload["data"])


if __name__ == "__main__":
    unittest.main()
