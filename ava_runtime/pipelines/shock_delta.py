"""Shock-delta workflow execution for the AVA runtime.

This pipeline is the runtime counterpart to the `ava_knowledge` shock-delta
skill. It loads model context, computes a dynamic response using either SRS or
modal FRF methods, applies a runtime-side hook aligned to the released shock
rule set, and emits structured output files for engineering review.

The rule-evaluation hook is intentionally lightweight. It mirrors the current
starter rule logic from `ava_knowledge/rules/shock/high_freq_modes.yaml`
without attempting to implement a generic YAML rule engine.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from ava_runtime.analysis.frf import FrequencyResponseResult, ModalTerm, compute_modal_frf
from ava_runtime.analysis.srs import ShockSpectrumResult, compute_srs
from ava_runtime.parsers.bdf_parser import BdfModelSummary, summarize_bdf
from ava_runtime.parsers.op2_parser import Op2StreamInfo, inspect_op2_stream
from ava_runtime.visualization.frf_plot import write_frf_svg


@dataclass(frozen=True)
class ShockDeltaCase:
    """Inputs required to execute the shock-delta pipeline."""

    case_name: str
    bdf_path: Path
    output_directory: Path
    response_metric: str
    event_duration_seconds: float
    first_mode_hz: float
    cumulative_effective_mass_percent: float
    damping_basis_documented: bool
    op2_path: Optional[Path] = None
    convergence_delta_percent: Optional[float] = None
    time_seconds: Sequence[float] = field(default_factory=tuple)
    base_acceleration_g: Sequence[float] = field(default_factory=tuple)
    srs_frequencies_hz: Sequence[float] = field(default_factory=tuple)
    frf_frequencies_hz: Sequence[float] = field(default_factory=tuple)
    modal_terms: Sequence[ModalTerm] = field(default_factory=tuple)
    frf_response_type: str = "acceleration"

    @property
    def event_duration_to_first_mode_period(self) -> float:
        """Return the dimensionless duration ratio used by the shock rule set."""

        if self.first_mode_hz <= 0.0:
            raise ValueError("First mode frequency must be positive")
        return self.event_duration_seconds * self.first_mode_hz


@dataclass(frozen=True)
class ModelContext:
    """Parsed model and result metadata used during execution."""

    bdf_summary: BdfModelSummary
    op2_stream: Optional[Op2StreamInfo]


@dataclass(frozen=True)
class ShockRuleOutcome:
    """Result of applying the runtime-side shock rule hook."""

    primary_rule_id: str
    primary_decision: str
    matched_rule_ids: Sequence[str]
    release_blocked: bool
    required_actions: Sequence[str]
    explanation: str
    rule_source: Path


@dataclass(frozen=True)
class ShockDeltaRunResult:
    """Structured outputs from the completed workflow."""

    model_context: ModelContext
    response_kind: str
    rule_outcome: ShockRuleOutcome
    summary_path: Path
    response_table_path: Path
    figure_path: Optional[Path]


class ShockRuleHook:
    """A narrow runtime mirror of the current shock rule set."""

    def __init__(self, knowledge_root: str | Path) -> None:
        self.knowledge_root = Path(knowledge_root)
        self.rule_source = self.knowledge_root / "rules" / "shock" / "high_freq_modes.yaml"
        if not self.rule_source.exists():
            raise FileNotFoundError(f"Shock rule source not found: {self.rule_source}")

    def evaluate(self, case: ShockDeltaCase) -> ShockRuleOutcome:
        """Apply the starter shock rule logic to a workflow case."""

        matched_rule_ids: List[str] = []
        primary_rule_id = "SHOCK-HF-003"
        primary_decision = "engineering_review_required"
        required_actions: List[str] = [
            "Escalate because no adequacy rule could be closed from the current inputs.",
        ]

        duration_ratio = case.event_duration_to_first_mode_period
        response_converged = self._response_converged(case)

        if duration_ratio <= 0.25 and case.response_metric in {"local_acceleration", "local_stress", "interface_load"}:
            primary_rule_id = "SHOCK-HF-001"
            primary_decision = "retain_high_frequency_modes"
            matched_rule_ids.append(primary_rule_id)
            required_actions = [
                "Extend the modal basis until the target response converges.",
                "Do not accept the model on cumulative effective mass alone.",
                "Record the final retained frequency range used for closure.",
            ]
        elif (
            case.response_metric == "global_displacement"
            and case.cumulative_effective_mass_percent >= 90.0
            and response_converged
        ):
            primary_rule_id = "SHOCK-HF-002"
            primary_decision = "low_order_modal_set_acceptable"
            matched_rule_ids.append(primary_rule_id)
            required_actions = [
                "Record the governing direction for the mass calculation.",
                "State that the decision applies only to global displacement screening.",
            ]

        release_blocked = False
        if not case.damping_basis_documented or not response_converged:
            matched_rule_ids.append("SHOCK-HF-003")
            release_blocked = True
            required_actions = list(required_actions) + [
                "Hold release of the adequacy decision until damping rationale and convergence evidence are documented.",
            ]

        explanation = self._build_explanation(
            case=case,
            primary_decision=primary_decision,
            response_converged=response_converged,
            release_blocked=release_blocked,
        )
        return ShockRuleOutcome(
            primary_rule_id=primary_rule_id,
            primary_decision=primary_decision,
            matched_rule_ids=tuple(dict.fromkeys(matched_rule_ids)),
            release_blocked=release_blocked,
            required_actions=tuple(required_actions),
            explanation=explanation,
            rule_source=self.rule_source,
        )

    @staticmethod
    def _response_converged(case: ShockDeltaCase) -> bool:
        """Return `True` when the supplied convergence delta meets the rule threshold."""

        if case.convergence_delta_percent is None:
            return False
        return case.convergence_delta_percent <= 10.0

    def _build_explanation(
        self,
        *,
        case: ShockDeltaCase,
        primary_decision: str,
        response_converged: bool,
        release_blocked: bool,
    ) -> str:
        """Generate a review-ready engineering explanation."""

        duration_ratio = case.event_duration_to_first_mode_period
        statements = [
            f"The target response quantity is {case.response_metric}.",
            f"The shock event duration to first-mode-period ratio is {duration_ratio:.3f}.",
        ]
        if primary_decision == "retain_high_frequency_modes":
            statements.append(
                "The case is treated as a short-duration local-response problem, so high-frequency structural content cannot be screened out using cumulative effective mass alone."
            )
        elif primary_decision == "low_order_modal_set_acceptable":
            statements.append(
                "The current modal basis is acceptable for global displacement screening because the case meets the internal mass screen and the response is already converged."
            )
        else:
            statements.append(
                "The available evidence is not sufficient to close the shock adequacy decision under the current rule set."
            )

        if response_converged:
            statements.append("The supplied convergence delta satisfies the 10 percent closure threshold.")
        else:
            statements.append("The supplied convergence evidence does not satisfy the 10 percent closure threshold.")

        if release_blocked:
            statements.append("Release remains blocked until damping rationale and convergence support are fully documented.")

        return " ".join(statements)


def load_model_data(case: ShockDeltaCase) -> ModelContext:
    """Load model metadata required by the workflow."""

    bdf_summary = summarize_bdf(case.bdf_path)
    op2_stream = inspect_op2_stream(case.op2_path) if case.op2_path else None
    return ModelContext(bdf_summary=bdf_summary, op2_stream=op2_stream)


def compute_response(case: ShockDeltaCase) -> ShockSpectrumResult | FrequencyResponseResult:
    """Compute the dynamic response for a workflow case.

    The pipeline prefers an SRS calculation when a time history is supplied.
    Otherwise it falls back to a modal FRF when modal terms and a frequency grid
    are available.
    """

    if case.time_seconds and case.base_acceleration_g:
        frequencies = case.srs_frequencies_hz or _logspace(
            start_hz=max(10.0, case.first_mode_hz * 0.5),
            stop_hz=max(case.first_mode_hz * 20.0, 1000.0),
            count=48,
        )
        return compute_srs(
            time_s=case.time_seconds,
            base_acceleration_g=case.base_acceleration_g,
            natural_frequencies_hz=frequencies,
        )

    if case.modal_terms and case.frf_frequencies_hz:
        return compute_modal_frf(
            modes=case.modal_terms,
            frequencies_hz=case.frf_frequencies_hz,
            response_type=case.frf_response_type,
        )

    raise ValueError(
        "Shock-delta response computation requires either a base-acceleration time history or modal terms with an FRF frequency grid"
    )


def run_shock_delta(case: ShockDeltaCase, *, knowledge_root: str | Path = "ava_knowledge") -> ShockDeltaRunResult:
    """Execute the complete shock-delta workflow."""

    model_context = load_model_data(case)
    response = compute_response(case)
    rule_outcome = ShockRuleHook(knowledge_root).evaluate(case)
    case.output_directory.mkdir(parents=True, exist_ok=True)

    if isinstance(response, ShockSpectrumResult):
        response_table_path = _write_srs_table(response, case.output_directory / "shock_srs.csv")
        figure_path = None
        response_kind = "srs"
    else:
        response_table_path = _write_frf_table(response, case.output_directory / "shock_frf.csv")
        figure_path = write_frf_svg(
            response,
            case.output_directory / "shock_frf.svg",
            title=f"{case.case_name} FRF",
        )
        response_kind = "frf"

    summary_path = _write_summary(
        case=case,
        model_context=model_context,
        response_kind=response_kind,
        rule_outcome=rule_outcome,
        response_table_path=response_table_path,
        figure_path=figure_path,
    )
    return ShockDeltaRunResult(
        model_context=model_context,
        response_kind=response_kind,
        rule_outcome=rule_outcome,
        summary_path=summary_path,
        response_table_path=response_table_path,
        figure_path=figure_path,
    )


def _logspace(*, start_hz: float, stop_hz: float, count: int) -> List[float]:
    """Generate a logarithmically spaced frequency grid."""

    if start_hz <= 0.0 or stop_hz <= 0.0:
        raise ValueError("Logarithmic frequency grids require positive endpoints")
    if count < 2:
        return [start_hz]
    log_start = math.log10(start_hz)
    log_stop = math.log10(stop_hz)
    return [10.0 ** (log_start + (log_stop - log_start) * index / (count - 1)) for index in range(count)]


def _write_srs_table(result: ShockSpectrumResult, path: Path) -> Path:
    """Write an SRS table to CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["natural_frequency_hz", "pseudo_acceleration_g", "relative_displacement_mm"])
        for point in result.points:
            writer.writerow(
                [
                    f"{point.natural_frequency_hz:.6f}",
                    f"{point.pseudo_acceleration_g:.6f}",
                    f"{point.relative_displacement_mm:.6f}",
                ]
            )
    return path


