"""Algorithm B — offline diff replay against v26.03 records.

CaTDD tests covering:
  AC-AlgB-1  single commit adds N lines → metrics match canonical scenario
  AC-AlgB-2  later commit deletes a prior line → surviving reflects delete
  AC-AlgB-3  later commit modifies a line → ownership transfers to the later commit
  AC-AlgB-4  pre-window add survives but is excluded from the metric
  AC-AlgB-5  commits after endTime are ignored
  AC-006-1   missing genCodeDesc entry → ZERO (default) attributes genRatio 0,
             ABORT raises, SKIP drops the line from the surviving set
    AC-AlgB-6  patch parser supports rename and rejects binary
"""

from __future__ import annotations

from datetime import datetime

import pytest

from aggregateGenCodeDesc.algorithms.alg_b import (
    AlgBResult,
    build_commit,
    run_algorithm_b,
)
from aggregateGenCodeDesc.core.patch import parse_unified_diff
from aggregateGenCodeDesc.core.protocol import OnMissing
from aggregateGenCodeDesc.core.validation import ValidationError


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _record(
    revision_id: str,
    timestamp: str,
    file_name: str,
    code_lines: list[dict],
) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": file_name, "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": revision_id,
            "revisionTimestamp": timestamp,
        },
    }


# ---------------------------------------------------------------------------
# AC-AlgB-1 [Typical] Single commit adds 10 lines — canonical scenario
# ---------------------------------------------------------------------------
def test_ac_algb_1_canonical_ten_lines() -> None:
    rec = _record(
        "c1",
        "2026-02-10T10:00:00Z",
        "src/auth.py",
        [
            {"lineRange": {"from": 1, "to": 5}, "genRatio": 100, "genMethod": "vibeCoding"},
            {"lineRange": {"from": 6, "to": 8}, "genRatio": 80, "genMethod": "vibeCoding"},
            {"lineLocation": 9, "genRatio": 30, "genMethod": "vibeCoding"},
            {"lineLocation": 10, "genRatio": 0, "genMethod": "Manual"},
        ],
    )
    # New file: 10 lines added.
    patch = (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "--- /dev/null\n"
        "+++ b/src/auth.py\n"
        "@@ -0,0 +1,10 @@\n"
        + "".join(f"+line{i}\n" for i in range(1, 11))
    )
    commit = build_commit(rec, patch)
    result = run_algorithm_b(
        [commit],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert isinstance(result, AlgBResult)
    m = result.metrics
    assert m.total_lines == 10
    assert m.weighted_value == pytest.approx(0.77, abs=1e-6)
    assert m.fully_ai_value == pytest.approx(0.50, abs=1e-6)
    assert m.mostly_ai_value == pytest.approx(0.80, abs=1e-6)


# ---------------------------------------------------------------------------
# AC-AlgB-2 [Typical] Later commit deletes a prior line
# ---------------------------------------------------------------------------
def test_ac_algb_2_later_commit_deletes_prior_add() -> None:
    r1 = _record(
        "c1", "2026-02-10T10:00:00Z", "src/a.py",
        [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    p1 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+line1\n+line2\n+line3\n"
    )
    # c2 deletes line 2 of src/a.py.
    r2 = _record("c2", "2026-02-11T10:00:00Z", "src/a.py", [])
    p2 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,3 +1,2 @@\n"
        " line1\n"
        "-line2\n"
        " line3\n"
    )
    result = run_algorithm_b(
        [build_commit(r1, p1), build_commit(r2, p2)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 2
    assert result.metrics.fully_ai_value == 1.0


# ---------------------------------------------------------------------------
# AC-AlgB-3 [Typical] Later commit modifies a line → ownership transfers
# ---------------------------------------------------------------------------
def test_ac_algb_3_modify_transfers_ownership() -> None:
    r1 = _record(
        "c1", "2026-02-10T10:00:00Z", "src/a.py",
        [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    p1 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+a1\n+a2\n+a3\n"
    )
    # c2 replaces line 2 (a2 → b2) with a human-written line (genRatio 0).
    r2 = _record(
        "c2", "2026-02-11T10:00:00Z", "src/a.py",
        [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}],
    )
    p2 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,3 +1,3 @@\n"
        " a1\n"
        "-a2\n"
        "+b2\n"
        " a3\n"
    )
    result = run_algorithm_b(
        [build_commit(r1, p1), build_commit(r2, p2)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 3
    # 2 AI + 1 human → fullyAI = 2/3, weighted = 2/3
    assert result.metrics.fully_ai_value == pytest.approx(2 / 3)
    assert result.metrics.weighted_value == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# AC-AlgB-4 [Edge] Pre-window add survives but is excluded from metric
# ---------------------------------------------------------------------------
def test_ac_algb_4_prewindow_excluded() -> None:
    r1 = _record(
        "c1", "2025-12-01T10:00:00Z", "src/a.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    p1 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+a\n"
    )
    r2 = _record(
        "c2", "2026-02-10T10:00:00Z", "src/a.py",
        [{"lineLocation": 2, "genRatio": 50, "genMethod": "vibeCoding"}],
    )
    p2 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +1,2 @@\n"
        " a\n"
        "+b\n"
    )
    result = run_algorithm_b(
        [build_commit(r1, p1), build_commit(r2, p2)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # Only c2's line is in-window.
    assert result.metrics.total_lines == 1
    assert result.metrics.weighted_value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# AC-AlgB-5 [Typical] Commits after endTime are ignored
# ---------------------------------------------------------------------------
def test_ac_algb_5_ignores_post_endtime_commits() -> None:
    r1 = _record(
        "c1", "2026-02-10T10:00:00Z", "src/a.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    p1 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+a\n"
    )
    # c2 (after endTime) would delete it; must be ignored.
    r2 = _record("c2", "2027-01-01T10:00:00Z", "src/a.py", [])
    p2 = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +0,0 @@\n"
        "-a\n"
    )
    result = run_algorithm_b(
        [build_commit(r1, p1), build_commit(r2, p2)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 1


# ---------------------------------------------------------------------------
# AC-006-1 [Fault] Missing genCodeDesc entry — policy-driven
# ---------------------------------------------------------------------------
def _commit_with_missing_entry() -> tuple:
    # Record declares genRatio only for line 1 but patch adds lines 1 and 2.
    rec = _record(
        "c1", "2026-02-10T10:00:00Z", "src/a.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    patch = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n+b\n"
    )
    return rec, patch


def test_ac_006_1_missing_entry_zero_default() -> None:
    rec, patch = _commit_with_missing_entry()
    result = run_algorithm_b(
        [build_commit(rec, patch)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 2
    # one 100 + one 0 → weighted 0.5, fullyAI 0.5, mostlyAI 0.5
    assert result.metrics.weighted_value == pytest.approx(0.5)
    assert any("src/a.py:2" in w for w in result.warnings)


def test_ac_006_1_missing_entry_abort() -> None:
    rec, patch = _commit_with_missing_entry()
    with pytest.raises(ValidationError, match="missing genCodeDesc"):
        run_algorithm_b(
            [build_commit(rec, patch)],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
            on_missing=OnMissing.ABORT,
        )


def test_ac_006_1_missing_entry_skip() -> None:
    rec, patch = _commit_with_missing_entry()
    result = run_algorithm_b(
        [build_commit(rec, patch)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
        on_missing=OnMissing.SKIP,
    )
    # Only the attributed line is counted.
    assert result.metrics.total_lines == 1
    assert result.metrics.fully_ai_value == 1.0


# ---------------------------------------------------------------------------
# AC-AlgB-6 Loader: missing revisionTimestamp → ValidationError
# ---------------------------------------------------------------------------
def test_build_commit_requires_revisionTimestamp() -> None:
    rec = _record("c1", "2026-02-10T10:00:00Z", "src/a.py",
                  [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}])
    del rec["REPOSITORY"]["revisionTimestamp"]
    patch = "diff --git a/src/a.py b/src/a.py\n--- /dev/null\n+++ b/src/a.py\n@@ -0,0 +1 @@\n+a\n"
    with pytest.raises(ValidationError, match="revisionTimestamp"):
        build_commit(rec, patch)


# ---------------------------------------------------------------------------
# Patch parser / replay: rename supported, binary still rejected
# ---------------------------------------------------------------------------
def test_patch_parses_pure_rename_without_hunks() -> None:
    text = (
        "diff --git a/old.py b/new.py\n"
        "similarity index 100%\n"
        "rename from old.py\n"
        "rename to new.py\n"
    )
    files = parse_unified_diff(text)
    assert len(files) == 1
    assert files[0].old_path == "old.py"
    assert files[0].new_path == "new.py"
    assert files[0].hunks == ()


def test_ac_algb_rename_chain_replay_keeps_line_and_updates_path() -> None:
    # c1: add a.py line 1 (AI)
    r1 = _record(
        "c1", "2026-02-10T10:00:00Z", "a.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    p1 = (
        "diff --git a/a.py b/a.py\n"
        "--- /dev/null\n"
        "+++ b/a.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+line\n"
    )
    # c2: pure rename a.py -> b.py
    r2 = _record("c2", "2026-02-11T10:00:00Z", "b.py", [])
    p2 = (
        "diff --git a/a.py b/b.py\n"
        "similarity index 100%\n"
        "rename from a.py\n"
        "rename to b.py\n"
    )
    # c3: pure rename b.py -> c.py
    r3 = _record("c3", "2026-02-12T10:00:00Z", "c.py", [])
    p3 = (
        "diff --git a/b.py b/c.py\n"
        "similarity index 100%\n"
        "rename from b.py\n"
        "rename to c.py\n"
    )

    result = run_algorithm_b(
        [
            build_commit(r1, p1),
            build_commit(r2, p2),
            build_commit(r3, p3),
        ],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )

    assert result.metrics.total_lines == 1
    assert result.metrics.fully_ai_value == 1.0
    assert len(result.surviving) == 1
    assert result.surviving[0].file_name == "c.py"
    # Pure renames do not change ownership.
    assert result.surviving[0].revision_id == "c1"


def test_patch_rejects_binary() -> None:
    text = (
        "diff --git a/img.png b/img.png\n"
        "Binary files a/img.png and b/img.png differ\n"
    )
    with pytest.raises(ValidationError, match="binary"):
        parse_unified_diff(text)


def test_patch_parses_multiple_files() -> None:
    text = (
        "diff --git a/a.py b/a.py\n"
        "--- /dev/null\n"
        "+++ b/a.py\n"
        "@@ -0,0 +1 @@\n"
        "+a\n"
        "diff --git a/b.py b/b.py\n"
        "--- /dev/null\n"
        "+++ b/b.py\n"
        "@@ -0,0 +1 @@\n"
        "+b\n"
    )
    files = parse_unified_diff(text)
    assert [f.new_path for f in files] == ["a.py", "b.py"]
    assert all(f.is_new_file for f in files)


def test_patch_parses_quoted_paths() -> None:
    text = (
        'diff --git "a/my file.py" "b/my file.py"\n'
        '--- "a/my file.py"\n'
        '+++ "b/my file.py"\n'
        "@@ -0,0 +1,1 @@\n"
        "+x\n"
    )
    files = parse_unified_diff(text)
    assert len(files) == 1
    assert files[0].old_path == "my file.py"
    assert files[0].new_path == "my file.py"


def test_patch_rejects_inconsistent_rename_metadata_and_hunk_paths() -> None:
    text = (
        "diff --git a/a.py b/b.py\n"
        "rename from a.py\n"
        "rename to b.py\n"
        "--- a/x.py\n"
        "+++ b/y.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    with pytest.raises(ValidationError, match="inconsistent rename paths"):
        parse_unified_diff(text)


def test_ac_algb_quoted_path_matches_record_file_name() -> None:
    rec = _record(
        "c1", "2026-02-10T10:00:00Z", "my file.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
    )
    patch = (
        'diff --git "a/my file.py" "b/my file.py"\n'
        "--- /dev/null\n"
        '+++ "b/my file.py"\n'
        "@@ -0,0 +1,1 @@\n"
        "+x\n"
    )

    result = run_algorithm_b(
        [build_commit(rec, patch)],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    assert result.metrics.total_lines == 1
    assert result.metrics.fully_ai_value == 1.0
    assert result.warnings == ()
