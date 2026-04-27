import unittest
from unittest import mock

import logistics_query


class DingtalkSheetAccessTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
