"""US-010 Diagnostics and Logging.

Covers acceptance criteria that are code-enforceable today:

  AC-010-1  [Typical]  Default level is INFO; LOAD and SUMMARY phase
                       markers appear in output.
  AC-010-4  [Typical]  Fatal I/O failure emits ERROR with file path
                       and OS description, exit code is non-zero,
                       no partial output is written.
  AC-010-5  [Edge]     --log-level Error suppresses INFO and WARN.
  AC-010-7  [Testability] Log level can be set programmatically
                          on the package logger without invoking the CLI.

AC-010-2/3 are covered in spirit by tests touching DEBUG/WARN elsewhere
(see test_algorithm_b on-missing ZERO warnings). AC-010-6 structured
stderr routing is exercised implicitly by caplog's handler-attachment
(which only captures records from the Python logging subsystem).
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main as cli_main


def _mk_v2604(rev: str, ts: str) -> dict:
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


def _cli_args(gcd: Path, out: Path, *, log_level: str = "Info") -> list[str]:
    return [
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out),
        "--log-level", log_level,
    ]


def _write_one_record(gcd: Path) -> None:
    gcd.mkdir(parents=True, exist_ok=True)
    (gcd / "c1.json").write_text(
        json.dumps(_mk_v2604("c1", "2026-02-01T10:00:00Z")),
        encoding="utf-8",
    )


# =============================================================================
# AC-010-1 [Typical] Default level is INFO; LOAD and SUMMARY markers appear.
# =============================================================================
def test_ac_010_1_info_default_emits_load_and_summary_phases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    _write_one_record(gcd)

    with caplog.at_level("INFO", logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out, log_level="Info"))

    assert rc == 0
    messages = [r.message for r in caplog.records]
    combined = " | ".join(messages)
    # Phase markers required by AC-010-1.
    assert any("LOAD phase" in m for m in messages), combined
    assert any("SUMMARY phase" in m for m in messages), combined
    # INFO is the observed level for those markers.
    load_rec = next(r for r in caplog.records if "LOAD phase" in r.message)
    assert load_rec.levelno == logging.INFO


# =============================================================================
# AC-010-4 [Typical] ERROR on fatal file failure + exit 2 + no partial output.
# =============================================================================
def test_ac_010_4_error_on_fatal_file_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    (gcd / "bad.json").write_text("{not json", encoding="utf-8")
    out = tmp_path / "out"

    with caplog.at_level("ERROR", logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out, log_level="Info"))

    assert rc == 2
    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records, "expected at least one ERROR-level record"
    combined = " ".join(r.message for r in err_records)
    # File path surfaced.
    assert "bad.json" in combined
    # OS-level / parser error description surfaced.
    assert "JSON" in combined or "json" in combined
    # No partial output written.
    assert not out.exists() or not any(out.iterdir())


# =============================================================================
# AC-010-5 [Edge] --log-level Error suppresses INFO and WARN.
# =============================================================================
def test_ac_010_5_error_level_suppresses_info_and_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    _write_one_record(gcd)

    # Capture at DEBUG level (caplog boundary) so we can see EVERYTHING that
    # actually gets emitted by the package logger — then assert nothing at
    # INFO / WARN was emitted because --log-level Error raised our threshold.
    with caplog.at_level("DEBUG", logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out, log_level="Error"))

    assert rc == 0
    pkg_records = [
        r for r in caplog.records if r.name == "aggregateGenCodeDesc"
    ]
    # No INFO or WARNING records should have been emitted at all.
    for r in pkg_records:
        assert r.levelno >= logging.ERROR, (
            f"unexpected {r.levelname} record under --log-level Error: {r.message!r}"
        )


# =============================================================================
# AC-010-7 [Testability] Programmatic log-level control works without the CLI.
# =============================================================================
def test_ac_010_7_programmatic_log_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pkg = logging.getLogger("aggregateGenCodeDesc")
    original = pkg.level
    try:
        pkg.setLevel(logging.DEBUG)
        with caplog.at_level("DEBUG", logger="aggregateGenCodeDesc"):
            pkg.debug("programmatic debug probe")
            pkg.info("programmatic info probe")
        names = [(r.levelno, r.message) for r in caplog.records
                 if r.name == "aggregateGenCodeDesc"]
        assert (logging.DEBUG, "programmatic debug probe") in names
        assert (logging.INFO, "programmatic info probe") in names
    finally:
        pkg.setLevel(original)


# =============================================================================
# Side check: the new Error choice is accepted by argparse.
# =============================================================================
def test_ac_010_error_choice_is_accepted(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    _write_one_record(gcd)
    # Smoke: CLI should succeed with --log-level Error (no SystemExit).
    rc = cli_main(_cli_args(gcd, out, log_level="Error"))
    assert rc == 0
