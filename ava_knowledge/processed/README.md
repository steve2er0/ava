# Processed Sources

This folder stores machine-usable conversions of the raw source set.

## What belongs here

- OCR text, normalized markdown, sectioned text exports, and structured metadata
- Cleaned tables or equation captures that preserve source meaning
- Source segmentation outputs prepared for extraction workflows

## What should not go here

- Original source binaries that belong in `raw/`
- Final engineering rules or agent decisions
- Free-form summaries that drop section boundaries or provenance

## How it fits into the AVA pipeline

`processed/` turns source material into consistent text that can be searched, parsed, and extracted without losing traceability to the original document set.
