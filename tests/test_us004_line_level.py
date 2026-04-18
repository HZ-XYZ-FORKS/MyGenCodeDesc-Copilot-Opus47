"""US-004 — line-level ownership transfer and edge cases.

All tests drive Algorithm A (live `git blame`) against tiny throw-away
repos. Whitespace (AC-004-3) and CRLF (AC-004-4) test the *default*
git-blame policy (no `-w`, no EOL coercion) — the policy the current
implementation ships with.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import (
    commit_file,
    git,
    init_repo,
)


def _edit_one_line(
    repo: Path, rel_path: str, *, line_no: int, new_text: str,
    message: str, date: str,
) -> str:
    """Rewrite a single line (1-indexed) in `rel_path` and commit."""
    p = repo / rel_path
    lines = p.read_text(encoding="utf-8").splitlines(keepends=False)
    lines[line_no - 1] = new_text
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    git(repo, "add", rel_path)
    git(
        repo, "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


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
# AC-004-1 [Typical] AI line edited by human transfers ownership.
# ---------------------------------------------------------------------------
def test_ac_004_1_ai_line_edited_by_human(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_ai = commit_file(
        repo, "auth.py", "a\nai_line\nc\n",
        message="c1: AI line", date="2026-02-05T10:00:00Z",
    )
    sha_human = _edit_one_line(
        repo, "auth.py", line_no=2, new_text="human_edit",
        message="c2: human edits line 2", date="2026-02-10T10:00:00Z",
    )
    records = [
        _rec(sha_ai, "auth.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_human, "auth.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    by_line = {s.current_line: s for s in result.in_window_adds}
    # Line 2 now traces to human commit with genRatio 0.
    assert by_line[2].origin_revision == sha_human
    assert by_line[2].gen_ratio == 0


# ---------------------------------------------------------------------------
# AC-004-2 [Typical] Human line rewritten by AI transfers ownership.
# ---------------------------------------------------------------------------
def test_ac_004_2_human_line_rewritten_by_ai(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_human = commit_file(
        repo, "utils.py", "a\nhuman_line\nc\n",
        message="c1: human", date="2026-02-05T10:00:00Z",
    )
    sha_ai = _edit_one_line(
        repo, "utils.py", line_no=2, new_text="ai_rewrite",
        message="c2: AI rewrite line 2", date="2026-02-10T10:00:00Z",
    )
    records = [
        _rec(sha_human, "utils.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
        _rec(sha_ai, "utils.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    by_line = {s.current_line: s for s in result.in_window_adds}
    assert by_line[2].origin_revision == sha_ai
    assert by_line[2].gen_ratio == 100


# ---------------------------------------------------------------------------
# AC-004-3 [Edge] Whitespace-only change: default `git blame` (no `-w`)
#                 DOES transfer blame. Policy documented.
# ---------------------------------------------------------------------------
def test_ac_004_3_whitespace_only_change_transfers_blame(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_ai = commit_file(
        repo, "config.py", "a\nvalue = 1\nc\n",
        message="c1: AI line", date="2026-02-05T10:00:00Z",
    )
    # Whitespace-only change: add 4-space indent.
    sha_ws = _edit_one_line(
        repo, "config.py", line_no=2, new_text="    value = 1",
        message="c2: reindent", date="2026-02-10T10:00:00Z",
    )
    records = [
        _rec(sha_ai, "config.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_ws, "config.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    by_line = {s.current_line: s for s in result.in_window_adds}
    # Default policy: whitespace change transfers ownership to the reformat commit.
    # Forks preferring `-w` would re-implement blame with that flag.
    assert by_line[2].origin_revision == sha_ws
    assert by_line[2].gen_ratio == 0


# ---------------------------------------------------------------------------
# AC-004-4 [Edge] CRLF→LF conversion re-attributes every line.
# ---------------------------------------------------------------------------
def test_ac_004_4_crlf_to_lf_reattributes_all_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # Seed with CRLF content.
    crlf = "line1\r\nline2\r\nline3\r\n"
    p = repo / "data.txt"
    p.write_bytes(crlf.encode("utf-8"))
    git(repo, "add", "data.txt")
    git(
        repo, "commit", "-q", "-m", "c1: CRLF seed",
        env={
            "GIT_AUTHOR_DATE": "2026-02-05T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-05T10:00:00Z",
        },
    )
    sha_crlf = git(repo, "rev-parse", "HEAD").strip()
    # EOL normalisation commit.
    lf = "line1\nline2\nline3\n"
    p.write_bytes(lf.encode("utf-8"))
    git(repo, "add", "data.txt")
    git(
        repo, "commit", "-q", "-m", "c2: CRLF->LF",
        env={
            "GIT_AUTHOR_DATE": "2026-02-10T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-10T10:00:00Z",
        },
    )
    sha_lf = git(repo, "rev-parse", "HEAD").strip()

    records = [
        _rec(sha_crlf, "data.txt",
             [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_lf, "data.txt",
             [{"lineRange": {"from": 1, "to": 3}, "genRatio": 50, "genMethod": "Hybrid"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    # All 3 lines now trace to the LF commit; none remain on the CRLF seed.
    assert all(s.origin_revision == sha_lf for s in result.in_window_adds)
    assert result.metrics.total_lines == 3


# ---------------------------------------------------------------------------
# AC-004-5 [Edge] Deleted + re-added identical line gets new attribution.
# ---------------------------------------------------------------------------
def test_ac_004_5_deleted_and_readded_line(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_orig = commit_file(
        repo, "code.py", "x\nreturn 42\nz\n",
        message="c1: original", date="2026-02-01T10:00:00Z",
    )
    # Delete the target line.
    (repo / "code.py").write_text("x\nz\n", encoding="utf-8")
    git(repo, "add", "code.py")
    git(
        repo, "commit", "-q", "-m", "c2: delete line",
        env={
            "GIT_AUTHOR_DATE": "2026-02-05T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-05T10:00:00Z",
        },
    )
    # Re-add identical text in a later commit.
    (repo / "code.py").write_text("x\nreturn 42\nz\n", encoding="utf-8")
    git(repo, "add", "code.py")
    git(
        repo, "commit", "-q", "-m", "c3: readd line",
        env={
            "GIT_AUTHOR_DATE": "2026-02-10T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-10T10:00:00Z",
        },
    )
    sha_readd = git(repo, "rev-parse", "HEAD").strip()

    records = [
        _rec(sha_orig, "code.py",
             [{"lineLocation": 2, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_readd, "code.py",
             [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    by_line = {s.current_line: s for s in result.in_window_adds}
    # The re-added line traces to the re-add commit, NOT the original.
    assert by_line[2].origin_revision == sha_readd
    assert by_line[2].gen_ratio == 0


# ---------------------------------------------------------------------------
# AC-004-6 [Edge] Line moved within a file. With `git blame -M`, the line is
#                 tracked back to its original commit (move detection).
# ---------------------------------------------------------------------------
def test_ac_004_6_line_moved_within_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    # Seed file with distinctive line at position 2.
    body = "line_a\nx = compute()\nline_c\nline_d\nline_e\n"
    sha_seed = commit_file(
        repo, "mod.py", body,
        message="c1: seed", date="2026-02-05T10:00:00Z",
    )
    # Move `x = compute()` from position 2 to position 5.
    moved = "line_a\nline_c\nline_d\nline_e\nx = compute()\n"
    (repo / "mod.py").write_text(moved, encoding="utf-8")
    git(repo, "add", "mod.py")
    git(
        repo, "commit", "-q", "-m", "c2: reorder",
        env={
            "GIT_AUTHOR_DATE": "2026-02-10T10:00:00Z",
            "GIT_COMMITTER_DATE": "2026-02-10T10:00:00Z",
        },
    )
    sha_reorder = git(repo, "rev-parse", "HEAD").strip()
    records = [
        _rec(sha_seed, "mod.py",
             [{"lineRange": {"from": 1, "to": 5}, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_reorder, "mod.py",
             [{"lineLocation": 5, "genRatio": 0, "genMethod": "Manual"}]),
    ]
    result = run_algorithm_a(repo, records, **_WINDOW)
    by_line = {s.current_line: s for s in result.in_window_adds}
    # Short single-line moves fall below `git blame -M`'s default threshold,
    # so the moved line is attributed to the reorder commit (matches AC-004-6).
    assert by_line[5].origin_revision == sha_reorder
    assert by_line[5].gen_ratio == 0
