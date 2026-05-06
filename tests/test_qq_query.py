import unittest
from unittest import mock

import qq_query


class _FakeHistoryClient:
    def __init__(self, first_page, paged_pages):
        self.first_page = first_page
        self.paged_pages = list(paged_pages)

    def get_group_msg_history(self, group_id, count):
        return self.first_page[:count]

    def get_group_msg_history_with_seq(self, group_id, message_seq, count, reverse_order=True):
        if not self.paged_pages:
            return []
        return self.paged_pages.pop(0)[:count]


class _FakeQueryClient:
    def __init__(self, history_pages=None, send_result=None):
        self.history_pages = list(history_pages or [])
        self.send_result = send_result or {"message_id": "sent-1"}
        self.sent_messages = []

    def get_group_msg_history(self, group_id, count):
        if self.history_pages:
            return self.history_pages.pop(0)[:count]
        return []

    def get_group_msg_history_with_seq(self, group_id, message_seq, count, reverse_order=True):
        return []

    def send_group_msg(self, group_id, user_id, tracking_no):
        self.sent_messages.append((group_id, user_id, tracking_no))
        return dict(self.send_result)


class QQTrackExpansionTests(unittest.TestCase):
    def test_expand_history_matches_splits_multiple_tracking_numbers(self):
        message = {
            "time": 1712458800,
            "message_seq": "123",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 KMFTORY2600604 船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
        }

        tracks = qq_query._expand_history_matches([message], "KMFTORY2600585")

        self.assertEqual(
            [track["单号"] for track in tracks],
            ["KMFTORY2600585", "KMFTORY2600604"],
        )
        self.assertNotIn("V.2603E", [track["单号"] for track in tracks])

    def test_extract_message_tracking_numbers_ignores_attachment_urls_and_equals_suffix(self):
        message = {
            "raw_message": "KMFTORY2600585=NJPF5A481200A 关税CAD 117.53= USD 88.15",
            "message": [
                {
                    "type": "text",
                    "data": {"text": "KMFTORY2600585=NJPF5A481200A 关税CAD 117.53= USD 88.15"},
                },
                {
                    "type": "image",
                    "data": {
                        "url": "http://example.com/file/abc123456789/image1.jpg",
                        "summary": "[图片]",
                    },
                },
            ],
        }

        tracking_numbers = qq_query._extract_message_tracking_numbers(message, "KMFTORY2600585")

        self.assertEqual(tracking_numbers, ["KMFTORY2600585"])

    def test_find_history_matches_ignores_tax_notice_messages(self):
        message = {
            "time": 1776931547,
            "message_seq": "267453192",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585=NJPF5A481200A 关税请于一个工作日内确认，如果因为货值低引起查验需要补缴关税及罚金",
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": "KMFTORY2600585=NJPF5A481200A 关税请于一个工作日内确认，如果因为货值低引起查验需要补缴关税及罚金"
                    },
                },
                {
                    "type": "image",
                    "data": {"url": "http://example.com/file/1.jpg", "summary": "[图片]"},
                },
            ],
        }

        matches = qq_query._find_history_matches([message], "KMFTORY2600585", 3001065660)

        self.assertEqual(matches, [])

    def test_find_history_matches_ignores_attachment_only_messages(self):
        file_message = {
            "time": 1775528331,
            "message_seq": "10",
            "sender": {"user_id": "3001065660"},
            "raw_message": "[CQ:file,file=KMFTORY2600585提单.pdf,url=https://example.com/bill.pdf]",
            "message": [
                {
                    "type": "file",
                    "data": {
                        "file_name": "KMFTORY2600585提单.pdf",
                        "url": "https://example.com/bill.pdf",
                    },
                }
            ],
        }
        text_message = {
            "time": 1775531931,
            "message_seq": "11",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 KMFTORY2600604 船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)",
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": "KMFTORY2600585 KMFTORY2600604 船舶SM SEOUL V.2603E 4-4已离港，预计4-27到港(TORONTO)"
                    },
                }
            ],
        }

        matches = qq_query._find_history_matches(
            [file_message, text_message],
            "KMFTORY2600585",
            3001065660,
        )

        self.assertEqual(matches, [text_message])

    def test_scan_history_messages_continues_when_anchor_page_has_one_duplicate(self):
        first_page = [
            {"message_id": f"m{i}", "message_seq": str(i), "time": i}
            for i in range(120, 100, -1)
        ]
        second_page = [{"message_id": "m101", "message_seq": "101", "time": 101}] + [
            {"message_id": f"m{i}", "message_seq": str(i), "time": i}
            for i in range(100, 81, -1)
        ]
        third_page = [{"message_id": "m82", "message_seq": "82", "time": 82}] + [
            {"message_id": f"m{i}", "message_seq": str(i), "time": i}
            for i in range(81, 62, -1)
        ]
        client = _FakeHistoryClient(first_page, [second_page, third_page])

        messages = qq_query._scan_history_messages(client, 1, page_size=20, max_messages=50)

        self.assertIn("m81", [item["message_id"] for item in messages])

    def test_query_qq_returns_recent_history_without_sending_message(self):
        now_ts = 1_800_000_000
        recent_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 3 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 已离港",
            "message": [{"type": "text", "data": {"text": "KMFTORY2600585 已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[recent_message]])

        with (
            mock.patch.object(qq_query, "NapCatOneBotClient", return_value=client),
            mock.patch.object(qq_query, "_resolve_group_id", return_value=123456),
            mock.patch.object(qq_query, "_resolve_user", return_value=(3001065660, "李美慧")),
            mock.patch.object(
                qq_query,
                "get_qq_api_settings",
                return_value=("http://127.0.0.1:6702", "", 15, 30, 0.01, 50),
            ),
            mock.patch.object(qq_query, "get_qq_history_lookback_count", return_value=50),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFTORY2600585")

        self.assertEqual(result["结果来源"], "群历史(按物流编号匹配，展开消息中的多单号)")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_sends_message_when_latest_history_is_older_than_seven_days(self):
        now_ts = 1_800_000_000
        stale_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 8 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 已离港",
            "message": [{"type": "text", "data": {"text": "KMFTORY2600585 已离港"}}],
        }
        fresh_reply = {
            "message_id": "m2",
            "message_seq": "101",
            "time": now_ts,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 已到港",
            "message": [{"type": "text", "data": {"text": "KMFTORY2600585 已到港"}}],
        }
        client = _FakeQueryClient(history_pages=[[stale_message], [stale_message], [stale_message, fresh_reply]])

        with (
            mock.patch.object(qq_query, "NapCatOneBotClient", return_value=client),
            mock.patch.object(qq_query, "_resolve_group_id", return_value=123456),
            mock.patch.object(qq_query, "_resolve_user", return_value=(3001065660, "李美慧")),
            mock.patch.object(
                qq_query,
                "get_qq_api_settings",
                return_value=("http://127.0.0.1:6702", "", 15, 30, 0.01, 50),
            ),
            mock.patch.object(qq_query, "get_qq_history_lookback_count", return_value=50),
            mock.patch.object(qq_query.time, "time", side_effect=[now_ts, now_ts, now_ts, now_ts + 1, now_ts + 1]),
            mock.patch.object(qq_query.time, "sleep", return_value=None),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFTORY2600585")

        self.assertEqual(client.sent_messages, [(123456, 3001065660, "KMFTORY2600585")])
        self.assertEqual(result["最新轨迹"]["内容"], "KMFTORY2600585 已到港")

    def test_query_qq_returns_stale_history_and_marks_question_needed_when_requested(self):
        now_ts = 1_800_000_000
        stale_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 8 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2600585 已离港",
            "message": [{"type": "text", "data": {"text": "KMFTORY2600585 已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[stale_message]])

        with (
            mock.patch.object(qq_query, "NapCatOneBotClient", return_value=client),
            mock.patch.object(qq_query, "_resolve_group_id", return_value=123456),
            mock.patch.object(qq_query, "_resolve_user", return_value=(3001065660, "李美慧")),
            mock.patch.object(
                qq_query,
                "get_qq_api_settings",
                return_value=("http://127.0.0.1:6702", "", 15, 30, 0.01, 50),
            ),
            mock.patch.object(qq_query, "get_qq_history_lookback_count", return_value=50),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq(
                {"货代公司": "金为"},
                "KMFTORY2600585",
                defer_if_stale=True,
            )

        self.assertNotIn("需要异步跟进", result)
        self.assertTrue(result["需要QQ询问"])
        self.assertEqual(result["最新轨迹"]["内容"], "KMFTORY2600585 已离港")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_marks_question_needed_without_waiting_when_no_history_in_preview(self):
        now_ts = 1_800_000_000
        client = _FakeQueryClient(history_pages=[[]])

        with (
            mock.patch.object(qq_query, "NapCatOneBotClient", return_value=client),
            mock.patch.object(qq_query, "_resolve_group_id", return_value=123456),
            mock.patch.object(qq_query, "_resolve_user", return_value=(3001065660, "李美慧")),
            mock.patch.object(
                qq_query,
                "get_qq_api_settings",
                return_value=("http://127.0.0.1:6702", "", 15, 0, 0.01, 50),
            ),
            mock.patch.object(qq_query, "get_qq_history_lookback_count", return_value=50),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq(
                {"货代公司": "金为"},
                "KMFTORY2600585",
                defer_if_stale=True,
            )

        self.assertTrue(result["需要QQ询问"])
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(client.sent_messages, [])


if __name__ == "__main__":
    unittest.main()
