# UNIUNI Export Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change UNIUNI tracking to export Excel from the detail page and build the result from the `Latest Track` column.

**Architecture:** Keep the current `UUS -> uniuni` routing and CDP browser flow intact, but replace page-HTML extraction inside `query_uniuni_tracking()` with a `More -> Download -> parse xlsx` pipeline. Reuse the existing runtime download directory layout and xlsx parsing style already used by GOFO and YunTrack.

**Tech Stack:** Python, Playwright async API, stdlib `zipfile/csv/xml`, unittest

---

### Task 1: Add UNIUNI export helper coverage

**Files:**
- Modify: `tests/test_uniuni_query.py`
- Test: `tests/test_uniuni_query.py`

- [ ] **Step 1: Write the failing tests**

Add helper coverage for:
- `build_uniuni_download_dir()`
- `build_uniuni_download_path()`
- `parse_uniuni_export_summary_xlsx()`
- query path with `More` retried once before `Download`

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_uniuni_query.py'`
Expected: FAIL because UNIUNI export helpers do not exist and query flow still uses HTML extraction.

- [ ] **Step 3: Write minimal implementation**

Add the UNIUNI download helpers and switch `query_uniuni_tracking()` to export parsing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_uniuni_query.py'`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_uniuni_query.py docs/superpowers/specs/2026-06-21-uniuni-export-tracking-design.md docs/superpowers/plans/2026-06-21-uniuni-export-tracking-implementation.md
git commit -m "feat: switch uniuni tracking to export download flow"
```

### Task 2: Verify broader impact

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_tracking_mode.py`

- [ ] **Step 1: Write the failing doc/test change if needed**

Add a short operation note that `UNIUNI` now reads exported Excel `Latest Track`.

- [ ] **Step 2: Run targeted verification**

Run: `python -m unittest discover -s tests -p 'test_tracking_mode.py'`
Expected: PASS

- [ ] **Step 3: Apply minimal doc update**

Update the UNIUNI bullet in `OPERATIONS.md`.

- [ ] **Step 4: Run focused regression tests**

Run:
- `python -m unittest discover -s tests -p 'test_uniuni_query.py'`
- `python -m unittest discover -s tests -p 'test_tracking_mode.py'`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add OPERATIONS.md tests/test_tracking_mode.py
git commit -m "docs: record uniuni export tracking flow"
```
