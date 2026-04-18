"""US-003 — commit-level conditions verified against Algorithm A.

Scenarios:
  AC-003-1  [Typical] Merge commit preserves original line origins (no-ff merge)
  AC-003-2  [Typical] Squash merge collapses attribution to the squash commit
  AC-003-3  [Typical] Cherry-pick creates independent attribution on the target branch
  AC-003-4  [Typical] Revert commit removes AI attribution from the live set
  AC-003-5  [Edge]    Amend/force-push orphans old genCodeDesc
  AC-003-6  [Edge]    Rebase replays commits with new revisionIds
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import (
    cherry_pick,
    checkout,
    checkout_new_branch,
    commit_file,
    init_repo,
    merge_no_ff,
    merge_squash,
    revert,
    rewrite_line,
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


_WINDOW = {
    "start_time": _utc("2026-01-01T00:00:00Z"),
    "end_time":   _utc("2026-12-31T00:00:00Z"),
    "threshold":  60,
}


# ---------------------------------------------------------------------------
# AC-003-1 [Typical] Merge commit preserves original line origins.
# ---------------------------------------------------------------------------
def test_ac_003_1_merge_preserves_origin(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # main: seed file.
    sha_main = commit_file(
        repo, "src/a.py", "main1\n",
        message="c0: main seed", date="2026-02-01T10:00:00Z",
    )
    # feature branch: adds AI lines.
    checkout_new_branch(repo, "feature")
    sha_feat = rewrite_line(
        repo, "src/a.py", "main1\nfeat1\nfeat2\n",
        message="f1: AI work", date="2026-02-05T10:00:00Z",
    )
    # Merge with --no-ff into main.
    checkout(repo, "main")
    merge_no_ff(
        repo, "feature", message="merge feature",
        date="2026-02-10T10:00:00Z",
    )
    # Only c0 and f1 have genCodeDesc; merge commit itself has none.
    records = [
        _rec(sha_main, "src/a.py",
             [{"lineLocation": 1, "genRatio": 0, "genMethod": "Manual"}]),
        _rec(sha_feat, "src/a.py",
             [{"lineRange": {"from": 2, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    # Blame attributes feat lines to f1 (not to the merge commit).
    for s in result.in_window_adds:
        if s.origin_file == "src/a.py" and s.origin_line in (2, 3):
            assert s.origin_revision == sha_feat
    # 2 feat + 1 main; main is pre-window still in-window here because window starts Jan 1.
    assert result.metrics.total_lines == 3
    assert result.metrics.fully_ai_value == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# AC-003-2 [Typical] Squash merge collapses attribution to the squash commit.
# ---------------------------------------------------------------------------
def test_ac_003_2_squash_merge_reattributes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_file(
        repo, "src/a.py", "main1\n",
        message="c0", date="2026-02-01T10:00:00Z",
    )
    checkout_new_branch(repo, "feature")
    rewrite_line(
        repo, "src/a.py", "main1\nf1\nf2\nf3\n",
        message="f1", date="2026-02-05T10:00:00Z",
    )
    checkout(repo, "main")
    sha_squash = merge_squash(
        repo, "feature", message="squash feature",
        date="2026-02-10T10:00:00Z",
    )
    # Only the squash commit has a genCodeDesc record. No record for main's seed
    # or the original feature commit, so OnMissing default (ZERO) gives line 1
    # genRatio 0 and fully_ai_value = 3/4.
    records = [
        _rec(sha_squash, "src/a.py",
             [{"lineRange": {"from": 2, "to": 4}, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    assert result.metrics.total_lines == 4
    # Squash commit owns lines 2-4 on main.
    squash_owned = [s for s in result.in_window_adds if s.origin_revision == sha_squash]
    assert len(squash_owned) == 3
    assert result.metrics.fully_ai_value == pytest.approx(3 / 4)


# ---------------------------------------------------------------------------
# AC-003-3 [Typical] Cherry-pick creates independent attribution.
# ---------------------------------------------------------------------------
def test_ac_003_3_cherry_pick_new_attribution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # main seed.
    commit_file(
        repo, "src/a.py", "main1\n",
        message="c0", date="2026-02-01T10:00:00Z",
    )
    # feature branch commit with AI lines.
    checkout_new_branch(repo, "feature")
    sha_feat = rewrite_line(
        repo, "src/a.py", "main1\nf1\n",
        message="feat", date="2026-02-05T10:00:00Z",
    )
    # Cherry-pick into main.
    checkout(repo, "main")
    sha_cp = cherry_pick(repo, sha_feat, date="2026-02-10T10:00:00Z")
    # On main, the new line's blame origin is the cherry-pick commit, not the
    # original feature commit.
    records = [
        _rec(sha_cp, "src/a.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    picked = [s for s in result.in_window_adds if s.origin_line == 2 and s.origin_file == "src/a.py"]
    assert len(picked) == 1
    assert picked[0].origin_revision == sha_cp
    assert picked[0].origin_revision != sha_feat


# ---------------------------------------------------------------------------
# AC-003-4 [Typical] Revert removes AI attribution from the live set.
# ---------------------------------------------------------------------------
def test_ac_003_4_revert_removes_ai_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_file(
        repo, "src/a.py", "seed\n",
        message="c0", date="2026-02-01T10:00:00Z",
    )
    sha_ai = rewrite_line(
        repo, "src/a.py", "seed\nAI1\nAI2\n",
        message="c1: add AI lines", date="2026-02-05T10:00:00Z",
    )
    revert(repo, sha_ai, date="2026-02-10T10:00:00Z")
    # After revert the file has only the original seed line.
    records = [_rec(sha_ai, "src/a.py",
                    [{"lineRange": {"from": 2, "to": 3},
                      "genRatio": 100, "genMethod": "vibeCoding"}])]
    result = run_algorithm_a(repo, records, **_WINDOW)
    assert result.metrics.total_lines == 1
    # None of the surviving lines trace back to the AI commit.
    assert all(s.origin_revision != sha_ai for s in result.surviving)


# ---------------------------------------------------------------------------
# AC-003-5 [Edge] Amend orphans old genCodeDesc.
# ---------------------------------------------------------------------------
def test_ac_003_5_amend_orphans_old_revision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_before = commit_file(
        repo, "src/a.py", "v1\n",
        message="c1", date="2026-02-05T10:00:00Z",
    )
    # Amend: rewrite the same tip commit. Use commit --amend.
    (repo / "src/a.py").write_text("v1_amended\n", encoding="utf-8")
    from tests._git_fixture import git as _git
    _git(repo, "add", "src/a.py")
    _git(
        repo, "commit", "-q", "--amend", "-m", "c1 amended",
        env={
            "GIT_AUTHOR_DATE": "2026-02-05T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-06T10:00:00Z",
        },
    )
    sha_after = _git(repo, "rev-parse", "HEAD").strip()
    assert sha_before != sha_after

    # Old record keyed by sha_before is now orphaned; only sha_after's record
    # matters. With OnMissing default (ZERO), the unattributed amended line
    # becomes genRatio 0.
    records = [
        _rec(sha_before, "src/a.py",
             [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    assert result.metrics.total_lines == 1
    # Orphan: line attributed to sha_after (not sha_before), so genRatio 0.
    only = result.in_window_adds[0]
    assert only.origin_revision == sha_after
    assert only.gen_ratio == 0
    assert any("no genCodeDesc record" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# AC-003-6 [Edge] Rebased commit has a different revisionId.
# ---------------------------------------------------------------------------
def test_ac_003_6_rebase_changes_revision_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_file(
        repo, "src/a.py", "base\n",
        message="c0", date="2026-02-01T10:00:00Z",
    )
    # Branch feat with one commit.
    checkout_new_branch(repo, "feat")
    sha_old = rewrite_line(
        repo, "src/a.py", "base\nfeat\n",
        message="c1", date="2026-02-05T10:00:00Z",
    )
    # Advance main so rebase has something to replay onto.
    checkout(repo, "main")
    commit_file(
        repo, "other.py", "x\n",
        message="main advance", date="2026-02-07T10:00:00Z",
    )
    # Rebase feat onto main.
    checkout(repo, "feat")
    from tests._git_fixture import git as _git
    _git(
        repo, "rebase", "main",
        env={
            "GIT_AUTHOR_DATE": "2026-02-05T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-08T10:00:00Z",
        },
    )
    sha_new = _git(repo, "rev-parse", "HEAD").strip()
    assert sha_old != sha_new

    # Provide records keyed by BOTH old and new ids; AlgA must ignore the stale
    # old-id record because blame reports sha_new.
    records = [
        _rec(sha_old, "src/a.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),   # stale
        _rec(sha_new, "src/a.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, end_rev="feat", **_WINDOW)
    feat_line = [s for s in result.in_window_adds if s.origin_line == 2 and s.current_file == "src/a.py"]
    assert len(feat_line) == 1
    assert feat_line[0].origin_revision == sha_new
    assert feat_line[0].gen_ratio == 100
