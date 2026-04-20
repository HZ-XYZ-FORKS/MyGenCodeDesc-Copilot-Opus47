"""US-010 AC-010-2 — per-algorithm DEBUG detail for line-origin decisions.

AC-010-2 requires DEBUG to expose "line-origin resolution decisions
(blame result / diff replay step / add-delete operation)". AlgC already
logs per-file adds/deletes counts at DEBUG (see test_us010_logging_detail),
but AlgA (blame) and AlgB (diff replay) previously emitted no DEBUG detail
for their resolution steps. These tests pin the contract.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b

from tests._git_fixture import commit_file, init_repo


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _rec_a(rev: str, file_name: str, lines: list[dict]) -> dict:
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


# =============================================================================
# AC-010-2 [Typical] AlgA DEBUG surfaces per-line blame resolution decisions:
# origin revisionId, origin file, origin line, and whether a genCodeDesc entry
# was matched.
# =============================================================================
def test_ac_010_2_alg_a_debug_logs_blame_decisions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha = commit_file(
        repo, "auth.py", "x\ny\n",
        message="c1", date="2026-02-05T10:00:00Z",
    )
    records = [
        _rec_a(sha, "auth.py", [
            {"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"},
            {"lineLocation": 2, "genRatio": 50, "genMethod": "vibeCoding"},
        ]),
    ]

    with caplog.at_level("DEBUG", logger="aggregateGenCodeDesc"):
        run_algorithm_a(repo, records, **_WINDOW)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    combined = " | ".join(debug_msgs)

    # Per-line blame decisions must name origin revisionId, origin file, and line.
    assert any(
        "BLAME" in m and sha[:7] in m and "auth.py" in m and "line=1" in m
        for m in debug_msgs
    ), combined
    assert any(
        "BLAME" in m and "line=2" in m for m in debug_msgs
    ), combined


# =============================================================================
# AC-010-2 [Typical] AlgB DEBUG surfaces diff-replay per-commit decisions:
# which commit is being replayed and how many (add, delete) ops it contributes.
# =============================================================================
def test_ac_010_2_alg_b_debug_logs_replay_steps(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _rec_b(rev: str, ts: str, lines: list[dict]) -> dict:
        return {
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": "utils.py", "codeLines": lines}],
            "REPOSITORY": {
                "vcsType": "git",
                "repoURL": "https://x/r",
                "repoBranch": "main",
                "revisionId": rev,
                "revisionTimestamp": ts,
            },
        }

    rec1 = _rec_b("b1", "2026-02-01T10:00:00Z", [
        {"lineRange": {"from": 1, "to": 2}, "genRatio": 80, "genMethod": "vibeCoding"},
    ])
    p1 = (
        "diff --git a/utils.py b/utils.py\n"
        "--- /dev/null\n"
        "+++ b/utils.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n+b\n"
    )
    rec2 = _rec_b("b2", "2026-02-02T10:00:00Z", [
        {"lineLocation": 1, "genRatio": 40, "genMethod": "vibeCoding"},
    ])
    p2 = (
        "diff --git a/utils.py b/utils.py\n"
        "--- a/utils.py\n"
        "+++ b/utils.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+a2\n"
        " b\n"
    )

    commits = [build_commit(rec1, p1), build_commit(rec2, p2)]

    with caplog.at_level("DEBUG", logger="aggregateGenCodeDesc"):
        run_algorithm_b(commits, **_WINDOW)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    combined = " | ".join(debug_msgs)

    # Per-commit replay decisions must name revisionId and op counts.
    assert any(
        "REPLAY" in m and "revisionId=b1" in m and "adds=2" in m
        for m in debug_msgs
    ), combined
    assert any(
        "REPLAY" in m and "revisionId=b2" in m and "adds=1" in m and "deletes=1" in m
        for m in debug_msgs
    ), combined
