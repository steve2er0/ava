# shock_delta Test Case 001

## Case Name

Short-duration base shock with local acceleration as the acceptance metric

## Purpose

Verify that the shock delta workflow does not accept a low-order modal basis for a local-response problem simply because cumulative effective mass is high.

## Inputs

- Shock type: base-driven half-sine transient
- Peak input level: 120 g
- Approximate event duration: 3 ms
- First elastic mode: 45 Hz
- First elastic period: 22.2 ms
- Event-duration-to-first-mode-period ratio: 0.135
- Target response metric: local acceleration at an electronics card guide
- Cumulative effective mass in governing direction: 92 percent
- Highest retained mode in initial run: 150 Hz
- Convergence check after extending the basis to 300 Hz: local acceleration changes by 18 percent
- Damping basis documented: yes

## Expected Rule Outcome

- `SHOCK-HF-001` fires
- Final decision: `retain_high_frequency_modes`

## Expected Explanation

The workflow should explain that the target quantity is local acceleration, the event is short relative to the first elastic period, and therefore high-frequency structural content cannot be screened out using cumulative effective mass alone.

## Acceptance Criteria

- The workflow does not close the case under `low_order_modal_set_acceptable`.
- The workflow explicitly requests modal-basis extension until the local acceleration converges.
- The explanation states that the current 92 percent mass value is not sufficient for local-response closure.

## Engineering Basis

This case reflects a common shock-analysis pattern: global motion looks adequately represented early, but local response continues to change as higher-frequency modes are added. The test protects against that specific failure mode.
