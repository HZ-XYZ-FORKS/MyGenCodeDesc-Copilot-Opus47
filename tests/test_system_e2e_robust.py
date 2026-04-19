"""System-level end-to-end tests for production-readiness confidence.

These tests exercise full CLI flows with realistic commit history and
policy switches, not just isolated algorithm units.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main as cli_main

from tests._git_fixture import git, init_repo, commit_file, rewrite_line, rename_file


def _write_json(path: Path, payload: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload), encoding="utf-8")


def _rec_v2603(
    rev: str,
    ts: str,
    file_name: str,
    code_lines: list[dict],
    *,
    repo_url: str = "https://demo/r",
    repo_branch: str = "main",
) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": file_name, "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": repo_url,
            "repoBranch": repo_branch,
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _mk_add(file_name: str, loc: int, gr: int, rev: str, orig_line: int, ts: str) -> dict:
    return {
        "changeType": "add",
        "lineLocation": loc,
        "genRatio": gr,
        "genMethod": "vibeCoding" if gr > 0 else "Manual",
        "blame": {
            "revisionId": rev,
            "originalFilePath": file_name,
            "originalLine": orig_line,
            "timestamp": ts,
        },
    }


def _mk_del(rev: str, file_name: str, orig_line: int) -> dict:
    return {
        "changeType": "delete",
        "blame": {
            "revisionId": rev,
            "originalFilePath": file_name,
            "originalLine": orig_line,
        },
    }


def _rec_v2604(
    rev: str,
    ts: str,
    detail: list[dict],
    *,
    repo_url: str = "https://demo/r",
    repo_branch: str = "main",
) -> dict:
    add_count = 0
    for block in detail:
        for line in block.get("codeLines", []):
            if line.get("changeType") == "add":
                add_count += 1
    return {
        "protocolVersion": "26.04",
        "SUMMARY": {"lineCount": add_count},
        "DETAIL": detail,
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": repo_url,
            "repoBranch": repo_branch,
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def _metrics(path: Path) -> tuple[float, float, float, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    m = data["AGGREGATE"]["metrics"]
    return (
        float(m["weighted"]["value"]),
        float(m["fullyAI"]["value"]),
        float(m["mostlyAI"]["value"]),
        int(data["SUMMARY"]["totalCodeLines"]),
    )


def test_system_rich_git_history_cli_a_b_c_consistency(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)

    c1 = commit_file(
        repo, "src/app.py", "a1\na2\na3\na4\n",
        message="c1 add app", date="2026-02-01T10:00:00Z",
    )
    c2 = rewrite_line(
        repo, "src/app.py", "a1\na2_human\na3\na4\n",
        message="c2 modify line2", date="2026-02-02T10:00:00Z",
    )
    c3 = commit_file(
        repo, "util.py", "u1\nu2\nu3\n",
        message="c3 add util", date="2026-02-03T10:00:00Z",
    )
    c4 = rename_file(
        repo, "src/app.py", "src/main.py",
        message="c4 rename app->main", date="2026-02-04T10:00:00Z",
    )
    c5 = rewrite_line(
        repo, "util.py", "u1\nu3\n",
        message="c5 delete util line2", date="2026-02-05T10:00:00Z",
    )

    repo_url = "https://demo/r"
    branch = "main"
    start = "2026-01-01T00:00:00Z"
    end = "2026-12-31T00:00:00Z"

    gcd_b = tmp_path / "gcd_v2603"
    gcd_c = tmp_path / "gcd_v2604"
    patch_dir = tmp_path / "patches"
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_c = tmp_path / "out_c"

    # v26.03 records for AlgA/B lookup.
    _write_json(gcd_b / "01-c1.json", _rec_v2603(
        c1, "2026-02-01T10:00:00Z", "src/app.py",
        [{"lineRange": {"from": 1, "to": 4}, "genRatio": 100, "genMethod": "vibeCoding"}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_b / "02-c2.json", _rec_v2603(
        c2, "2026-02-02T10:00:00Z", "src/app.py",
        [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_b / "03-c3.json", _rec_v2603(
        c3, "2026-02-03T10:00:00Z", "util.py",
        [{"lineRange": {"from": 1, "to": 3}, "genRatio": 80, "genMethod": "vibeCoding"}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_b / "04-c4.json", _rec_v2603(
        c4, "2026-02-04T10:00:00Z", "src/main.py", [],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_b / "05-c5.json", _rec_v2603(
        c5, "2026-02-05T10:00:00Z", "util.py", [],
        repo_url=repo_url, repo_branch=branch,
    ))

    # v26.04 records for AlgC replay.
    _write_json(gcd_c / "01-c1.json", _rec_v2604(
        c1, "2026-02-01T10:00:00Z",
        [{"fileName": "src/app.py", "codeLines": [
            _mk_add("src/app.py", 1, 100, c1, 1, "2026-02-01T10:00:00Z"),
            _mk_add("src/app.py", 2, 100, c1, 2, "2026-02-01T10:00:00Z"),
            _mk_add("src/app.py", 3, 100, c1, 3, "2026-02-01T10:00:00Z"),
            _mk_add("src/app.py", 4, 100, c1, 4, "2026-02-01T10:00:00Z"),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_c / "02-c2.json", _rec_v2604(
        c2, "2026-02-02T10:00:00Z",
        [{"fileName": "src/app.py", "codeLines": [
            _mk_del(c1, "src/app.py", 2),
            _mk_add("src/app.py", 2, 0, c2, 2, "2026-02-02T10:00:00Z"),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_c / "03-c3.json", _rec_v2604(
        c3, "2026-02-03T10:00:00Z",
        [{"fileName": "util.py", "codeLines": [
            _mk_add("util.py", 1, 80, c3, 1, "2026-02-03T10:00:00Z"),
            _mk_add("util.py", 2, 80, c3, 2, "2026-02-03T10:00:00Z"),
            _mk_add("util.py", 3, 80, c3, 3, "2026-02-03T10:00:00Z"),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_c / "04-c4.json", _rec_v2604(
        c4, "2026-02-04T10:00:00Z", [],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd_c / "05-c5.json", _rec_v2604(
        c5, "2026-02-05T10:00:00Z",
        [{"fileName": "util.py", "codeLines": [
            _mk_del(c3, "util.py", 2),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))

    # Per-commit patches for AlgB.
    patch_dir.mkdir(parents=True, exist_ok=True)
    for rev in (c1, c2, c3, c4, c5):
        patch = git(repo, "show", "--format=", "--patch", rev)
        (patch_dir / f"{rev}.patch").write_text(patch, encoding="utf-8")

    rc_a = cli_main([
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", start,
        "--end-time", end,
        "--threshold", "60",
        "--algorithm", "A",
        "--gen-code-desc-dir", str(gcd_b),
        "--repo-path", str(repo),
        "--output-dir", str(out_a),
    ])
    assert rc_a == 0

    rc_b = cli_main([
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", start,
        "--end-time", end,
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd_b),
        "--commit-patch-dir", str(patch_dir),
        "--output-dir", str(out_b),
    ])
    assert rc_b == 0

    rc_c = cli_main([
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", start,
        "--end-time", end,
        "--threshold", "60",
        "--algorithm", "C",
        "--gen-code-desc-dir", str(gcd_c),
        "--output-dir", str(out_c),
    ])
    assert rc_c == 0

    for out in (out_a, out_b, out_c):
        assert (out / "genCodeDescV26.03.json").exists()
        assert (out / "commitStart2EndTime.patch").exists()

    m_a = _metrics(out_a / "genCodeDescV26.03.json")
    m_b = _metrics(out_b / "genCodeDescV26.03.json")
    m_c = _metrics(out_c / "genCodeDescV26.03.json")

    assert m_a == pytest.approx(m_b, abs=1e-9)
    assert m_b == pytest.approx(m_c, abs=1e-9)

    # Stable expected metrics for this history.
    assert m_a[3] == 6
    # JSON output rounds ratio values to 6 decimals.
    assert m_a[0] == pytest.approx(4.6 / 6, abs=1e-6)
    assert m_a[1] == pytest.approx(3 / 6, abs=1e-6)
    assert m_a[2] == pytest.approx(5 / 6, abs=1e-6)


def test_system_cli_algc_clock_skew_abort_vs_ignore(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    out_abort = tmp_path / "out_abort"
    out_ignore = tmp_path / "out_ignore"

    repo_url = "https://demo/r"
    branch = "main"

    # Intentionally ordered later file first by name to trigger input-order skew.
    _write_json(gcd / "01-later.json", _rec_v2604(
        "c2", "2026-03-02T10:00:00Z",
        [{"fileName": "app.py", "codeLines": [
            _mk_add("app.py", 1, 80, "c2", 1, "2026-03-02T10:00:00Z"),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(gcd / "02-earlier.json", _rec_v2604(
        "c1", "2026-03-01T10:00:00Z",
        [{"fileName": "app.py", "codeLines": [
            _mk_add("app.py", 1, 100, "c1", 1, "2026-03-01T10:00:00Z"),
        ]}],
        repo_url=repo_url, repo_branch=branch,
    ))

    rc_abort = cli_main([
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--on-clock-skew", "abort",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out_abort),
    ])
    assert rc_abort == 2

    rc_ignore = cli_main([
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "C",
        "--on-clock-skew", "ignore",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(out_ignore),
    ])
    assert rc_ignore == 0
    assert (out_ignore / "genCodeDescV26.03.json").exists()


def test_system_cli_algb_on_missing_policy_matrix(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    patches = tmp_path / "patches"
    repo_url = "https://demo/r"
    branch = "main"

    _write_json(gcd / "c1.json", _rec_v2603(
        "c1", "2026-03-01T10:00:00Z", "src/a.py",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}],
        repo_url=repo_url, repo_branch=branch,
    ))
    _write_json(patches / "c1.patch", (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n"
        "+b\n"
    ))

    out_zero = tmp_path / "out_zero"
    out_skip = tmp_path / "out_skip"
    out_abort = tmp_path / "out_abort"

    base = [
        "--repo-url", repo_url,
        "--repo-branch", branch,
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd),
        "--commit-patch-dir", str(patches),
    ]

    rc_zero = cli_main(base + ["--on-missing", "zero", "--output-dir", str(out_zero)])
    rc_skip = cli_main(base + ["--on-missing", "skip", "--output-dir", str(out_skip)])
    rc_abort = cli_main(base + ["--on-missing", "abort", "--output-dir", str(out_abort)])

    assert rc_zero == 0
    assert rc_skip == 0
    assert rc_abort == 2

    mz = _metrics(out_zero / "genCodeDescV26.03.json")
    ms = _metrics(out_skip / "genCodeDescV26.03.json")

    # ZERO: two lines counted (one unattributed 0) -> fullyAI 0.5.
    assert mz[3] == 2
    assert mz[1] == pytest.approx(0.5)

    # SKIP: unattributed line dropped -> only one line remains.
    assert ms[3] == 1
    assert ms[1] == pytest.approx(1.0)
