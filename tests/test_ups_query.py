import unittest

from logistics_query import extract_ups_current_status_from_html


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


class UpsQueryParsingTests(unittest.TestCase):
    def test_extract_ups_current_status_from_html_reads_active_step(self):
        status = extract_ups_current_status_from_html(UPS_HTML)
        self.assertEqual(status, "We Have Your Package")


if __name__ == "__main__":
    unittest.main()
