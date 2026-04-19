"""US-009 Algorithm-specific behavior — gap-closing tests.

Covers acceptance criteria not already exercised by per-algorithm suites:

  AC-009-3  [Fault]   AlgA reports clear error when VCS is unreachable.
    AC-009-5  [Edge]    AlgB chained renames preserve line ownership while
                                            updating current path.
  AC-009-6  [Fault]   AlgB diff missing for one commit in the chain →
                      CLI aborts with the offending revisionId in the error.
  AC-009-8  [Edge]    AlgC duplicate add for same (rev, origFile, origLine) →
                      fork policy: later entry wins (overwrite).
  AC-009-9  [Fault]   v26.04 SUMMARY.lineCount disagrees with DETAIL add
                      count → ValidationError mentioning the revisionId.

AC-009-1/2/4/7 are already covered by test_algorithm_a / test_us002 /
test_algorithm_b / test_algorithm_c and intentionally not duplicated here.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms import alg_a as alg_a_module
from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import load_v2604_record, run_algorithm_c
from aggregateGenCodeDesc.cli import main as cli_main
from aggregateGenCodeDesc.core.git import GitError
from aggregateGenCodeDesc.core.protocol import OnMissing
from aggregateGenCodeDesc.core.validation import ValidationError

from tests._git_fixture import commit_file, init_repo


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# =============================================================================
# AC-009-3 [Fault] AlgA reports clear error when VCS is unreachable.
# =============================================================================
def test_ac_009_3_alga_reports_unreachable_vcs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_file(
        repo, "a.py", "x\n",
        message="seed", date="2026-02-01T10:00:00Z",
    )

    # Simulate the remote being unreachable during list_tracked_files.
    def _boom(_repo: Path, _rev: str) -> list[str]:
        raise GitError(
            "git ls-tree failed (rc=128): "
            "fatal: unable to access 'https://git.example.com/repo.git/': "
            "Could not resolve host: git.example.com"
        )

    monkeypatch.setattr(alg_a_module, "list_tracked_files", _boom)

    with pytest.raises(ValidationError) as excinfo:
        run_algorithm_a(
            repo,
            records=[],
            start_time=_utc("2026-01-01T00:00:00Z"),
            end_time=_utc("2026-12-31T00:00:00Z"),
            threshold=60,
        )

    msg = str(excinfo.value)
    # Clear connection error with the server URL surfaced.
    assert "Could not resolve host" in msg
    assert "git.example.com" in msg


# =============================================================================
# AC-009-5 [Edge] AlgB supports chained renames; line ownership persists while
# current path moves to the final file name.
# =============================================================================
def test_ac_009_5_algb_rename_chain_preserves_ownership() -> None:
    r1 = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [
            {
                "fileName": "v1.py",
                "codeLines": [
                    {
                        "lineLocation": 1,
                        "genRatio": 100,
                        "genMethod": "vibeCoding",
                    },
                ],
            }
        ],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": "c1",
            "revisionTimestamp": "2026-03-01T10:00:00Z",
        },
    }

    p1 = (
        "diff --git a/v1.py b/v1.py\n"
        "--- /dev/null\n"
        "+++ b/v1.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+line\n"
    )

    r2 = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": "c2",
            "revisionTimestamp": "2026-03-02T10:00:00Z",
        },
    }
    p2 = (
        "diff --git a/v1.py b/v2.py\n"
        "similarity index 100%\n"
        "rename from v1.py\n"
        "rename to v2.py\n"
    )

    r3 = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": "c3",
            "revisionTimestamp": "2026-03-03T10:00:00Z",
        },
    }
    p3 = (
        "diff --git a/v2.py b/v3.py\n"
        "similarity index 100%\n"
        "rename from v2.py\n"
        "rename to v3.py\n"
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
        on_missing=OnMissing.ZERO,
    )

    assert result.metrics.total_lines == 1
    assert result.metrics.fully_ai_value == 1.0
    assert len(result.surviving) == 1
    assert result.surviving[0].file_name == "v3.py"
    assert result.surviving[0].revision_id == "c1"


# =============================================================================
# AC-009-6 [Fault] AlgB missing diff for one commit → CLI aborts and names it.
# =============================================================================
def _v2603_record_dict(rev: str, ts: str, file_name: str, n_lines: int) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{
            "fileName": file_name,
            "codeLines": [
                {"lineLocation": i, "genRatio": 100, "genMethod": "vibeCoding"}
                for i in range(1, n_lines + 1)
            ],
        }],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _unified_add_patch(file_name: str, n_lines: int) -> str:
    header = (
        f"diff --git a/{file_name} b/{file_name}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{file_name}\n"
        f"@@ -0,0 +1,{n_lines} @@\n"
    )
    body = "".join(f"+line{i}\n" for i in range(1, n_lines + 1))
    return header + body


def test_ac_009_6_algb_cli_missing_patch_names_revision(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    gcd = tmp_path / "gcd"
    patches = tmp_path / "patches"
    out = tmp_path / "out"
    gcd.mkdir()
    patches.mkdir()

    # 3 commits in a chain; we deliberately omit the patch for C3.
    chain = [
        ("c1", "2026-02-01T10:00:00Z", "app.py", 2),
        ("c2", "2026-02-02T10:00:00Z", "app.py", 2),
        ("c3", "2026-02-03T10:00:00Z", "app.py", 2),
    ]
    for i, (rev, ts, fn, n) in enumerate(chain):
        (gcd / f"{i:02d}-{rev}.json").write_text(
            json.dumps(_v2603_record_dict(rev, ts, fn, n)), encoding="utf-8",
        )
        if rev != "c3":
            (patches / f"{rev}.patch").write_text(
                _unified_add_patch(fn, n), encoding="utf-8",
            )
        # no c3.patch written → simulates unavailable diff

    argv = [
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd),
        "--commit-patch-dir", str(patches),
        "--output-dir", str(out),
    ]
    with caplog.at_level("ERROR", logger="aggregateGenCodeDesc"):
        rc = cli_main(argv)

    assert rc == 2
    combined = " ".join(r.message for r in caplog.records)
    # The offending revisionId must appear in the error.
    assert "c3" in combined
    # And no partial output written.
    assert not out.exists() or not any(out.iterdir())


# =============================================================================
# AC-009-8 [Edge] AlgC duplicate add for same line → later entry overwrites.
# =============================================================================
def _mk_alg_c_record(
    rev: str,
    rev_ts: str,
    adds: list[tuple[int, int, str, int, str]] | None = None,
) -> dict:
    code_lines: list[dict] = []
    for loc, gr, brev, bline, bts in adds or []:
        code_lines.append({
            "changeType": "add",
            "lineLocation": loc,
            "genRatio": gr,
            "genMethod": "vibeCoding",
            "blame": {
                "revisionId": brev,
                "originalFilePath": "app.py",
                "originalLine": bline,
                "timestamp": bts,
            },
        })
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "app.py", "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": rev_ts,
        },
    }


def test_ac_009_8_algc_duplicate_add_later_wins() -> None:
    # c1 adds (blame=c1, origLine=42) with genRatio 100.
    r1 = load_v2604_record(_mk_alg_c_record(
        "c1", "2026-03-01T10:00:00Z",
        adds=[(1, 100, "c1", 42, "2026-03-01T10:00:00Z")],
    ))
    # c2 also emits an add for the same blame key, genRatio 30, without
    # a preceding delete → duplicate per AC-009-8.
    r2 = load_v2604_record(_mk_alg_c_record(
        "c2", "2026-03-02T10:00:00Z",
        adds=[(1, 30, "c1", 42, "2026-03-01T10:00:00Z")],
    ))
    metrics = run_algorithm_c(
        [r1, r2],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # Single surviving line (key collapsed), genRatio from the later record.
    assert metrics.total_lines == 1
    # weighted = 0.30 (later-wins, not first-wins, not averaged).
    assert metrics.weighted_value == pytest.approx(0.30)


# =============================================================================
# AC-009-9 [Fault] SUMMARY.lineCount ≠ DETAIL add count → ValidationError.
# =============================================================================
def test_ac_009_9_algc_summary_detail_mismatch_is_rejected() -> None:
    data = _mk_alg_c_record(
        "c1", "2026-03-01T10:00:00Z",
        adds=[
            (1, 100, "c1", 1, "2026-03-01T10:00:00Z"),
            (2, 100, "c1", 2, "2026-03-01T10:00:00Z"),
        ],
    )
    # Declare the wrong lineCount — 5 instead of 2.
    data["SUMMARY"] = {"lineCount": 5}

    with pytest.raises(ValidationError) as excinfo:
        load_v2604_record(data)

    msg = str(excinfo.value)
    assert "SUMMARY" in msg and "DETAIL" in msg
    # revisionId surfaced so operators can locate the bad file.
    assert "c1" in msg
    # Numbers shown for operator diagnosis.
    assert "5" in msg and "2" in msg


def test_ac_009_9_algc_summary_matching_lineCount_is_accepted() -> None:
    data = _mk_alg_c_record(
        "c1", "2026-03-01T10:00:00Z",
        adds=[
            (1, 100, "c1", 1, "2026-03-01T10:00:00Z"),
            (2, 100, "c1", 2, "2026-03-01T10:00:00Z"),
        ],
    )
    data["SUMMARY"] = {"lineCount": 2}  # matches
    rec = load_v2604_record(data)
    assert len(rec.adds) == 2
