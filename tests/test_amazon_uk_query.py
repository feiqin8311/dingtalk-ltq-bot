import unittest

from logistics_query import (
    extract_amazon_uk_summary_from_html,
    extract_amazon_uk_tracking_items_from_html,
)


AMAZON_UK_HTML = """
<div class="css-dsf1ob">
  <h3 class="css-p7vi71" mdn-text=""><span>由亚马逊配送</span></h3>
  <h5 class="css-176mvq0" mdn-text=""><span>追踪编号：UK4413632304</span></h5>
  <div class="css-1xz1o3r"><p class="css-1bhbd4d" mdn-text="">6月8日，星期一</p></div>
  <div class="css-193enz3">
    <div class="css-dsf1ob"><p class="css-1bhbd4d" mdn-text="">19:34</p></div>
    <div class="css-dsf1ob">
      <p class="css-1bhbd4d _3jMMC2" mdn-text="">
        <div class="css-1xz1o3r">标签已创建</div>
        <div class="css-1xz1o3r"><i>英国伯明翰萨顿科尔菲尔德</i></div>
      </p>
    </div>
  </div>
  <div class="css-193enz3">
    <div class="css-dsf1ob"><p class="css-1bhbd4d" mdn-text="">19:34</p></div>
    <div class="css-dsf1ob">
      <p class="css-1bhbd4d _3jMMC2" mdn-text="">
        <div class="css-1xz1o3r">包裹已到达承运商仓库</div>
        <div class="css-1xz1o3r"><i>英国伯明翰萨顿科尔菲尔德</i></div>
      </p>
    </div>
  </div>
  <div class="css-193enz3">
    <div class="css-dsf1ob"><p class="css-1bhbd4d" mdn-text="">23:30</p></div>
    <div class="css-dsf1ob">
      <p class="css-1bhbd4d _3jMMC2" mdn-text="">
        <div class="css-1xz1o3r">包裹已离开承运商仓库</div>
        <div class="css-1xz1o3r"><i>英国伯明翰萨顿科尔菲尔德</i></div>
      </p>
    </div>
  </div>
  <div class="css-1xz1o3r"><p class="css-1bhbd4d" mdn-text="">6月9日，星期二</p></div>
  <div class="css-193enz3">
    <div class="css-dsf1ob"><p class="css-1bhbd4d" mdn-text="">09:32</p></div>
    <div class="css-dsf1ob">
      <p class="css-1bhbd4d _3jMMC2" mdn-text="">
        <div class="css-1xz1o3r">包裹已到达最终配送中心/派送站</div>
        <div class="css-1xz1o3r"><i>英国德文郡普利茅斯</i></div>
      </p>
    </div>
  </div>
  <p class="css-1bhbd4d" mdn-text=""><i>时间以当地时区显示</i></p>
</div>
"""

AMAZON_UK_SUMMARY_HTML = """
<section id="tracker-app">
  <div class="css-152ekj">
    <div class="css-dsf1ob">
      <h1 class="css-alxyr3" mdn-text="">Label Created</h1>
      <div class="css-cfbaop">
        <div class="css-1e2l6d8">
          <div class="css-w98r6t">
            <div class="css-152ekj">
              <p class="css-1bhbd4d _2VpQZN" mdn-text="">
                <div class="css-9j97m5">
                  <div class="css-12kg56l">
                    <div>A shipping label has been created. Tracking details will be available once your package reaches our facility. Please check back soon!</div>
                  </div>
                </div>
              </p>
            </div>
          </div>
        </div>
        <button type="button" class="SNqzD- css-mah6cr"><span>See all updates (4)</span></button>
      </div>
    </div>
  </div>
</section>
"""


class AmazonUkQueryParsingTests(unittest.TestCase):
    def test_extract_amazon_uk_summary(self):
        self.assertEqual(
            extract_amazon_uk_summary_from_html(AMAZON_UK_SUMMARY_HTML),
            {
                "状态": "Label Created",
                "说明": "A shipping label has been created. Tracking details will be available once your package reaches our facility. Please check back soon!",
            },
        )

    def test_extract_amazon_uk_tracking_items(self):
        self.assertEqual(
            extract_amazon_uk_tracking_items_from_html(AMAZON_UK_HTML),
            [
                {"时间": "6月9日，星期二 09:32", "内容": "包裹已到达最终配送中心/派送站", "地点": "英国德文郡普利茅斯"},
                {"时间": "6月8日，星期一 23:30", "内容": "包裹已离开承运商仓库", "地点": "英国伯明翰萨顿科尔菲尔德"},
                {"时间": "6月8日，星期一 19:34", "内容": "包裹已到达承运商仓库", "地点": "英国伯明翰萨顿科尔菲尔德"},
                {"时间": "6月8日，星期一 19:34", "内容": "标签已创建", "地点": "英国伯明翰萨顿科尔菲尔德"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