def _write_frf_table(result: FrequencyResponseResult, path: Path) -> Path:
    """Write an FRF table to CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frequency_hz", "real", "imag", "magnitude", "phase_degrees"])
        for point in result.points:
            writer.writerow(
                [
                    f"{point.frequency_hz:.6f}",
                    f"{point.complex_response.real:.9e}",
                    f"{point.complex_response.imag:.9e}",
                    f"{point.magnitude:.9e}",
                    f"{point.phase_degrees:.3f}",
                ]
            )
    return path


def _write_summary(
    *,
    case: ShockDeltaCase,
    model_context: ModelContext,
    response_kind: str,
    rule_outcome: ShockRuleOutcome,
    response_table_path: Path,
    figure_path: Optional[Path],
) -> Path:
    """Write a JSON summary for the completed workflow."""

    bounding_box = None
    if model_context.bdf_summary.bounding_box is not None:
        bounding_box = asdict(model_context.bdf_summary.bounding_box)

    payload = {
        "case_name": case.case_name,
        "response_kind": response_kind,
        "response_metric": case.response_metric,
        "event_duration_to_first_mode_period": case.event_duration_to_first_mode_period,
        "cumulative_effective_mass_percent": case.cumulative_effective_mass_percent,
        "damping_basis_documented": case.damping_basis_documented,
        "convergence_delta_percent": case.convergence_delta_percent,
        "model_summary": {
            "bdf_path": str(model_context.bdf_summary.path),
            "grid_count": model_context.bdf_summary.grid_count,
            "element_counts": model_context.bdf_summary.element_counts,
            "mass_element_count": model_context.bdf_summary.mass_element_count,
            "bounding_box": bounding_box,
        },
        "op2_stream": asdict(model_context.op2_stream) if model_context.op2_stream else None,
        "rule_outcome": {
            "primary_rule_id": rule_outcome.primary_rule_id,
            "primary_decision": rule_outcome.primary_decision,
            "matched_rule_ids": list(rule_outcome.matched_rule_ids),
            "release_blocked": rule_outcome.release_blocked,
            "required_actions": list(rule_outcome.required_actions),
            "explanation": rule_outcome.explanation,
            "rule_source": str(rule_outcome.rule_source),
        },
        "artifacts": {
            "response_table": str(response_table_path),
            "figure": str(figure_path) if figure_path else None,
        },
    }

    summary_path = case.output_directory / "shock_delta_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path
