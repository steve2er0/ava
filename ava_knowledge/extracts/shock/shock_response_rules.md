# Shock Response Rules

This starter extract captures rule-ready observations from common shock-analysis practice. It is intentionally uncited until actual source documents are ingested into `raw/` and traced through `processed/`.

## Scope

- Short-duration structural shock
- Base-driven or interface-driven transient response
- Modal representations used to estimate displacement, acceleration, load, or stress

## Extracted Statements

### SR-001: Response metric matters

Low-order modes often govern global displacement and major reaction transfer, but local acceleration and local stress can remain sensitive to higher modes with small effective mass. A shock workflow should therefore ask what response quantity is being qualified before it accepts a reduced modal basis.

### SR-002: Short pulses can activate high-frequency content

When shock duration is short relative to structural periods, the excitation contains enough high-frequency content that local dynamic amplification can persist well above the frequency range needed for displacement convergence. A mode set that is adequate for quasi-global motion may still underpredict local shock response.

### SR-003: Cumulative effective mass is not a complete shock adequacy test

High cumulative effective mass in a translation direction is useful, but it does not prove convergence for all response metrics. Effective mass is a screening measure for how well the model represents global base-motion participation, not a guarantee that local peaks are converged.

### SR-004: Damping assumptions can hide dynamic demand

Shock peaks are sensitive to the damping model, especially when only a few cycles dominate the response. Damping should stay conservative and documented unless test evidence supports higher values for the relevant hardware and load path.

### SR-005: Residual and rebound behavior can be important

Peak absolute acceleration is not always the controlling quantity. Residual displacement, rebound, and secondary impact risk may matter for gaps, latches, or internal clearances, so shock evaluations should preserve multiple response metrics where practical.

## Rule Authoring Cues

- Require the target response metric as an explicit input.
- Separate global adequacy checks from local-response adequacy checks.
- Prefer convergence checks over simple mode-count rules.
- Record the damping basis whenever it changes a decision.
