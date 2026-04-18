"""US-007 — Git vs SVN revisionId format validation.

Covers:

  AC-007-1  [Typical] Git revisionId is 40-hex (SHA-1) or 64-hex (SHA-256).
  AC-007-2  [Typical] SVN revisionId is a positive integer.

AC-007-3 through AC-007-5 (SVN merge imprecision, rebase/amend Git-only,
branch-as-path) are documentation-only acceptance criteria and are not
code-enforced.
"""

from __future__ import annotations

import pytest

from aggregateGenCodeDesc.core.protocol import load_record_from_dict
from aggregateGenCodeDesc.core.validation import ValidationError


def _record(vcs_type: str, revision_id: str) -> dict:
    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "SUMMARY": {},
        "DETAIL": [],
        "REPOSITORY": {
            "vcsType": vcs_type,
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": revision_id,
        },
    }


# ---------------------------------------------------------------------------
# AC-007-1 — Git accepts SHA-1 (40 hex) and SHA-256 (64 hex).
# ---------------------------------------------------------------------------
class TestAc007_1GitRevisionId:
    def test_accepts_40_hex_sha1(self) -> None:
        sha1 = "a" * 40
        rec = load_record_from_dict(_record("git", sha1), strict_revision_id=True)
        assert rec.revision_id == sha1

    def test_accepts_64_hex_sha256(self) -> None:
        sha256 = "0123456789abcdef" * 4  # 64 hex chars
        rec = load_record_from_dict(_record("git", sha256), strict_revision_id=True)
        assert rec.revision_id == sha256

    def test_accepts_mixed_case_hex(self) -> None:
        # Git historically lower-cases, but accept upper/mixed for resilience.
        sha1_upper = "ABCDEF0123456789" + "0" * 24
        rec = load_record_from_dict(_record("git", sha1_upper), strict_revision_id=True)
        assert rec.revision_id == sha1_upper

    @pytest.mark.parametrize("bad", [
        "4217",                 # numeric (SVN-shape) rejected for Git
        "deadbeef",             # too short
        "g" * 40,               # non-hex
        "a" * 41,               # wrong length
        "a" * 63,               # close to SHA-256 but off by one
    ])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            load_record_from_dict(_record("git", bad), strict_revision_id=True)


# ---------------------------------------------------------------------------
# AC-007-2 — SVN accepts positive integer revisionId.
# ---------------------------------------------------------------------------
class TestAc007_2SvnRevisionId:
    @pytest.mark.parametrize("rev", ["1", "42", "4217", "1000000"])
    def test_accepts_positive_integer(self, rev: str) -> None:
        rec = load_record_from_dict(_record("svn", rev), strict_revision_id=True)
        assert rec.revision_id == rev

    @pytest.mark.parametrize("bad", [
        "0",                    # zero is not a valid SVN revision
        "-1",                   # negative
        "04217",                # leading zero
        "4217a",                # trailing garbage
        "a" * 40,               # SHA-shape rejected for SVN
    ])
    def test_rejects_non_integer(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            load_record_from_dict(_record("svn", bad), strict_revision_id=True)
