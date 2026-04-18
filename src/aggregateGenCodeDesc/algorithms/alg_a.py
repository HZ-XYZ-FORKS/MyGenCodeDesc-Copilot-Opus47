"""Algorithm A — live `git blame` against a working repo.

For each file tracked at `--end-rev` (HEAD by default):
  1. Run `git blame --line-porcelain -M -C` → one BlameEntry per line.
  2. Filter lines whose origin commit timestamp ∈ [startTime, endTime].
  3. Look up genRatio in the v26.03 record whose revisionId matches the
     origin commit, keyed by (origin_file, origin_line).
  4. Missing record / entry → OnMissing policy (ZERO / ABORT / SKIP).

Rename/move support comes for free from `git blame -M -C`
(AC-009-1, AC-009-2, AC-002-1/2, AC-004-1/2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aggregateGenCodeDesc.core.git import (
    BlameEntry,
    blame_file,
    commit_timestamp,
    list_tracked_files,
)
from aggregateGenCodeDesc.core.metric import Metrics, compute_metrics
from aggregateGenCodeDesc.core.protocol import (
    OnMissing,
    load_record_from_dict,
)
from aggregateGenCodeDesc.core.validation import ValidationError


@dataclass(frozen=True)
class _SurvivingLine:
    origin_revision: str
    origin_timestamp: datetime
    origin_file: str
    origin_line: int
    current_file: str
    current_line: int
    gen_ratio: int
    gen_method: str


@dataclass(frozen=True)
class AlgAResult:
    metrics: Metrics
    surviving: tuple[_SurvivingLine, ...]
    in_window_adds: tuple[_SurvivingLine, ...]
    warnings: tuple[str, ...]


def _index_records(records: list[dict[str, Any]]) -> dict[str, dict[tuple[str, int], tuple[int, str]]]:
    """Build revisionId → {(fileName, lineLocation): (genRatio, genMethod)}."""
    out: dict[str, dict[tuple[str, int], tuple[int, str]]] = {}
    for raw in records:
        rec = load_record_from_dict(raw)
        table: dict[tuple[str, int], tuple[int, str]] = {}
        for line in rec.lines:
            table[(line.file_name, line.line_location)] = (line.gen_ratio, line.gen_method)
        out[rec.revision_id] = table
    return out


def run_algorithm_a(
    repo_path: Path,
    records: list[dict[str, Any]],
    *,
    start_time: datetime,
    end_time: datetime,
    end_rev: str = "HEAD",
    threshold: int,
    on_missing: OnMissing = OnMissing.ZERO,
) -> AlgAResult:
    if start_time > end_time:
        raise ValidationError(f"startTime {start_time} must be <= endTime {end_time}")
    if not (repo_path / ".git").exists():
        raise ValidationError(f"not a git repository: {repo_path}")

    by_rev = _index_records(records)
    warnings: list[str] = []
    surviving: list[_SurvivingLine] = []

    files = list_tracked_files(repo_path, end_rev)
    for fpath in files:
        blame = blame_file(repo_path, end_rev, fpath)
        for b in blame:
            entry = _resolve_line(
                b, by_rev=by_rev, on_missing=on_missing, warnings=warnings
            )
            if entry is None:
                continue
            surviving.append(entry)

    in_window = tuple(
        s for s in surviving if start_time <= s.origin_timestamp <= end_time
    )
    metrics = compute_metrics([s.gen_ratio for s in in_window], threshold=threshold)

    # Resolve end_rev timestamp so the caller can log it (not strictly needed).
    _ = commit_timestamp(repo_path, end_rev)

    return AlgAResult(
        metrics=metrics,
        surviving=tuple(surviving),
        in_window_adds=in_window,
        warnings=tuple(warnings),
    )


def _resolve_line(
    b: BlameEntry,
    *,
    by_rev: dict[str, dict[tuple[str, int], tuple[int, str]]],
    on_missing: OnMissing,
    warnings: list[str],
) -> _SurvivingLine | None:
    rec_table = by_rev.get(b.origin_revision)
    if rec_table is None:
        if on_missing is OnMissing.ABORT:
            raise ValidationError(
                f"no genCodeDesc record for revision {b.origin_revision}"
            )
        if on_missing is OnMissing.SKIP:
            return None
        warnings.append(
            f"no genCodeDesc record for revision {b.origin_revision} "
            f"(treated as genRatio 0)"
        )
        return _SurvivingLine(
            origin_revision=b.origin_revision,
            origin_timestamp=b.origin_timestamp,
            origin_file=b.origin_file,
            origin_line=b.origin_line,
            current_file=b.file_path,
            current_line=b.line_number,
            gen_ratio=0,
            gen_method="unattributed",
        )

    key = (b.origin_file, b.origin_line)
    entry = rec_table.get(key)
    if entry is None:
        if on_missing is OnMissing.ABORT:
            raise ValidationError(
                f"missing genCodeDesc entry for {b.origin_file}:{b.origin_line} "
                f"in revision {b.origin_revision}"
            )
        if on_missing is OnMissing.SKIP:
            return None
        warnings.append(
            f"revision {b.origin_revision}: no genCodeDesc for "
            f"{b.origin_file}:{b.origin_line} (treated as genRatio 0)"
        )
        gr, gm = 0, "unattributed"
    else:
        gr, gm = entry

    return _SurvivingLine(
        origin_revision=b.origin_revision,
        origin_timestamp=b.origin_timestamp,
        origin_file=b.origin_file,
        origin_line=b.origin_line,
        current_file=b.file_path,
        current_line=b.line_number,
        gen_ratio=gr,
        gen_method=gm,
    )
