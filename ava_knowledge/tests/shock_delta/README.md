# Shock Delta Tests

This folder contains validation cases for the `shock_delta_v1` workflow and associated shock rules.

## What belongs here

- Cases that verify shock-specific rule firing, explanation quality, and fail-safe behavior
- Boundary cases for mode truncation, damping caution, and response metric scope
- Regression cases derived from reviewed engineering examples

## What should not go here

- Generic modal QA with no shock workflow linkage
- Informal examples that do not specify the expected decision
- Test artifacts that bypass the versioned skill under evaluation

## How it fits into the AVA pipeline

These tests validate that the shock skill behaves consistently as the rule base evolves. They protect both the logic and the explanation layer from silent drift.
