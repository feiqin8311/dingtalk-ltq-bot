import unittest

from logistics_query import decide_tracking_platform


class TrackingPlatformDecisionTests(unittest.TestCase):
    def test_known_prefixes_route_to_expected_platforms(self):
        cases = {
            "UUS123456789": "uniuni",
            "GFUS123456789": "gofo",
            "9123456789012345678901": "usps",
            "1Z0123456799999999": "ups",
            "H00RVA123456789": "yuntrack",
            "GV123456789US": "yuntrack",
            "UK123456789": "amazon_uk",
            "TBC123456789": "swiship_ca",
            "INTL123456789": "swiship_ca",
            "BNI123456789": "swiship_ca",
            "TBA123456789000": "amazon_us",
        }

        for tracking_no, expected in cases.items():
            with self.subTest(tracking_no=tracking_no):
                self.assertEqual(decide_tracking_platform(tracking_no), expected)

    def test_unknown_prefix_falls_back_to_17track_en(self):
        self.assertEqual(decide_tracking_platform("LM123456789CN"), "17track_en")

    def test_decision_ignores_whitespace_and_case(self):
        self.assertEqual(decide_tracking_platform("  uus123456789  "), "uniuni")


if __name__ == "__main__":
    unittest.main()
