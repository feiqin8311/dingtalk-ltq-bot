import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import logistics_query


class BrowserStealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_browser_stealth_uses_playwright_stealth_when_available(self):
        context = SimpleNamespace(
            set_extra_http_headers=mock.AsyncMock(),
        )
        page = SimpleNamespace(
            set_viewport_size=mock.AsyncMock(),
            add_init_script=mock.AsyncMock(),
        )

        stealth_instance = SimpleNamespace(apply_stealth_async=mock.AsyncMock())
        stealth_module = types.ModuleType("playwright_stealth")
        stealth_module.Stealth = mock.Mock(return_value=stealth_instance)

        with mock.patch.dict(sys.modules, {"playwright_stealth": stealth_module}):
            await logistics_query.apply_browser_stealth(context, page, platform="USPS")

        stealth_instance.apply_stealth_async.assert_awaited_once_with(context)
        context.set_extra_http_headers.assert_awaited_once()
        page.set_viewport_size.assert_awaited_once()
        page.add_init_script.assert_awaited_once()

    async def test_apply_browser_stealth_falls_back_when_playwright_stealth_missing(self):
        context = SimpleNamespace(
            set_extra_http_headers=mock.AsyncMock(),
        )
        page = SimpleNamespace(
            set_viewport_size=mock.AsyncMock(),
            add_init_script=mock.AsyncMock(),
        )

        original_module = sys.modules.pop("playwright_stealth", None)
        try:
            await logistics_query.apply_browser_stealth(context, page, platform="USPS")
        finally:
            if original_module is not None:
                sys.modules["playwright_stealth"] = original_module

        context.set_extra_http_headers.assert_awaited_once()
        page.set_viewport_size.assert_awaited_once()
        page.add_init_script.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
