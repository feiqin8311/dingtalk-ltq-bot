import unittest

from logistics_query import (
    extract_ups_current_status_from_html,
    extract_ups_latest_time_from_html,
)


UPS_HTML = """
<div class="col-lg-12 col-md-12 col-sm-12 mx-auto">
  <ol role="horizontal" aria-label="horizontal Progress Steps" class="progress-steps-container horizontalstepdisabled mobile-vertical ng-star-inserted">
    <li class="px-2 progress-step completed ng-star-inserted" aria-current="false">
      <button type="button" class="horizontalstep-aligner step-label currentsteplabel ups-cta ups-cta-tertiary mt-0 mr-0 currentstephorizontal text-decoration-none font-weight-normal disabled" aria-label="Complete Label Created">Label Created </button>
    </li>
    <li class="px-2 progress-step active ng-star-inserted" aria-current="true">
      <div class="horizontalstep-aligner">
        <button class="horizontalstep-aligner step-label currentsteplabel ups-cta ups-cta-tertiary mt-0 mr-0 currentstephorizontal step-label"><span>We Have Your Package </span></button>
      </div>
    </li>
    <li class="px-2 progress-step inactive ng-star-inserted" aria-current="false">
      <div class="horizontalstep-aligner">
        <button class="horizontalstep-aligner step-label currentsteplabel ups-cta ups-cta-tertiary mt-0 mr-0 currentstephorizontal step-label"><span>On the Way </span></button>
      </div>
    </li>
  </ol>
</div>
"""

UPS_TIME_HTML = """
<div class="ups-card">
  <span>Delivered On</span>
  <span>Jun 18, 2026 at 3:42 P.M.</span>
</div>
"""

UPS_SCHEDULED_HTML = """
<div class="ups-card">
  <div>Scheduled Delivery</div>
  <div>06/18/2026, 1:15 P.M.</div>
</div>
"""

UPS_LAST_LOCATION_HTML = """
<p id="stApp_lastLocationDateTime"> Flint, MI, United States, 06/20/2026, 6:08 A.M. </p>
"""

UPS_ESTIMATED_SECTION_HTML = """
<div id="estimatedDeliverySection">
  <p class="mb-0">
    <span class="d-inline-block text-nowrap mr-1 ups-txt_size_double">
      Tomorrow,
      June
      22
    </span>
    <span class="d-inline-block text-nowrap ups-txt_size_double">
      <span id="stApp_packageStatusTimeLbl_time">
        by 9:00 P.M.
      </span>
    </span>
  </p>
</div>
"""


class UpsQueryParsingTests(unittest.TestCase):
    def test_extract_ups_current_status_from_html_reads_active_step(self):
        status = extract_ups_current_status_from_html(UPS_HTML)
        self.assertEqual(status, "We Have Your Package")

    def test_extract_ups_latest_time_from_html_reads_delivered_on_value(self):
        value = extract_ups_latest_time_from_html(UPS_TIME_HTML)
        self.assertEqual(value, "Jun 18, 2026 at 3:42 P.M.")

    def test_extract_ups_latest_time_from_html_reads_scheduled_delivery_value(self):
        value = extract_ups_latest_time_from_html(UPS_SCHEDULED_HTML)
        self.assertEqual(value, "06/18/2026, 1:15 P.M.")

    def test_extract_ups_latest_time_from_html_prefers_last_location_datetime(self):
        value = extract_ups_latest_time_from_html(UPS_LAST_LOCATION_HTML)
        self.assertEqual(value, "06/20/2026, 6:08 A.M.")

    def test_extract_ups_latest_time_from_html_falls_back_to_estimated_delivery_section(self):
        value = extract_ups_latest_time_from_html(UPS_ESTIMATED_SECTION_HTML)
        self.assertEqual(value, "Tomorrow, June 22 by 9:00 P.M.")


if __name__ == "__main__":
    unittest.main()
