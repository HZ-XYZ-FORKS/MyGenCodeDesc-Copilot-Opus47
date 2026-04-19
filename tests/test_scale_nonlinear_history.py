"""Scale tests with non-linear git history.

Shape built per test:

    main:    A1 - A2 - ... - A10 -------------- M ----- CP - RV
                                 \\          /
    feature:                      F1 - F2 - F3

Where:
  - A1..A10 add one line per commit to ``base.py``.
  - F1..F3 add one line per commit to ``feat.py`` on branch ``feature``.
  - M is a --no-ff merge of ``feature`` into ``main``.
  - CP is a cherry-pick of a commit from a short-lived sibling branch
    ``hotfix`` that touches ``hot.py``.
  - RV is a revert of ``CP`` itself (cleanly removes ``hot.py``), which
    avoids the conflicts that reverting an older base commit would cause
    after many subsequent rewrites to the same file.

Assertions (for AlgA, AlgB):
  - Final surviving line count matches the effective tree:
      base.py: 10 lines (all A1..A10).
      feat.py: 3 lines (F1..F3).
      hot.py:  0 lines (added by CP, removed by RV).
      Total:  13 lines.
  - fully_ai_value == 1.0 (all added lines claimed at genRatio 100).

Patches for AlgB are produced with ``git diff <parent> <sha>``, which
gives each commit a well-defined first-parent diff (including the merge
commit, where it reduces to the feature branch's net delta against main).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b

from tests._git_fixture import (
    cherry_pick,
    checkout,
    checkout_new_branch,
    commit_file,
    git,
    init_repo,
    merge_no_ff,
    revert,
    rewrite_line,
)


START = datetime.fromisoformat("2026-03-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(i: int) -> str:
    return _iso(START + timedelta(minutes=i))


def _append_record(
    records: list[dict],
    *,
    sha: str,
    ts: str,
    rel: str,
    from_line: int,
    to_line: int,
) -> None:
    records.append({
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": rel, "codeLines": [
            {"lineRange": {"from": from_line, "to": to_line},
             "genRatio": 100, "genMethod": "vibeCoding"},
        ]}],
        "REPOSITORY": {
            "vcsType": "git", "repoURL": "https://x/r", "repoBranch": "main",
            "revisionId": sha, "revisionTimestamp": ts,
        },
    })


def _build_nonlinear_repo(
    repo: Path,
) -> tuple[list[dict], list[str], dict[str, str], list[str]]:
    """Return ``(records, shas_topological, patches_by_sha, mainline_shas)``.

    ``mainline_shas`` is the linear sequence from main's perspective
    (A1..A10, M, CP, RV) — used by AlgB which only understands linear
    patch replay. Feature-branch commits exist in the graph but AlgB
    learns about their content only through the merge commit's
    first-parent diff.
    """
    init_repo(repo)
    records: list[dict] = []
    shas: list[str] = []
    patches: dict[str, str] = {}
    mainline_shas: list[str] = []
    # AlgB-specific records: claim feat.py lines at the merge commit
    # (since AlgB learns about feat.py only through main's first-parent diff).
    mainline_records: list[dict] = []

    # --- 10 base commits on main ---
    base_lines: list[str] = []
    for i in range(1, 11):
        base_lines = base_lines + [f"base_{i}"]
        content = "".join(x + "\n" for x in base_lines)
        ts = _ts(i)
        if i == 1:
            sha = commit_file(repo, "base.py", content, message=f"A{i}", date=ts)
        else:
            sha = rewrite_line(repo, "base.py", content, message=f"A{i}", date=ts)
        _append_record(records, sha=sha, ts=ts, rel="base.py",
                       from_line=i, to_line=i)
        _append_record(mainline_records, sha=sha, ts=ts, rel="base.py",
                       from_line=i, to_line=i)
        shas.append(sha)
        mainline_shas.append(sha)

    sha_A10 = shas[-1]

    # --- feature branch from A10 with 3 commits touching feat.py ---
    checkout_new_branch(repo, "feature", from_rev=sha_A10)
    feat_lines: list[str] = []
    for j in range(1, 4):
        feat_lines = feat_lines + [f"feat_{j}"]
        content = "".join(x + "\n" for x in feat_lines)
        ts = _ts(20 + j)
        if j == 1:
            sha = commit_file(repo, "feat.py", content, message=f"F{j}", date=ts)
        else:
            sha = rewrite_line(repo, "feat.py", content, message=f"F{j}", date=ts)
        _append_record(records, sha=sha, ts=ts, rel="feat.py",
                       from_line=j, to_line=j)
        shas.append(sha)

    # --- back to main, merge feature with --no-ff ---
    checkout(repo, "main")
    merge_ts = _ts(30)
    sha_M = merge_no_ff(repo, "feature", message="merge feature", date=merge_ts)
    shas.append(sha_M)
    mainline_shas.append(sha_M)
    # AlgB view: the merge first-parent diff introduces 3 feat.py lines;
    # claim them against the merge commit so AlgB can match.
    _append_record(mainline_records, sha=sha_M, ts=merge_ts, rel="feat.py",
                   from_line=1, to_line=3)

    # --- hotfix branch from A10 with one commit touching hot.py ---
    checkout_new_branch(repo, "hotfix", from_rev=sha_A10)
    hot_ts = _ts(35)
    sha_H = commit_file(repo, "hot.py", "hot_1\n", message="H1", date=hot_ts)

    # --- back to main, cherry-pick the hotfix commit ---
    checkout(repo, "main")
    cp_ts = _ts(40)
    sha_CP = cherry_pick(repo, sha_H, date=cp_ts)
    _append_record(records, sha=sha_CP, ts=cp_ts, rel="hot.py",
                   from_line=1, to_line=1)
    _append_record(mainline_records, sha=sha_CP, ts=cp_ts, rel="hot.py",
                   from_line=1, to_line=1)
    shas.append(sha_CP)
    mainline_shas.append(sha_CP)

    # --- revert the cherry-pick (cleanly removes hot.py) ---
    rv_ts = _ts(50)
    sha_RV = revert(repo, sha_CP, date=rv_ts)
    shas.append(sha_RV)
    mainline_shas.append(sha_RV)
    # Revert removes a line; no AI-claim added.

    # --- build per-commit first-parent patches for AlgB ---
    for sha in shas:
        parents = git(repo, "rev-list", "--parents", "-n", "1", sha).strip().split()
        if len(parents) == 1:
            patch = git(repo, "show", "--format=", "--patch", sha)
        else:
            p1 = parents[1]
            patch = git(repo, "diff", p1, sha)
        patches[sha] = patch

    return records, shas, patches, mainline_shas, mainline_records


def _expected_total_lines() -> int:
    # 10 base + 3 feat + 0 hot (reverted) = 13
    return 13


# ---------------------------------------------------------------------------
# AlgA: shape-agnostic, blames final HEAD.
# ---------------------------------------------------------------------------
def test_nonlinear_alga_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    records, _, _, _, _ = _build_nonlinear_repo(repo)

    result = run_algorithm_a(
        repo, records, start_time=START, end_time=END, threshold=60,
    )
    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)

    # Per-file sanity.
    by_file: dict[str, int] = {}
    for s in result.surviving:
        by_file[s.current_file] = by_file.get(s.current_file, 0) + 1
    assert by_file == {"base.py": 10, "feat.py": 3}


# ---------------------------------------------------------------------------
# AlgB: patch replay across merge + cherry-pick + revert.
# ---------------------------------------------------------------------------
def test_nonlinear_algb_git_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _, _, patches, mainline_shas, mainline_records = _build_nonlinear_repo(repo)

    # AlgB replays the mainline sequence only. For mainline commits without
    # AI claims (the revert), synthesize an empty-DETAIL record so the
    # patch still replays and keeps line numbers consistent.
    records_by_sha = {r["REPOSITORY"]["revisionId"]: r for r in mainline_records}

    commits = []
    for sha in mainline_shas:
        if sha in records_by_sha:
            rec = records_by_sha[sha]
        else:
            ts = git(repo, "show", "-s", "--format=%aI", sha).strip()
            rec = {
                "protocolName": "generatedTextDesc",
                "protocolVersion": "26.03",
                "SUMMARY": {},
                "DETAIL": [],
                "REPOSITORY": {
                    "vcsType": "git", "repoURL": "https://x/r",
                    "repoBranch": "main",
                    "revisionId": sha, "revisionTimestamp": ts,
                },
            }
        commits.append(build_commit(rec, patches[sha]))

    result = run_algorithm_b(
        commits, start_time=START, end_time=END, threshold=60,
    )
    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
