# compare_processed_psds

Status: approved

This skill compares processed PSD datasets across analysis runs and produces a
review-ready summary of changed channels, missing channels, frequency-grid
compatibility, and RMS deltas.

## Validation Requirement

Approval is controlled by:

- `ava_core/validation/approval_records/compare_processed_psds.json`
- `ava_core/validation/golden_cases/compare_processed_psds.json`
- `ava_core/validation/expected_outputs/compare_processed_psds.json`
- `ava_core/validation/regression_tests/compare_processed_psds.md`

Validated on:

- synthetic PSD case
- known AR01/AR02 comparison case
- missing channel case
- mismatched frequency grid case

## Output Contract

The skill should return:

- comparison status: `pass`, `review_required`, or `fail`
- compared channel count
- missing baseline/candidate channels
- frequency-grid compatibility finding
- channel-level PSD and RMS deltas
- artifact paths for detailed plots or tables

Raw PSD arrays should stay local unless explicitly approved for exposure.
