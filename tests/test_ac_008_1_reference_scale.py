"""AC-008-1 reference-scale test — opt-in via ``RUN_AC_008_1=1``.

US-008 AC-008-1 target: **1,000 commits × 100 files × 10,000 lines/file**
with ~10,000 distinct files at endTime. AlgA runs live ``git blame`` and
the acceptance criterion is *correctness over speed* with **peak memory
bounded below 1 GiB**.

Running the full 10^8-lines shape is infeasible on CI, so this test:

  * **Preserves the 1K-commits × 100-files dimensions** (the AlgA cost
    drivers — one blame call per file at HEAD).
  * Scales the per-commit line count down (default 10 lines/commit) so
    total surviving lines = 10,000 — still non-trivial.
  * Allows env overrides so a fork author can run the full reference
    magnitude (the AC explicitly defers actual timing to the fork).

Assertions
----------
  * total_lines is exact
  * fully_ai_value == 1.0
  * peak RSS < AC008_RSS_BUDGET_MB (default 1024 MiB, per AC)
  * runtime is recorded but only gated by AC008_TIME_BUDGET_SEC
    (generous default — AC says correctness over speed)

Env overrides
-------------
  RUN_AC_008_1=1              (required to enable)
  AC008_N_COMMITS=1000
  AC008_N_FILES=100
  AC008_LINES_PER_COMMIT=10
  AC008_TIME_BUDGET_SEC=900
  AC008_RSS_BUDGET_MB=1024
"""

from __future__ import annotations

import os
import platform
import resource
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import commit_file, init_repo, rewrite_line


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AC_008_1") != "1",
    reason="opt-in AC-008-1 reference scale; set RUN_AC_008_1=1 to run",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


N_COMMITS = _env_int("AC008_N_COMMITS", 1000)
N_FILES = _env_int("AC008_N_FILES", 100)
LINES_PER_COMMIT = _env_int("AC008_LINES_PER_COMMIT", 10)
TIME_BUDGET_SEC = _env_float("AC008_TIME_BUDGET_SEC", 900.0)
RSS_BUDGET_MB = _env_float("AC008_RSS_BUDGET_MB", 1024.0)  # AC: <1 GiB

START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
# Span wide enough for 1000 commits spaced 1 minute apart (~17 hours) plus
# slack if the fork cranks N_COMMITS up.
END = datetime.fromisoformat("2027-12-31T00:00:00+00:00")


def _peak_rss_mb() -> float:
    """Best-effort peak RSS in MiB. macOS: bytes; Linux: KiB."""
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024.0 * 1024.0)
    return maxrss / 1024.0


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    # Round-robin commits across N_FILES distinct files so the endTime
    # tree holds exactly N_FILES files — the AlgA blame fan-out driver.
    return f"src/f{i % N_FILES}.py"


def _build_reference_scale(repo: Path) -> list[dict]:
    """Build a git repo with N_COMMITS commits touching N_FILES files.

    Returns the list of v26.03 records claiming every new line at
    genRatio=100 so that total_lines and fully_ai are deterministic.
    """
    init_repo(repo)
    records: list[dict] = []
    file_state: dict[str, list[str]] = {}

    for i in range(N_COMMITS):
        rel = _file_name(i)
        new_lines = [f"line_{i}_{j}" for j in range(LINES_PER_COMMIT)]
        existing = file_state.get(rel, [])
        updated = existing + new_lines
        new_content = "".join(x + "\n" for x in updated)

        date = _iso(START + timedelta(minutes=i))
        if rel not in file_state:
            sha = commit_file(repo, rel, new_content, message=f"c{i}", date=date)
        else:
            sha = rewrite_line(repo, rel, new_content, message=f"c{i}", date=date)

        from_line = len(existing) + 1
        to_line = len(existing) + LINES_PER_COMMIT
        records.append({
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{
                "fileName": rel,
                "codeLines": [{
                    "lineRange": {"from": from_line, "to": to_line},
                    "genRatio": 100,
                    "genMethod": "vibeCoding",
                }],
            }],
            "REPOSITORY": {
                "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
                "revisionId": sha, "revisionTimestamp": date,
            },
        })
        file_state[rel] = updated

    return records


# ---------------------------------------------------------------------------
# AC-008-1: AlgA at reference scale.
#
# Dimension check: the built tree has exactly N_FILES files (each touched
# N_COMMITS/N_FILES times on average). AlgA therefore issues ~N_FILES
# blame calls at HEAD — that's the cost driver the AC targets.
# ---------------------------------------------------------------------------
def test_ac_008_1_alga_reference_scale(tmp_path: Path) -> None:
    if pytest.importorskip is None:  # pragma: no cover — defensive no-op
        pass
    repo = tmp_path / "repo"

    t_build_start = time.monotonic()
    records = _build_reference_scale(repo)
    build_elapsed = time.monotonic() - t_build_start

    t_run_start = time.monotonic()
    result = run_algorithm_a(
        repo, records, start_time=START, end_time=END, threshold=60,
    )
    run_elapsed = time.monotonic() - t_run_start
    rss_after = _peak_rss_mb()

    expected_total = N_COMMITS * LINES_PER_COMMIT

    # Observability for the fork author (AC: "fork documents actual time").
    print(
        f"\n[AC-008-1] N_COMMITS={N_COMMITS} N_FILES={N_FILES} "
        f"LINES_PER_COMMIT={LINES_PER_COMMIT} "
        f"expected_total_lines={expected_total}"
    )
    print(
        f"[AC-008-1] build_repo={build_elapsed:.1f}s "
        f"run_alga={run_elapsed:.1f}s peak_rss={rss_after:.1f}MiB "
        f"platform={platform.system()}"
    )

    # Correctness (AC's primary criterion).
    assert result.metrics.total_lines == expected_total
    assert result.metrics.fully_ai_value == pytest.approx(1.0)

    # Memory bound (AC: <1 GiB).
    assert rss_after < RSS_BUDGET_MB, (
        f"AC-008-1 peak RSS {rss_after:.1f} MiB exceeds budget "
        f"{RSS_BUDGET_MB} MiB (platform={platform.system()})"
    )

    # Runtime is only a soft upper bound — AC defers to fork timing.
    assert run_elapsed < TIME_BUDGET_SEC, (
        f"AC-008-1 AlgA took {run_elapsed:.1f}s (budget {TIME_BUDGET_SEC}s; "
        f"{N_COMMITS} commits × {N_FILES} files × {LINES_PER_COMMIT} lines)"
    )
