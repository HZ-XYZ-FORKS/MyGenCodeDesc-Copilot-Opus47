"""AC-008-2 [Performance] Streaming AlgC — memory-bounded replay.

Contract (run_algorithm_c_streaming, see alg_c.py design note):
  * Accepts an Iterable[Path] (may be a single-use generator).
  * Produces the same Metrics as the eager run_algorithm_c for equivalent
    inputs.
  * Peak live state is ≤ one record being parsed + the surviving-set
    dictionary; the full set of records is never resident at once.

The tests below assert:
  1. Functional parity against eager run_algorithm_c on a 30-record input.
  2. Generator input is accepted (proves the public API takes an iterable,
     not a concrete list of records).
  3. No more than one V2604Record is ever alive at replay time — measured
     by instrumenting _load_single_record to track concurrent calls'
     returned objects via a weakref finalizer.
  4. Clock-skew policy ABORT still fires for out-of-order input.
"""

from __future__ import annotations

import gc
import json
import weakref
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms import alg_c as alg_c_module
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c,
    run_algorithm_c_streaming,
)
from aggregateGenCodeDesc.core.protocol import OnClockSkew
from aggregateGenCodeDesc.core.validation import ValidationError


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _mk(rev: str, ts: str, *, add_count: int) -> dict:
    """Build a v26.04 record dict with add_count adds, one delete of
    the first line from the previous revision (makes a non-trivial
    surviving set)."""
    code_lines: list[dict] = [
        {
            "changeType": "add",
            "lineLocation": i,
            "genRatio": 100 if i % 2 == 0 else 50,
            "genMethod": "vibeCoding",
            "blame": {
                "revisionId": rev,
                "originalFilePath": "app.py",
                "originalLine": i,
                "timestamp": ts,
            },
        }
        for i in range(1, add_count + 1)
    ]
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "app.py", "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _write_records(tmp_path: Path, n: int) -> list[Path]:
    """Write n records with ascending timestamps; return list of paths."""
    paths: list[Path] = []
    base_day = 1
    for i in range(n):
        ts = f"2026-03-{base_day + i:02d}T10:00:00Z"
        rev = f"c{i:04d}"
        p = tmp_path / f"{i:04d}-{rev}.json"
        p.write_text(json.dumps(_mk(rev, ts, add_count=5)), encoding="utf-8")
        paths.append(p)
    return paths


# =============================================================================
# 1. Functional parity against eager AlgC.
# =============================================================================
def test_streaming_matches_eager_metrics(tmp_path: Path) -> None:
    paths = _write_records(tmp_path, n=30)

    # Eager: load all records into memory, feed run_algorithm_c.
    eager_records = [
        load_v2604_record(json.loads(p.read_text(encoding="utf-8")))
        for p in paths
    ]
    eager = run_algorithm_c(
        eager_records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )

    # Streaming: same inputs, one record at a time.
    stream = run_algorithm_c_streaming(
        paths,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )

    assert stream.total_lines == eager.total_lines
    assert stream.weighted_value == pytest.approx(eager.weighted_value)
    assert stream.fully_ai_value == pytest.approx(eager.fully_ai_value)
    assert stream.mostly_ai_value == pytest.approx(eager.mostly_ai_value)


# =============================================================================
# 2. Generator input is accepted (iterable, not list).
# =============================================================================
def test_streaming_accepts_generator_input(tmp_path: Path) -> None:
    paths = _write_records(tmp_path, n=5)

    def _gen():
        for p in paths:
            yield p

    result = run_algorithm_c_streaming(
        _gen(),
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # 5 records × 5 adds, no deletes → 25 surviving lines.
    assert result.total_lines == 25


# =============================================================================
# 3. Peak live records during replay ≤ 1.
#
# Instrument _load_single_record with a weakref to the returned V2604Record.
# After the call returns and the replay loop completes its iteration, the
# record should become unreachable before the next _load_single_record
# call. We measure by tracking: (a) cumulative load count, and (b) how many
# prior-record weakrefs are still alive when the next load happens.
# =============================================================================
def test_streaming_never_holds_more_than_one_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_records(tmp_path, n=10)

    live_refs: list[weakref.ReferenceType] = []
    concurrency: list[int] = []  # alive count observed at each load entry

    original = alg_c_module._load_single_record

    def traced(path: Path):
        # Force collection of any dead record before measuring.
        gc.collect()
        alive = sum(1 for r in live_refs if r() is not None)
        concurrency.append(alive)
        rec = original(path)
        live_refs.append(weakref.ref(rec))
        return rec

    monkeypatch.setattr(alg_c_module, "_load_single_record", traced)

    run_algorithm_c_streaming(
        paths,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )

    assert len(concurrency) == 10, "each path should be loaded exactly once"
    # First load: 0 alive; every subsequent load: prior record must have
    # been released by the replay loop before the next file is opened.
    assert concurrency == [0] * 10, (
        f"streaming held >1 record at once: observed alive counts {concurrency}"
    )


# =============================================================================
# 4. Clock-skew ABORT policy still fires on out-of-order streaming input.
# =============================================================================
def test_streaming_honors_clock_skew_abort(tmp_path: Path) -> None:
    # Write two records in reverse timestamp order (later file first).
    p_later = tmp_path / "a-later.json"
    p_earlier = tmp_path / "b-earlier.json"
    p_later.write_text(json.dumps(_mk(
        "c2", "2026-03-10T10:00:00Z", add_count=1
    )), encoding="utf-8")
    p_earlier.write_text(json.dumps(_mk(
        "c1", "2026-03-01T10:00:00Z", add_count=1
    )), encoding="utf-8")

    with pytest.raises(ValidationError) as excinfo:
        run_algorithm_c_streaming(
            [p_later, p_earlier],  # out-of-order on purpose
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
            on_clock_skew=OnClockSkew.ABORT,
        )
    assert "clock skew" in str(excinfo.value).lower()


# =============================================================================
# 5. Timestamp filter: records with revisionTimestamp > end_time are dropped
# in Pass 1 (so Pass 2 never even opens those files).
# =============================================================================
def test_streaming_skips_post_endtime_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three records: c1 in-window, c2 in-window, c3 past end_time.
    p1 = tmp_path / "c1.json"
    p2 = tmp_path / "c2.json"
    p3 = tmp_path / "c3.json"
    p1.write_text(json.dumps(_mk("c1", "2026-03-01T10:00:00Z", add_count=2)),
                  encoding="utf-8")
    p2.write_text(json.dumps(_mk("c2", "2026-03-02T10:00:00Z", add_count=2)),
                  encoding="utf-8")
    p3.write_text(json.dumps(_mk("c3", "2027-01-01T10:00:00Z", add_count=2)),
                  encoding="utf-8")

    loaded: list[Path] = []
    original = alg_c_module._load_single_record

    def traced(path: Path):
        loaded.append(path)
        return original(path)

    monkeypatch.setattr(alg_c_module, "_load_single_record", traced)

    result = run_algorithm_c_streaming(
        [p1, p2, p3],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )

    # c3 must never have been opened for the full replay load.
    assert p3 not in loaded, (
        f"post-endTime record was loaded in Pass 2: {loaded}"
    )
    assert {p1, p2} == set(loaded)
    # 2 in-window records × 2 adds each = 4 surviving lines.
    assert result.total_lines == 4
