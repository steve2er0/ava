"""Compatibility stub for the retired legacy AVA plugin toolset.

AVA engineering capabilities are now exposed through the approved
``engineering`` toolset rather than direct ``ava_*`` plugin tools.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Register no legacy AVA tools."""

    return None
