# AVA Knowledge Map

This map shows how the current starter knowledge set is organized and where coverage exists today.

## Pipeline Map

1. `raw/` stores received engineering sources.
2. `processed/` converts those sources into searchable, structured text.
3. `extracts/` captures rule-bearing statements by discipline.
4. `concepts/` stabilizes engineering meaning across related extracts.
5. `rules/` encodes deterministic decision logic.
6. `skills/` applies rules in versioned agent workflows.
7. `tests/` validates rule and skill behavior.
8. `../ava_core/validation/` gates approved engineering skills with golden cases, expected outputs, regression procedures, and approval records.
9. `references/` controls source IDs for theory, thresholds, and rule rationale.
10. `index/` provides navigation and coverage visibility.

## Current Domain Coverage

| Domain | Extracts | Concepts | Rules | Skills | Tests | Approval Evidence | Coverage Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shock | `extracts/shock/shock_response_rules.md` | `concepts/high_frequency_effects.md` | `rules/shock/high_freq_modes.yaml` | `skills/shock_delta_v1/` | `tests/shock_delta/case_001.md` | Not yet approval-gated | Starter coverage present |
| PSD comparison | Planned | Planned | Planned | `skills/compare_processed_psds/` | Validation package in `ava_core/validation/` | `approval_records/compare_processed_psds.json` | Approved example gate present |
| Modal | `extracts/modal/modal_mass_rules.md` | Shared through high-frequency and adequacy concepts | `rules/modal/` reserved for expansion | Referenced by `shock_delta_v1` | Covered indirectly through shock test | Not yet approval-gated | Partial |
| Damping | `extracts/damping/` | Not yet formalized | Not yet formalized | Not yet formalized | Not yet formalized | Not yet approval-gated | Planned |
| Acoustics | `extracts/acoustics/` | Not yet formalized | Not yet formalized | Not yet formalized | Not yet formalized | Not yet approval-gated | Planned |

## Key Relationships

- Shock rules depend on both shock extracts and modal adequacy extracts.
- The `high_frequency_effects` concept explains why mass-based screening can fail for local shock response.
- `shock_delta_v1` is the first operational workflow that ties shock inputs to deterministic rule outcomes.
- `case_001` is the baseline regression test for that workflow.
- `compare_processed_psds` demonstrates the approval gate: approved engineering skills must have golden cases, expected outputs, regression procedures, and an approval record.
- Theory-bearing outputs should cite source IDs from `references/reference_index.json`; placeholder references mark starter guidance that is not yet approved external theory.

## Immediate Next Steps

- Add source-linked IDs once real documents are ingested into `raw/` and `processed/`.
- Replace placeholder references with governing source records before approving shock or modal theory.
- Expand `rules/modal/` with explicit effective-mass and residual-term logic.
- Add damping rules that prevent non-conservative assumptions from closing a shock case.
- Add acoustic concepts and workflows when that branch of the knowledge base is activated.
- Backfill approval records for existing engineering skills before marking them approved.
