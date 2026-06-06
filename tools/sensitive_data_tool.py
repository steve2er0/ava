#!/usr/bin/env python3
"""Sensitive data reader routed through the approved auxiliary model.

This tool is intentionally separate from read_file.  It lets the primary
agent keep planning and coding while raw tabular/document/database contents
are inspected only by the configured ``auxiliary.sensitive_data`` model.
The primary model receives the sensitive model's sanitized handoff, not the
raw extraction.
"""

from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

from agent.auxiliary_client import (
    call_llm,
    extract_content_or_reasoning,
    _resolve_task_provider_model,
)
from agent.redact import redact_sensitive_text
from tools.file_tools import _resolve_path_for_task, _check_file_reqs
from tools.registry import registry, tool_error


SENSITIVE_DATA_EXTENSIONS = frozenset({
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".db",
    ".sqlite",
    ".sqlite3",
})

_MAX_EXTRACT_CHARS = 30_000
_MAX_SHEETS = 5
_MAX_ROWS_PER_BLOCK = 80
_MAX_COLUMNS = 30
_MAX_CELL_CHARS = 200
_MAX_DOC_BLOCKS = 180
_MAX_DB_TABLES = 8


@dataclass
class Extraction:
    kind: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False


def is_sensitive_data_path(path: str) -> bool:
    """Return True for file types that should use the sensitive-data route."""
    return Path(str(path or "")).suffix.lower() in SENSITIVE_DATA_EXTENSIONS


def _tag_name(elem: ET.Element) -> str:
    return elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag


def _text_from(elem: ET.Element) -> str:
    return "".join(t.text or "" for t in elem.iter() if _tag_name(t) == "t").strip()


def _clip_text(value: Any, limit: int = _MAX_CELL_CHARS) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _clip_lines(lines: list[str], max_chars: int = _MAX_EXTRACT_CHARS) -> tuple[str, bool]:
    total = 0
    kept: list[str] = []
    truncated = False
    for line in lines:
        add = len(line) + 1
        if kept and total + add > max_chars:
            truncated = True
            break
        kept.append(line)
        total += add
    return "\n".join(kept), truncated


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    if not letters:
        return 0
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return max(0, value - 1)


def _read_zip_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def _extract_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = _read_zip_xml(zf, "xl/sharedStrings.xml")
    if root is None:
        return []
    return [_text_from(si) for si in root.findall(".//{*}si")]


def _extract_workbook_sheet_names(zf: zipfile.ZipFile) -> dict[int, str]:
    root = _read_zip_xml(zf, "xl/workbook.xml")
    if root is None:
        return {}
    names: dict[int, str] = {}
    for idx, sheet in enumerate(root.findall(".//{*}sheet"), start=1):
        names[idx] = str(sheet.attrib.get("name") or f"Sheet{idx}")
    return names


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _clip_text(_text_from(cell))
    value_elem = cell.find("{*}v")
    value = value_elem.text if value_elem is not None else ""
    if cell_type == "s":
        try:
            return _clip_text(shared_strings[int(value)])
        except (ValueError, IndexError):
            return ""
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE" if value == "0" else _clip_text(value)
    return _clip_text(value)


