import unittest

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


if __name__ == "__main__":
    unittest.main()
