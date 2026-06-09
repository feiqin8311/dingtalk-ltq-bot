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


if __name__ == "__main__":
    unittest.main()