def _extract_xlsx(path: Path) -> Extraction:
    lines: list[str] = []
    metadata: dict[str, Any] = {"sheets": []}
    with zipfile.ZipFile(path) as zf:
        shared_strings = _extract_shared_strings(zf)
        sheet_names = _extract_workbook_sheet_names(zf)
        worksheet_paths = sorted(
            name for name in zf.namelist()
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
        for sheet_idx, worksheet in enumerate(worksheet_paths[:_MAX_SHEETS], start=1):
            root = _read_zip_xml(zf, worksheet)
            if root is None:
                continue
            sheet_name = sheet_names.get(sheet_idx) or Path(worksheet).stem
            row_count = 0
            metadata["sheets"].append(sheet_name)
            lines.append(f"Sheet: {sheet_name}")
            for row in root.findall(".//{*}row"):
                if row_count >= _MAX_ROWS_PER_BLOCK:
                    break
                values = [""] * _MAX_COLUMNS
                has_value = False
                for cell in row.findall("{*}c"):
                    col = min(_column_index(cell.attrib.get("r", "")), _MAX_COLUMNS - 1)
                    value = _xlsx_cell_value(cell, shared_strings)
                    if value:
                        values[col] = value
                        has_value = True
                if has_value:
                    row_num = row.attrib.get("r") or str(row_count + 1)
                    while values and not values[-1]:
                        values.pop()
                    lines.append(f"R{row_num}: " + " | ".join(values))
                    row_count += 1
            metadata[f"{sheet_name}_rows_extracted"] = row_count
            if row_count >= _MAX_ROWS_PER_BLOCK:
                metadata[f"{sheet_name}_truncated"] = True
            lines.append("")
    content, truncated = _clip_lines(lines)
    truncated = truncated or len(metadata["sheets"]) >= _MAX_SHEETS
    return Extraction(kind="excel", content=content, metadata=metadata, truncated=truncated)


def _extract_docx(path: Path) -> Extraction:
    lines: list[str] = []
    metadata: dict[str, Any] = {"paragraphs": 0, "tables": 0}
    with zipfile.ZipFile(path) as zf:
        root = _read_zip_xml(zf, "word/document.xml")
        if root is None:
            raise ValueError("DOCX file does not contain word/document.xml")
        body = root.find(".//{*}body")
        if body is None:
            body = root
        block_count = 0
        for block in list(body):
            if block_count >= _MAX_DOC_BLOCKS:
                break
            tag = _tag_name(block)
            if tag == "p":
                text = _text_from(block)
                if text:
                    metadata["paragraphs"] += 1
                    lines.append(f"P{metadata['paragraphs']}: {_clip_text(text, 800)}")
                    block_count += 1
            elif tag == "tbl":
                metadata["tables"] += 1
                lines.append(f"Table {metadata['tables']}:")
                row_num = 0
                for row in block.findall(".//{*}tr"):
                    if row_num >= _MAX_ROWS_PER_BLOCK:
                        break
                    cells = [_clip_text(_text_from(cell)) for cell in row.findall(".//{*}tc")]
                    if any(cells):
                        row_num += 1
                        lines.append(f"  R{row_num}: " + " | ".join(cells[:_MAX_COLUMNS]))
                block_count += 1
    content, truncated = _clip_lines(lines)
    truncated = truncated or metadata["paragraphs"] + metadata["tables"] >= _MAX_DOC_BLOCKS
    return Extraction(kind="word", content=content, metadata=metadata, truncated=truncated)


def _quote_sql_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _extract_sqlite(path: Path) -> Extraction:
    lines: list[str] = []
    metadata: dict[str, Any] = {"tables": []}
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name LIMIT ?",
            (_MAX_DB_TABLES,),
        ).fetchall()
        for row in rows:
            name = str(row["name"])
            kind = str(row["type"])
            metadata["tables"].append({"name": name, "type": kind})
            lines.append(f"{kind.title()}: {name}")
            cols = conn.execute(f"PRAGMA table_info({_quote_sql_identifier(name)})").fetchall()
            col_names = [str(c["name"]) for c in cols]
            lines.append("Columns: " + " | ".join(col_names))
            try:
                sample = conn.execute(
                    f"SELECT * FROM {_quote_sql_identifier(name)} LIMIT ?",
                    (_MAX_ROWS_PER_BLOCK,),
                ).fetchall()
            except sqlite3.Error as exc:
                lines.append(f"Rows unavailable: {exc}")
                lines.append("")
                continue
            for idx, sample_row in enumerate(sample, start=1):
                values = [_clip_text(sample_row[col]) for col in col_names[:_MAX_COLUMNS]]
                lines.append(f"R{idx}: " + " | ".join(values))
            if len(sample) >= _MAX_ROWS_PER_BLOCK:
                lines.append(f"Rows truncated at {_MAX_ROWS_PER_BLOCK}.")
            lines.append("")
    finally:
        conn.close()
    content, truncated = _clip_lines(lines)
    truncated = truncated or len(metadata["tables"]) >= _MAX_DB_TABLES
    return Extraction(kind="sqlite", content=content, metadata=metadata, truncated=truncated)


def extract_sensitive_file(path: Path) -> Extraction:
    """Extract a bounded text representation for the sensitive auxiliary model."""
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return _extract_xlsx(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext in {".sqlite", ".sqlite3", ".db"}:
        return _extract_sqlite(path)
    if ext == ".xls":
        raise ValueError("Legacy .xls files are detected as Sensitive but are not parsed in v1. Convert to .xlsx.")
    if ext == ".doc":
        raise ValueError("Legacy .doc files are detected as Sensitive but are not parsed in v1. Convert to .docx.")
    raise ValueError(f"Unsupported sensitive data file type: {ext or '(none)'}")


def _redact_sensitive_handoff(text: str) -> str:
    """Apply lightweight PII/secret masking to the handoff returned upstream."""
    redacted = redact_sensitive_text(text or "", code_file=False)
    redacted = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", redacted)
    redacted = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", redacted)
    redacted = re.sub(
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)",
        "[REDACTED_PHONE]",
        redacted,
    )
    redacted = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_NUMBER]", redacted)
    return redacted.strip()


