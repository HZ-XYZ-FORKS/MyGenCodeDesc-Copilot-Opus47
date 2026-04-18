"""US-008 — scale, performance, and robustness.

Covers:
  AC-008-1 [Performance] AlgA completes at small-scale smoke test (regression guard).
  AC-008-3 [Edge]        Zero commits in window → metrics all zero, no error.
  AC-008-4 [Robust]      I/O failure reports file path + revisionId; no partial output written.

AC-008-2 [Performance] AlgC streaming over ~200 GB requires a streaming
refactor of alg_c (loads all records into memory today) and is tracked
as future work.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c_full,
)
from aggregateGenCodeDesc.cli import main as cli_main

from tests._git_fixture import commit_file, init_repo, rewrite_line


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ===========================================================================
# AC-008-3 [Edge] Zero commits in the window → all-zero metrics, no error.
# ===========================================================================
def test_ac_008_3_alg_a_empty_window(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # All commits pre-window.
    sha_pre = commit_file(
        repo, "src/a.py", "a\nb\n",
        message="pre-window seed", date="2025-12-01T10:00:00Z",
    )
    records = [{
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "src/a.py", "codeLines": [
            {"lineRange": {"from": 1, "to": 2}, "genRatio": 100, "genMethod": "vibeCoding"},
        ]}],
        "REPOSITORY": {
            "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
            "revisionId": sha_pre,
        },
    }]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-06-30T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 0
    assert result.metrics.weighted_value == 0.0
    assert result.metrics.fully_ai_value == 0.0
    assert result.metrics.mostly_ai_value == 0.0
    assert result.in_window_adds == ()


def test_ac_008_3_alg_b_empty_window() -> None:
    rec = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "src/a.py", "codeLines": [
            {"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"},
        ]}],
        "REPOSITORY": {
            "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
            "revisionId": "c_pre", "revisionTimestamp": "2025-12-01T10:00:00Z",
        },
    }
    patch = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+a\n+b\n+c\n"
    )
    commit = build_commit(rec, patch)
    result = run_algorithm_b(
        [commit],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-06-30T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 0
    assert result.metrics.weighted_value == 0.0
    assert result.metrics.fully_ai_value == 0.0


def test_ac_008_3_alg_c_empty_window() -> None:
    rec = load_v2604_record({
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "src/a.py", "codeLines": [
            {
                "changeType": "add", "lineLocation": 1, "genRatio": 100,
                "genMethod": "vibeCoding",
                "blame": {
                    "revisionId": "c_pre",
                    "originalFilePath": "src/a.py",
                    "originalLine": 1,
                    "timestamp": "2025-12-01T10:00:00Z",
                },
            },
        ]}],
        "REPOSITORY": {
            "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
            "revisionId": "c_pre", "revisionTimestamp": "2025-12-01T10:00:00Z",
        },
    })
    result = run_algorithm_c_full(
        [rec],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-06-30T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 0
    assert result.metrics.weighted_value == 0.0
    assert result.metrics.fully_ai_value == 0.0


def test_ac_008_3_alg_c_no_records_at_all() -> None:
    """Extreme: zero records passed in at all."""
    result = run_algorithm_c_full(
        [],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-06-30T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 0
    assert result.metrics.weighted_value == 0.0


# ===========================================================================
# AC-008-4 [Robust] I/O failure reports path + revisionId; no partial output.
# ===========================================================================
def _cli_args(gcd: Path, out: Path, *, extra: list[str] | None = None) -> list[str]:
    return [
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out),
        *(extra or []),
    ]


def test_ac_008_4_malformed_json_reports_file_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    bad = gcd / "broken.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    out = tmp_path / "out"

    with caplog.at_level("ERROR", logger="aggregateGenCodeDesc"):
        rc = cli_main(_cli_args(gcd, out))
    assert rc == 2
    # Error message must identify the offending file.
    combined = " ".join(r.message for r in caplog.records)
    assert "broken.json" in combined
    # No partial output should be written.
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.skipif(sys.platform == "win32",
                    reason="chmod-based unreadable file simulation is POSIX-only")
def test_ac_008_4_unreadable_file_reports_file_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    unreadable = gcd / "locked.json"
    unreadable.write_text(json.dumps({
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [],
        "REPOSITORY": {
            "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
            "revisionId": "c1", "revisionTimestamp": "2026-02-01T10:00:00Z",
        },
    }), encoding="utf-8")
    # Skip if running as root (chmod 0 won't prevent reads).
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not restrict reads")
    unreadable.chmod(0)
    out = tmp_path / "out"
    try:
        with caplog.at_level("ERROR", logger="aggregateGenCodeDesc"):
            rc = cli_main(_cli_args(gcd, out))
    finally:
        # Restore permissions so pytest can clean up tmp_path.
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert rc == 2
    combined = " ".join(r.message for r in caplog.records)
    assert "locked.json" in combined
    assert "cannot read file" in combined
    # No partial output.
    assert not out.exists() or not any(out.iterdir())


# ===========================================================================
# AC-008-1 [Performance] AlgA small-scale smoke (regression guard).
#
# The acceptance criterion's real target is 1K commits × 100 files × 10K
# lines and is documented as correctness-over-speed. This test guards
# against gross regressions at a shape that runs in seconds on CI.
# ===========================================================================
def test_ac_008_1_alg_a_small_scale_smoke(tmp_path: Path) -> None:
    NUM_COMMITS = 20
    LINES_PER_COMMIT = 10
    TIME_BUDGET_SEC = 15.0  # generous for slow CI; real cost is a few seconds.

    repo = tmp_path / "repo"
    init_repo(repo)

    records: list[dict] = []
    content = ""
    for i in range(NUM_COMMITS):
        # Append LINES_PER_COMMIT lines per commit.
        new_block = "".join(f"line_{i}_{j}\n" for j in range(LINES_PER_COMMIT))
        content += new_block
        date = f"2026-02-{(i % 27) + 1:02d}T10:00:00Z"
        sha = rewrite_line(
            repo, "src/big.py", content,
            message=f"c{i}", date=date,
        ) if i > 0 else commit_file(
            repo, "src/big.py", content,
            message=f"c{i}", date=date,
        )
        # Each commit claims its new lines at genRatio 100.
        from_line = i * LINES_PER_COMMIT + 1
        to_line = (i + 1) * LINES_PER_COMMIT
        records.append({
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": "src/big.py", "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
                "revisionId": sha,
            },
        })

    t0 = time.monotonic()
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    elapsed = time.monotonic() - t0

    # Correctness.
    expected_lines = NUM_COMMITS * LINES_PER_COMMIT
    assert result.metrics.total_lines == expected_lines
    # All lines claimed at genRatio 100 → fullyAI == 1.0.
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    # Regression guard.
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgA small-scale smoke took {elapsed:.2f}s "
        f"(budget {TIME_BUDGET_SEC}s; {NUM_COMMITS} commits, {expected_lines} lines)"
    )
