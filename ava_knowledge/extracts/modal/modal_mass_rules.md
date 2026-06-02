# Modal Mass Rules

This starter extract captures modal-mass concepts that commonly drive adequacy decisions in reduced-order dynamic models. It should be linked to ingested source records before release use.

## Scope

- Modal truncation decisions
- Effective mass interpretation
- Reduced-basis adequacy for structural dynamics

## Extracted Statements

### MM-001: Effective mass is directional

Modal effective mass must be assessed in the direction of the applied base motion or response of interest. A model can meet a cumulative mass target in one translation and remain incomplete in another direction that drives the actual load path.

### MM-002: Cumulative mass is a screening measure, not an endpoint

Reaching a cumulative effective mass target such as 90 percent is often useful for global response screening, but it should not be treated as sufficient proof for all quantities. Local stress, local acceleration, and interface detail can remain sensitive to higher-frequency content.

### MM-003: Mode count alone is a weak adequacy metric

Retaining a fixed number of modes without checking frequency range, directional mass, or response convergence can produce a false sense of completeness. Rules should key off physics-based quantities rather than mode count alone.

### MM-004: Closely spaced modes deserve grouped review

Where several modes cluster in frequency, individual modal importance can shift with coordinate choice or damping assumptions. The retained basis should preserve the cluster if the grouped response materially affects the decision quantity.

### MM-005: Residual flexibility or residual inertia may be required

If the truncated modal basis is used to represent dynamic behavior beyond the highest retained mode, residual terms or equivalent corrective treatment may be needed. Otherwise the reduced model can become artificially stiff or dynamically incomplete above the truncation band.

## Rule Authoring Cues

- Carry effective mass by direction, not as a single scalar.
- Keep convergence evidence separate from screening evidence.
- Require the intended response metric before accepting modal truncation.
- Flag cases where residual terms are omitted from a truncated model.