def _resolve_sensitive_route() -> tuple[str, str | None]:
    provider, model, _base_url, _api_key, _api_mode = _resolve_task_provider_model("sensitive_data")
    provider_norm = (provider or "").strip().lower()
    if provider_norm in {"", "auto", "main"}:
        raise RuntimeError(
            "Sensitive data reading requires an explicitly configured approved model. "
            "Set auxiliary.sensitive_data.provider and auxiliary.sensitive_data.model "
            "to an approved hosted model or local OpenAI-compatible endpoint."
        )
    return provider, model


def _notice(provider: str, model: str | None) -> str:
    model_label = model or "provider default"
    return (
        f"We're using {provider}/{model_label} to handle this data because it was "
        "marked or assumed to be Sensitive."
    )


def sensitive_data_read_tool(
    path: str,
    question: str = "",
    sensitive: bool = True,
    task_id: str = "default",
) -> str:
    """Read sensitive data through ``auxiliary.sensitive_data``."""
    try:
        resolved = _resolve_path_for_task(path, task_id)
        ext_assumed_sensitive = is_sensitive_data_path(str(resolved))
        if not sensitive and not ext_assumed_sensitive:
            return tool_error(
                "sensitive_data_read is for data marked or assumed Sensitive. "
                "Use read_file for ordinary source/config text files."
            )
        if not resolved.exists():
            return tool_error(f"File not found: {path}")
        if not resolved.is_file():
            return tool_error(f"Not a file: {path}")

        provider, configured_model = _resolve_sensitive_route()
        extraction = extract_sensitive_file(resolved)
        if not extraction.content.strip():
            return tool_error(f"No extractable content found in {path}")

        prompt_question = (question or "Summarize the useful contents for the primary model.").strip()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the approved sensitive-data model. Inspect the provided "
                    "bounded extraction and answer the user's request. Return only a "
                    "sanitized handoff for the primary model: summarize, aggregate, "
                    "cite sheet/table/row/paragraph references when useful, and avoid "
                    "copying raw rows or long verbatim snippets. Redact direct personal "
                    "identifiers unless the user explicitly needs them."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Request:\n{prompt_question}\n\n"
                    f"Source type: {extraction.kind}\n"
                    f"Source path: {resolved.name}\n"
                    f"Extraction truncated: {extraction.truncated}\n\n"
                    "Bounded extracted content for sensitive-model inspection only:\n"
                    f"{extraction.content}"
                ),
            },
        ]

        response = call_llm(
            task="sensitive_data",
            messages=messages,
            temperature=0,
            max_tokens=1400,
        )
        used_model = str(getattr(response, "model", "") or configured_model or "provider default")
        handoff = _redact_sensitive_handoff(extract_content_or_reasoning(response))
        if not handoff:
            return tool_error("Sensitive data model returned an empty handoff.")
        result = {
            "notice": _notice(provider, used_model),
            "path": str(resolved),
            "sensitivity": "marked or assumed Sensitive",
            "source_type": extraction.kind,
            "content_returned_to_primary": "sanitized_handoff_only",
            "handoff": handoff,
            "extraction": {
                "metadata": extraction.metadata,
                "truncated": extraction.truncated,
                "raw_content_withheld": True,
            },
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return tool_error(str(exc))


SENSITIVE_DATA_READ_SCHEMA = {
    "name": "sensitive_data_read",
    "description": (
        "Inspect Excel, Word, or SQLite/database contents through the configured "
        "approved sensitive-data model, then return only a sanitized handoff to "
        "the primary model. Use this when a file/task is marked Sensitive or is "
        "assumed Sensitive by type (.xlsx, .xls, .docx, .doc, .db, .sqlite, "
        ".sqlite3). Do not use read_file, terminal, or execute_code to dump raw "
        "sensitive contents into the primary model. Ordinary code/script work "
        "around data processing can stay on the primary model."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the Excel/Word/SQLite data file.",
            },
            "question": {
                "type": "string",
                "description": "Question or instruction for the approved sensitive-data model.",
                "default": "",
            },
            "sensitive": {
                "type": "boolean",
                "description": "True when the user marked this data Sensitive. File types may also be assumed Sensitive.",
                "default": True,
            },
        },
        "required": ["path"],
    },
}


registry.register(
    name="sensitive_data_read",
    toolset="file",
    schema=SENSITIVE_DATA_READ_SCHEMA,
    handler=lambda args, **kw: sensitive_data_read_tool(
        path=args.get("path", ""),
        question=args.get("question", ""),
        sensitive=bool(args.get("sensitive", True)),
        task_id=kw.get("task_id") or "default",
    ),
    check_fn=_check_file_reqs,
    emoji="🔒",
    max_result_size_chars=20_000,
)
