"""US-001 — Core Metric Calculation.

Mirrors README_UserStories.md US-001 AC-001-1..6:
  - Weighted         = Sum(genRatio/100) / totalLines
  - Fully AI (==100) = Count(genRatio == 100) / totalLines
  - Mostly AI (>=T)  = Count(genRatio >= T) / totalLines
  - Zero denominator yields 0.0 for all modes.

Tests are pure-math: no VCS, no I/O.
"""

from __future__ import annotations

import pytest

from aggregateGenCodeDesc.core.metric import Metrics, compute_metrics

# Canonical fixture shared with README example:
#   10 in-window live lines: 5 × 100, 3 × 80, 1 × 30, 1 × 0.
CANONICAL = [100, 100, 100, 100, 100, 80, 80, 80, 30, 0]


# ---------------------------------------------------------------------------
# AC-001-1 [Typical] Weighted mode calculates sum of genRatio
# ---------------------------------------------------------------------------
def test_ac_001_1_weighted_mode_typical() -> None:
    # GIVEN 10 in-window live lines with the canonical genRatio list
    # WHEN  compute_metrics runs
    # THEN  weighted is 77.0% (7.7 / 10)
    m = compute_metrics(CANONICAL, threshold=60)
    assert m.weighted_value == pytest.approx(0.77, abs=1e-9)
    assert m.weighted_numerator == pytest.approx(7.7, abs=1e-9)


# ---------------------------------------------------------------------------
# AC-001-2 [Typical] Fully AI mode counts only genRatio == 100
# ---------------------------------------------------------------------------
def test_ac_001_2_fully_ai_mode_typical() -> None:
    m = compute_metrics(CANONICAL, threshold=60)
    assert m.fully_ai_value == pytest.approx(0.50, abs=1e-9)
    assert m.fully_ai_numerator == 5


# ---------------------------------------------------------------------------
# AC-001-3 [Typical] Mostly AI mode counts genRatio >= threshold
# ---------------------------------------------------------------------------
def test_ac_001_3_mostly_ai_mode_typical() -> None:
    m = compute_metrics(CANONICAL, threshold=60)
    assert m.mostly_ai_value == pytest.approx(0.80, abs=1e-9)
    assert m.mostly_ai_numerator == 8
    assert m.mostly_ai_threshold == 60


# ---------------------------------------------------------------------------
# AC-001-4 [Edge] All lines are human-written
# ---------------------------------------------------------------------------
def test_ac_001_4_all_human_edge() -> None:
    m = compute_metrics([0] * 50, threshold=60)
    assert m.total_lines == 50
    assert m.weighted_value == 0.0
    assert m.fully_ai_value == 0.0
    assert m.mostly_ai_value == 0.0


# ---------------------------------------------------------------------------
# AC-001-5 [Edge] All lines are fully AI-generated
# ---------------------------------------------------------------------------
def test_ac_001_5_all_fully_ai_edge() -> None:
    m = compute_metrics([100] * 50, threshold=60)
    assert m.total_lines == 50
    assert m.weighted_value == 1.0
    assert m.fully_ai_value == 1.0
    assert m.mostly_ai_value == 1.0


# ---------------------------------------------------------------------------
# AC-001-6 [Edge] No lines changed within the time window
# ---------------------------------------------------------------------------
def test_ac_001_6_empty_window_edge() -> None:
    m = compute_metrics([], threshold=60)
    assert m.total_lines == 0
    assert m.weighted_value == 0.0
    assert m.fully_ai_value == 0.0
    assert m.mostly_ai_value == 0.0
    # numerators are also zero
    assert m.weighted_numerator == 0.0
    assert m.fully_ai_numerator == 0
    assert m.mostly_ai_numerator == 0


# ---------------------------------------------------------------------------
# Cross-check: the returned Metrics is a dataclass / has the expected shape.
# ---------------------------------------------------------------------------
def test_metrics_shape_has_all_fields() -> None:
    m = compute_metrics(CANONICAL, threshold=60)
    assert isinstance(m, Metrics)
    # threshold is echoed, denominator is echoed
    assert m.mostly_ai_threshold == 60
    assert m.total_lines == 10


# ---------------------------------------------------------------------------
# Input validation (not in US-001 AC but required for safety).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_ratio", [-1, 101, 200])
def test_rejects_out_of_range_genratio(bad_ratio: int) -> None:
    with pytest.raises(ValueError):
        compute_metrics([50, bad_ratio, 80], threshold=60)


@pytest.mark.parametrize("bad_threshold", [-1, 101])
def test_rejects_out_of_range_threshold(bad_threshold: int) -> None:
    with pytest.raises(ValueError):
        compute_metrics([50], threshold=bad_threshold)
