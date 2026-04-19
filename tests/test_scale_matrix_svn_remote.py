"""Scale matrix — svn-remote × AlgA, AlgB, and AlgC via `svnserve` over `svn://`.

Spins up a local `svnserve -d --foreground --listen-port <p>` process
against a temporary repo, checks out via `svn://127.0.0.1:<p>/` (real
network transport), commits N times, then validates AlgA, AlgB and AlgC.
"""

from __future__ import annotations

import os
import shutil
import socket
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


pytestmark = pytest.mark.skipif(
    shutil.which("svnadmin") is None
    or shutil.which("svn") is None
    or shutil.which("svnserve") is None,
    reason="svn/svnadmin/svnserve not installed",
)


N_COMMITS = 15
N_FILES = 4
LINES_PER_COMMIT = 5
TIME_BUDGET_SEC = 90.0
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


def _configure_repo_for_anon_write(repo_root: Path) -> None:
    # Allow anonymous read/write so svnserve accepts commits without auth.
    conf = repo_root / "conf" / "svnserve.conf"
    conf.write_text(
        "[general]\n"
        "anon-access = write\n"
        "auth-access = write\n",
        encoding="utf-8",
    )


@pytest.fixture
def svnserve_remote(tmp_path: Path):
    repo_root = tmp_path / "svnrepo"
    _svnadmin("create", str(repo_root))
    _configure_repo_for_anon_write(repo_root)

    port = _find_free_port()
    proc = subprocess.Popen(
        [
            "svnserve", "-d", "--foreground",
            "--listen-host", "127.0.0.1",
            "--listen-port", str(port),
            "-r", str(repo_root),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait until port is accepting connections.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        proc.terminate()
        pytest.fail("svnserve did not start in time")

    url = f"svn://127.0.0.1:{port}"
    try:
        yield url, repo_root
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def _build_remote_svn_and_records(
    tmp_path: Path, url: str,
) -> tuple[Path, list[dict], list[str], dict[str, str]]:
    wc = tmp_path / "wc"
    _svn(tmp_path, "checkout", "-q", url, str(wc))

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
            _svn(wc, "add", "--parents", rel)

        commit_out = _svn(
            wc, "commit", "-m", f"c{i}", "--username", "t",
            "--non-interactive",
        )
        rev = ""
        for line in commit_out.splitlines():
            line = line.strip()
            if line.startswith("Committed revision") and line.endswith("."):
                rev = line.split()[-1].rstrip(".")
                break
        assert rev, f"could not parse svn commit output: {commit_out!r}"

        date = _iso(START + timedelta(minutes=i))
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
                "vcsType": "svn", "repoURL": url,
                "repoBranch": "/trunk",
                "revisionId": rev, "revisionTimestamp": date,
            },
        }
        records.append(rec)
        revisions.append(rev)
        file_state[rel] = updated

    return wc, records, revisions, patches


def _expected_total_lines() -> int:
    return N_COMMITS * LINES_PER_COMMIT


# ---------------------------------------------------------------------------
# AlgA × svn-remote
# ---------------------------------------------------------------------------
def test_scale_alga_svn_remote(tmp_path: Path, svnserve_remote) -> None:
    url, _ = svnserve_remote
    wc, records, _, _ = _build_remote_svn_and_records(tmp_path, url)

    t0 = time.monotonic()
    result = run_algorithm_a_svn(
        wc, records, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC


# ---------------------------------------------------------------------------
# AlgB × svn-remote
# ---------------------------------------------------------------------------
def test_scale_algb_svn_remote(tmp_path: Path, svnserve_remote) -> None:
    url, _ = svnserve_remote
    _wc, records, revisions, patches = _build_remote_svn_and_records(tmp_path, url)
    commits = [build_commit(rec, patches[rev]) for rec, rev in zip(records, revisions)]

    t0 = time.monotonic()
    result = run_algorithm_b(
        commits, start_time=START, end_time=END, threshold=60,
    )
    elapsed = time.monotonic() - t0

    assert result.metrics.total_lines == _expected_total_lines()
    assert result.metrics.fully_ai_value == pytest.approx(1.0)
    assert elapsed < TIME_BUDGET_SEC


# ---------------------------------------------------------------------------
# AlgC × svn-remote
# ---------------------------------------------------------------------------
def test_scale_algc_svn_remote(tmp_path: Path, svnserve_remote) -> None:
    url, _ = svnserve_remote
    _wc, records, revisions, _ = _build_remote_svn_and_records(tmp_path, url)

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
    assert elapsed < TIME_BUDGET_SEC
