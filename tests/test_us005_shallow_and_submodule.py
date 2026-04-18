"""US-005 AC-005-4 and AC-005-5 — repository-boundary edge cases.

AC-005-4 [Edge] Shallow clone limits AlgA blame accuracy.
AC-005-5 [Edge] Git submodule lines are not included in parent's metric.

Both are real end-to-end tests using throw-away git repos in tmp_path.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.core.git import list_tracked_files
from aggregateGenCodeDesc.core.protocol import OnMissing

from tests._git_fixture import commit_file, init_repo, git


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


# =============================================================================
# AC-005-4 [Edge] Shallow clone — lines past the boundary are attributed to the
# boundary commit (git's documented behavior), not to their true origin.
# The fork policy: surface this via normal blame output; no special error.
# =============================================================================
def test_ac_005_4_shallow_clone_blame_hits_boundary(tmp_path: Path) -> None:
    # Build an origin repo with 5 commits, then shallow-clone --depth=2.
    origin = tmp_path / "origin"
    init_repo(origin)
    shas: list[str] = []
    for i in range(1, 6):
        content = "".join(f"line{j}\n" for j in range(1, i + 1))
        shas.append(commit_file(
            origin, "app.py", content,
            message=f"c{i}",
            date=f"2026-02-{i:02d}T10:00:00Z",
        ))

    # Shallow clone depth=2 → only the last 2 commits are reachable.
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "2", "--no-local",
         f"file://{origin}", str(shallow)],
        check=True, capture_output=True,
    )

    # The earliest reachable commit in the shallow clone is the "boundary".
    reachable = git(shallow, "rev-list", "HEAD").strip().splitlines()
    assert len(reachable) == 2, f"depth=2 should expose 2 commits, got {reachable}"
    boundary_sha = reachable[-1]

    # line1 was originally added in shas[0] (c1). In the full repo blame
    # would attribute it to shas[0]; in the shallow clone git MUST stop at
    # the boundary commit — the boundary SHA appears as the origin.
    # We only supply records for the boundary and newer commits (beyond
    # the boundary is unknowable to the consumer of the shallow clone).
    records = []
    for sha in reachable:
        records.append(_rec(sha, "app.py", [
            {"lineLocation": i, "genRatio": 100, "genMethod": "vibeCoding"}
            for i in range(1, 6)  # pad to 5; blame will filter
        ]))

    result = run_algorithm_a(
        shallow,
        records,
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
        on_missing=OnMissing.ZERO,
    )

    # No crash, metric produced. All origin revisions reported by blame
    # must be among the reachable set — nothing beyond the shallow
    # boundary leaked through.
    origins_seen = {s.origin_revision for s in result.surviving}
    assert origins_seen.issubset(set(reachable)), (
        f"blame reported origins beyond shallow boundary: "
        f"{origins_seen - set(reachable)}"
    )
    # The boundary SHA carries the pre-boundary lines (AC-005-4 contract).
    assert boundary_sha in origins_seen


# =============================================================================
# AC-005-5 [Edge] Submodule lines are NOT included in the parent's metric.
# `list_tracked_files` from the parent repo must not surface files that live
# inside a submodule; `git blame` on such paths would be impossible anyway.
# =============================================================================
def test_ac_005_5_submodule_files_not_in_parent_scope(tmp_path: Path) -> None:
    # Build the submodule (an independent git repo).
    sub = tmp_path / "submod"
    init_repo(sub)
    commit_file(
        sub, "crypto.py", "secret=1\n",
        message="sub-c1", date="2026-02-01T10:00:00Z",
    )

    # Build the parent.
    parent = tmp_path / "parent"
    init_repo(parent)
    commit_file(
        parent, "app.py", "x=1\n",
        message="parent-c1", date="2026-02-02T10:00:00Z",
    )

    # Add submodule. `git submodule add` requires protocol.file.allow=always
    # on modern git versions because we're adding a local path.
    result = subprocess.run(
        ["git", "-c", "protocol.file.allow=always",
         "submodule", "add", f"file://{sub}", "libs/crypto"],
        cwd=parent, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"git submodule add unavailable on this host: {result.stderr}")

    git(parent, "commit", "-q", "-m", "add submodule",
        env={"GIT_AUTHOR_DATE": "2026-02-03T10:00:00Z",
             "GIT_COMMITTER_DATE": "2026-02-03T10:00:00Z"})

    # AC-005-5 contract: list_tracked_files on the parent should NOT
    # enumerate any files that live inside libs/crypto. `git ls-tree`
    # treats a submodule as a single gitlink (mode 160000) so the
    # submodule's internal files never appear — confirm that.
    tracked = list_tracked_files(parent, "HEAD")
    for f in tracked:
        assert not f.startswith("libs/crypto/"), (
            f"parent scope leaked submodule file: {f}"
        )
    # The submodule pointer itself may appear as 'libs/crypto' (the gitlink);
    # that is acceptable because `git blame` refuses to blame a gitlink,
    # and the AlgA loop skips files with no blame output. We verify by
    # running AlgA with an empty record set — must not crash on the gitlink.
    result = run_algorithm_a(
        parent,
        records=[_rec("dummy", "app.py", [
            {"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}
        ])],
        start_time=_utc("2026-01-01T00:00:00Z"),
        end_time=_utc("2026-12-31T00:00:00Z"),
        threshold=60,
        on_missing=OnMissing.ZERO,
    )
    # All surviving lines must belong to parent files, never submodule files.
    for s in result.surviving:
        assert not s.current_file.startswith("libs/crypto/"), (
            f"AlgA surfaced submodule-internal file: {s.current_file}"
        )
