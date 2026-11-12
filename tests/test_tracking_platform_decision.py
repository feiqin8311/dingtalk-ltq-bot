import unittest

from logistics_query import decide_platform, decide_tracking_platform, extract_yinghe_track_items_from_html


class TrackingPlatformDecisionTests(unittest.TestCase):
    def test_known_prefixes_route_to_expected_platforms(self):
        cases = {
            "UUS123456789": "uniuni",
            "GFUS123456789": "gofo",
            "9123456789012345678901": "usps",
            "1Z0123456799999999": "ups",
            "YT123456789": "yuntrack",
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
        self.assertEqual(decide_tracking_platform("H00RVA123456789"), "17track_en")
        self.assertEqual(decide_tracking_platform("GV123456789US"), "17track_en")

    def test_decision_ignores_whitespace_and_case(self):
        self.assertEqual(decide_tracking_platform("  uus123456789  "), "uniuni")

    def test_yinghe_carrier_routes_to_yinghe(self):
        self.assertEqual(decide_platform({'货代公司': '盈和'}, 'auto'), 'yinghe')

    def test_extract_yinghe_timeline(self):
        html = '''
        <ul class="el-timeline">
          <li class="el-timeline-item">
            <div class="el-timeline-item__timestamp is-top">2026-07-03 08:35</div>
            <div class="el-timeline-item__content">运单签收</div>
          </li>
          <li class="el-timeline-item">
            <div class="el-timeline-item__timestamp is-top">2026-06-26 09:28</div>
            <div class="el-timeline-item__content">预计预约当地时间入仓</div>
          </li>
        </ul>
        '''
        self.assertEqual(
            extract_yinghe_track_items_from_html(html),
            [
                {'时间': '2026-07-03 08:35', '内容': '运单签收'},
                {'时间': '2026-06-26 09:28', '内容': '预计预约当地时间入仓'},
            ],
        )


if __name__ == "__main__":
    unittest.main()
