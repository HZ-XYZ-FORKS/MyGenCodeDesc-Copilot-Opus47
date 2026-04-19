"""High-magnitude scale tests — opt-in via ``RUN_SCALE_MAGNITUDE=1``.

Goal: push one representative cell of the matrix (git-local) to a size
closer to real production workloads, and assert:

  - Correctness: total_lines is exact, fully_ai_value==1.0.
  - Performance: runtime under a generous budget.
  - Memory: peak RSS under a budget (best-effort via resource.getrusage).
  - Determinism: two consecutive runs produce identical metrics and the
    same sorted set of surviving (file, line, revisionId) tuples.

Defaults (overridable via env):
    SCALE_N_COMMITS         500
    SCALE_N_FILES           50
    SCALE_LINES_PER_COMMIT  5
    SCALE_TIME_BUDGET_SEC   300
    SCALE_RSS_BUDGET_MB     1024

Skipped by default so CI doesn't pay the cost. Wire into production-check
script by exporting ``RUN_SCALE_MAGNITUDE=1``.
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
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c_full,
)

from tests._git_fixture import commit_file, init_repo, rewrite_line


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SCALE_MAGNITUDE") != "1",
    reason="opt-in; set RUN_SCALE_MAGNITUDE=1 to run",
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


N_COMMITS = _env_int("SCALE_N_COMMITS", 500)
N_FILES = _env_int("SCALE_N_FILES", 50)
LINES_PER_COMMIT = _env_int("SCALE_LINES_PER_COMMIT", 5)
TIME_BUDGET_SEC = _env_float("SCALE_TIME_BUDGET_SEC", 300.0)
RSS_BUDGET_MB = _env_float("SCALE_RSS_BUDGET_MB", 1024.0)

START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _peak_rss_mb() -> float:
    """Best-effort peak RSS of this process, in MiB.

    macOS ru_maxrss is in bytes; Linux is in KiB.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    maxrss = usage.ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024.0 * 1024.0)
    return maxrss / 1024.0


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _build_git_and_records(
    repo: Path,
) -> tuple[list[dict], list[str], dict[str, str]]:
    init_repo(repo)
    records: list[dict] = []
    shas: list[str] = []
    patches: dict[str, str] = {}
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
            body = "".join(" " + line + "\n" for line in existing) + \
                   "".join("+" + line + "\n" for line in new_lines)
        patches[sha] = header + body
        file_state[rel] = updated

    return records, shas, patches


def _expected_total_lines() -> int:
    return N_COMMITS * LINES_PER_COMMIT


def _surviving_fingerprint(result) -> tuple:
    """Order-independent fingerprint of surviving lines.

    AlgA's _SurvivingLine uses ``origin_revision`` / ``current_file`` /
    ``current_line``; AlgB and AlgC use ``revision_id`` / ``file_name`` /
    ``line_location``. Normalise both shapes into a common tuple.
    """
    fp = []
    for s in result.surviving:
        rev = getattr(s, "revision_id", None) or getattr(s, "origin_revision")
        fname = getattr(s, "file_name", None) or getattr(s, "current_file")
        lineno = getattr(s, "line_location", None)
        if lineno is None:
            lineno = getattr(s, "current_line")
        fp.append((fname, lineno, rev, s.gen_ratio))
    return tuple(sorted(fp))


# ---------------------------------------------------------------------------
# AlgA (heaviest — live blame)
# ---------------------------------------------------------------------------
def test_magnitude_alga_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, _, _ = _build_git_and_records(repo)

    t0 = time.monotonic()
    r1 = run_algorithm_a(repo, records, start_time=START, end_time=END, threshold=60)
    elapsed1 = time.monotonic() - t0
    rss_after = _peak_rss_mb()

    assert r1.metrics.total_lines == _expected_total_lines()
    assert r1.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed1 < TIME_BUDGET_SEC, (
        f"AlgA magnitude took {elapsed1:.1f}s (budget {TIME_BUDGET_SEC}s; "
        f"{N_COMMITS} commits × {N_FILES} files × {LINES_PER_COMMIT} lines)"
    )
    assert rss_after < RSS_BUDGET_MB, (
        f"AlgA peak RSS {rss_after:.1f} MiB exceeds budget {RSS_BUDGET_MB} MiB "
        f"(platform={platform.system()})"
    )

    # Determinism: second run produces the same answer.
    r2 = run_algorithm_a(repo, records, start_time=START, end_time=END, threshold=60)
    assert r2.metrics.total_lines == r1.metrics.total_lines
    assert r2.metrics.fully_ai_value == r1.metrics.fully_ai_value
    assert _surviving_fingerprint(r2) == _surviving_fingerprint(r1)


# ---------------------------------------------------------------------------
# AlgB (patch replay)
# ---------------------------------------------------------------------------
def test_magnitude_algb_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, shas, patches = _build_git_and_records(repo)
    commits = [build_commit(rec, patches[sha]) for rec, sha in zip(records, shas)]

    t0 = time.monotonic()
    r1 = run_algorithm_b(commits, start_time=START, end_time=END, threshold=60)
    elapsed1 = time.monotonic() - t0
    rss_after = _peak_rss_mb()

    assert r1.metrics.total_lines == _expected_total_lines()
    assert r1.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed1 < TIME_BUDGET_SEC, (
        f"AlgB magnitude took {elapsed1:.1f}s (budget {TIME_BUDGET_SEC}s)"
    )
    assert rss_after < RSS_BUDGET_MB, (
        f"AlgB peak RSS {rss_after:.1f} MiB exceeds budget {RSS_BUDGET_MB} MiB"
    )

    r2 = run_algorithm_b(commits, start_time=START, end_time=END, threshold=60)
    assert _surviving_fingerprint(r2) == _surviving_fingerprint(r1)


# ---------------------------------------------------------------------------
# AlgC (embedded blame timeline)
# ---------------------------------------------------------------------------
def test_magnitude_algc_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, shas, _ = _build_git_and_records(repo)

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
            "REPOSITORY": {**rec["REPOSITORY"], "revisionId": sha},
        }))

    t0 = time.monotonic()
    r1 = run_algorithm_c_full(v2604_records, start_time=START, end_time=END, threshold=60)
    elapsed1 = time.monotonic() - t0
    rss_after = _peak_rss_mb()

    assert r1.metrics.total_lines == _expected_total_lines()
    assert r1.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed1 < TIME_BUDGET_SEC, (
        f"AlgC magnitude took {elapsed1:.1f}s (budget {TIME_BUDGET_SEC}s)"
    )
    assert rss_after < RSS_BUDGET_MB, (
        f"AlgC peak RSS {rss_after:.1f} MiB exceeds budget {RSS_BUDGET_MB} MiB"
    )

    r2 = run_algorithm_c_full(v2604_records, start_time=START, end_time=END, threshold=60)
    assert _surviving_fingerprint(r2) == _surviving_fingerprint(r1)
