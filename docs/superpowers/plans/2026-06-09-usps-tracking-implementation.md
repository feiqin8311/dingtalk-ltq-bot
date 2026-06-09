# USPS Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the USPS placeholder with a real page parser that returns the current and historical `tb-step` tracking items.

**Architecture:** Keep the existing prefix router unchanged and implement USPS entirely inside `logistics_query.py`. First add a pure HTML parser for `tb-step` blocks, then wrap it with a Playwright query that loads the direct USPS tracking URL and returns the normalized event list.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add `extract_usps_tracking_items_from_html`.
  - Replace the placeholder `query_usps_tracking` with a real async browser query.
- Create: `tests/test_usps_query.py`
  - Cover USPS HTML parsing.
- Modify: `tests/test_tracking_mode.py`
  - Add a route test for USPS helper dispatch.

### Task 1: Add USPS HTML parsing tests

**Files:**
- Create: `tests/test_usps_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_usps_query.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from logistics_query import extract_usps_tracking_items_from_html


USPS_HTML = """
<div>
  <div class="tb-step current-step">
    <span class="bar-fill-animation"></span>
    <p class="tb-status">USPS 等待物品</p>
    <p class="tb-status-detail">寄件标签已创建</p>
    <p class="tb-location">HOUSTON, TX 77041 </p>
    <p class="tb-date">2026 年 06 月 08 日 3:40 下午</p>
  </div>
  <div class="tb-step"><div>
    <p class="tb-status-detail">发送给 USPS 的寄件前信息 </p>
    <p class="tb-location"></p>
    <p class="tb-date">2026 年 06 月 08 日</p>
  </div></div>
</div>
"""


class UspsQueryParsingTests(unittest.TestCase):
    def test_extract_usps_tracking_items_reads_current_and_history_steps(self):
        items = extract_usps_tracking_items_from_html(USPS_HTML)

        self.assertEqual(
            items,
            [
                {
                    "时间": "2026 年 06 月 08 日 3:40 下午",
                    "内容": "USPS 等待物品 - 寄件标签已创建",
                    "地点": "HOUSTON, TX 77041",
                },
                {
                    "时间": "2026 年 06 月 08 日",
                    "内容": "发送给 USPS 的寄件前信息",
                    "地点": "",
                },
            ],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_usps_query.py' -v`
Expected: FAIL because `extract_usps_tracking_items_from_html` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Requirements:

- Parse every `tb-step` block in page order.
- Extract:
  - `tb-status`
  - `tb-status-detail`
  - `tb-location`
  - `tb-date`
- Build `内容` with:
  - `<status> - <detail>` if both exist
  - otherwise whichever exists
- Skip only fully empty blocks.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_usps_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_usps_query.py logistics_query.py
git commit -m "test: cover usps tracking html parsing"
```

### Task 2: Add USPS route test and real browser query

**Files:**
- Modify: `tests/test_tracking_mode.py`
- Modify: `logistics_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_usps_query.py`

- [ ] **Step 1: Write the failing test**

```python
    async def test_query_tracking_number_routes_to_usps_helper(self):
        import logistics_query

        expected = {
            "平台": "USPS",
            "查询值": "9214490411372861932437",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_usps_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("9214490411372861932437")

        self.assertEqual(result, expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL if USPS routing is missing. If it already passes, keep it as the route safety net and proceed.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements for `query_usps_tracking`:

- Open:
  - `https://zh-tools.usps.com/tracking/<tracking_no>`
- Wait for page load and a short settle delay.
- Read `page.content()`
- Parse with `extract_usps_tracking_items_from_html`
- Return:

```python
{
    "平台": "USPS",
    "查询值": normalized,
    "物流轨迹": items,
    "最新轨迹": items[0],
}
```

If no items:

```python
{
    "平台": "USPS",
    "查询值": normalized,
    "物流轨迹": [],
    "最新轨迹": {},
    "错误": "USPS 页面未返回轨迹信息",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_usps_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_usps_query.py tests/test_tracking_mode.py
git commit -m "feat: implement usps tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_usps_query.py`
- Test: `tests/test_gofo_query.py`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

Add one concise line to `OPERATIONS.md` stating that USPS now reads all `tb-step` status blocks from the USPS tracking detail page.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
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
git add OPERATIONS.md logistics_query.py tests/test_usps_query.py tests/test_gofo_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify usps tracking integration"
```
