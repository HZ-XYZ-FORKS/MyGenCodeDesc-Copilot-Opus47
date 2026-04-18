"""Cross-record validation for US-006.

Keeps exceptions & collection-level checks out of the loader so they can be
composed with policy enums at the algorithm boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aggregateGenCodeDesc.core.protocol import (
        GenCodeDescRecord,
        OnDuplicate,
        RepositoryTarget,
    )


class ValidationError(Exception):
    """Structural / range validation failure on a single record."""


class RepositoryMismatchError(ValidationError):
    """AC-006-2: genCodeDesc REPOSITORY does not match CLI target."""


class DuplicateRevisionError(ValidationError):
    """AC-006-3 (with OnDuplicate.REJECT): two records share a revisionId."""


def validate_record_against_target(
    record: GenCodeDescRecord,
    target: RepositoryTarget,
) -> None:
    """AC-006-2: reject records whose REPOSITORY block contradicts the CLI target."""
    mismatches: list[str] = []
    if record.repository.vcs_type != target.vcs_type:
        mismatches.append(f"vcsType: record={record.repository.vcs_type} target={target.vcs_type}")
    if record.repository.repo_url != target.repo_url:
        mismatches.append(f"repoURL: record={record.repository.repo_url} target={target.repo_url}")
    if record.repository.repo_branch != target.repo_branch:
        mismatches.append(
            f"repoBranch: record={record.repository.repo_branch} target={target.repo_branch}"
        )
    if mismatches:
        raise RepositoryMismatchError(
            f"REPOSITORY mismatch for revision {record.revision_id}: " + "; ".join(mismatches)
        )


def detect_duplicates(
    records: list[GenCodeDescRecord],
    *,
    policy: OnDuplicate,
) -> tuple[list[GenCodeDescRecord], list[str]]:
    """AC-006-3.

    Returns:
        (kept_records, warnings)
    Raises:
        DuplicateRevisionError when policy is REJECT and a duplicate exists.
    """
    # Local import to avoid circularity (protocol imports ValidationError from here).
    from aggregateGenCodeDesc.core.protocol import OnDuplicate as _OnDup

    seen: dict[str, GenCodeDescRecord] = {}
    warnings: list[str] = []

    for rec in records:
        rev = rec.revision_id
        if rev not in seen:
            seen[rev] = rec
            continue
        if policy is _OnDup.REJECT:
            raise DuplicateRevisionError(f"duplicate genCodeDesc for revisionId {rev}")
        if policy is _OnDup.LAST_WINS:
            warnings.append(f"duplicate genCodeDesc for revisionId {rev}: last-wins applied")
            seen[rev] = rec
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown OnDuplicate policy: {policy!r}")

    # Preserve original order of first occurrences, but substitute with winner.
    kept: list[GenCodeDescRecord] = []
    emitted: set[str] = set()
    for rec in records:
        if rec.revision_id in emitted:
            continue
        kept.append(seen[rec.revision_id])
        emitted.add(rec.revision_id)
    return kept, warnings
