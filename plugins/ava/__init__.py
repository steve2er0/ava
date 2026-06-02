"""AVA vibroacoustic engineering plugin.

The plugin exposes the AVA runtime package through Hermes tools while keeping
the engineering knowledge and numerical code outside the agent core.
"""

from __future__ import annotations

from plugins.ava.tools import (
    AVA_BUILD_MODAL_DECK_SCHEMA,
    AVA_COMPUTE_MODAL_FRF_SCHEMA,
    AVA_COMPUTE_SRS_SCHEMA,
    AVA_INSPECT_OP2_SCHEMA,
    AVA_RUN_SHOCK_DELTA_SCHEMA,
    AVA_SUMMARIZE_BDF_SCHEMA,
    handle_build_modal_deck,
    handle_compute_modal_frf,
    handle_compute_srs,
    handle_inspect_op2,
    handle_run_shock_delta,
    handle_summarize_bdf,
)


_TOOLS = (
    ("ava_compute_modal_frf", AVA_COMPUTE_MODAL_FRF_SCHEMA, handle_compute_modal_frf),
    ("ava_compute_srs", AVA_COMPUTE_SRS_SCHEMA, handle_compute_srs),
    ("ava_summarize_bdf", AVA_SUMMARIZE_BDF_SCHEMA, handle_summarize_bdf),
    ("ava_inspect_op2", AVA_INSPECT_OP2_SCHEMA, handle_inspect_op2),
    ("ava_build_modal_deck", AVA_BUILD_MODAL_DECK_SCHEMA, handle_build_modal_deck),
    ("ava_run_shock_delta", AVA_RUN_SHOCK_DELTA_SCHEMA, handle_run_shock_delta),
)


def register(ctx) -> None:
    """Register AVA runtime tools with Hermes."""
    for name, schema, handler in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="ava",
            schema=schema,
            handler=handler,
            emoji="~",
        )
