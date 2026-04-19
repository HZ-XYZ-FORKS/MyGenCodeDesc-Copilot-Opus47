"""Scale matrix — svn-local × AlgA, AlgB, and AlgC.

Creates a real SVN repository with `svnadmin create` and uses `file://`
as the repo URL. AlgA runs against the SVN working copy using the
svn-blame backend. AlgB replays unified-diff patches; AlgC uses
embedded blame (protocol 26.04) and does not touch the repo.

Dimensions are kept moderate so the full matrix runs in seconds locally.
If `svn`/`svnadmin` are not installed, tests skip cleanly.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a_svn import run_algorithm_a_svn
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c_full,
)
from aggregateGenCodeDesc.cli import main as cli_main


pytestmark = pytest.mark.skipif(
    shutil.which("svnadmin") is None or shutil.which("svn") is None,
    reason="svn/svnadmin not installed",
)


N_COMMITS = 20
N_FILES = 5
LINES_PER_COMMIT = 5
TIME_BUDGET_SEC = 90.0
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _svn(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["svn", *args], cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout


def _svnadmin(*args: str) -> None:
    subprocess.run(
        ["svnadmin", *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _make_svn_repo(tmp_path: Path) -> tuple[str, Path]:
    """Create an SVN repo under tmp_path/svnrepo, check out working copy.

    Returns (file_url, working_copy_path).
    """
    repo_root = tmp_path / "svnrepo"
    _svnadmin("create", str(repo_root))
    file_url = f"file://{repo_root}"
    wc = tmp_path / "wc"
    _svn(tmp_path, "checkout", "-q", file_url, str(wc))
    return file_url, wc


def _build_svn_and_records(tmp_path: Path) -> tuple[str, Path, list[dict], list[str], dict[str, str]]:
    """Build a real svn working copy with N_COMMITS commits.

    Returns (file_url, wc_path, records_v2603, revisions, patches_by_rev).
    """
    file_url, wc = _make_svn_repo(tmp_path)

    records: list[dict] = []
    revisions: list[str] = []
    patches: dict[str, str] = {}
    file_state: dict[str, list[str]] = {}

    for i in range(N_COMMITS):
        rel = _file_name(i)
        new_lines = [f"line_{i}_{j}" for j in range(LINES_PER_COMMIT)]
        existing = file_state.get(rel, [])
        updated = existing + new_lines
        new_content = "".join(x + "\n" for x in updated)

        full_path = wc / rel
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(new_content, encoding="utf-8")

        is_new_file = rel not in file_state
        if is_new_file:
            # `svn add --parents` creates intermediate dirs and schedules add.
            _svn(wc, "add", "--parents", rel)

        commit_out = _svn(wc, "commit", "-m", f"c{i}", "--username", "t")
        # Parse "Committed revision N." from commit output.
        rev = ""
        for line in commit_out.splitlines():
            line = line.strip()
            if line.startswith("Committed revision") and line.endswith("."):
                rev = line.split()[-1].rstrip(".")
                break
        assert rev, f"could not parse svn commit output: {commit_out!r}"
        date = _iso(START + timedelta(minutes=i))

        # Build unified diff patch matching the change.
        from_line = len(existing) + 1
        to_line = len(existing) + LINES_PER_COMMIT
        if len(existing) == 0:
            header = (
                f"diff --git a/{rel} b/{rel}\n"
                "--- /dev/null\n"
                f"+++ b/{rel}\n"
                f"@@ -0,0 +1,{len(updated)} @@\n"
            )
            body = "".join("+" + line + "\n" for line in updated)
        else:
            header = (
                f"diff --git a/{rel} b/{rel}\n"
                f"--- a/{rel}\n"
                f"+++ b/{rel}\n"
                f"@@ -1,{len(existing)} +1,{len(updated)} @@\n"
            )
            body = "".join(" " + line + "\n" for line in existing) + \
                   "".join("+" + line + "\n" for line in new_lines)
        patches[rev] = header + body

        rec = {
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": rel, "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "svn", "repoURL": file_url,
                "repoBranch": "/trunk",
                "revisionId": rev, "revisionTimestamp": date,
            },
        }
        records.append(rec)
        revisions.append(rev)
        file_state[rel] = updated

    return file_url, wc, records, revisions, patches


def _expected_total_lines() -> int:
    return N_COMMITS * LINES_PER_COMMIT


# ---------------------------------------------------------------------------
# AlgA × svn-local (svn-blame backend).
# ---------------------------------------------------------------------------
def test_scale_alga_svn_local(tmp_path: Path) -> None:
    _, wc, records, _, _ = _build_svn_and_records(tmp_path)

    t0 = time.monotonic()
    result = run_algorithm_a_svn(
        wc, records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgA svn scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s)"
    )


# ---------------------------------------------------------------------------
# AlgB × svn-local (patch replay — vcs-agnostic)
# ---------------------------------------------------------------------------
def test_scale_algb_svn_local(tmp_path: Path) -> None:
    _, _wc, records, revisions, patches = _build_svn_and_records(tmp_path)
    commits = [build_commit(rec, patches[rev]) for rec, rev in zip(records, revisions)]

    t0 = time.monotonic()
    result = run_algorithm_b(
        commits, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgB svn scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s)"
    )


# ---------------------------------------------------------------------------
# AlgC × svn-local (embedded blame)
# ---------------------------------------------------------------------------
def test_scale_algc_svn_local(tmp_path: Path) -> None:
    _, _wc, records, revisions,_ = _build_svn_and_records(tmp_path)

    v2604_records = []
    for rec, rev in zip(records, revisions):
        detail_in = rec["DETAIL"][0]
        fn = detail_in["fileName"]
        ts = rec["REPOSITORY"]["revisionTimestamp"]
        lr = detail_in["codeLines"][0]["lineRange"]
        code_lines = []
        for lineno in range(lr["from"], lr["to"] + 1):
            code_lines.append({
                "changeType": "add",
                "lineLocation": lineno,
                "genRatio": 100,
                "genMethod": "vibeCoding",
                "blame": {
                    "revisionId": rev,
                    "originalFilePath": fn,
                    "originalLine": lineno,
                    "timestamp": ts,
                },
            })
        v2604_records.append(load_v2604_record({
            "protocolVersion": "26.04",
            "SUMMARY": {},
            "DETAIL": [{"fileName": fn, "codeLines": code_lines}],
            "REPOSITORY": {
                **rec["REPOSITORY"],
                "revisionId": rev,
            },
        }))

    t0 = time.monotonic()
    result = run_algorithm_c_full(
        v2604_records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC, (
        f"AlgC svn scale took {elapsed:.2f}s (budget {TIME_BUDGET_SEC}s)"
    )
