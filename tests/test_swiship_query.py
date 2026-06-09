import unittest

from logistics_query import (
    extract_swiship_tracking_items_from_html,
    extract_swiship_tracking_summary_from_html,
)


SWISHIP_HTML = """
<div class="css-k57vob css-1u4jz8b" role="region">
  <div class="css-gvrnls"><p class="css-nv2jk2" mdn-text=""> 1 item arrives</p></div>
  <div class="css-163ns6o"><p class="css-1qtjq54" mdn-text="">In-Transit. Delivery  June 11</p></div>
  <p class="css-p6zxe3" mdn-text="">TRACKING HISTORY</p>
  <div class="css-1kxonj9">
    <table class="css-ayloq6">
      <tbody>
        <tr class="css-xlf10u">
          <th class="css-149auxl" colspan="100" scope="colgroup"><span><p class="css-1qtjq54 eventText" mdn-text="">June 9</p></span></th>
        </tr>
        <tr class="css-xlf10u">
          <td class="css-14tsgjy"><span><p class="css-1qtjq54" mdn-text="">10:14 am <span>CST</span></p></span></td>
          <td class="css-1copoy9"><span><p class="css-1qtjq54" mdn-text="">Package left an Amazon facility. </p></span></td>
          <td class="css-pg5h5h"><span><p class="css-1qtjq54" mdn-text="">Hamilton, ON, CA</p></span></td>
        </tr>
        <tr class="css-xlf10u">
          <td class="css-14tsgjy"><span><p class="css-1qtjq54" mdn-text="">5:31 am <span>CST</span></p></span></td>
          <td class="css-1copoy9"><span><p class="css-1qtjq54" mdn-text="">Package arrived at an Amazon facility. </p></span></td>
          <td class="css-pg5h5h"><span><p class="css-1qtjq54" mdn-text="">Hamilton, ON, CA</p></span></td>
        </tr>
        <tr class="css-xlf10u">
          <td class="css-14tsgjy"><span><p class="css-1qtjq54" mdn-text="">2:26 am <span>CST</span></p></span></td>
          <td class="css-1copoy9"><span><p class="css-1qtjq54" mdn-text="">Carrier picked up the package. </p></span></td>
          <td class="css-pg5h5h"><span><p class="css-1qtjq54" mdn-text=""></p></span></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""


class SwishipQueryParsingTests(unittest.TestCase):
    def test_extract_swiship_summary_and_items(self):
        summary = extract_swiship_tracking_summary_from_html(SWISHIP_HTML)
        items = extract_swiship_tracking_items_from_html(SWISHIP_HTML)

        self.assertEqual(summary["摘要标题"], "1 item arrives")
        self.assertEqual(summary["摘要状态"], "In-Transit. Delivery June 11")
        self.assertEqual(
            items,
            [
                {
                    "时间": "June 9 10:14 am CST",
                    "内容": "Package left an Amazon facility.",
                    "地点": "Hamilton, ON, CA",
                },
                {
                    "时间": "June 9 5:31 am CST",
                    "内容": "Package arrived at an Amazon facility.",
                    "地点": "Hamilton, ON, CA",
                },
                {
                    "时间": "June 9 2:26 am CST",
                    "内容": "Carrier picked up the package.",
                    "地点": "",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
