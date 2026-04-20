"""Transport coverage — AlgA over `git://` via ``git daemon``.

Beyond the file:// transport already covered by
``test_scale_matrix_git_remote.py``, this exercises a real network
transport: spawning ``git daemon`` on a loopback port and cloning over
``git://127.0.0.1:<port>/remote.git``.

This proves AlgA works against repos reached via TCP (not just on-disk
paths). True ``https://`` would require either a TLS cert + a Git
HTTP-backend WSGI host, or an external server — both add fragility
without changing the algorithm code path beyond what ``git://`` already
demonstrates. This test deliberately stops at git:// because:

  * Git's transport selection is below the algorithm layer (libcurl /
    git-daemon vs. local fs); once the clone succeeds, AlgA runs the
    same blame code regardless.
  * git:// is the cheapest reproducible TCP transport bundled with Git
    itself — no Apache/nginx/sshd setup required.

If ``git daemon`` is not available on the running system the test skips
rather than fails.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a

from tests._git_fixture import commit_file, init_repo, rewrite_line


N_COMMITS = 30
N_FILES = 5
LINES_PER_COMMIT = 4
TIME_BUDGET_SEC = 60.0
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_name(i: int) -> str:
    return f"src/f{i % N_FILES}.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.05)
    raise RuntimeError(f"git-daemon never opened {host}:{port}: {last_exc}")


def _build_seed_and_records(repo: Path) -> list[dict]:
    init_repo(repo)
    records: list[dict] = []
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
        records.append({
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": rel, "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "git", "repoURL": "git://placeholder",
                "repoBranch": "main",
                "revisionId": sha, "revisionTimestamp": date,
            },
        })
        file_state[rel] = updated
    return records


def _have_git_daemon() -> bool:
    if not shutil.which("git"):
        return False
    # `git daemon --help` exits 0 when the subcommand exists; on stripped
    # builds it returns non-zero with "is not a git command".
    res = subprocess.run(
        ["git", "daemon", "--help"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


# ---------------------------------------------------------------------------
# AlgA over git:// via git-daemon.
# ---------------------------------------------------------------------------
def test_scale_alga_git_daemon_transport(tmp_path: Path) -> None:
    if not _have_git_daemon():
        pytest.skip("git daemon not available on this system")

    # 1. Build seed and bare remote.
    seed = tmp_path / "seed"
    records = _build_seed_and_records(seed)
    base = tmp_path / "srv"
    base.mkdir()
    bare = base / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    # Mark the bare repo as exportable via git-daemon.
    (bare / "git-daemon-export-ok").write_text("", encoding="utf-8")

    # 2. Spawn git daemon on a loopback port.
    port = _free_port()
    daemon = subprocess.Popen(
        [
            "git", "daemon",
            "--reuseaddr",
            "--listen=127.0.0.1",
            f"--port={port}",
            f"--base-path={base}",
            "--export-all",
            "--informative-errors",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_port("127.0.0.1", port)

        # 3. Clone via git:// transport.
        remote_url = f"git://127.0.0.1:{port}/remote.git"
        clone = tmp_path / "clone"
        result = subprocess.run(
            ["git", "clone", remote_url, str(clone)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            pytest.skip(
                "git:// clone failed (transport not supported here): "
                + result.stderr.decode("utf-8", errors="replace")
            )

        # 4. Stamp records with the git:// URL and run AlgA.
        recs = []
        for r in records:
            rr = dict(r)
            rr["REPOSITORY"] = {**r["REPOSITORY"], "repoURL": remote_url}
            recs.append(rr)

        t0 = time.monotonic()
        out = run_algorithm_a(
            clone, recs, start_time=START, end_time=END, threshold=60,
        )
        elapsed = time.monotonic() - t0

        assert out.metrics.total_lines == N_COMMITS * LINES_PER_COMMIT
        assert out.metrics.fully_ai_value == pytest.approx(1.0)
        assert elapsed < TIME_BUDGET_SEC, (
            f"AlgA over git:// took {elapsed:.1f}s (budget {TIME_BUDGET_SEC}s)"
        )
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=3)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=3)
        # Close stderr pipe to avoid ResourceWarning.
        if daemon.stderr is not None:
            daemon.stderr.close()
