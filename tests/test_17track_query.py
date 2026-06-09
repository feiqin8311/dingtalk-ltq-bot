import unittest

from logistics_query import extract_17track_items_from_html


TRACK_17_HTML = """
<div class="relative">
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-primary font-medium">
        <span class="inline-block w-[130px] yq-time">2026-05-27 12:56</span>
        <span class="flex-1">Delivered, Delivered.</span>
      </div>
    </div>
  </div>
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-secondary">
        <span class="inline-block w-[130px] yq-time">2026-05-26 16:55</span>
        <span class="flex-1">Delivery, 【Melbourne Center】Shipment out for delivery.</span>
      </div>
    </div>
  </div>
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-secondary">
        <span class="inline-block w-[130px] yq-time">2026-05-26 16:31</span>
        <span class="flex-1">Delivery, 【Melbourne Center】Dispatch task assigned to DA.</span>
      </div>
    </div>
  </div>
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-secondary">
        <span class="inline-block w-[130px] yq-time">2026-05-25 16:09</span>
        <span class="flex-1">Delivery, 【Melbourne Center】Arrived.</span>
      </div>
    </div>
  </div>
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-secondary">
        <span class="inline-block w-[130px] yq-time">2026-05-25 16:09</span>
        <span class="flex-1">Delivery, 【Melbourne Center】Received.</span>
      </div>
    </div>
  </div>
  <div class="flex gap-3 relative min-h-7 mb-[1px]">
    <div class="pt-1">
      <div class="text-sm flex max-[767px]:flex-col-reverse text-text-secondary">
        <span class="inline-block w-[130px] yq-time">2026-05-19 01:58</span>
        <span class="flex-1">Order Creation, Order Submited.</span>
      </div>
    </div>
  </div>
</div>
"""


class Track17QueryParsingTests(unittest.TestCase):
    def test_extract_17track_items_from_new_timeline_html(self):
        self.assertEqual(
            extract_17track_items_from_html(TRACK_17_HTML),
            [
                {"时间": "2026-05-27 12:56", "内容": "Delivered, Delivered."},
                {"时间": "2026-05-26 16:55", "内容": "Delivery, 【Melbourne Center】Shipment out for delivery."},
                {"时间": "2026-05-26 16:31", "内容": "Delivery, 【Melbourne Center】Dispatch task assigned to DA."},
                {"时间": "2026-05-25 16:09", "内容": "Delivery, 【Melbourne Center】Arrived."},
                {"时间": "2026-05-25 16:09", "内容": "Delivery, 【Melbourne Center】Received."},
                {"时间": "2026-05-19 01:58", "内容": "Order Creation, Order Submited."},
            ],
        )


if __name__ == "__main__":
    unittest.main()
