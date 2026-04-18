"""US-010 AC-010-2, AC-010-3, AC-010-6 — DEBUG detail / WARN anomaly / format+stderr.

These complement test_us010_logging.py with the remaining ACs.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main as cli_main


def _mk_v2604(rev: str, ts: str, *, n_adds: int = 1) -> dict:
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{
            "fileName": "app.py",
            "codeLines": [
                {
                    "changeType": "add",
                    "lineLocation": i,
                    "genRatio": 100,
                    "genMethod": "vibeCoding",
                    "blame": {
                        "revisionId": rev,
                        "originalFilePath": "app.py",
                        "originalLine": i,
                        "timestamp": ts,
                    },
                }
                for i in range(1, n_adds + 1)
            ],
        }],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _cli_args(gcd: Path, out: Path, log_level: str = "Debug") -> list[str]:
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


# =============================================================================
# AC-010-2 [Typical] DEBUG level exposes: algorithm start, per-file load,
# revisionId, and entry counts.
# =============================================================================
def test_ac_010_2_debug_surfaces_per_file_detail(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    gcd.mkdir()
    (gcd / "c1.json").write_text(
        json.dumps(_mk_v2604("c1", "2026-02-01T10:00:00Z", n_adds=3)),
        encoding="utf-8",
    )
    (gcd / "c2.json").write_text(
        json.dumps(_mk_v2604("c2", "2026-02-02T10:00:00Z", n_adds=5)),
        encoding="utf-8",
    )

    with caplog.at_level("DEBUG", logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out, log_level="Debug"))

    assert rc == 0
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    debug_msgs = [r.message for r in debug_records]
    combined = " | ".join(debug_msgs)

    # Algorithm-start marker.
    assert any("algorithm=C start" in m for m in debug_msgs), combined
    # Per-file load records naming the file and its revisionId + add count.
    assert any("c1.json" in m and "revisionId=c1" in m for m in debug_msgs), combined
    assert any("c2.json" in m and "revisionId=c2" in m for m in debug_msgs), combined
    # Entry counts present.
    assert any("adds=3" in m for m in debug_msgs), combined
    assert any("adds=5" in m for m in debug_msgs), combined


# =============================================================================
# AC-010-3 [Typical] WARN emitted for non-fatal anomalies (duplicate record
# under OnDuplicate.LAST_WINS) — records flow through and contain the offending
# revisionId.
# =============================================================================
def test_ac_010_3_warn_on_duplicate_records(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    gcd.mkdir()
    # Two files with the SAME revisionId → duplicate.
    (gcd / "a.json").write_text(
        json.dumps(_mk_v2604("dup", "2026-02-01T10:00:00Z")),
        encoding="utf-8",
    )
    (gcd / "b.json").write_text(
        json.dumps(_mk_v2604("dup", "2026-02-01T10:00:00Z")),
        encoding="utf-8",
    )
    argv = _cli_args(gcd, out, log_level="Warning") + ["--on-duplicate", "last-wins"]

    with caplog.at_level("WARNING", logger="aggregateGenCodeDesc"):
        rc = cli_main(argv)

    assert rc == 0
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warns, "expected a WARN record for the duplicate"
    combined = " ".join(r.message for r in warns)
    assert "duplicate" in combined.lower()
    assert "dup" in combined  # the offending revisionId


# =============================================================================
# AC-010-6 [Observability] Format is structured and log output goes to STDERR
# (not stdout). Exercised by running the CLI in a subprocess so we can inspect
# the raw streams.
# =============================================================================
def test_ac_010_6_format_and_stderr_routing(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    gcd.mkdir()
    (gcd / "c1.json").write_text(
        json.dumps(_mk_v2604("c1", "2026-02-01T10:00:00Z")),
        encoding="utf-8",
    )

    argv = [
        sys.executable, "-m", "aggregateGenCodeDesc",
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out),
        "--log-level", "Info",
    ]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr

    # stdout should NOT carry log lines — it is reserved for metric/result
    # payloads. Log lines go to stderr.
    assert "LOAD phase" not in result.stdout
    assert "SUMMARY phase" not in result.stdout

    # stderr must contain the structured log entries.
    assert "LOAD phase" in result.stderr
    assert "SUMMARY phase" in result.stderr

    # Format contract: every non-empty stderr line that includes "LOAD phase"
    # or "SUMMARY phase" must match:
    #   <timestamp> <LEVEL> <logger> <message>
    # where <timestamp> is an ISO-like datetime.
    pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"  # date + time
        r"(?:[,.]\d+)?\s+"                            # optional millis
        r"(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"   # level
        r"aggregateGenCodeDesc\s+"                    # logger name
        r".+$"                                        # message
    )
    phase_lines = [
        ln for ln in result.stderr.splitlines()
        if "LOAD phase" in ln or "SUMMARY phase" in ln
    ]
    assert phase_lines, f"no phase lines captured; stderr={result.stderr!r}"
    for ln in phase_lines:
        assert pattern.match(ln), f"log line did not match structured format: {ln!r}"
