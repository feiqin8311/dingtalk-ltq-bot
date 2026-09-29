import asyncio
import logging
import os
import unittest
from unittest import mock

from services import tracking_runtime


class TrackingRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_tracking_query_attempt_timeout_uses_platform_override(self):
        with mock.patch.dict(
            os.environ,
            {
                'TRACKING_QUERY_ATTEMPT_TIMEOUT_SECONDS': '30',
                'TRACKING_USPS_ATTEMPT_TIMEOUT_SECONDS': '75',
            },
            clear=False,
        ):
            self.assertEqual(tracking_runtime.get_tracking_query_attempt_timeout_seconds('USPS'), 75)
            self.assertEqual(tracking_runtime.get_tracking_query_attempt_timeout_seconds('UPS'), 30)

    async def test_tracking_query_attempt_timeout_cancels_operation(self):
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        result = await tracking_runtime.run_tracking_query_attempt_with_timeout(
            'UNIUNI',
            'UUS123456789',
            operation,
            timeout_seconds=0.01,
        )

        self.assertTrue(cancelled.is_set())
        self.assertEqual(result['平台'], 'UNIUNI')
        self.assertIn('超过 0.01 秒', result['错误'])

    async def test_browser_queue_reuses_in_flight_query_with_the_same_key(self):
        tracking_runtime.BROWSER_TRACKING_QUEUE_STATE.clear()
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return {'平台': 'AGL', '查询值': 'AL0-TEST', '物流轨迹': []}

        first = asyncio.create_task(
            tracking_runtime.run_browser_tracking_query_with_queue(
                logging.getLogger('test'),
                'AGL',
                'AL0-TEST',
                operation,
                dedup_key='agl:YPLUS:AL0-TEST',
            )
        )
        await asyncio.sleep(0.01)
        second = asyncio.create_task(
            tracking_runtime.run_browser_tracking_query_with_queue(
                logging.getLogger('test'),
                'AGL',
                'AL0-TEST',
                operation,
                dedup_key='agl:YPLUS:AL0-TEST',
            )
        )

        first_result, second_result = await asyncio.gather(first, second)

        self.assertEqual(calls, 1)
        self.assertEqual(first_result, second_result)

    def test_attach_tracking_result_link_prefers_runtime_url_when_it_is_a_concrete_result_page(self):
        result = tracking_runtime.attach_tracking_result_link(
            {
                "平台": "UPS",
                "查询值": "1Z0Y84W20367221132",
                "当前URL": "https://www.ups.com/track?loc=en_US&tracknum=1Z0Y84W20367221132&requester=ST/",
            }
        )

        self.assertEqual(
            result["物流链接"],
            "https://www.ups.com/track?loc=en_US&tracknum=1Z0Y84W20367221132&requester=ST/",
        )

    def test_attach_tracking_result_link_prefers_platform_specific_query_url(self):
        result = tracking_runtime.attach_tracking_result_link(
            {
                "平台": "UNIUNI",
                "查询值": "UUS6671260344149426",
                "当前URL": "https://www.uniuni.com/",
            }
        )

        self.assertEqual(
            result["物流链接"],
            "https://www.uniuni.com//tracking#tracking-detail?no=UUS6671260344149426",
        )


if __name__ == "__main__":
    unittest.main()
