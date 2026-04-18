"""End-to-end milestone test: Algorithm C CLI produces both artifacts.

Canonical 10-line scenario from README_UserGuide.md:
  genRatios = [100×5, 80×3, 30, 0], threshold=60
  → weighted=0.77, fullyAI=0.50, mostlyAI=0.80
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aggregateGenCodeDesc.cli import main


REPO_URL = "https://github.com/acme/foo"
REPO_BRANCH = "main"


def _write_v2604(path: Path, name: str, *, revision_id: str, revision_ts: str,
                 file_name: str, code_lines: list[dict]) -> None:
    payload = {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.04",
        "codeAgent": "HuayanCoder",
        "SUMMARY": {},
        "DETAIL": [{"fileName": file_name, "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": REPO_URL,
            "repoBranch": REPO_BRANCH,
            "revisionId": revision_id,
            "revisionTimestamp": revision_ts,
        },
    }
    (path / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _add(loc: int, gr: int, rev: str, orig_line: int, ts: str) -> dict:
    return {
        "changeType": "add",
        "lineLocation": loc,
        "genRatio": gr,
        "genMethod": "vibeCoding",
        "blame": {
            "revisionId": rev,
            "originalFilePath": "src/auth.py",
            "originalLine": orig_line,
            "timestamp": ts,
        },
    }


def _add_range(from_: int, to: int, gr: int, rev: str, orig_line_start: int, ts: str) -> dict:
    return {
        "changeType": "add",
        "lineRange": {"from": from_, "to": to},
        "genRatio": gr,
        "genMethod": "vibeCoding",
        "blame": {
            "revisionId": rev,
            "originalFilePath": "src/auth.py",
            "originalLine": orig_line_start,
            "timestamp": ts,
        },
    }


def test_milestone_algc_end_to_end(tmp_path: Path) -> None:
    """10-line canonical scenario, one file across two commits → matches README."""
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    out = tmp_path / "out"

    # Commit 1 (2026-02-10) adds lines 1..8 with the "100 × 5, 80 × 3" prefix.
    _write_v2604(
        gcd,
        "c1.json",
        revision_id="c1",
        revision_ts="2026-02-10T10:00:00Z",
        file_name="src/auth.py",
        code_lines=[
            _add_range(1, 5, 100, "c1", 1, "2026-02-10T10:00:00Z"),
            _add_range(6, 8, 80, "c1", 6, "2026-02-10T10:00:00Z"),
        ],
    )
    # Commit 2 (2026-03-15) adds lines 9 and 10 (genRatio 30 and 0).
    _write_v2604(
        gcd,
        "c2.json",
        revision_id="c2",
        revision_ts="2026-03-15T10:00:00Z",
        file_name="src/auth.py",
        code_lines=[
            _add(9, 30, "c2", 9, "2026-03-15T10:00:00Z"),
            _add(10, 0, "c2", 10, "2026-03-15T10:00:00Z"),
        ],
    )

    rc = main(
        [
            "--repo-url", REPO_URL,
            "--repo-branch", REPO_BRANCH,
            "--start-time", "2026-01-01T00:00:00Z",
            "--end-time", "2026-04-01T00:00:00Z",
            "--threshold", "60",
            "--algorithm", "C",
            "--scope", "A",
            "--gen-code-desc-dir", str(gcd),
            "--output-dir", str(out),
        ]
    )
    assert rc == 0

    json_out = out / "genCodeDescV26.03.json"
    patch_out = out / "commitStart2EndTime.patch"
    assert json_out.exists()
    assert patch_out.exists()

    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["protocolVersion"] == "26.03"
    assert data["codeAgent"] == "aggregateGenCodeDesc"
    assert data["SUMMARY"]["totalCodeLines"] == 10
    assert data["SUMMARY"]["fullGeneratedCodeLines"] == 5
    assert data["SUMMARY"]["partialGeneratedCodeLines"] == 4  # 80,80,80,30

    metrics = data["AGGREGATE"]["metrics"]
    assert metrics["weighted"]["value"] == pytest.approx(0.77, abs=1e-6)
    assert metrics["fullyAI"]["value"] == pytest.approx(0.50, abs=1e-6)
    assert metrics["mostlyAI"]["value"] == pytest.approx(0.80, abs=1e-6)
    assert metrics["mostlyAI"]["threshold"] == 60

    assert data["REPOSITORY"]["revisionId"].startswith("aggregate:")

    patch_text = patch_out.read_text(encoding="utf-8")
    assert "commitStart2EndTime.patch" in patch_text
    assert f"repoURL:     {REPO_URL}" in patch_text
    assert "diff --git a/src/auth.py b/src/auth.py" in patch_text


def test_milestone_rejects_mixed_protocol_versions(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    gcd.mkdir()

    # One v26.04 record
    _write_v2604(
        gcd, "c1.json",
        revision_id="c1", revision_ts="2026-02-10T10:00:00Z",
        file_name="src/a.py",
        code_lines=[_add(1, 100, "c1", 1, "2026-02-10T10:00:00Z")],
    )
    # One v26.03-shaped record (homogeneity check must trip first, since
    # load_v2604_record would fail otherwise — either error is acceptable).
    (gcd / "c2.json").write_text(
        json.dumps(
            {
                "protocolVersion": "26.03",
                "SUMMARY": {},
                "DETAIL": [],
                "REPOSITORY": {
                    "vcsType": "git",
                    "repoURL": REPO_URL,
                    "repoBranch": REPO_BRANCH,
                    "revisionId": "c2",
                },
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--repo-url", REPO_URL,
            "--repo-branch", REPO_BRANCH,
            "--start-time", "2026-01-01T00:00:00Z",
            "--end-time", "2026-04-01T00:00:00Z",
            "--threshold", "60",
            "--algorithm", "C",
            "--gen-code-desc-dir", str(gcd),
            "--output-dir", str(tmp_path / "out"),
        ]
    )
    assert rc == 2  # validation error exit code


def test_milestone_rejects_repository_mismatch(tmp_path: Path) -> None:
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    _write_v2604(
        gcd, "c1.json",
        revision_id="c1", revision_ts="2026-02-10T10:00:00Z",
        file_name="src/a.py",
        code_lines=[_add(1, 100, "c1", 1, "2026-02-10T10:00:00Z")],
    )

    rc = main(
        [
            "--repo-url", "https://WRONG/foo",
            "--repo-branch", REPO_BRANCH,
            "--start-time", "2026-01-01T00:00:00Z",
            "--end-time", "2026-04-01T00:00:00Z",
            "--threshold", "60",
            "--algorithm", "C",
            "--gen-code-desc-dir", str(gcd),
            "--output-dir", str(tmp_path / "out"),
        ]
    )
    assert rc == 2


def test_milestone_alg_a_requires_repo_path(tmp_path: Path) -> None:
    """Algorithm A now implemented; missing --repo-path must fail with rc=2."""
    gcd = tmp_path / "gcd"
    gcd.mkdir()
    _write_v2604(
        gcd, "c1.json",
        revision_id="c1", revision_ts="2026-02-10T10:00:00Z",
        file_name="src/a.py",
        code_lines=[_add(1, 100, "c1", 1, "2026-02-10T10:00:00Z")],
    )
    rc = main(
        [
            "--repo-url", REPO_URL, "--repo-branch", REPO_BRANCH,
            "--start-time", "2026-01-01T00:00:00Z",
            "--end-time", "2026-04-01T00:00:00Z",
            "--threshold", "60",
            "--algorithm", "A",
            "--gen-code-desc-dir", str(gcd),
            "--output-dir", str(tmp_path / "out"),
        ]
    )
    assert rc == 2
