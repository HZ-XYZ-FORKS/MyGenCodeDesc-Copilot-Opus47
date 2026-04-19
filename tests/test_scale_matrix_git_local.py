"""Scale matrix — AlgA/B/C × git-local.

Fills the 3 git-local cells of the "git/svn × local/remote × AlgA/B/C"
matrix with a real (not toy) workload: N_COMMITS commits, each touching
one of N_FILES files by appending LINES_PER_COMMIT lines.

Intent:
  - Catch gross performance regressions (time budget).
  - Catch correctness regressions (total_lines must be exact).
  - Exercise AlgA (live blame), AlgB (patch replay), AlgC (embedded blame)
    at a shape that is closer to production than the 20-commit smoke.

Remote and SVN cells are tracked as separate follow-ups; see
`scripts/run_local_production_check.sh`.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c_full,
)

from tests._git_fixture import commit_file, init_repo, rewrite_line


# Dimensions. Kept moderate so the full matrix runs in seconds locally.
N_COMMITS = 100
N_FILES = 10
LINES_PER_COMMIT = 5
TIME_BUDGET_SEC = 60.0  # generous; laptops usually finish each in a few seconds.
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _build_git_and_records(repo: Path) -> tuple[list[dict], list[str], dict[str, list[str]]]:
    """Build a real git repo with N_COMMITS commits, round-robin across N_FILES.

    Returns:
      records_v2603: list of protocol 26.03 records (for AlgA/AlgB).
      shas:          ordered commit SHAs.
      patches:       SHA -> unified diff text (for AlgB).
    """
    init_repo(repo)
    records: list[dict] = []
    shas: list[str] = []
    patches: dict[str, list[str]] = {}
    # Per-file current content (list of lines without trailing \n).
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

        # Claim the new lines at genRatio 100.
        from_line = len(existing) + 1
        to_line = len(existing) + LINES_PER_COMMIT
        rec = {
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": rel, "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
                "revisionId": sha, "revisionTimestamp": date,
            },
        }
        records.append(rec)
        shas.append(sha)

        # Build a minimal unified diff patch for AlgB replay.
        old_len = len(existing)
        new_len = len(updated)
        if old_len == 0:
            header = (
                f"diff --git a/{rel} b/{rel}\n"
                "--- /dev/null\n"
                f"+++ b/{rel}\n"
                f"@@ -0,0 +1,{new_len} @@\n"
            )
            body = "".join("+" + line + "\n" for line in updated)
        else:
            header = (
                f"diff --git a/{rel} b/{rel}\n"
                f"--- a/{rel}\n"
                f"+++ b/{rel}\n"
                f"@@ -1,{old_len} +1,{new_len} @@\n"
            )
            # Context = all existing lines, then additions.
            body = "".join(" " + line + "\n" for line in existing) + \
                   "".join("+" + line + "\n" for line in new_lines)
        patches[sha] = header + body
        file_state[rel] = updated

    return records, shas, patches


def _expected_total_lines() -> int:
    return N_COMMITS * LINES_PER_COMMIT


# ---------------------------------------------------------------------------
# AlgA × git-local
# ---------------------------------------------------------------------------
def test_scale_alga_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, _, _ = _build_git_and_records(repo)

    t0 = time.monotonic()
    result = run_algorithm_a(
        repo, records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgA scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s; "
        f"{N_COMMITS} commits, {N_FILES} files)"
    )


# ---------------------------------------------------------------------------
# AlgB × git-local (patch replay — no repo access needed)
# ---------------------------------------------------------------------------
def test_scale_algb_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, shas, patches = _build_git_and_records(repo)

    commits = [build_commit(rec, patches[sha]) for rec, sha in zip(records, shas)]

    t0 = time.monotonic()
    result = run_algorithm_b(
        commits, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgB scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s)"
    )


# ---------------------------------------------------------------------------
# AlgC × git-local (embedded blame → self-attributed)
# ---------------------------------------------------------------------------
def test_scale_algc_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, shas, _ = _build_git_and_records(repo)

    # Convert 26.03 line-range records to 26.04 per-line add records with
    # self-blame (blame points to the commit introducing the line).
    v2604_records = []
    for rec, sha in zip(records, shas):
        detail_in = rec["DETAIL"][0]
        fn = detail_in["fileName"]
        ts = rec["REPOSITORY"]["revisionTimestamp"]
        lr = detail_in["codeLines"][0]["lineRange"]
        code_lines = []
        for lineno in range(lr["from"], lr["to"] + 1):
            code_lines.append({
                "changeType": "add",
                "lineLocation": lineno,
                "genRatio": 100,
                "genMethod": "vibeCoding",
                "blame": {
                    "revisionId": sha,
                    "originalFilePath": fn,
                    "originalLine": lineno,
                    "timestamp": ts,
                },
            })
        v2604_records.append(load_v2604_record({
            "protocolVersion": "26.04",
            "SUMMARY": {},
            "DETAIL": [{"fileName": fn, "codeLines": code_lines}],
            "REPOSITORY": {
                **rec["REPOSITORY"],
                "revisionId": sha,
            },
        }))

    t0 = time.monotonic()
    result = run_algorithm_c_full(
        v2604_records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgC scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s)"
    )
