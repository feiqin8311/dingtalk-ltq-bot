# UPS Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the UPS placeholder with a real page query that extracts the current active progress-step status.

**Architecture:** Keep UPS narrow for this iteration: only parse the active progress-step from the UPS tracking detail page and map that single state into the existing unified result structure. Start with a pure HTML parser, then wrap it in the usual Playwright + CDP query path.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add `extract_ups_current_status_from_html`
  - Replace placeholder `query_ups_tracking`
- Create: `tests/test_ups_query.py`
  - Cover active-step parsing
- Modify: `tests/test_tracking_mode.py`
  - Add UPS helper route test

### Task 1: Add UPS HTML parsing tests

**Files:**
- Create: `tests/test_ups_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_ups_query.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_ups_query.py' -v`
Expected: FAIL because `extract_ups_current_status_from_html` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Requirements:

- Locate the `li` whose class contains `progress-step active`
- Require `aria-current="true"`
- Extract visible button/span text inside that node
- Return a cleaned string or empty string

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_ups_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ups_query.py logistics_query.py
git commit -m "test: cover ups tracking status parsing"
```

### Task 2: Add UPS route test and real browser query

**Files:**
- Modify: `tests/test_tracking_mode.py`
- Modify: `logistics_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_ups_query.py`

- [ ] **Step 1: Write the failing test**

```python
    async def test_query_tracking_number_routes_to_ups_helper(self):
        import logistics_query

        expected = {
            "平台": "UPS",
            "查询值": "1Z0VV9660319941066",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_ups_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("1Z0VV9660319941066")

        self.assertEqual(result, expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL if UPS routing is broken. If it already passes, keep it and proceed.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements for `query_ups_tracking`:

- Open:
  - `https://www.ups.com/track?tracknum=<tracking_no>`
- Wait for page load and short settle delay
- Read `page.content()`
- Parse current status with `extract_ups_current_status_from_html`
- Return:

```python
{
    "平台": "UPS",
    "查询值": normalized,
    "物流轨迹": [{"时间": "", "内容": status, "地点": ""}],
    "最新轨迹": {"时间": "", "内容": status, "地点": ""},
}
```

If no status:

```python
{
    "平台": "UPS",
    "查询值": normalized,
    "物流轨迹": [],
    "最新轨迹": {},
    "错误": "UPS 页面未返回当前物流状态",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_ups_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_ups_query.py tests/test_tracking_mode.py
git commit -m "feat: implement ups tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_ups_query.py`
- Test: `tests/test_usps_query.py`
- Test: `tests/test_gofo_query.py`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

Add one concise line to `OPERATIONS.md` stating that UPS now reads the active progress-step text from the UPS tracking detail page.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
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
git add OPERATIONS.md logistics_query.py tests/test_ups_query.py tests/test_usps_query.py tests/test_gofo_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify ups tracking integration"
```
