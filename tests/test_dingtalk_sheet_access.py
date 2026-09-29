import unittest
from unittest import mock

import logistics_query


class DingtalkSheetAccessTests(unittest.TestCase):
    def test_timestamp_fields_are_formatted_in_china_time(self):
        timestamp_ms = 1790006400000

        self.assertEqual(
            logistics_query.format_timestamp_ms(timestamp_ms),
            "2026-09-22 00:00:00 GMT+8",
        )

    def test_iter_search_sheets_fetches_sheet_list_once(self):
        sheets = [
            {"id": "sheet-1", "name": "2025New!"},
            {"id": "sheet-2", "name": "Other"},
        ]
        with mock.patch.object(logistics_query, "get_all_sheets", return_value=sheets) as get_all_sheets_mock:
            ordered = logistics_query.iter_search_sheets("doc-1")

        get_all_sheets_mock.assert_called_once_with("doc-1")
        self.assertEqual([sheet["id"] for sheet in ordered], ["sheet-1", "sheet-2"])

    def test_get_primary_logistics_no_uses_first_split_code(self):
        order = {"物流编号": "HZNL26011940 HZNL26011943"}
        self.assertEqual(logistics_query.get_primary_logistics_no(order), "HZNL26011940")

    def test_get_primary_logistics_no_uses_first_embedded_code_when_concatenated(self):
        order = {"物流编号": "HZNL26011940HZNL26011943"}
        self.assertEqual(logistics_query.get_primary_logistics_no(order), "HZNL26011940")

    def test_get_logistics_nos_keeps_each_distinct_number_in_order(self):
        order = {"物流编号": "HZUK26070287\nHZUK26070290\nHZUK26070287"}

        self.assertEqual(
            logistics_query.get_logistics_nos(order),
            ["HZUK26070287", "HZUK26070290"],
        )

    def test_combine_tracking_results_keeps_tracks_separated_by_logistics_no(self):
        result = logistics_query.combine_tracking_results_by_logistics_no(
            "堡森",
            [
                (
                    "HZUK26070287",
                    {
                        "平台": "堡森",
                        "查询值": "HZUK26070287",
                        "物流轨迹": [{"时间": "2026-09-10 10:00:00", "内容": "第一票已开船"}],
                    },
                ),
                (
                    "HZUK26070290",
                    {
                        "平台": "堡森",
                        "查询值": "HZUK26070290",
                        "物流轨迹": [{"时间": "2026-09-11 10:00:00", "内容": "第二票已到港"}],
                    },
                ),
            ],
        )

        self.assertEqual(result["查询值"], "HZUK26070287,HZUK26070290")
        self.assertEqual(
            [item["物流编号"] for item in result["物流编号查询结果"]],
            ["HZUK26070287", "HZUK26070290"],
        )
        self.assertEqual(result["物流编号查询结果"][0]["物流轨迹"][0]["单号"], "HZUK26070287")
        self.assertEqual(result["物流编号查询结果"][1]["物流轨迹"][0]["单号"], "HZUK26070290")
        self.assertEqual(result["物流轨迹"][0]["单号"], "HZUK26070290")


if __name__ == "__main__":
    unittest.main()
