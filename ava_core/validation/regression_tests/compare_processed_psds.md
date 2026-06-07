# compare_processed_psds Regression Tests

## Status

Required before the skill can remain `approved`.

## Cases

| Case ID | Required outcome |
| --- | --- |
| `synthetic_psd_case` | Pass with known PSD ratio and RMS delta recovered within tolerance. |
| `known_ar01_ar02_comparison_case` | Review required with known AR01/AR02 changed channels flagged. |
| `missing_channel_case` | Review required with missing channel reported and no silent pass. |
| `mismatched_frequency_grid_case` | Review required with frequency-grid mismatch and policy reported. |

## Regression Procedure

1. Load the golden case manifest from `validation/golden_cases/compare_processed_psds.json`.
2. Execute the `compare_processed_psds` workflow for each case using local files or sanitized fixtures.
3. Compare the result envelope against `validation/expected_outputs/compare_processed_psds.json`.
4. Store review artifacts outside the LLM transcript when raw PSD data is proprietary.
5. Update the approval record only after all required cases pass or produce the expected review-required finding.

## Release Rule

Any change to channel matching, frequency-grid handling, RMS integration,
thresholds, or summary wording must replay all four cases before the skill can
remain approved.
