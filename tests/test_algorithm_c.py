"""Algorithm C — embedded-blame aggregation over v26.04 records.

CaTDD tests for the core replay+filter behavior. No disk I/O — records are
constructed as dicts and fed through load_v2604_record().
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aggregateGenCodeDesc.algorithms.alg_c import (
    V2604Record,
    load_v2604_record,
    run_algorithm_c,
)
from aggregateGenCodeDesc.core.protocol import OnClockSkew
from aggregateGenCodeDesc.core.validation import ValidationError


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _mk(
    revision_id: str,
    revision_ts: str,
    *,
    adds: list[tuple[int, int, str, int, str]] | None = None,
    deletes: list[tuple[str, str, int]] | None = None,
) -> dict:
    """Build a v26.04 record dict.

    adds entry = (lineLocation, genRatio, blame_revId, blame_origLine, blame_ts)
    deletes entry = (blame_revId, blame_origFile, blame_origLine)
    """
    code_lines: list[dict] = []
    for rev, orig_file, orig_line in deletes or []:
        code_lines.append(
            {
                "changeType": "delete",
                "blame": {
                    "revisionId": rev,
                    "originalFilePath": orig_file,
                    "originalLine": orig_line,
                },
            }
        )
    for loc, gr, brev, bline, bts in adds or []:
        code_lines.append(
            {
                "changeType": "add",
                "lineLocation": loc,
                "genRatio": gr,
                "genMethod": "vibeCoding",
                "blame": {
                    "revisionId": brev,
                    "originalFilePath": "src/a.py",
                    "originalLine": bline,
                    "timestamp": bts,
                },
            }
        )
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "src/a.py", "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": revision_id,
            "revisionTimestamp": revision_ts,
        },
    }


# ---------------------------------------------------------------------------
# AC-AlgC-1 [Typical] In-window adds are summed via compute_metrics
# ---------------------------------------------------------------------------
def test_ac_algc_1_in_window_adds_are_summed() -> None:
    # One record adds 3 lines with genRatio [100, 80, 30], all in-window.
    rec = load_v2604_record(
        _mk(
            "c1",
            "2026-03-15T10:00:00Z",
            adds=[
                (1, 100, "c1", 1, "2026-03-15T10:00:00Z"),
                (2, 80, "c1", 2, "2026-03-15T10:00:00Z"),
                (3, 30, "c1", 3, "2026-03-15T10:00:00Z"),
            ],
        )
    )
    m = run_algorithm_c(
        [rec],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 3
    assert m.weighted_value == pytest.approx((1.0 + 0.8 + 0.3) / 3)
    assert m.fully_ai_numerator == 1
    assert m.mostly_ai_numerator == 2


# ---------------------------------------------------------------------------
# AC-AlgC-2 [Typical] Later commit's delete removes prior add
# ---------------------------------------------------------------------------
def test_ac_algc_2_delete_removes_prior_add() -> None:
    r1 = load_v2604_record(
        _mk(
            "c1",
            "2026-03-15T10:00:00Z",
            adds=[
                (1, 100, "c1", 1, "2026-03-15T10:00:00Z"),
                (2, 100, "c1", 2, "2026-03-15T10:00:00Z"),
            ],
        )
    )
    r2 = load_v2604_record(
        _mk(
            "c2",
            "2026-03-16T10:00:00Z",
            deletes=[("c1", "src/a.py", 2)],
        )
    )
    m = run_algorithm_c(
        [r1, r2],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 1
    assert m.fully_ai_value == 1.0


# ---------------------------------------------------------------------------
# AC-AlgC-3 [Edge] Out-of-order input sorts ascending by revisionTimestamp
# ---------------------------------------------------------------------------
def test_ac_algc_3_sorts_out_of_order_input() -> None:
    # r2 (later) provided first; it deletes a line that r1 (earlier) will add.
    # Correct order: r1 first (adds), then r2 (deletes) → 0 lines remain.
    r1 = load_v2604_record(
        _mk("c1", "2026-03-15T10:00:00Z",
            adds=[(1, 100, "c1", 1, "2026-03-15T10:00:00Z")])
    )
    r2 = load_v2604_record(
        _mk("c2", "2026-03-16T10:00:00Z",
            deletes=[("c1", "src/a.py", 1)])
    )
    m = run_algorithm_c(
        [r2, r1],  # deliberately reversed
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 0


# ---------------------------------------------------------------------------
# AC-AlgC-4 [Typical] Lines whose blame.timestamp is outside [start,end] excluded
# ---------------------------------------------------------------------------
def test_ac_algc_4_filters_by_blame_timestamp() -> None:
    # r1 adds a pre-window line (genRatio 100) — surviving but out-of-window.
    # r2 adds an in-window line (genRatio 50).
    r1 = load_v2604_record(
        _mk("c1", "2025-12-15T10:00:00Z",
            adds=[(1, 100, "c1", 1, "2025-12-15T10:00:00Z")])
    )
    r2 = load_v2604_record(
        _mk("c2", "2026-03-15T10:00:00Z",
            adds=[(2, 50, "c2", 2, "2026-03-15T10:00:00Z")])
    )
    m = run_algorithm_c(
        [r1, r2],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 1
    assert m.weighted_value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# AC-AlgC-5 [Typical] Records with revisionTimestamp > endTime are not processed
# ---------------------------------------------------------------------------
def test_ac_algc_5_ignores_records_after_endtime() -> None:
    # r1 is in-window (adds line); r2 is AFTER endTime (would delete line).
    # r2 must be ignored, so the line survives.
    r1 = load_v2604_record(
        _mk("c1", "2026-03-15T10:00:00Z",
            adds=[(1, 100, "c1", 1, "2026-03-15T10:00:00Z")])
    )
    r2 = load_v2604_record(
        _mk("c2", "2027-01-01T10:00:00Z",
            deletes=[("c1", "src/a.py", 1)])
    )
    m = run_algorithm_c(
        [r1, r2],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 1


# ---------------------------------------------------------------------------
# AC-AlgC-6 [Typical] lineRange expansion on add
# ---------------------------------------------------------------------------
def test_ac_algc_6_add_lineRange_expands() -> None:
    data = _mk("c1", "2026-03-15T10:00:00Z")
    data["DETAIL"][0]["codeLines"] = [
        {
            "changeType": "add",
            "lineRange": {"from": 1, "to": 5},
            "genRatio": 100,
            "genMethod": "vibeCoding",
            "blame": {
                "revisionId": "c1",
                "originalFilePath": "src/a.py",
                "originalLine": 10,
                "timestamp": "2026-03-15T10:00:00Z",
            },
        }
    ]
    rec = load_v2604_record(data)
    m = run_algorithm_c(
        [rec],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 5
    assert m.fully_ai_value == 1.0


# ---------------------------------------------------------------------------
# AC-006-4 [Fault] Clock-skew policy
# ---------------------------------------------------------------------------
def test_ac_006_4_clock_skew_abort() -> None:
    r1 = load_v2604_record(_mk("c1", "2026-03-15T10:00:00Z"))
    r2 = load_v2604_record(_mk("c2", "2026-03-14T10:00:00Z"))  # earlier than r1
    with pytest.raises(ValidationError, match="clock skew"):
        run_algorithm_c(
            [r1, r2],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
            on_clock_skew=OnClockSkew.ABORT,
        )


def test_ac_006_4_clock_skew_ignore_sorts_and_continues() -> None:
    r1 = load_v2604_record(
        _mk("c1", "2026-03-15T10:00:00Z",
            adds=[(1, 100, "c1", 1, "2026-03-15T10:00:00Z")])
    )
    r2 = load_v2604_record(
        _mk("c2", "2026-03-14T10:00:00Z",
            adds=[(2, 80, "c2", 2, "2026-03-14T10:00:00Z")])
    )
    # Default policy = IGNORE: sort ascending and continue.
    m = run_algorithm_c(
        [r1, r2],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert m.total_lines == 2


# ---------------------------------------------------------------------------
# Loader: rejects non-26.04 protocolVersion
# ---------------------------------------------------------------------------
def test_load_rejects_non_v2604() -> None:
    with pytest.raises(ValidationError, match="26.04"):
        load_v2604_record({"protocolVersion": "26.03", "REPOSITORY": {}})


def test_load_returns_typed_record() -> None:
    rec = load_v2604_record(_mk("c1", "2026-03-15T10:00:00Z"))
    assert isinstance(rec, V2604Record)
    assert rec.revision_id == "c1"
