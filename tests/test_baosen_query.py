import unittest

import logistics_query


class ExtractBaosenTrackItemsTests(unittest.TestCase):
    def test_extract_baosen_track_items_uses_time_embedded_in_current_timeline(self):
        html = """
        <div class="trajectory-box">
          <ul class="el-timeline trajectory-line">
            <li class="el-timeline-item timeline">
              <div class="el-timeline-item__content">
                <div class="operation"><span>HZUK26070290 在 2026-08-12 10:08:31已离港 NINGBO CHINA。</span></div>
              </div>
              <div class="el-timeline-item__timestamp is-bottom"></div>
            </li>
            <li class="el-timeline-item timeline">
              <div class="el-timeline-item__content">
                <div class="operation"><span>HZUK26070290预计 2026-09-21 10:30:00到港</span></div>
              </div>
              <div class="el-timeline-item__timestamp is-bottom"></div>
            </li>
            <li class="el-timeline-item timeline">
              <div class="el-timeline-item__content">
                <div class="operation"><span>HZUK26070290 航次信息：OOCL FELIXSTOWE011W，订舱确认。</span></div>
              </div>
            </li>
          </ul>
        </div>
        """

        items = logistics_query.extract_baosen_track_items_from_html(html)

        self.assertEqual(
            items,
            [
                {"时间": "2026-08-12 10:08:31", "内容": "HZUK26070290 在 2026-08-12 10:08:31已离港 NINGBO CHINA。"},
                {"时间": "2026-09-21 10:30:00", "内容": "HZUK26070290预计 2026-09-21 10:30:00到港"},
                {"时间": "", "内容": "HZUK26070290 航次信息：OOCL FELIXSTOWE011W，订舱确认。"},
            ],
        )

    def test_extract_baosen_track_items_keeps_items_after_customs(self):
        html = """
        <ul class="el-timeline trajectory-line">
          <li class="el-timeline-item">
            <div class="title">清关管理</div>
          </li>
          <li class="el-timeline-item timeline">
            <div class="operation-time base-flex-between"><span>2026-04-08 13:51:18</span></div>
            <div class="operation"><span>HZNL26011928 在 2026-04-08 13:51:18 清关登记。</span></div>
          </li>
          <li class="el-timeline-item">
            <div class="title">海外仓-拆柜</div>
          </li>
          <li class="el-timeline-item timeline">
            <div class="operation-time base-flex-between"><span>2026-04-13 15:31:12</span></div>
            <div class="operation"><span>HZNL26011928 在 2026-04-13 09:31:17 完成提拆柜。</span></div>
          </li>
          <li class="el-timeline-item">
            <div class="title">海外仓-派送</div>
          </li>
          <li class="el-timeline-item timeline">
            <div class="operation-time base-flex-between"><span>2026-04-15 21:11:23</span></div>
            <div class="operation"><span>【卡车】HZNL26011928 &lt;FBA15LC8N3RR&gt; 在 2026-04-15 15:11 已出发，出发数量：82。</span></div>
          </li>
        </ul>
        """

        items = logistics_query.extract_baosen_track_items_from_html(html)

        self.assertEqual(
            items,
            [
                {"时间": "2026-04-08 13:51:18", "内容": "HZNL26011928 在 2026-04-08 13:51:18 清关登记。"},
                {"时间": "2026-04-13 15:31:12", "内容": "HZNL26011928 在 2026-04-13 09:31:17 完成提拆柜。"},
                {"时间": "2026-04-15 21:11:23", "内容": "【卡车】HZNL26011928 <FBA15LC8N3RR> 在 2026-04-15 15:11 已出发，出发数量：82。"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
