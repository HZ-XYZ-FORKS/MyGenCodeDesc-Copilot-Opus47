"""US-002 — file-level conditions verified against Algorithm A.

Rename (AC-002-1) is already covered in tests/test_algorithm_a.py. This file
adds the remaining file-level ACs:

  AC-002-2  [Typical] Rename + modify: unchanged lines keep origin, modified
            lines transfer to the rename-commit.
  AC-002-3  [Typical] Deleted file contributes 0 lines to the live metric.
  AC-002-4  [Edge]    File copied to new path: copy is attributed to the copy commit.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import (
    commit_file,
    copy_file,
    delete_file,
    git,
    init_repo,
    rename_file,
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
# AC-002-2 [Typical] Rename + modify preserves unchanged-line origin,
#                    transfers modified lines to the rename commit.
# ---------------------------------------------------------------------------
def test_ac_002_2_rename_plus_modify(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_seed = commit_file(
        repo, "src/old.py", "a\nb\nc\n",
        message="c1: seed old.py", date="2026-02-05T10:00:00Z",
    )
    # Step 1: rename.
    git(repo, "mv", "src/old.py", "src/new.py")
    # Step 2: modify line 2 in the new file (same commit).
    (repo / "src/new.py").write_text("a\nB\nc\n", encoding="utf-8")
    git(repo, "add", "src/new.py")
    git(
        repo, "commit", "-q", "-m", "c2: rename+modify",
        env={
            "GIT_AUTHOR_DATE": "2026-02-10T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-10T10:00:00Z",
        },
    )
    sha_ren = git(repo, "rev-parse", "HEAD").strip()

    records = [
        _rec(sha_seed, "src/old.py",
             [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_ren, "src/new.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    assert result.metrics.total_lines == 3

    by_line = {s.current_line: s for s in result.in_window_adds}
    # Lines 1 and 3 still trace to the seed commit (pre-modify content in old.py).
    assert by_line[1].origin_revision == sha_seed
    assert by_line[1].origin_file == "src/old.py"
    assert by_line[1].gen_ratio == 100
    assert by_line[3].origin_revision == sha_seed
    # Line 2 transferred to the rename-commit.
    assert by_line[2].origin_revision == sha_ren
    assert by_line[2].gen_ratio == 0


# ---------------------------------------------------------------------------
# AC-002-3 [Typical] Deleted file contributes 0 lines to the metric.
# ---------------------------------------------------------------------------
def test_ac_002_3_deleted_file_contributes_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_seed = commit_file(
        repo, "src/removed.py", "a\nb\nc\n",
        message="c1: seed", date="2026-02-05T10:00:00Z",
    )
    # Also seed another file that survives.
    commit_file(
        repo, "src/survives.py", "s\n",
        message="c2: survivor", date="2026-02-06T10:00:00Z",
    )
    delete_file(
        repo, "src/removed.py",
        message="c3: delete removed.py", date="2026-02-10T10:00:00Z",
    )

    records = [
        _rec(sha_seed, "src/removed.py",
             [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    # Only src/survives.py contributes lines; removed.py is gone from live state.
    assert result.metrics.total_lines == 1
    assert all(s.current_file == "src/survives.py" for s in result.in_window_adds)


# ---------------------------------------------------------------------------
# AC-002-4 [Edge] File copied to new path: copy lines are attributed to the
#                 copy commit per user story (not back-traced to the seed).
#                 The original src/lib.py retains its seed attribution.
# ---------------------------------------------------------------------------
def test_ac_002_4_file_copied(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_seed = commit_file(
        repo, "src/lib.py", "x\ny\n",
        message="c1: seed lib", date="2026-02-05T10:00:00Z",
    )
    sha_copy = copy_file(
        repo, "src/lib.py", "src/lib_v2.py",
        message="c2: copy lib", date="2026-02-10T10:00:00Z",
    )
    records = [
        _rec(sha_seed, "src/lib.py",
             [{"lineRange": {"from": 1, "to": 2}, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_copy, "src/lib_v2.py",
             [{"lineRange": {"from": 1, "to": 2}, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    assert result.metrics.total_lines == 4

    by_file: dict[str, list] = {}
    for s in result.in_window_adds:
        by_file.setdefault(s.current_file, []).append(s)
    assert set(by_file) == {"src/lib.py", "src/lib_v2.py"}

    # Original file keeps seed attribution.
    for s in by_file["src/lib.py"]:
        assert s.origin_revision == sha_seed
    # Copy is attributed to the copy commit.
    for s in by_file["src/lib_v2.py"]:
        assert s.origin_revision == sha_copy
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
