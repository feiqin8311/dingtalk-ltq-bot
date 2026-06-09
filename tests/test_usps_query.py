import unittest

from logistics_query import (
    extract_usps_tracking_items_from_html,
    is_usps_blocked_page_html,
)


USPS_HTML = """
<div>
  <div class="tb-step current-step">
    <span class="bar-fill-animation"></span>
    <p class="tb-status">USPS 等待物品</p>
    <p class="tb-status-detail">寄件标签已创建</p>
    <p class="tb-location">HOUSTON, TX 77041 </p>
    <p class="tb-date">2026 年 06 月 08 日 3:40 下午</p>
  </div>
  <div class="tb-step"><div>
    <p class="tb-status-detail">发送给 USPS 的寄件前信息 </p>
    <p class="tb-location"></p>
    <p class="tb-date">2026 年 06 月 08 日</p>
  </div></div>
</div>
"""

USPS_BLOCKED_HTML = """
<!DOCTYPE html><html><head>
  <title></title>
</head>
<body>
  <script>
    var vendor = "akamai";
    var note = "bot detection";
  </script>
</body>
</html>
"""


class UspsQueryParsingTests(unittest.TestCase):
    def test_detects_usps_blocked_blank_page(self):
        self.assertTrue(is_usps_blocked_page_html(USPS_BLOCKED_HTML))

    def test_extract_usps_tracking_items_reads_current_and_history_steps(self):
        items = extract_usps_tracking_items_from_html(USPS_HTML)

        self.assertEqual(
            items,
            [
                {
                    "时间": "2026 年 06 月 08 日 3:40 下午",
                    "内容": "USPS 等待物品 - 寄件标签已创建",
                    "地点": "HOUSTON, TX 77041",
                },
                {
                    "时间": "2026 年 06 月 08 日",
                    "内容": "发送给 USPS 的寄件前信息",
                    "地点": "",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
