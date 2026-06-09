# UNIUNI Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `uniuni` tracking placeholder with a real Playwright-backed page query that extracts and cleans UniUni tracking events.

**Architecture:** Keep the current tracking-mode router intact and only deepen the `query_uniuni_tracking` path inside `logistics_query.py`. Split the work into a pure HTML parser first, then a browser query wrapper that loads the direct tracking URL, clicks the matching tracking number, retries once if needed, and returns the normalized event structure already used by the rest of the bot.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add `extract_uniuni_tracking_items_from_html`.
  - Replace the placeholder `query_uniuni_tracking` with a real async browser implementation.
- Create: `tests/test_uniuni_query.py`
  - Cover HTML parsing and content cleanup.
- Modify: `tests/test_tracking_mode.py`
  - Keep the existing route test and add a direct `query_uniuni_tracking` retry-path test only if a pure unit seam is available.

### Task 1: Add UniUni HTML parsing tests

**Files:**
- Create: `tests/test_uniuni_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_uniuni_query.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_uniuni_query.py' -v`
Expected: FAIL with `ImportError` because `extract_uniuni_tracking_items_from_html` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implementation sketch:

```python
def extract_uniuni_tracking_items_from_html(html: str) -> list[dict[str, str]]:
    blocks = re.findall(r'<div[^>]*class="tracking-large"[^>]*>(.*?)</div>\s*</div>', html, flags=re.S)
    items: list[dict[str, str]] = []
    for block in blocks:
        time_match = re.search(r'<div[^>]*class="date-time-large"[^>]*>\s*<div[^>]*>\s*([^<]+?)\s*</div>', block, flags=re.S)
        status_match = re.search(r'<div[^>]*class="status-title"[^>]*>\s*([^<]+?)\s*</div>', block, flags=re.S)
        date_match = re.search(r'text-align:\s*end;[^>]*>\s*([^<]+?)\s*</div>', block, flags=re.S)
        location_matches = re.findall(r'<div>\s*([^<]*?)\s*</div>', block, flags=re.S)
        ...
```

Requirements for the implementation:

- Only parse `tracking-large` blocks.
- Ignore `tracking-small`.
- Keep the parser pure and deterministic.
- Use `unescape()` and `clean_text()` on extracted fields.
- Return items in page order.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_uniuni_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_uniuni_query.py logistics_query.py
git commit -m "test: cover uniuni tracking html parsing"
```

### Task 2: Replace the UniUni placeholder query with a real browser query

**Files:**
- Modify: `logistics_query.py`
- Modify: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_uniuni_query.py`

- [ ] **Step 1: Write the failing test**

Add a route-level assertion that the real helper still gets called:

```python
    async def test_query_tracking_number_routes_to_uniuni_helper(self):
        import logistics_query

        expected = {
            "平台": "UNIUNI",
            "查询值": "UUS123456789",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_uniuni_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("UUS123456789")

        self.assertEqual(result, expected)
```

If you add a retry seam such as `_open_uniuni_tracking_page`, add a focused unit test for “no tracks after first click -> click once more”.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL only if the route test was changed or the helper signature no longer matches. If it already passes, keep it as the safety net and proceed to Step 3.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements:

```python
async def query_uniuni_tracking(tracking_no: str) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    query_url = f"https://www.uniuni.com//tracking#tracking-detail?no={tracking_no}"
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(query_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1500)
            tracking_locator = page.get_by_text(tracking_no, exact=True).first
            await tracking_locator.click(timeout=10000)
            await page.wait_for_timeout(1500)
            html = await page.content()
            items = extract_uniuni_tracking_items_from_html(html)
            if not items:
                await tracking_locator.click(timeout=10000)
                await page.wait_for_timeout(1500)
                html = await page.content()
                items = extract_uniuni_tracking_items_from_html(html)
            ...
        finally:
            await page.close()
```

Return rules:

- If `items` exists:
  - `平台: UNIUNI`
  - `查询值: tracking_no`
  - `物流轨迹: items`
  - `最新轨迹: items[0]`
- If no click target:
  - return structured error `未找到 UNIUNI 跟踪号结果`
- If two clicks still yield no items:
  - return structured error `UNIUNI 页面未返回轨迹信息`

Keep the browser context handling consistent with current project style:

- Reuse existing CDP browser.
- Close only the page you open.
- Do not close the shared browser.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_uniuni_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py
git commit -m "feat: implement uniuni tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

If implementation details changed the current tracking-platform notes, add a short line to `OPERATIONS.md` noting that `uniuni` now uses a direct tracking-detail URL and extracts events from the UniUni page.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_uniuni_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_platform_decision.py' -v
python3 -m unittest discover -s tests -p 'test_main_queue.py' -v
```

Expected: all PASS

- [ ] **Step 3: Fix remaining issues with minimal code**

Only if Step 2 fails, make the smallest correction needed.

- [ ] **Step 4: Re-run tests**

Run the same four commands from Step 2.
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add OPERATIONS.md logistics_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify uniuni tracking integration"
```
