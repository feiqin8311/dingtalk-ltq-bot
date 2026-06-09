# YunTrack Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the YunTrack placeholder with a real export-driven query that downloads the summary workbook and returns the `Delivery Status` field.

**Architecture:** Reuse the existing export-platform pattern established for GOFO: direct detail URL, Playwright download, standardized dated download directory, and pure XLSX first-row parsing in `logistics_query.py`. Keep the response narrow by exposing only `Delivery Status`.

**Tech Stack:** Python 3.11, `unittest`, existing async Playwright + local CDP flow, standard-library XLSX parsing, existing tracking result formatting

---

## File Structure

- Modify: `logistics_query.py`
  - Add YunTrack download-path helpers.
  - Add YunTrack export parsing helper.
  - Replace placeholder `query_yuntrack_tracking`.
- Create: `tests/test_yuntrack_query.py`
  - Cover path building and workbook parsing.
- Modify: `tests/test_tracking_mode.py`
  - Add `H00RVA` and `GV` route tests.

### Task 1: Add YunTrack helper tests

**Files:**
- Create: `tests/test_yuntrack_query.py`
- Modify: `logistics_query.py`
- Test: `tests/test_yuntrack_query.py`

- [ ] **Step 1: Write the failing test**

```python
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import tempfile
import unittest

from logistics_query import (
    build_yuntrack_download_dir,
    build_yuntrack_download_path,
    parse_yuntrack_export_summary_xlsx,
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
    header_cells = []
    row_cells = []
    for index in range(len(headers)):
        column = chr(ord("A") + index)
        header_cells.append(f'<c r="{column}1" t="s"><v>{index}</v></c>')
    for index in range(len(row)):
        column = chr(ord("A") + index)
        row_cells.append(f'<c r="{column}2" t="s"><v>{len(headers) + index}</v></c>')
    sheet = f"""<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1">{''.join(header_cells)}</row><row r="2">{''.join(row_cells)}</row></sheetData>
    </worksheet>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared_strings}</sst>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class YunTrackQueryHelperTests(unittest.TestCase):
    def test_build_yuntrack_download_path_uses_date_platform_and_tracking_number(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            directory = build_yuntrack_download_dir(base_dir=base, day_text="2026-06-09")
            target = build_yuntrack_download_path("H00RVA0498916385", base_dir=base, day_text="2026-06-09")

            self.assertEqual(directory, base / "tracking-downloads" / "2026-06-09" / "yuntrack")
            self.assertEqual(target.name, "H00RVA0498916385-yuntrack-summary.xlsx")

    def test_parse_yuntrack_export_summary_xlsx_reads_delivery_status(self):
        payload = _build_xlsx_bytes(
            ["Tracking Number", "Delivery Status"],
            ["H00RVA0498916385", "In transit"],
        )

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            row = parse_yuntrack_export_summary_xlsx(Path(temp_file.name))

        self.assertEqual(row["Delivery Status"], "In transit")

    def test_parse_yuntrack_export_summary_xlsx_requires_delivery_status(self):
        payload = _build_xlsx_bytes(["Tracking Number"], ["H00RVA0498916385"])

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            with self.assertRaisesRegex(RuntimeError, "Delivery Status"):
                parse_yuntrack_export_summary_xlsx(Path(temp_file.name))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_yuntrack_query.py' -v`
Expected: FAIL because helper functions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Requirements:

- Add `build_yuntrack_download_dir`
- Add `build_yuntrack_download_path`
- Add `parse_yuntrack_export_summary_xlsx`
- Reuse the current standard-library XLSX parsing approach.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_yuntrack_query.py' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_yuntrack_query.py logistics_query.py
git commit -m "test: cover yuntrack export helpers"
```

### Task 2: Add YunTrack route tests and real browser export query

**Files:**
- Modify: `tests/test_tracking_mode.py`
- Modify: `logistics_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_yuntrack_query.py`

- [ ] **Step 1: Write the failing test**

```python
    async def test_query_tracking_number_routes_to_yuntrack_helper_for_h00rva(self):
        import logistics_query

        expected = {
            "平台": "YUNTRACK",
            "查询值": "H00RVA0498916385",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_yuntrack_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("H00RVA0498916385")

        self.assertEqual(result, expected)

    async def test_query_tracking_number_routes_to_yuntrack_helper_for_gv(self):
        import logistics_query

        expected = {
            "平台": "YUNTRACK",
            "查询值": "GV123456789US",
            "物流轨迹": [],
            "最新轨迹": {},
        }

        with patch.object(logistics_query, "query_yuntrack_tracking", new=AsyncMock(return_value=expected)):
            result = await logistics_query.query_tracking_number("GV123456789US")

        self.assertEqual(result, expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v`
Expected: FAIL if YunTrack routing is broken. If it already passes, keep it and proceed.

- [ ] **Step 3: Write minimal implementation**

Implementation requirements for `query_yuntrack_tracking`:

- Open:
  - `https://www.yuntrack.com/parcelTracking?id=<tracking_no>`
- Click:
  - `Copy & Export`
  - `Export Summary`
- Wait for download
- Save file to:
  - `tmp/tracking-downloads/<YYYY-MM-DD>/yuntrack/<tracking_no>-yuntrack-summary.xlsx`
- Parse with `parse_yuntrack_export_summary_xlsx`
- Read `Delivery Status`
- Return:

```python
{
    "平台": "YUNTRACK",
    "查询值": normalized,
    "物流轨迹": [{"时间": "", "内容": delivery_status, "地点": ""}],
    "最新轨迹": {"时间": "", "内容": delivery_status, "地点": ""},
}
```

Errors:

- missing button -> `YunTrack 页面未找到导出入口`
- missing menu -> `YunTrack 页面未找到 Export Summary 菜单`
- download failure -> `YunTrack 导出文件下载失败`
- parse failure -> `YunTrack 导出文件解析失败: ...`
- missing field -> `YunTrack 导出文件缺少 Delivery Status 字段`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_yuntrack_query.py' -v
python3 -m unittest discover -s tests -p 'test_tracking_mode.py' -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logistics_query.py tests/test_yuntrack_query.py tests/test_tracking_mode.py
git commit -m "feat: implement yuntrack export tracking query"
```

### Task 3: Final regression verification

**Files:**
- Modify: `OPERATIONS.md`
- Test: `tests/test_yuntrack_query.py`
- Test: `tests/test_ups_query.py`
- Test: `tests/test_usps_query.py`
- Test: `tests/test_gofo_query.py`
- Test: `tests/test_uniuni_query.py`
- Test: `tests/test_tracking_mode.py`
- Test: `tests/test_tracking_platform_decision.py`
- Test: `tests/test_main_queue.py`

- [ ] **Step 1: Update docs if needed**

Add one concise line to `OPERATIONS.md` stating that YunTrack now downloads `Export Summary` and reads `Delivery Status`.

- [ ] **Step 2: Run the affected tests**

Run:

```bash
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
git add OPERATIONS.md logistics_query.py tests/test_yuntrack_query.py tests/test_ups_query.py tests/test_usps_query.py tests/test_gofo_query.py tests/test_uniuni_query.py tests/test_tracking_mode.py tests/test_tracking_platform_decision.py tests/test_main_queue.py
git commit -m "test: verify yuntrack tracking integration"
```
