"""Milestone test: Algorithm A end-to-end through the CLI.

AC-Milestone-AlgA:
  GIVEN a tiny git repo with two commits (one pre-window, one in-window)
        and --gen-code-desc-dir of v26.03 records keyed by actual SHAs,
  WHEN  `aggregateGenCodeDesc --algorithm A --repo-path <repo> ...` runs,
  THEN  it writes genCodeDescV26.03.json + commitStart2EndTime.patch and exit 0,
        and only in-window lines are counted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main

from tests._git_fixture import commit_file, init_repo, rewrite_line


def _rec_file(dir_path: Path, name: str, rev: str, file_name: str, lines: list[dict]) -> None:
    (dir_path / name).write_text(
        json.dumps({
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
        }),
        encoding="utf-8",
    )


def test_milestone_alga_cli_end_to_end(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    sha_pre = commit_file(
        repo, "src/a.py", "a\nb\n",
        message="c0: seed pre-window", date="2025-12-01T10:00:00Z",
    )
    sha_in = rewrite_line(
        repo, "src/a.py", "a\nb\nc\n",
        message="c1: add line in-window", date="2026-02-10T10:00:00Z",
    )

    gcd = tmp_path / "gcd"
    gcd.mkdir()
    _rec_file(gcd, "c0.json", sha_pre, "src/a.py",
              [{"lineRange": {"from": 1, "to": 2}, "genRatio": 0, "genMethod": "Manual"}])
    _rec_file(gcd, "c1.json", sha_in, "src/a.py",
              [{"lineLocation": 3, "genRatio": 100, "genMethod": "vibeCoding"}])

    out = tmp_path / "out"
    rc = main([
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "A",
        "--gen-code-desc-dir", str(gcd),
        "--repo-path", str(repo),
        "--output-dir", str(out),
    ])
    assert rc == 0

    payload = json.loads((out / "genCodeDescV26.03.json").read_text())
    assert payload["SUMMARY"]["totalCodeLines"] == 1
    assert payload["AGGREGATE"]["metrics"]["fullyAI"]["value"] == pytest.approx(1.0)
    assert payload["AGGREGATE"]["parameters"]["algorithm"] == "A"

    assert (out / "commitStart2EndTime.patch").exists()


def test_milestone_alga_rejects_non_git_repo_path(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    _rec_file(gcd, "c1.json", "a" * 40, "src/a.py",
              [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}])

    rc = main([
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "A",
        "--gen-code-desc-dir", str(gcd),
        "--repo-path", str(plain),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 2
