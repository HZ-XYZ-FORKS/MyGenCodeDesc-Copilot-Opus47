"""Milestone test: Algorithm B end-to-end through the CLI.

AC-Milestone-AlgB:
  GIVEN a --gen-code-desc-dir of v26.03 records (each with REPOSITORY.revisionTimestamp)
        and a --commit-patch-dir of per-revision *.patch files,
  WHEN  `aggregateGenCodeDesc --algorithm B ...` runs,
  THEN  it writes genCodeDescV26.03.json + commitStart2EndTime.patch and exit 0,
        and the JSON reports the replayed metrics.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main


def _write(path: Path, data) -> None:  # type: ignore[no-untyped-def]
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data), encoding="utf-8")


def _rec(rev: str, ts: str, lines: list[dict]) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [{"fileName": "src/a.py", "codeLines": lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }


def test_milestone_algb_cli_end_to_end(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    patches = tmp_path / "patches"
    out = tmp_path / "out"

    _write(gcd / "c1.json", _rec("c1", "2026-02-10T10:00:00Z",
        [{"lineRange": {"from": 1, "to": 3}, "genRatio": 100, "genMethod": "vibeCoding"}]))
    _write(patches / "c1.patch",
        "diff --git a/src/a.py b/src/a.py\n"
        "--- /dev/null\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+a\n+b\n+c\n")

    _write(gcd / "c2.json", _rec("c2", "2026-02-11T10:00:00Z",
        [{"lineLocation": 2, "genRatio": 0, "genMethod": "Manual"}]))
    _write(patches / "c2.patch",
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,3 +1,3 @@\n"
        " a\n"
        "-b\n"
        "+B\n"
        " c\n")

    rc = main([
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd),
        "--commit-patch-dir", str(patches),
        "--output-dir", str(out),
    ])
    assert rc == 0

    payload = json.loads((out / "genCodeDescV26.03.json").read_text())
    assert payload["SUMMARY"]["totalCodeLines"] == 3
    metrics = payload["AGGREGATE"]["metrics"]
    assert metrics["fullyAI"]["value"] == pytest.approx(2 / 3, abs=1e-6)
    assert metrics["weighted"]["value"] == pytest.approx(2 / 3, abs=1e-6)

    patch_text = (out / "commitStart2EndTime.patch").read_text()
    assert "algorithm=B" in patch_text
    assert "commit c1" in patch_text
    assert "commit c2" in patch_text


def test_milestone_algb_missing_patch_file_errors(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    patches = tmp_path / "patches"
    patches.mkdir()
    out = tmp_path / "out"

    _write(gcd / "c1.json", _rec("c1", "2026-02-10T10:00:00Z",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]))
    # No c1.patch.

    rc = main([
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd),
        "--commit-patch-dir", str(patches),
        "--output-dir", str(out),
    ])
    assert rc == 2


def test_milestone_algb_requires_commit_patch_dir(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    _write(gcd / "c1.json", _rec("c1", "2026-02-10T10:00:00Z",
        [{"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"}]))

    rc = main([
        "--repo-url", "https://x/r",
        "--repo-branch", "main",
        "--start-time", "2026-01-01T00:00:00Z",
        "--end-time", "2026-12-31T00:00:00Z",
        "--threshold", "60",
        "--algorithm", "B",
        "--gen-code-desc-dir", str(gcd),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 2
