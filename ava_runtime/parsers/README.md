# Parsers

This folder contains file readers and translators for structural models and solver results.

## Purpose

Provide deterministic access to the minimum model and result data required by AVA pipelines without embedding domain knowledge into file I/O code.

## What belongs here

- Readers for BDF, OP2, and other structural-analysis data sources
- Typed summaries and low-level record extraction helpers
- Input validation for file format assumptions

## What should not go here

- Rule logic or engineering acceptance decisions
- Solver launch code
- Plotting or report-generation routines

## How it interacts with `ava_knowledge`

Parsers feed structured runtime inputs into workflows that later apply knowledge-layer rules. They should expose measurable quantities such as modal frequencies, effective mass summaries, and response series, but they should not decide what those quantities mean.
