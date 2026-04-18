"""US-005 — branch and history conditions.

Covers:
  AC-005-1  [Typical] Lines committed before startTime are excluded.
  AC-005-2  [Typical] Multiple merges: each line attributes to one origin only.
  AC-005-3  [Edge]    Long-lived divergent branch: lines trace to their
                      actual origin commit on whichever branch.

AC-005-4 (shallow clone) and AC-005-5 (submodule) are policy-documented
edge cases not code-enforced.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import (
    checkout,
    checkout_new_branch,
    commit_file,
    init_repo,
    merge_no_ff,
)


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _rec(rev: str, file_name: str, lines: list[dict]) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": file_name, "codeLines": lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
        },
    }


# ---------------------------------------------------------------------------
# AC-005-1 [Typical] Pre-window lines excluded from metric.
# ---------------------------------------------------------------------------
def test_ac_005_1_pre_window_line_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # Pre-window commit (2025).
    sha_pre = commit_file(
        repo, "main.py", "old_line\n",
        message="c0: pre-window", date="2025-12-01T10:00:00Z",
    )
    # In-window commit adds a second line.
    sha_in = commit_file(
        repo, "main.py", "old_line\nnew_line\n",
        message="c1: in-window", date="2026-02-05T10:00:00Z",
    )
    records = [
        _rec(sha_pre, "main.py",
             [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_in, "main.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # Only the in-window line counts; old_line is excluded even though alive.
    assert result.metrics.total_lines == 1
    assert result.in_window_adds[0].origin_revision == sha_in
    assert result.in_window_adds[0].current_line == 2


# ---------------------------------------------------------------------------
# AC-005-2 [Typical] Multiple merges: each line has exactly one origin.
# ---------------------------------------------------------------------------
def test_ac_005_2_multiple_merges_single_origin_each(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_base = commit_file(
        repo, "app.py", "base\n",
        message="c0: base", date="2026-02-01T10:00:00Z",
    )
    # Branch A adds line_a.
    checkout_new_branch(repo, "feat-a", from_rev=sha_base)
    sha_a = commit_file(
        repo, "app.py", "base\nline_a\n",
        message="feat-a", date="2026-02-05T10:00:00Z",
    )
    checkout(repo, "main")
    merge_no_ff(repo, "feat-a", message="merge feat-a", date="2026-02-06T10:00:00Z")
    # Branch B adds line_b.
    checkout_new_branch(repo, "feat-b", from_rev="main")
    sha_b = commit_file(
        repo, "app.py", "base\nline_a\nline_b\n",
        message="feat-b", date="2026-02-10T10:00:00Z",
    )
    checkout(repo, "main")
    merge_no_ff(repo, "feat-b", message="merge feat-b", date="2026-02-11T10:00:00Z")
    # Branch C adds line_c.
    checkout_new_branch(repo, "feat-c", from_rev="main")
    sha_c = commit_file(
        repo, "app.py", "base\nline_a\nline_b\nline_c\n",
        message="feat-c", date="2026-02-15T10:00:00Z",
    )
    checkout(repo, "main")
    merge_no_ff(repo, "feat-c", message="merge feat-c", date="2026-02-16T10:00:00Z")

    records = [
        _rec(sha_a, "app.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_b, "app.py",
             [{"lineLocation": 3, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_c, "app.py",
             [{"lineLocation": 4, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 4
    origin_by_line = {s.current_line: s.origin_revision for s in result.in_window_adds}
    # Each line attributes to exactly one origin — the branch tip that introduced it.
    assert origin_by_line[2] == sha_a
    assert origin_by_line[3] == sha_b
    assert origin_by_line[4] == sha_c
    # base is sha_base (pre-window if outside window; here it's in-window).
    assert origin_by_line[1] == sha_base
    # No duplicate blame: every line appears once.
    assert len(result.in_window_adds) == 4


# ---------------------------------------------------------------------------
# AC-005-3 [Edge] Long-lived divergent branch: each line traces to its
#                 actual origin commit regardless of which branch it lived on.
# ---------------------------------------------------------------------------
def test_ac_005_3_long_lived_branch_divergence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_file(
        repo, "README.md", "anchor\n",
        message="c0: base", date="2026-02-01T10:00:00Z",
    )
    # `main` evolves its own file.
    sha_main = commit_file(
        repo, "main_side.py", "main_line\n",
        message="main evolve", date="2026-02-05T10:00:00Z",
    )
    # Long-lived `feature` diverged from base, touches a different file.
    checkout_new_branch(repo, "feature", from_rev="HEAD~1")
    sha_feat1 = commit_file(
        repo, "feat_side.py", "feat_line_1\n",
        message="feat c1", date="2026-03-01T10:00:00Z",
    )
    sha_feat2 = commit_file(
        repo, "feat_side.py", "feat_line_1\nfeat_line_2\n",
        message="feat c2", date="2026-06-01T10:00:00Z",
    )
    # Merge feature into main (6 months later) — no conflict, disjoint files.
    checkout(repo, "main")
    merge_no_ff(
        repo, "feature",
        message="merge feature", date="2026-08-01T10:00:00Z",
    )
    records = [
        _rec(sha_main, "main_side.py",
             [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_feat1, "feat_side.py",
             [{"lineLocation": 1, "genRatio": 50, "genMethod": "Hybrid"}]),
        _rec(sha_feat2, "feat_side.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    origins = {s.origin_revision for s in result.in_window_adds}
    # Every line traces back to its actual origin commit across both branches.
    assert sha_main in origins
    assert sha_feat1 in origins
    assert sha_feat2 in origins
