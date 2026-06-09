# GOFO Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `gofo` tracking placeholder with a real export-driven query that downloads the summary workbook and returns the `Current status` field.

**Architecture:** Keep the existing prefix router unchanged and implement the feature only inside `query_gofo_tracking` plus a few pure helpers in `logistics_query.py`. Use Playwright only for page navigation and file download; use Python standard-library XLSX parsing so the project does not need a new dependency.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, `zipfile`, `xml.etree.ElementTree`, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add GOFO download-directory helpers.
  - Add pure XLSX parsing helpers.
  - Replace the placeholder `query_gofo_tracking` with a real export workflow.
- Create: `tests/test_gofo_query.py`
  - Cover download path building and workbook parsing.
- Modify: `tests/test_tracking_mode.py`
  - Add a `GFUS` route test for `query_gofo_tracking`.

### Task 1: Add GOFO pure helper tests

**Files:**
- Create: `tests/test_gofo_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_gofo_query.py`

- [ ] **Step 1: Write the failing test**

```python
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import tempfile
import unittest

from logistics_query import (
    build_gofo_download_dir,
    build_gofo_download_path,
    parse_gofo_export_summary_xlsx,
)


def _build_xlsx_bytes(headers, row):
    shared_strings = "".join(f"<si><t>{value}</t></si>" for value in [*headers, *row])
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
    </workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
      <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
    </Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
      <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
    </Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
    </Relationships>"""
    cells = []
    for index in range(len(headers)):
        column = chr(ord("A") + index)
        cells.append(f'<c r="{column}1" t="s"><v>{index}</v></c>')
    for index in range(len(row)):
        column = chr(ord("A") + index)
        cells.append(f'<c r="{column}2" t="s"><v>{len(headers) + index}</v></c>')
    sheet = f'''<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1">{"".join(cells[:len(headers)])}</row><row r="2">{"".join(cells[len(headers):])}</row></sheetData>
    </worksheet>'''

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/sharedStrings.xml", f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared_strings}</sst>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class GofoQueryHelperTests(unittest.TestCase):
    def test_build_gofo_download_path_uses_date_platform_and_tracking_number(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            directory = build_gofo_download_dir(base_dir=base, day_text="2026-06-09")
            target = build_gofo_download_path("GFUS01055496346945", base_dir=base, day_text="2026-06-09")

        self.assertEqual(directory, base / "tracking-downloads" / "2026-06-09" / "gofo")
        self.assertEqual(target.name, "GFUS01055496346945-gofo-summary.xlsx")

    def test_parse_gofo_export_summary_xlsx_reads_current_status(self):
        payload = _build_xlsx_bytes(
            ["Tracking Number", "Waybill No", "Current status", "Last Event"],
            ["OBS0822606080XV1198082", "GFUS01055496346945", "Transit", "2026/06/08 14:34:35 Arrived at GOFO Regional Hub"],
        )

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            row = parse_gofo_export_summary_xlsx(Path(temp_file.name))

        self.assertEqual(row["Current status"], "Transit")
        self.assertEqual(row["Waybill No"], "GFUS01055496346945")

    def test_parse_gofo_export_summary_xlsx_requires_current_status(self):
        payload = _build_xlsx_bytes(["Tracking Number", "Waybill No"], ["OBS", "GFUS01055496346945"])

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            with self.assertRaisesRegex(RuntimeError, "Current status"):
                parse_gofo_export_summary_xlsx(Path(temp_file.name))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_gofo_query.py' -v`
Expected: FAIL because the helper functions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Requirements:

- Add `build_gofo_download_dir(base_dir: Path | None = None, day_text: str | None = None) -> Path`
- Add `build_gofo_download_path(tracking_no: str, base_dir: Path | None = None, day_text: str | None = None) -> Path`
- Add `parse_gofo_export_summary_xlsx(path: Path) -> dict[str, str]`
- Use only standard library:
  - `zipfile.ZipFile`
  - `xml.etree.ElementTree`
- Parse:
  - `xl/sharedStrings.xml`
  - `xl/worksheets/sheet1.xml`
- Return header -> value mapping from the first data row.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_gofo_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_gofo_query.py logistics_query.py
git commit -m "test: cover gofo export helpers"
```

### Task 2: Add GOFO routing test and real browser download query

**Files:**
- Modify: `tests/test_tracking_mode.py`
- Modify: `logistics_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_gofo_query.py`

- [ ] **Step 1: Write the failing test**

```python
    async def test_query_tracking_number_routes_to_gofo_helper(self):
        import logistics_query

        expected = {
            "平台": "GOFO",
            "查询值": "GFUS01055496346945",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_gofo_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("GFUS01055496346945")

        self.assertEqual(result, expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL if GOFO routing is missing or broken. If it already passes, keep it and proceed.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements for `query_gofo_tracking`:

- Open:
  - `https://www.gofo.com/us/track?searchID=<tracking_no>`
- Use Playwright download handling:
  - click `COPY & EXPORT`
  - click `Export Summary`
  - wait for `page.expect_download()`
- Save file to:
  - `tmp/tracking-downloads/<YYYY-MM-DD>/gofo/<tracking_no>-gofo-summary.xlsx`
- Parse workbook with `parse_gofo_export_summary_xlsx`
- Read `Current status`
- Return:

```python
{
    "平台": "GOFO",
    "查询值": normalized,
    "物流轨迹": [{"时间": "", "内容": current_status, "地点": ""}],
    "最新轨迹": {"时间": "", "内容": current_status, "地点": ""},
}
```

Structured errors:

- missing export button -> `GOFO 页面未找到导出入口`
- missing export menu -> `GOFO 页面未找到 Export Summary 菜单`
- download failure -> `GOFO 导出文件下载失败`
- parsing failure -> `GOFO 导出文件解析失败: ...`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_gofo_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_gofo_query.py tests/test_tracking_mode.py
git commit -m "feat: implement gofo export tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_gofo_query.py`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

If implementation matches the spec, add one concise line to `OPERATIONS.md` stating that `gofo` now downloads `Export Summary` and reads `Current status`.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
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
git add OPERATIONS.md logistics_query.py tests/test_gofo_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify gofo tracking integration"
```
