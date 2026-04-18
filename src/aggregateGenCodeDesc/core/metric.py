"""Core metric math for aggregateGenCodeDesc.

Implements the three modes defined in README.md / README_UserStories.md US-001:

    weighted  = Sum(genRatio / 100) / totalLines
    fullyAI   = Count(genRatio == 100) / totalLines
    mostlyAI  = Count(genRatio >= threshold) / totalLines

Pure functions: no VCS, no I/O. Reused by all algorithms (A / B / C).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Metrics:
    """Aggregate result on the in-window live-line set."""

    total_lines: int
    weighted_value: float
    weighted_numerator: float
    fully_ai_value: float
    fully_ai_numerator: int
    mostly_ai_value: float
    mostly_ai_numerator: int
    mostly_ai_threshold: int


def compute_metrics(gen_ratios: Sequence[int], *, threshold: int) -> Metrics:
    """Compute weighted / fullyAI / mostlyAI metrics for a list of per-line genRatio values.

    Args:
        gen_ratios: per-line genRatio values, each an integer in [0, 100].
        threshold: threshold T for the Mostly AI mode, integer in [0, 100].

    Returns:
        Metrics with all three mode values and their numerators.

    Raises:
        ValueError: if any gen_ratio is out of [0, 100] or threshold is out of [0, 100].
    """
    if not 0 <= threshold <= 100:
        raise ValueError(f"threshold must be in [0, 100], got {threshold}")

    for r in gen_ratios:
        if not 0 <= r <= 100:
            raise ValueError(f"genRatio must be in [0, 100], got {r}")

    n = len(gen_ratios)

    if n == 0:
        return Metrics(
            total_lines=0,
            weighted_value=0.0,
            weighted_numerator=0.0,
            fully_ai_value=0.0,
            fully_ai_numerator=0,
            mostly_ai_value=0.0,
            mostly_ai_numerator=0,
            mostly_ai_threshold=threshold,
        )

    weighted_num = sum(r / 100.0 for r in gen_ratios)
    fully_num = sum(1 for r in gen_ratios if r == 100)
    mostly_num = sum(1 for r in gen_ratios if r >= threshold)

    return Metrics(
        total_lines=n,
        weighted_value=weighted_num / n,
        weighted_numerator=weighted_num,
        fully_ai_value=fully_num / n,
        fully_ai_numerator=fully_num,
        mostly_ai_value=mostly_num / n,
        mostly_ai_numerator=mostly_num,
        mostly_ai_threshold=threshold,
    )
