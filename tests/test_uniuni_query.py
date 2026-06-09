import unittest

from logistics_query import extract_uniuni_tracking_items_from_html


UNIUNI_HTML = """
<div data-v-21bdb846="" style="margin-top:10px; margin-bottom:40px">
  <div class="edd-block">
    <div class="edd-unavailable">Estimated delivery will be available once your parcel arrives at UniUni's facility.</div>
  </div>
  <div class="tracking-large">
    <div style="display: flex; align-items: center;">
      <div class="date-time-large"><div>17:00:37</div></div>
      <div style="display: flex; align-items: center;">
        <div class="status-title">Parcel scanned at the pickup location.</div>
      </div>
    </div>
    <div style="display: flex;">
      <div style="width: 180px; text-align: end; margin-right: 30px;">2026-06-08</div>
      <div><div class="path-description" style="margin-left: 7px;"><div>Houston TX</div><div></div></div></div>
    </div>
  </div>
  <div class="tracking-small">
    <span class="status-title">17:00:37</span>
    <div class="status-title-small">Parcel scanned at the pickup location.</div>
  </div>
  <div class="tracking-large">
    <div style="display: flex; align-items: center;">
      <div class="date-time-large"><div>16:48:19</div></div>
      <div style="display: flex; align-items: center;">
        <div class="status-title">Driver has arrived at the pickup location.</div>
      </div>
    </div>
    <div style="display: flex;">
      <div style="width: 180px; text-align: end; margin-right: 30px;">2026-06-08</div>
      <div><div class="path-description" style="margin-left: 7px;"><div>Houston TX</div><div></div></div></div>
    </div>
  </div>
  <div class="tracking-large">
    <div style="display: flex; align-items: center;">
      <div class="date-time-large"><div>06:39:12</div></div>
      <div style="display: flex; align-items: center;">
        <div class="status-title">Order received.</div>
      </div>
    </div>
    <div style="display: flex;">
      <div style="width: 180px; text-align: end; margin-right: 30px;">2026-06-08 (UTC)</div>
      <div><div class="path-description-last" style="margin-left: 7px;"><div>UNI DATA CENTER</div><div></div></div></div>
    </div>
  </div>
  <div style="font-size: 18px; margin-top: 20px;">
    <a href="https://www.uniuni.com/support/" class="link-class">Contact Customer Service</a> for Help
  </div>
</div>
"""


class UniUniQueryParsingTests(unittest.TestCase):
    def test_extract_uniuni_tracking_items_ignores_non_tracking_content(self):
        items = extract_uniuni_tracking_items_from_html(UNIUNI_HTML)

        self.assertEqual(len(items), 3)
        self.assertEqual(
            items[0],
            {
                "时间": "2026-06-08 17:00:37",
                "内容": "Parcel scanned at the pickup location.",
                "地点": "Houston TX",
            },
        )
        self.assertEqual(items[1]["内容"], "Driver has arrived at the pickup location.")
        self.assertEqual(items[2]["时间"], "2026-06-08 (UTC) 06:39:12")
        joined = " ".join(
            " ".join(str(value) for value in item.values())
            for item in items
        )
        self.assertNotIn("Estimated delivery will be available", joined)
        self.assertNotIn("Contact Customer Service", joined)


if __name__ == "__main__":
    unittest.main()
