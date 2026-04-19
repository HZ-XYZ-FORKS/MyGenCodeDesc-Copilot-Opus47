"""Scale matrix — git-remote × AlgA/B/C using a bare file:// remote.

Uses a bare git repo as the "remote" (`file:///.../remote.git`) and
clones to a working copy. AlgA blames against the cloned working copy;
AlgB and AlgC are repo-agnostic so the remote URL is just metadata.

`file://` is used because it is the cheapest reproducible "remote"
transport git supports (no sshd/git-daemon required). It exercises the
same clone + fetch + checkout code paths that a real remote uses.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_b import build_commit, run_algorithm_b
from aggregateGenCodeDesc.algorithms.alg_c import (
    load_v2604_record,
    run_algorithm_c_full,
)

from tests._git_fixture import commit_file, init_repo, git, rewrite_line


N_COMMITS = 60
N_FILES = 8
LINES_PER_COMMIT = 5
TIME_BUDGET_SEC = 60.0
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _build_seed_and_records(repo: Path) -> tuple[list[dict], list[str], dict[str, str]]:
    init_repo(repo)
    records: list[dict] = []
    shas: list[str] = []
    patches: dict[str, str] = {}
    file_state: dict[str, list[str]] = {}

    for i in range(N_COMMITS):
        rel = _file_name(i)
        new_lines = [f"line_{i}_{j}" for j in range(LINES_PER_COMMIT)]
        existing = file_state.get(rel, [])
        updated = existing + new_lines
        new_content = "".join(x + "\n" for x in updated)
        date = _iso(START + timedelta(minutes=i))
        if rel not in file_state:
            sha = commit_file(repo, rel, new_content, message=f"c{i}", date=date)
        else:
            sha = rewrite_line(repo, rel, new_content, message=f"c{i}", date=date)

        from_line = len(existing) + 1
        to_line = len(existing) + LINES_PER_COMMIT
        rec = {
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": rel, "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "git", "repoURL": "file:///placeholder",
                "repoBranch": "main",
                "revisionId": sha, "revisionTimestamp": date,
            },
        }
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
        records.append(rec)
        shas.append(sha)
        patches[sha] = header + body
        file_state[rel] = updated

    return records, shas, patches


def _make_bare_and_clone(tmp_path: Path) -> tuple[Path, str, Path]:
    """Build a seed repo, push to a bare `remote.git`, then clone from file://.

    Returns (clone_path, remote_url, seed_repo).
    """
    seed = tmp_path / "seed"
    records_and_shas = _build_seed_and_records(seed)  # noqa: F841
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    remote_url = f"file://{bare}"
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", remote_url, str(clone)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return clone, remote_url, seed


def _records_with_url(records: list[dict], url: str) -> list[dict]:
    out = []
    for r in records:
        rr = dict(r)
        rr["REPOSITORY"] = {**r["REPOSITORY"], "repoURL": url}
        out.append(rr)
    return out


def _expected_total_lines() -> int:
    return N_COMMITS * LINES_PER_COMMIT


# ---------------------------------------------------------------------------
# AlgA × git-remote: blame runs against a clone of a file:// bare remote.
# ---------------------------------------------------------------------------
def test_scale_alga_git_remote(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    records, _, _ = _build_seed_and_records(seed)
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    remote_url = f"file://{bare}"
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", remote_url, str(clone)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    recs = _records_with_url(records, remote_url)

    t0 = time.monotonic()
    result = run_algorithm_a(
        clone, recs, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC


# ---------------------------------------------------------------------------
# AlgB × git-remote (repo-agnostic; only URL metadata differs).
# ---------------------------------------------------------------------------
def test_scale_algb_git_remote(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    records, shas, patches = _build_seed_and_records(seed)
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    remote_url = f"file://{bare}"
    recs = _records_with_url(records, remote_url)
    commits = [build_commit(rec, patches[sha]) for rec, sha in zip(recs, shas)]

    t0 = time.monotonic()
    result = run_algorithm_b(
        commits, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC


# ---------------------------------------------------------------------------
# AlgC × git-remote (embedded blame; URL is just metadata).
# ---------------------------------------------------------------------------
def test_scale_algc_git_remote(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    records, shas, _ = _build_seed_and_records(seed)
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    remote_url = f"file://{bare}"

    v2604_records = []
    for rec, sha in zip(records, shas):
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
                    "revisionId": sha,
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
                **rec["REPOSITORY"], "repoURL": remote_url,
                "revisionId": sha,
            },
        }))

    t0 = time.monotonic()
    result = run_algorithm_c_full(
        v2604_records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC
