"""Guard against uncaught runtime exceptions in cli.main.

README_UserGuide.md §7 promises exit code 1 for "Runtime/IO error ...
uncaught exception". Any non-ValidationError escaping orchestration
must be logged and return 1, not propagate as a traceback.
"""

from __future__ import annotations

import json
import logging
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


def _cli_args(gcd: Path, out: Path) -> list[str]:
    return [
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out),
    ]


# =============================================================================
# Uncaught non-ValidationError must not crash the process. It must be logged
# at ERROR and return exit code 1.
# =============================================================================
def test_uncaught_exception_returns_exit_1(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    gcd.mkdir()
    (gcd / "c1.json").write_text(
        json.dumps(_mk_v2604("c1", "2026-02-01T10:00:00Z")),
        encoding="utf-8",
    )

    # Inject a runtime bug deep in the orchestration: make write_output_json
    # raise a generic RuntimeError (NOT a ValidationError). This simulates
    # an I/O failure, a stdlib bug, or any other unexpected runtime error.
    from aggregateGenCodeDesc import cli as cli_module

    def boom(*_a, **_k):
        raise RuntimeError("simulated disk failure writing output JSON")

    monkeypatch.setattr(cli_module, "write_output_json", boom)

    with caplog.at_level(logging.ERROR, logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out))

    assert rc == 1, f"expected exit 1, got {rc}"
    # Error must be logged with the original message (diagnosable).
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected an ERROR log record"
    combined = " ".join(r.message for r in error_records)
    assert "simulated disk failure" in combined, combined
