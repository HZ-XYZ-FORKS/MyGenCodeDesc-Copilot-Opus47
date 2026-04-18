"""US-007 AC-007-3/4/5 — SVN-specific edge cases.

These acceptance criteria describe fork-policy behavior rather than
algorithmic contracts; we have no SVN binary available in tests. The
tests below assert what the library *does* enforce: SVN inputs are
accepted end-to-end, and the SVN-specific fields (integer revisionId,
branch-as-path, post-merge record) flow through validation, Algorithm C
replay, and JSON output unmodified.

AC-007-3 [Edge]  SVN merge blame is imprecise — policy: accept the
                  recorded attribution as-is; document in the user guide.
AC-007-4 [Edge]  Rebase/amend are Git-only — SVN records with any
                  revisionTimestamp progression pass through without a
                  rebase check being applied.
AC-007-5 [Edge]  SVN branch is a path like "/branches/feature-x" — it
                  is a free-form string, stored and round-tripped.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c,
)
from aggregateGenCodeDesc.cli import main as cli_main
from aggregateGenCodeDesc.core.protocol import load_record_from_dict


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _mk_svn_v2604(
    revision_id: str,
    revision_ts: str,
    *,
    repo_branch: str,
    adds: list[tuple[int, int, str, int, str]],
) -> dict:
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{
            "fileName": "app.py",
            "codeLines": [
                {
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
                }
                for (loc, gr, brev, bline, bts) in adds
            ],
        }],
        "REPOSITORY": {
            "vcsType": "svn",
            "repoURL": "svn+ssh://svn.example.com/repo",
            "repoBranch": repo_branch,
            "revisionId": revision_id,
            "revisionTimestamp": revision_ts,
        },
    }


# =============================================================================
# AC-007-3 [Edge] SVN merge blame imprecision — fork policy ACCEPT.
#
# A simulated SVN "merge" record (r10 represents a merge from a branch) carries
# blame attributions pointing at the merged-from revisions (r3, r4). The
# aggregator must accept the record and produce a metric using those blame
# values as-is; it does NOT try to verify SVN merge accuracy.
# =============================================================================
def test_ac_007_3_svn_merge_blame_accepted_as_is() -> None:
    # r10 (merge commit on trunk) adds 3 lines whose blame points back to r3
    # and r4 on a feature branch — the canonical SVN merge-blame shape.
    merge_record = _mk_svn_v2604(
        revision_id="10",
        revision_ts="2026-03-10T10:00:00Z",
        repo_branch="/trunk",
        adds=[
            (1, 100, "3", 1, "2026-03-01T10:00:00Z"),
            (2, 80, "3", 2, "2026-03-01T10:00:00Z"),
            (3, 40, "4", 1, "2026-03-02T10:00:00Z"),
        ],
    )
    rec = load_v2604_record(merge_record)
    metrics = run_algorithm_c(
        [rec],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # All three lines survive, attributed to whatever blame said (r3/r4).
    assert metrics.total_lines == 3
    # No error, no warning about merge — fork policy is to trust SVN.


# =============================================================================
# AC-007-4 [Edge] SVN history is immutable — rebase/amend checks don't apply.
#
# For SVN, later revisionId means later revisionTimestamp (monotonic by
# definition). The aggregator should not flag rebase/amend for SVN input:
# distinct, strictly increasing integer revisionIds with monotonic timestamps
# must process cleanly without any warnings about history rewriting.
# =============================================================================
def test_ac_007_4_svn_no_rebase_amend_flags() -> None:
    records = [
        load_v2604_record(_mk_svn_v2604(
            revision_id=str(i),
            revision_ts=f"2026-03-{i:02d}T10:00:00Z",
            repo_branch="/trunk",
            adds=[(1, 100, str(i), 1, f"2026-03-{i:02d}T10:00:00Z")],
        ))
        for i in range(1, 4)
    ]
    metrics = run_algorithm_c(
        records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
    )
    # 3 distinct (rev, line) keys → 3 surviving lines.
    assert metrics.total_lines == 3


# =============================================================================
# AC-007-5 [Edge] SVN branch is a path like "/branches/feature-x".
#
# The aggregator accepts slashes and path-shaped repoBranch values unchanged
# and round-trips them in REPOSITORY.repoBranch at the output.
# =============================================================================
@pytest.mark.parametrize("svn_branch", [
    "/trunk",
    "/branches/feature-x",
    "/branches/release/2026.04",
    "/tags/v1.2.3",
])
def test_ac_007_5_svn_branch_path_roundtrips(
    tmp_path: Path, svn_branch: str,
) -> None:
    gcd = tmp_path / "gcd"
    out = tmp_path / "out"
    gcd.mkdir()
    (gcd / "c.json").write_text(
        json.dumps(_mk_svn_v2604(
            revision_id="42",
            revision_ts="2026-03-01T10:00:00Z",
            repo_branch=svn_branch,
            adds=[(1, 100, "42", 1, "2026-03-01T10:00:00Z")],
        )),
        encoding="utf-8",
    )
    rc = cli_main([
        "--repo-url", "svn+ssh://svn.example.com/repo",
        "--repo-branch", svn_branch,
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "genCodeDescV26.03.json").read_text(encoding="utf-8"))
    assert payload["REPOSITORY"]["repoBranch"] == svn_branch
    assert payload["REPOSITORY"]["vcsType"] == "svn"


# Sanity: SVN integer revisionId flows through non-strict validation as well
# (CLI does not enable strict_revision_id today).
def test_ac_007_5_svn_record_loads_under_default_policy() -> None:
    data = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [],
        "REPOSITORY": {
            "vcsType": "svn",
            "repoURL": "svn+ssh://svn.example.com/repo",
            "repoBranch": "/branches/feature-x",
            "revisionId": "4217",
        },
    }
    rec = load_record_from_dict(data)
    assert rec.revision_id == "4217"
