"""US-006 — Destructive and Edge Conditions.

Covers (record / collection level):
  AC-006-2: REPOSITORY mismatch rejection
  AC-006-3: duplicate revisionId detection
  AC-006-5: genRatio out-of-range rejection

AC-006-1 (missing revision) and AC-006-4 (clock skew) are enforced at the
algorithm layer against the `OnMissing` / `OnClockSkew` policies; they are
unit-tested here only at the policy-enum level.
"""

from __future__ import annotations

import pytest

from aggregateGenCodeDesc.core.protocol import (
    GenCodeDescRecord,
    OnClockSkew,
    OnDuplicate,
    OnMissing,
    RepositoryTarget,
    load_record_from_dict,
)
from aggregateGenCodeDesc.core.validation import (
    DuplicateRevisionError,
    RepositoryMismatchError,
    ValidationError,
    detect_duplicates,
    validate_record_against_target,
)


# ---------------------------------------------------------------------------
# Canonical valid v26.03 record (minimal shape used across US-006 tests).
# ---------------------------------------------------------------------------
def _make_record(revision_id: str = "abc123", repo_url: str = "https://x/r") -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {"totalCodeLines": 0, "fullGeneratedCodeLines": 0, "partialGeneratedCodeLines": 0},
        "DETAIL": [
            {
                "fileName": "a.py",
                "codeLines": [
                    {"lineLocation": 1, "genRatio": 100, "genMethod": "vibeCoding"},
                ],
            }
        ],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": repo_url,
            "repoBranch": "main",
            "revisionId": revision_id,
        },
    }


# ---------------------------------------------------------------------------
# AC-006-5 [Misuse] genRatio outside [0, 100] → record rejected on load
# ---------------------------------------------------------------------------
def test_ac_006_5_rejects_out_of_range_genratio() -> None:
    rec = _make_record()
    rec["DETAIL"][0]["codeLines"][0]["genRatio"] = 150
    with pytest.raises(ValidationError, match="genRatio"):
        load_record_from_dict(rec)


def test_ac_006_5_accepts_boundary_values() -> None:
    for r in (0, 100):
        rec = _make_record()
        rec["DETAIL"][0]["codeLines"][0]["genRatio"] = r
        out = load_record_from_dict(rec)
        assert out.lines[0].gen_ratio == r


# ---------------------------------------------------------------------------
# AC-006-2 [Fault] Corrupted genCodeDesc with wrong REPOSITORY fields
# ---------------------------------------------------------------------------
def test_ac_006_2_rejects_repoURL_mismatch() -> None:
    rec = load_record_from_dict(_make_record(repo_url="https://WRONG/r"))
    target = RepositoryTarget(vcs_type="git", repo_url="https://x/r", repo_branch="main")
    with pytest.raises(RepositoryMismatchError) as exc:
        validate_record_against_target(rec, target)
    assert "repoURL" in str(exc.value)


def test_ac_006_2_rejects_vcsType_mismatch() -> None:
    rec_dict = _make_record()
    rec_dict["REPOSITORY"]["vcsType"] = "svn"
    rec = load_record_from_dict(rec_dict)
    target = RepositoryTarget(vcs_type="git", repo_url="https://x/r", repo_branch="main")
    with pytest.raises(RepositoryMismatchError, match="vcsType"):
        validate_record_against_target(rec, target)


def test_ac_006_2_accepts_matching_repository() -> None:
    rec = load_record_from_dict(_make_record())
    target = RepositoryTarget(vcs_type="git", repo_url="https://x/r", repo_branch="main")
    # Does not raise.
    validate_record_against_target(rec, target)


# ---------------------------------------------------------------------------
# AC-006-3 [Misuse] Two genCodeDesc records for the same revisionId
# ---------------------------------------------------------------------------
def test_ac_006_3_detect_duplicate_raises_when_policy_reject() -> None:
    r1 = load_record_from_dict(_make_record(revision_id="abc123"))
    r2 = load_record_from_dict(_make_record(revision_id="abc123"))
    with pytest.raises(DuplicateRevisionError, match="abc123"):
        detect_duplicates([r1, r2], policy=OnDuplicate.REJECT)


def test_ac_006_3_detect_duplicate_last_wins_keeps_second() -> None:
    r1 = load_record_from_dict(_make_record(revision_id="abc123", repo_url="https://x/r"))
    r2_dict = _make_record(revision_id="abc123", repo_url="https://x/r")
    # Distinguish r2 so we can verify it wins.
    r2_dict["DETAIL"][0]["codeLines"][0]["genRatio"] = 50
    r2 = load_record_from_dict(r2_dict)

    kept, warnings = detect_duplicates([r1, r2], policy=OnDuplicate.LAST_WINS)
    assert len(kept) == 1
    assert kept[0].lines[0].gen_ratio == 50
    assert any("abc123" in w for w in warnings)


def test_ac_006_3_no_duplicate_returns_all() -> None:
    r1 = load_record_from_dict(_make_record(revision_id="aaa"))
    r2 = load_record_from_dict(_make_record(revision_id="bbb"))
    kept, warnings = detect_duplicates([r1, r2], policy=OnDuplicate.REJECT)
    assert len(kept) == 2
    assert warnings == []


# ---------------------------------------------------------------------------
# Policy enums exist (AC-006-1 and AC-006-4 will be exercised by algorithms).
# ---------------------------------------------------------------------------
def test_policy_enums_exposed() -> None:
    assert {p.name for p in OnMissing} >= {"ABORT", "ZERO", "SKIP"}
    assert {p.name for p in OnDuplicate} >= {"REJECT", "LAST_WINS"}
    assert {p.name for p in OnClockSkew} >= {"ABORT", "IGNORE"}


# ---------------------------------------------------------------------------
# Loader: lineRange expands to per-line entries.
# ---------------------------------------------------------------------------
def test_load_expands_lineRange() -> None:
    rec = _make_record()
    rec["DETAIL"][0]["codeLines"] = [
        {"lineRange": {"from": 10, "to": 12}, "genRatio": 80, "genMethod": "vibeCoding"}
    ]
    out = load_record_from_dict(rec)
    assert [line.line_location for line in out.lines] == [10, 11, 12]
    assert all(line.gen_ratio == 80 for line in out.lines)


def test_load_rejects_invalid_lineRange() -> None:
    rec = _make_record()
    rec["DETAIL"][0]["codeLines"] = [
        {"lineRange": {"from": 12, "to": 10}, "genRatio": 80, "genMethod": "vibeCoding"}
    ]
    with pytest.raises(ValidationError, match="lineRange"):
        load_record_from_dict(rec)


def test_load_returns_typed_record() -> None:
    out = load_record_from_dict(_make_record())
    assert isinstance(out, GenCodeDescRecord)
    assert out.revision_id == "abc123"
    assert out.repository.vcs_type == "git"
