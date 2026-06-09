import unittest

from logistics_query import (
    extract_amazon_us_not_found_error_from_html,
    extract_amazon_us_status_from_html,
)


class AmazonUsQueryParsingTests(unittest.TestCase):
    def test_extract_arriving_status_title(self):
        html = '<h1 class="css-alxyr3" mdn-text="">Arriving tomorrow</h1>'

        self.assertEqual(extract_amazon_us_status_from_html(html), "Arriving tomorrow")

    def test_extract_delivered_status_title(self):
        html = '<h1 class="css-alxyr3" mdn-text="">Delivered Tuesday, June 9, 5:23 AM</h1>'

        self.assertEqual(
            extract_amazon_us_status_from_html(html),
            "Delivered Tuesday, June 9, 5:23 AM",
        )

    def test_extract_status_title_from_generic_h1(self):
        html = '<h1 class="other-heading" mdn-text="">Package delayed</h1>'

        self.assertEqual(
            extract_amazon_us_status_from_html(html),
            "Package delayed",
        )

    def test_extract_not_found_error_message(self):
        html = """
        <div class="css-1jlcqid" role="alert" aria-describedby="alert-1-children">
          <div mdn-text="">
            <div mdn-alert-message="" id="alert-1-children">
              <div class="css-1m2ifrf">
                <h2 class="css-3v0dvo" mdn-text=""><span>We're sorry</span></h2>
                <p class="css-1u30ppu _2VpQZN" mdn-text="">
                  <span>We couldn't find the package you're looking for</span>
                </p>
              </div>
            </div>
          </div>
        </div>
        """

        self.assertEqual(
            extract_amazon_us_not_found_error_from_html(html),
            "We're sorry We couldn't find the package you're looking for",
        )

    def test_extract_not_found_error_message_returns_empty_when_absent(self):
        html = '<h1 class="css-alxyr3" mdn-text="">Arriving tomorrow</h1>'

        self.assertEqual(extract_amazon_us_not_found_error_from_html(html), "")


if __name__ == "__main__":
    unittest.main()
