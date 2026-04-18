"""Algorithm A — live `git blame` with `-M -C`.

CaTDD tests covering:
  AC-AlgA-1  [Typical] single commit, all lines live → metrics match canonical scenario
  AC-AlgA-2  [Typical] human edit transfers ownership to the later commit (AC-004-1)
  AC-009-1 / AC-002-1  [Typical] rename preserves blame to original commit
  AC-005-1   [Typical] commits before startTime excluded from metric
  AC-006-1   [Fault] missing genCodeDesc record → ZERO(default) / ABORT / SKIP
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.core.protocol import OnMissing
from aggregateGenCodeDesc.core.validation import ValidationError

from tests._git_fixture import (
    commit_file,
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


# ---------------------------------------------------------------------------
# AC-AlgA-1 [Typical] Canonical 10-line scenario in a single commit
# ---------------------------------------------------------------------------
def test_ac_alga_1_canonical_ten_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    content = "".join(f"line{i}\n" for i in range(1, 11))
    sha = commit_file(
        repo, "src/auth.py", content,
        message="c1: seed 10 lines", date="2026-02-10T10:00:00Z",
    )
    rec = _rec(sha, "src/auth.py", [
        {"lineRange": {"from": 1, "to": 5}, "genRatio": 100, "genMethod": "vibeCoding"},
        {"lineRange": {"from": 6, "to": 8}, "genRatio": 80, "genMethod": "vibeCoding"},
        {"lineLocation": 9, "genRatio": 30, "genMethod": "vibeCoding"},
        {"lineLocation": 10, "genRatio": 0, "genMethod": "Manual"},
    ])

    result = run_algorithm_a(
        repo, [rec],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    m = result.metrics
    assert m.total_lines == 10
    assert m.weighted_value == pytest.approx(0.77, abs=1e-6)
    assert m.fully_ai_value == pytest.approx(0.50, abs=1e-6)
    assert m.mostly_ai_value == pytest.approx(0.80, abs=1e-6)


# ---------------------------------------------------------------------------
# AC-AlgA-2 [Typical] Human edit transfers ownership (AC-004-1)
# ---------------------------------------------------------------------------
def test_ac_alga_2_human_edit_transfers_ownership(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha1 = commit_file(
        repo, "src/a.py", "a1\na2\na3\n",
        message="c1", date="2026-02-10T10:00:00Z",
    )
    # Rewrite line 2 with a human line.
    sha2 = rewrite_line(
        repo, "src/a.py", "a1\nb2\na3\n",
        message="c2", date="2026-02-11T10:00:00Z",
    )
    records = [
        _rec(sha1, "src/a.py", [
            {"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"},
        ]),
        _rec(sha2, "src/a.py", [
            {"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"},
        ]),
    ]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 3
    # 2 AI + 1 human → fullyAI = 2/3, weighted = 2/3
    assert result.metrics.fully_ai_value == pytest.approx(2 / 3)
    assert result.metrics.weighted_value == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# AC-009-1 / AC-002-1 [Typical] Pure rename preserves blame
# ---------------------------------------------------------------------------
def test_ac_alga_rename_preserves_blame(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha1 = commit_file(
        repo, "src/old.py", "a\nb\nc\n",
        message="c1: seed", date="2026-02-10T10:00:00Z",
    )
    # Pure rename only.
    rename_file(
        repo, "src/old.py", "src/new.py",
        message="c2: rename", date="2026-02-11T10:00:00Z",
    )
    # Only c1 has genCodeDesc; c2 is a pure rename with no content change.
    records = [_rec(sha1, "src/old.py", [
        {"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"},
    ])]

    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # All 3 lines attributed to c1 via `git blame -M`.
    assert result.metrics.total_lines == 3
    assert result.metrics.fully_ai_value == 1.0
    # Current path in surviving view is src/new.py; origin_file remains src/old.py.
    for s in result.in_window_adds:
        assert s.current_file == "src/new.py"
        assert s.origin_file == "src/old.py"
        assert s.origin_revision == sha1


# ---------------------------------------------------------------------------
# AC-005-1 [Typical] Pre-window commit excluded from metric
# ---------------------------------------------------------------------------
def test_ac_alga_prewindow_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_pre = commit_file(
        repo, "src/a.py", "pre\n",
        message="c0", date="2025-12-01T10:00:00Z",
    )
    sha_in = rewrite_line(
        repo, "src/a.py", "pre\nin\n",
        message="c1", date="2026-02-10T10:00:00Z",
    )
    records = [
        _rec(sha_pre, "src/a.py", [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]),
        _rec(sha_in, "src/a.py", [{"lineLocation": 2, "genRatio": 50, "genMethod": "vibeCoding"}]),
    ]
    result = run_algorithm_a(
        repo, records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 1
    assert result.metrics.weighted_value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# AC-006-1 Missing record — ZERO / ABORT / SKIP
# ---------------------------------------------------------------------------
def _setup_missing(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha = commit_file(
        repo, "src/a.py", "a\nb\n",
        message="c1", date="2026-02-10T10:00:00Z",
    )
    return repo, sha


def test_ac_alga_missing_record_zero_default(tmp_path: Path) -> None:
    repo, _sha = _setup_missing(tmp_path)
    result = run_algorithm_a(
        repo, records=[],  # no genCodeDesc supplied
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 2
    assert result.metrics.weighted_value == pytest.approx(0.0)
    assert any("no genCodeDesc record" in w for w in result.warnings)


def test_ac_alga_missing_record_abort(tmp_path: Path) -> None:
    repo, _sha = _setup_missing(tmp_path)
    with pytest.raises(ValidationError, match="no genCodeDesc record"):
        run_algorithm_a(
            repo, records=[],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
            on_missing=OnMissing.ABORT,
        )


def test_ac_alga_missing_record_skip(tmp_path: Path) -> None:
    repo, _sha = _setup_missing(tmp_path)
    result = run_algorithm_a(
        repo, records=[],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
        on_missing=OnMissing.SKIP,
    )
    assert result.metrics.total_lines == 0


# ---------------------------------------------------------------------------
# Guard: non-git directory rejected
# ---------------------------------------------------------------------------
def test_rejects_non_git_directory(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(ValidationError, match="not a git repository"):
        run_algorithm_a(
            tmp_path / "plain", [],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
        )
