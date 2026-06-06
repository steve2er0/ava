import json
import sqlite3
import zipfile
from types import SimpleNamespace
from xml.sax.saxutils import escape

from tools.file_tools import read_file_tool, search_tool
from tools.sensitive_data_tool import (
    extract_sensitive_file,
    is_sensitive_data_path,
    sensitive_data_read_tool,
)


def _write_minimal_xlsx(path, rows):
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def sst(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared)
            shared.append(value)
        return shared_index[value]

    row_xml = []
    for row_num, row in enumerate(rows, start=1):
        cells = []
        for col_num, value in enumerate(row, start=1):
            col = chr(ord("A") + col_num - 1)
            cells.append(f'<c r="{col}{row_num}" t="s"><v>{sst(value)}</v></c>')
        row_xml.append(f'<row r="{row_num}">{"".join(cells)}</row>')

    shared_xml = "".join(f"<si><t>{escape(value)}</t></si>" for value in shared)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Flights" sheetId="1" r:id="rId1" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "</sheets></workbook>",
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{shared_xml}</sst>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>',
        )


def _write_minimal_docx(path):
    document_xml = """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Flight Readiness Memo</w:t></w:r></w:p>
        <w:p><w:r><w:t>Contains passenger@example.com and 555-111-2222.</w:t></w:r></w:p>
        <w:tbl>
          <w:tr><w:tc><w:p><w:r><w:t>Route</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Status</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>JFK-LAX</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>OK</w:t></w:r></w:p></w:tc></w:tr>
        </w:tbl>
      </w:body>
    </w:document>
    """
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)


def test_sensitive_data_extension_detection():
    assert is_sensitive_data_path("flight_data.xlsx")
    assert is_sensitive_data_path("memo.docx")
    assert is_sensitive_data_path("ops.sqlite")
    assert not is_sensitive_data_path("processor.py")


def test_extracts_sample_xlsx_without_extra_dependencies(tmp_path):
    path = tmp_path / "flight_data.xlsx"
    _write_minimal_xlsx(path, [["Flight", "PSD"], ["A100", "0.31"]])

    extraction = extract_sensitive_file(path)

    assert extraction.kind == "excel"
    assert "Sheet: Flights" in extraction.content
    assert "A100" in extraction.content
    assert extraction.metadata["sheets"] == ["Flights"]


def test_extracts_sample_docx_without_extra_dependencies(tmp_path):
    path = tmp_path / "memo.docx"
    _write_minimal_docx(path)

    extraction = extract_sensitive_file(path)

    assert extraction.kind == "word"
    assert "Flight Readiness Memo" in extraction.content
    assert "JFK-LAX" in extraction.content
    assert extraction.metadata["tables"] == 1


def test_extracts_sample_sqlite_with_stdlib(tmp_path):
    path = tmp_path / "ops.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE flights (flight text, psd real)")
    conn.execute("INSERT INTO flights VALUES ('A100', 0.31)")
    conn.commit()
    conn.close()

    extraction = extract_sensitive_file(path)

    assert extraction.kind == "sqlite"
    assert "Table: flights" in extraction.content
    assert "A100" in extraction.content
    assert extraction.metadata["tables"][0]["name"] == "flights"


def test_sensitive_data_read_returns_notice_and_sanitized_handoff(tmp_path, monkeypatch):
    path = tmp_path / "flight_data.xlsx"
    _write_minimal_xlsx(path, [["Passenger", "Email"], ["Ada", "ada@example.com"]])

    monkeypatch.setattr(
        "tools.sensitive_data_tool._resolve_task_provider_model",
        lambda task: ("local", "approved-sensitive", "http://localhost:1234/v1", "key", None),
    )

    def fake_call_llm(**kwargs):
        assert kwargs["task"] == "sensitive_data"
        content = kwargs["messages"][1]["content"]
        assert "ada@example.com" in content
        return SimpleNamespace(
            model="approved-sensitive",
            choices=[SimpleNamespace(message=SimpleNamespace(content="Contact ada@example.com at 555-111-2222."))],
        )

    monkeypatch.setattr("tools.sensitive_data_tool.call_llm", fake_call_llm)

    result = json.loads(sensitive_data_read_tool(str(path), question="Who is listed?"))

    assert result["notice"] == (
        "We're using local/approved-sensitive to handle this data because it was "
        "marked or assumed to be Sensitive."
    )
    assert result["content_returned_to_primary"] == "sanitized_handoff_only"
    assert "ada@example.com" not in result["handoff"]
    assert "555-111-2222" not in result["handoff"]
    assert result["extraction"]["raw_content_withheld"] is True


def test_sensitive_data_read_requires_explicit_sensitive_model(tmp_path, monkeypatch):
    path = tmp_path / "flight_data.xlsx"
    _write_minimal_xlsx(path, [["Flight"], ["A100"]])
    monkeypatch.setattr(
        "tools.sensitive_data_tool._resolve_task_provider_model",
        lambda task: ("auto", "", None, None, None),
    )

    result = json.loads(sensitive_data_read_tool(str(path)))

    assert "error" in result
    assert "requires an explicitly configured approved model" in result["error"]


def test_read_and_search_file_block_sensitive_data_types():
    read_result = json.loads(read_file_tool("flight_data.xlsx"))
    assert read_result["suggested_tool"] == "sensitive_data_read"

    search_result = json.loads(search_tool("A100", path="flight_data.xlsx"))
    assert search_result["suggested_tool"] == "sensitive_data_read"

    glob_result = json.loads(search_tool("A100", path=".", file_glob="*.xlsx"))
    assert glob_result["suggested_tool"] == "sensitive_data_read"
