# Analysis

This folder contains reusable numerical routines for vibration and shock response calculations.

## Purpose

Provide solver-independent response computations that can support screening, post-processing, and workflow validation.

## What belongs here

- FRF, SRS, and related dynamic-response calculations
- Response comparison and convergence utilities
- Typed result containers that downstream visualization and pipelines can consume

## What should not go here

- File parsers or solver command wrappers
- Knowledge-layer thresholds hard-coded as released engineering policy
- Presentation-only output formatting

## How it interacts with `ava_knowledge`

Analysis routines calculate the quantities that knowledge-layer rules act on. They should remain numerically focused and let `ava_knowledge/` determine whether a computed response is acceptable, incomplete, or requires further review.
