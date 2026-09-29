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

    def test_find_history_matches_keeps_tax_notice_messages_with_tracking_number(self):
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

        self.assertEqual(matches, [message])

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

    def test_query_qq_returns_stale_history_with_manual_follow_up_notice_when_requested(self):
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
        self.assertFalse(result.get("需要QQ询问", False))
        self.assertEqual(result["提示"], "消息已7天未更新，请询问单证")
        self.assertEqual(result["最新轨迹"]["内容"], "KMFTORY2600585 已离港")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_returns_manual_follow_up_notice_without_waiting_when_no_history_in_preview(self):
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

        self.assertFalse(result.get("需要QQ询问", False))
        self.assertEqual(result["提示"], "消息已7天未更新，请询问单证")
        self.assertEqual(result["物流轨迹"], [])
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_uses_recent_reply_after_latest_prompt_even_when_reply_is_image_only(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "200",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "@3001065660 KMFMTLY2600197 物流状态",
            "message": [
                {"type": "at", "data": {"qq": "3001065660"}},
                {"type": "text", "data": {"text": " KMFMTLY2600197 物流状态"}},
            ],
        }
        image_reply = {
            "message_id": "r1",
            "message_seq": "201",
            "time": now_ts - 24 * 60 * 60 + 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "[CQ:image,file=reply.jpg,url=http://example.com/reply.jpg]",
            "message": [
                {
                    "type": "image",
                    "data": {"url": "http://example.com/reply.jpg", "summary": "[图片]"},
                }
            ],
        }
        stale_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 20 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197 已离港",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197 已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[image_reply, prompt_message, stale_message]])

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
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertFalse(result.get("需要QQ询问", False))
        self.assertEqual(result["最新轨迹"]["消息类型"], "附件")
        self.assertEqual(result["最新轨迹"]["附件"][0]["类型"], "图片")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_uses_recent_reply_when_prompt_exists_only_in_raw_message(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "200",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
            "message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
        }
        image_reply = {
            "message_id": "r1",
            "message_seq": "201",
            "time": now_ts - 24 * 60 * 60 + 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "[CQ:image,file=reply.jpg,url=http://example.com/reply.jpg]",
            "message": [
                {
                    "type": "image",
                    "data": {"url": "http://example.com/reply.jpg", "summary": "[图片]"},
                }
            ],
        }
        stale_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 20 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197 已离港",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197 已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[image_reply, prompt_message, stale_message]])

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
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(result["结果来源"], "群历史(按最近一次QQ询问后的连续回复匹配)")
        self.assertEqual(result["最新轨迹"]["消息类型"], "附件")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_collects_multiple_recent_replies_after_latest_prompt(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "300",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "@3001065660 KMFMTLY2600197 物流状态",
            "message": [
                {"type": "at", "data": {"qq": "3001065660"}},
                {"type": "text", "data": {"text": " KMFMTLY2600197 物流状态"}},
            ],
        }
        text_reply = {
            "message_id": "r1",
            "message_seq": "301",
            "time": now_ts - 24 * 60 * 60 + 30,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197 5-22已离港，预计6-16到港",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197 5-22已离港，预计6-16到港"}}],
        }
        image_reply = {
            "message_id": "r2",
            "message_seq": "302",
            "time": now_ts - 24 * 60 * 60 + 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "[CQ:image,file=reply.jpg,url=http://example.com/reply.jpg]",
            "message": [
                {
                    "type": "image",
                    "data": {"url": "http://example.com/reply.jpg", "summary": "[图片]"},
                }
            ],
        }
        customs_reply = {
            "message_id": "r3",
            "message_seq": "303",
            "time": now_ts - 24 * 60 * 60 + 90,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197=NJBD5G884100A 关税请于一个工作日内确认",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197=NJBD5G884100A 关税请于一个工作日内确认"}}],
        }
        client = _FakeQueryClient(history_pages=[[customs_reply, image_reply, text_reply, prompt_message]])

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
            mock.patch.object(qq_query, "get_qq_history_context_window", return_value=5),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(len(result["物流轨迹"]), 3)
        self.assertEqual(result["结果来源"], "群历史(按最近一次QQ询问后的连续回复匹配)")
        self.assertEqual(result["物流轨迹"][0]["内容"], "到港，清关中")
        self.assertEqual(result["物流轨迹"][1]["消息类型"], "附件")
        self.assertIn("已离港", result["物流轨迹"][2]["内容"])

    def test_query_qq_limits_recent_reply_chain_by_context_window(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "300",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "@3001065660 KMFMTLY2600197 物流状态",
            "message": [
                {"type": "at", "data": {"qq": "3001065660"}},
                {"type": "text", "data": {"text": " KMFMTLY2600197 物流状态"}},
            ],
        }
        replies = []
        for idx in range(1, 7):
            replies.append(
                {
                    "message_id": f"r{idx}",
                    "message_seq": str(300 + idx),
                    "time": now_ts - 24 * 60 * 60 + idx * 30,
                    "user_id": "3001065660",
                    "sender": {"user_id": "3001065660"},
                    "raw_message": f"KMFMTLY2600197 回复{idx}",
                    "message": [{"type": "text", "data": {"text": f"KMFMTLY2600197 回复{idx}"}}],
                }
            )
        client = _FakeQueryClient(history_pages=[list(reversed(replies)) + [prompt_message]])

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
            mock.patch.object(qq_query, "get_qq_history_context_window", return_value=3),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(len(result["物流轨迹"]), 3)
        self.assertIn("回复6", result["物流轨迹"][0]["内容"])
        self.assertIn("回复4", result["物流轨迹"][-1]["内容"])

    def test_query_qq_stops_recent_reply_chain_when_other_tracking_number_appears(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "300",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "@3001065660 KMFMTLY2600197 物流状态",
            "message": [
                {"type": "at", "data": {"qq": "3001065660"}},
                {"type": "text", "data": {"text": " KMFMTLY2600197 物流状态"}},
            ],
        }
        relevant_reply = {
            "message_id": "r1",
            "message_seq": "301",
            "time": now_ts - 24 * 60 * 60 + 30,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197 船舶SM QINGDAO V.2604E 5-22已离港",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197 船舶SM QINGDAO V.2604E 5-22已离港"}}],
        }
        unrelated_reply = {
            "message_id": "r2",
            "message_seq": "302",
            "time": now_ts - 24 * 60 * 60 + 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFCALY2600424 船舶YM MUTUALITY V.113E 6-18已离港",
            "message": [{"type": "text", "data": {"text": "KMFCALY2600424 船舶YM MUTUALITY V.113E 6-18已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[unrelated_reply, relevant_reply, prompt_message]])

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
            mock.patch.object(qq_query, "get_qq_history_context_window", return_value=5),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(len(result["物流轨迹"]), 1)
        self.assertIn("KMFMTLY2600197", result["物流轨迹"][0]["内容"])
        self.assertNotIn("KMFCALY2600424", result["物流轨迹"][0]["内容"])

    def test_query_qq_collects_prompt_reply_even_when_reply_seq_is_lower_than_prompt_seq(self):
        now_ts = 1_800_000_000
        prompt_message = {
            "message_id": "p1",
            "message_seq": "500",
            "time": now_ts - 24 * 60 * 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
            "message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
        }
        image_reply = {
            "message_id": "r1",
            "message_seq": "400",
            "time": now_ts - 24 * 60 * 60 + 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "[CQ:file,file=reply.png,url=http://example.com/reply.png]",
            "message": [
                {
                    "type": "file",
                    "data": {"file_name": "reply.png", "url": "http://example.com/reply.png"},
                }
            ],
        }
        stale_message = {
            "message_id": "m1",
            "message_seq": "100",
            "time": now_ts - 20 * 24 * 60 * 60,
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197 已离港",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197 已离港"}}],
        }
        client = _FakeQueryClient(history_pages=[[image_reply, prompt_message, stale_message]])

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
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(result["结果来源"], "群历史(按最近一次QQ询问后的连续回复匹配)")
        self.assertEqual(result["最新轨迹"]["消息类型"], "附件")
        self.assertEqual(client.sent_messages, [])

    def test_query_qq_ignores_prompt_reply_chain_when_first_reply_is_other_tracking_number_with_image(self):
        now_ts = 1_800_000_000
        history_message = {
            "message_id": "h1",
            "message_seq": "100",
            "time": now_ts - 8 * 24 * 60 * 60,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFMTLY2600197=NJBD5G884100A 关税请于一个工作日内确认",
            "message": [{"type": "text", "data": {"text": "KMFMTLY2600197=NJBD5G884100A 关税请于一个工作日内确认"}}],
        }
        prompt_message = {
            "message_id": "p1",
            "message_seq": "200",
            "time": now_ts - 60,
            "user_id": "123456789",
            "sender": {"user_id": "123456789"},
            "raw_message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
            "message": "[CQ:at,qq=3001065660] KMFMTLY2600197 物流状态",
        }
        unrelated_reply = {
            "message_id": "r1",
            "message_seq": "201",
            "time": now_ts - 30,
            "user_id": "3001065660",
            "sender": {"user_id": "3001065660"},
            "raw_message": "KMFTORY2601394 进仓数据请确认 报关资料发下 @易达-乔丹 [图片]",
            "message": [
                {"type": "text", "data": {"text": "KMFTORY2601394 进仓数据请确认 报关资料发下 @易达-乔丹"}},
                {"type": "image", "data": {"url": "http://example.com/reply.jpg", "summary": "[图片]"}},
            ],
        }
        client = _FakeQueryClient(history_pages=[[unrelated_reply, prompt_message, history_message]])

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
            mock.patch.object(qq_query, "get_qq_history_context_window", return_value=5),
            mock.patch.object(qq_query.time, "time", return_value=now_ts),
        ):
            result = qq_query.query_qq({"货代公司": "金为"}, "KMFMTLY2600197", defer_if_stale=True)

        self.assertEqual(result["结果来源"], "群历史已超过7天")
        self.assertFalse(result.get("需要QQ询问", False))
        self.assertEqual(result["提示"], "消息已7天未更新，请询问单证")
        self.assertEqual(result["最新轨迹"]["内容"], "到港，清关中")
        self.assertNotIn("KMFTORY2601394", result["最新轨迹"]["内容"])


if __name__ == "__main__":
    unittest.main()
