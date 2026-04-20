"""US-008 AC-008-4 partial-failure tests for streaming AlgC.

Existing coverage:
  * tests/test_us008_scale_robust.py exercises AC-008-4 through the CLI's
    eager AlgC path (malformed JSON, unreadable file).
  * tests/test_us008_alg_c_streaming.py exercises the streaming contract
    (parity, generator input, single-record resident, clock skew).

Missing coverage (this file):
  * Streaming with a mid-stream malformed record at position k > 0:
    - Error must identify the failing file's path.
    - AC-008-4 also requires the revisionId be reported; in the streaming
      flow, Pass 1 has already indexed earlier files' timestamps and could
      capture revisionId cheaply — verify it's actually there.
  * Streaming with a mid-stream unreadable file (POSIX chmod 0) at
    position k > 0.
  * Streaming must not write any output — the streaming API itself
    returns Metrics, so "no partial output" is enforced at the caller
    boundary. Instead assert: no successful Metrics returned and the
    exception carries enough context.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_c import run_algorithm_c_streaming
from aggregateGenCodeDesc.core.validation import ValidationError


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _good(rev: str, ts: str) -> dict:
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{
            "fileName": "app.py",
            "codeLines": [{
                "changeType": "add",
                "lineLocation": 1,
                "genRatio": 100,
                "genMethod": "vibeCoding",
                "blame": {
                    "revisionId": rev,
                    "originalFilePath": "app.py",
                    "originalLine": 1,
                    "timestamp": ts,
                },
            }],
        }],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _write_record(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


# =============================================================================
# 1. Malformed JSON at position k > 0 must be reported with file path
#    AND the revisionId surfaced by Pass 1 (AC-008-4).
# =============================================================================
def test_streaming_midstream_malformed_json_reports_path_and_context(
    tmp_path: Path,
) -> None:
    p1 = tmp_path / "001-c1.json"
    p2 = tmp_path / "002-c2.json"  # malformed: will fail in Pass 1
    p3 = tmp_path / "003-c3.json"
    _write_record(p1, _good("c1", "2026-03-01T10:00:00Z"))
    p2.write_text("{ this is not json", encoding="utf-8")
    _write_record(p3, _good("c3", "2026-03-03T10:00:00Z"))

    with pytest.raises(ValidationError) as excinfo:
        run_algorithm_c_streaming(
            [p1, p2, p3],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
        )
    msg = str(excinfo.value)
    # AC-008-4: file path is reported.
    assert str(p2) in msg or p2.name in msg, (
        f"malformed-file error must identify the file: {msg!r}"
    )
    # Pass 1 failed BEFORE we could read revisionId — so the AC's
    # "revisionId" requirement cannot be met for a JSON-parse failure.
    # This test asserts at minimum the "invalid JSON" diagnostic.
    assert "json" in msg.lower() or "JSON" in msg


# =============================================================================
# 2. Malformed v26.04 record STRUCTURE at position k > 0 — parses as JSON
#    but is missing REPOSITORY.revisionTimestamp.
# =============================================================================
def test_streaming_midstream_missing_repo_ts_reports_path_and_field(
    tmp_path: Path,
) -> None:
    p1 = tmp_path / "001-c1.json"
    p2 = tmp_path / "002-c2.json"
    p3 = tmp_path / "003-c3.json"
    _write_record(p1, _good("c1", "2026-03-01T10:00:00Z"))
    bad = _good("c2", "2026-03-02T10:00:00Z")
    # Strip the required field in Pass-1's view.
    bad["REPOSITORY"].pop("revisionTimestamp")
    _write_record(p2, bad)
    _write_record(p3, _good("c3", "2026-03-03T10:00:00Z"))

    with pytest.raises(ValidationError) as excinfo:
        run_algorithm_c_streaming(
            [p1, p2, p3],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
        )
    msg = str(excinfo.value)
    assert p2.name in msg or str(p2) in msg
    assert "revisionTimestamp" in msg


# =============================================================================
# 3. Structurally valid v26.04 file that FAILS in Pass 2 — Pass 1 succeeded
#    so revisionId was indexed; the AC-008-4 "path AND revisionId" clause
#    applies. Construct a record with valid REPOSITORY.revisionTimestamp
#    but a malformed DETAIL entry (invalid genRatio).
# =============================================================================
def test_streaming_pass2_failure_reports_path_and_revision_id(
    tmp_path: Path,
) -> None:
    p1 = tmp_path / "001-c1.json"
    p2 = tmp_path / "002-c2.json"  # fails in Pass 2
    _write_record(p1, _good("c1", "2026-03-01T10:00:00Z"))
    bad = _good("c2", "2026-03-02T10:00:00Z")
    # genRatio 999 is out of [0, 100]; flagged in load_v2604_record (Pass 2).
    bad["DETAIL"][0]["codeLines"][0]["genRatio"] = 999
    _write_record(p2, bad)

    with pytest.raises(ValidationError) as excinfo:
        run_algorithm_c_streaming(
            [p1, p2],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
        )
    msg = str(excinfo.value)
    # Path must be reported.
    assert p2.name in msg or str(p2) in msg, (
        f"Pass-2 failure must identify the file: {msg!r}"
    )
    # AC-008-4: revisionId must be reported. Pass 1 has it; production code
    # is expected to include it on any Pass-2 error.
    assert "c2" in msg, (
        f"Pass-2 failure must include the revisionId (indexed in Pass 1): "
        f"{msg!r}"
    )


# =============================================================================
# 4. POSIX-only: unreadable mid-stream file (chmod 0) at position k > 0.
# =============================================================================
@pytest.mark.skipif(sys.platform == "win32",
                    reason="chmod-based unreadable simulation is POSIX-only")
def test_streaming_midstream_unreadable_file_reports_path(
    tmp_path: Path,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not restrict reads")

    p1 = tmp_path / "001-c1.json"
    p2 = tmp_path / "002-c2.json"
    p3 = tmp_path / "003-c3.json"
    _write_record(p1, _good("c1", "2026-03-01T10:00:00Z"))
    _write_record(p2, _good("c2", "2026-03-02T10:00:00Z"))
    _write_record(p3, _good("c3", "2026-03-03T10:00:00Z"))
    p2.chmod(0)

    try:
        with pytest.raises(ValidationError) as excinfo:
            run_algorithm_c_streaming(
                [p1, p2, p3],
                start_time=_utc("2026-01-01T00:00:00Z"),
                end_time=_utc("2026-12-31T00:00:00Z"),
                threshold=60,
            )
        msg = str(excinfo.value)
        assert p2.name in msg or str(p2) in msg
        assert "cannot read" in msg.lower() or "permission" in msg.lower()
    finally:
        p2.chmod(stat.S_IRUSR | stat.S_IWUSR)
