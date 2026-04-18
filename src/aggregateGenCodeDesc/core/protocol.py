"""Protocol v26.03 loader and shared policy enums.

Parses a genCodeDesc record (dict form) into typed dataclasses, expanding
`lineRange` entries into per-line `GenCodeLine` instances. Record-level
validation covered here maps to US-006 AC-006-5 (genRatio range).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aggregateGenCodeDesc.core.validation import ValidationError


_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_GIT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SVN_REV_RE = re.compile(r"^[1-9][0-9]*$")


def _validate_revision_id(vcs_type: str, revision_id: str) -> None:
    """Enforce US-007 AC-007-1 / AC-007-2 revisionId shape by vcsType.

    - Git: 40-hex (SHA-1) or 64-hex (SHA-256), lower-case.
    - SVN: positive integer, no leading zero.
    - Other vcsType values: accepted as-is (forks may add their own shapes).
    """
    vt = vcs_type.lower()
    if vt == "git":
        rid = revision_id.lower()
        if not (_GIT_SHA1_RE.match(rid) or _GIT_SHA256_RE.match(rid)):
            raise ValidationError(
                f"invalid Git revisionId {revision_id!r}: "
                "expected 40-hex SHA-1 or 64-hex SHA-256"
            )
    elif vt == "svn":
        if not _SVN_REV_RE.match(revision_id):
            raise ValidationError(
                f"invalid SVN revisionId {revision_id!r}: "
                "expected positive integer"
            )


class OnMissing(Enum):
    """Policy for missing genCodeDesc records (AC-006-1)."""

    ABORT = "abort"
    ZERO = "zero"   # treat missing lines as genRatio 0 (AlgA/B default)
    SKIP = "skip"


class OnDuplicate(Enum):
    """Policy for duplicate revisionId records (AC-006-3)."""

    REJECT = "reject"
    LAST_WINS = "last-wins"


class OnClockSkew(Enum):
    """Policy for non-monotonic revisionTimestamp in AlgC (AC-006-4)."""

    ABORT = "abort"
    IGNORE = "ignore"


@dataclass(frozen=True)
class GenCodeLine:
    file_name: str
    line_location: int
    gen_ratio: int
    gen_method: str


@dataclass(frozen=True)
class RepositoryTarget:
    """Expected repository identity provided via CLI (--repo-url, --repo-branch)."""

    vcs_type: str
    repo_url: str
    repo_branch: str


@dataclass(frozen=True)
class RepositoryRef:
    vcs_type: str
    repo_url: str
    repo_branch: str
    revision_id: str


@dataclass(frozen=True)
class GenCodeDescRecord:
    protocol_version: str
    repository: RepositoryRef
    lines: tuple[GenCodeLine, ...] = field(default_factory=tuple)

    @property
    def revision_id(self) -> str:
        return self.repository.revision_id


def _expand_entry(file_name: str, entry: dict[str, Any]) -> list[GenCodeLine]:
    if "genRatio" not in entry:
        raise ValidationError(f"missing genRatio in entry for {file_name}: {entry}")
    gen_ratio = entry["genRatio"]
    if not isinstance(gen_ratio, int) or not 0 <= gen_ratio <= 100:
        # AC-006-5
        raise ValidationError(
            f"genRatio must be integer 0..100, got {gen_ratio!r} in {file_name}"
        )
    gen_method = entry.get("genMethod", "")

    if "lineLocation" in entry:
        loc = entry["lineLocation"]
        if not isinstance(loc, int) or loc < 1:
            raise ValidationError(f"invalid lineLocation {loc!r} in {file_name}")
        return [GenCodeLine(file_name, loc, gen_ratio, gen_method)]

    if "lineRange" in entry:
        rng = entry["lineRange"]
        lo, hi = rng.get("from"), rng.get("to")
        if not (isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi):
            raise ValidationError(f"invalid lineRange {rng!r} in {file_name}")
        return [GenCodeLine(file_name, n, gen_ratio, gen_method) for n in range(lo, hi + 1)]

    raise ValidationError(f"entry must have lineLocation or lineRange: {entry}")


def load_record_from_dict(
    data: dict[str, Any],
    *,
    strict_revision_id: bool = False,
) -> GenCodeDescRecord:
    """Parse a v26.03 genCodeDesc record dict into a typed record.

    Args:
        data: parsed JSON dict matching the v26.03 / v26.04 shape.
        strict_revision_id: when True, enforce US-007 AC-007-1 / AC-007-2
            revisionId shape by vcsType (Git 40/64-hex, SVN positive int).
            Disabled by default so internal unit tests can use short
            synthetic ids like "r1". Production CLI paths should enable it.

    Raises:
        ValidationError on any structural or range violation.
    """
    version = data.get("protocolVersion")
    if version not in {"26.03", "26.04"}:
        raise ValidationError(f"unsupported protocolVersion: {version!r}")

    repo = data.get("REPOSITORY")
    if not isinstance(repo, dict):
        raise ValidationError("missing REPOSITORY block")
    required = ("vcsType", "repoURL", "repoBranch", "revisionId")
    for key in required:
        if not repo.get(key):
            raise ValidationError(f"REPOSITORY.{key} is required")

    repo_ref = RepositoryRef(
        vcs_type=str(repo["vcsType"]),
        repo_url=str(repo["repoURL"]),
        repo_branch=str(repo["repoBranch"]),
        revision_id=str(repo["revisionId"]),
    )
    if strict_revision_id:
        _validate_revision_id(repo_ref.vcs_type, repo_ref.revision_id)

    details = data.get("DETAIL") or []
    if not isinstance(details, list):
        raise ValidationError("DETAIL must be a list")

    lines: list[GenCodeLine] = []
    for file_block in details:
        file_name = file_block.get("fileName")
        if not file_name:
            raise ValidationError("DETAIL entry missing fileName")
        for key in ("codeLines", "docLines"):
            for entry in file_block.get(key, []) or []:
                lines.extend(_expand_entry(file_name, entry))

    return GenCodeDescRecord(
        protocol_version=str(version),
        repository=repo_ref,
        lines=tuple(lines),
    )
