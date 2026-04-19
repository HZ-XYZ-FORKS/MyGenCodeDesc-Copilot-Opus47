"""Algorithm A (SVN variant) — live `svn blame` against an SVN working copy.

Mirrors `alg_a.py` but uses the SVN backend. Rename tracking is not
provided by `svn blame` the way `git blame -M -C` is, so ownership is
tracked at the file-path level (sufficient for repositories without
rename-heavy history; for rename-heavy workloads use AlgB or AlgC).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aggregateGenCodeDesc.algorithms.alg_a import (
    AlgAResult,
    _SurvivingLine,
    _resolve_line,
)
from aggregateGenCodeDesc.core.metric import compute_metrics
from aggregateGenCodeDesc.core.protocol import OnMissing, load_record_from_dict
from aggregateGenCodeDesc.core.svn import (
    blame_file_svn,
    commit_timestamp_svn,
    list_tracked_files_svn,
)
from aggregateGenCodeDesc.core.validation import ValidationError


def _index_records(records: list[dict[str, Any]]) -> dict[str, dict[tuple[str, int], tuple[int, str]]]:
    out: dict[str, dict[tuple[str, int], tuple[int, str]]] = {}
    for raw in records:
        rec = load_record_from_dict(raw)
        table: dict[tuple[str, int], tuple[int, str]] = {}
        for line in rec.lines:
            table[(line.file_name, line.line_location)] = (line.gen_ratio, line.gen_method)
        out[rec.revision_id] = table
    return out


def run_algorithm_a_svn(
    wc: Path,
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
    if not (wc / ".svn").exists():
        raise ValidationError(f"not an SVN working copy: {wc}")

    by_rev = _index_records(records)
    warnings: list[str] = []
    surviving: list[_SurvivingLine] = []

    files = list_tracked_files_svn(wc, end_rev)
    for fpath in files:
        blame = blame_file_svn(wc, end_rev, fpath)
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
    _ = commit_timestamp_svn(wc, end_rev)

    return AlgAResult(
        metrics=metrics,
        surviving=tuple(surviving),
        in_window_adds=in_window,
        warnings=tuple(warnings),
    )
