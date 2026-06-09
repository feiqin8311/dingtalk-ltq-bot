# Swiship Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Swiship placeholder with a real page query that returns both summary status and tracking-history events.

**Architecture:** Keep Swiship fully page-parsed: one pure helper for summary extraction, one for history extraction, then a Playwright wrapper that loads the direct tracking page and combines both outputs into the existing result shape with two extra summary fields.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add `extract_swiship_tracking_summary_from_html`
  - Add `extract_swiship_tracking_items_from_html`
  - Replace placeholder `query_swiship_tracking`
- Create: `tests/test_swiship_query.py`
  - Cover summary parsing and history parsing
- Modify: `tests/test_tracking_mode.py`
  - Add TBC / INTL / BNI route tests

### Task 1: Add Swiship parsing tests

**Files:**
- Create: `tests/test_swiship_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_swiship_query.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_swiship_query.py' -v`
Expected: FAIL because the Swiship helper functions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Requirements:

- `extract_swiship_tracking_summary_from_html`:
  - extract title text
  - extract summary status text
- `extract_swiship_tracking_items_from_html`:
  - track current date-group header
  - parse each event row into `时间 / 内容 / 地点`
  - compose `时间 = <date-group> <time>`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_swiship_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_swiship_query.py logistics_query.py
git commit -m "test: cover swiship tracking parsing"
```

### Task 2: Add Swiship route tests and real page query

**Files:**
- Modify: `tests/test_tracking_mode.py`
- Modify: `logistics_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_swiship_query.py`

- [ ] **Step 1: Write the failing test**

```python
    async def test_query_tracking_number_routes_to_swiship_helper_for_tbc(self):
        import logistics_query

        expected = {
            "平台": "SWISHIP_CA",
            "查询值": "TBC906468472009",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("TBC906468472009")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_swiship_helper_for_intl(self):
        import logistics_query
        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value={"平台": "SWISHIP_CA", "查询值": "INTL123456789", "物流轨迹": [], "最新轨迹": {}})):
            result = await logistics_query.query_tracking_number("INTL123456789")
        self.assertEqual(result["平台"], "SWISHIP_CA")

    async def test_query_tracking_number_routes_to_swiship_helper_for_bni(self):
        import logistics_query
        with patch.object(logistics_query, "query_swiship_tracking", new=AsyncMock(return_value={"平台": "SWISHIP_CA", "查询值": "BNI123456789", "物流轨迹": [], "最新轨迹": {}})):
            result = await logistics_query.query_tracking_number("BNI123456789")
        self.assertEqual(result["平台"], "SWISHIP_CA")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL if Swiship routing is broken. If it already passes, keep it and proceed.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements for `query_swiship_tracking`:

- Open:
  - `https://www.swiship.com/track?loc=en-US&id=<tracking_no>`
- Wait for page load and short settle delay
- Read `page.content()`
- Parse summary with `extract_swiship_tracking_summary_from_html`
- Parse items with `extract_swiship_tracking_items_from_html`
- If both summary and items are empty:
  - return structured error `Swiship 页面未返回轨迹信息`
- Else return:

```python
{
    "平台": "SWISHIP_CA",
    "查询值": normalized,
    "摘要标题": summary.get("摘要标题", ""),
    "摘要状态": summary.get("摘要状态", ""),
    "物流轨迹": items,
    "最新轨迹": items[0] if items else {},
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_swiship_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_swiship_query.py tests/test_tracking_mode.py
git commit -m "feat: implement swiship tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_swiship_query.py`
- Test: `tests/test_yuntrack_query.py`
- Test: `tests/test_ups_query.py`
- Test: `tests/test_usps_query.py`
- Test: `tests/test_gofo_query.py`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

Add one concise line to `OPERATIONS.md` stating that Swiship now reads summary status plus tracking-history rows from the page.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_swiship_query.py' -v
python3 -m unittest discover -s tests -p 'test_yuntrack_query.py' -v
python3 -m unittest discover -s tests -p 'test_ups_query.py' -v
python3 -m unittest discover -s tests -p 'test_usps_query.py' -v
python3 -m unittest discover -s tests -p 'test_gofo_query.py' -v
python3 -m unittest discover -s tests -p 'test_uniuni_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_platform_decision.py' -v
python3 -m unittest discover -s tests -p 'test_main_queue.py' -v
```

Expected: all PASS

- [ ] **Step 3: Fix remaining issues with minimal code**

Only if Step 2 fails, make the smallest correction needed.

- [ ] **Step 4: Re-run tests**

Run the same commands from Step 2.
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add OPERATIONS.md logistics_query.py tests/test_swiship_query.py tests/test_yuntrack_query.py tests/test_ups_query.py tests/test_usps_query.py tests/test_gofo_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify swiship tracking integration"
```
