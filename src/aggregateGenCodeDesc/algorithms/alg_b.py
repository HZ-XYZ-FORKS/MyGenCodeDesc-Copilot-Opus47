"""Algorithm B — offline diff replay against v26.03 records.

Inputs:
  - v26.03 records, each with REPOSITORY.revisionId + REPOSITORY.revisionTimestamp.
  - Per-commit unified diff patches (one per revisionId).

For each commit in ascending revisionTimestamp order:
  1. Apply the patch to a per-file surviving-line list (deletes remove entries,
     adds insert new entries).
  2. For each added line, look up genRatio in the same commit's v26.03 DETAIL
     by (fileName, lineLocation). Missing attribution ⇒ genRatio 0 by default
     (OnMissing.ZERO, AC-006-1) or abort (OnMissing.ABORT).

After replay, filter surviving lines by introduction timestamp in
[startTime, endTime] and pass the genRatio list to core.metric.compute_metrics.

Not supported by design: copy and binary diffs. They raise ValidationError.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aggregateGenCodeDesc.core.metric import Metrics, compute_metrics
from aggregateGenCodeDesc.core.patch import (
    FilePatch,
    Hunk,
    HunkEventKind,
    parse_unified_diff,
)
from aggregateGenCodeDesc.core.protocol import (
    OnMissing,
    load_record_from_dict,
)
from aggregateGenCodeDesc.core.validation import ValidationError


_log = logging.getLogger("aggregateGenCodeDesc")


@dataclass(frozen=True)
class AlgBCommit:
    """A single commit: v26.03 record data + its unified diff."""

    revision_id: str
    revision_timestamp: datetime
    gen_ratio_by_line: dict[tuple[str, int], tuple[int, str]]
    # (fileName, lineLocation) → (genRatio, genMethod)
    patch_files: tuple[FilePatch, ...]


@dataclass(frozen=True)
class _SurvivingLine:
    revision_id: str         # commit that introduced this line
    timestamp: datetime      # that commit's revisionTimestamp
    gen_ratio: int
    gen_method: str
    file_name: str           # current fileName (renames not supported)
    line_location: int       # current line number (recomputed per hunk replay)


@dataclass(frozen=True)
class AlgBResult:
    metrics: Metrics
    surviving: tuple[_SurvivingLine, ...]
    in_window_adds: tuple[_SurvivingLine, ...]
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _parse_ts(s: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValidationError(f"invalid timestamp in {field}: {s!r}") from exc


def build_commit(record_dict: dict[str, Any], patch_text: str) -> AlgBCommit:
    """Combine a v26.03 record dict with its unified-diff text into an AlgBCommit."""
    rec = load_record_from_dict(record_dict)

    repo = record_dict.get("REPOSITORY") or {}
    ts_raw = repo.get("revisionTimestamp")
    if not ts_raw:
        raise ValidationError(
            f"Algorithm B requires REPOSITORY.revisionTimestamp in record "
            f"{rec.revision_id!r}"
        )
    ts = _parse_ts(ts_raw, f"{rec.revision_id}:REPOSITORY.revisionTimestamp")

    gen_by_line: dict[tuple[str, int], tuple[int, str]] = {}
    for line in rec.lines:
        gen_by_line[(line.file_name, line.line_location)] = (
            line.gen_ratio,
            line.gen_method,
        )

    patch_files = tuple(parse_unified_diff(patch_text))

    return AlgBCommit(
        revision_id=rec.revision_id,
        revision_timestamp=ts,
        gen_ratio_by_line=gen_by_line,
        patch_files=patch_files,
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def _apply_hunk_to_file(
    surviving: list[_SurvivingLine],
    hunk: Hunk,
    *,
    commit: AlgBCommit,
    new_file_name: str,
    on_missing: OnMissing,
    warnings: list[str],
) -> None:
    """Apply one hunk in place to the per-file surviving list."""
    # Convert old_start (1-based) to list index.
    idx = hunk.old_start - 1
    for event in hunk.events:
        if event.kind is HunkEventKind.KEEP:
            if idx >= len(surviving):
                raise ValidationError(
                    f"patch replay: context line past end of file {new_file_name} "
                    f"(hunk old_start={hunk.old_start})"
                )
            idx += 1
        elif event.kind is HunkEventKind.DELETE:
            if idx >= len(surviving):
                raise ValidationError(
                    f"patch replay: delete past end of file {new_file_name}"
                )
            del surviving[idx]
            # do not advance idx
        elif event.kind is HunkEventKind.ADD:
            key = (new_file_name, event.new_line)
            entry = commit.gen_ratio_by_line.get(key)
            if entry is None:
                # AC-006-1: unattributed line.
                if on_missing is OnMissing.ABORT:
                    raise ValidationError(
                        f"missing genCodeDesc entry for {new_file_name}:{event.new_line} "
                        f"in commit {commit.revision_id}"
                    )
                if on_missing is OnMissing.SKIP:
                    # SKIP: do not record this line at all; still advance idx.
                    idx += 1
                    continue
                # ZERO (default): genRatio 0, genMethod "unattributed".
                gr, gm = 0, "unattributed"
                warnings.append(
                    f"commit {commit.revision_id}: no genCodeDesc for "
                    f"{new_file_name}:{event.new_line} (treated as genRatio 0)"
                )
            else:
                gr, gm = entry
            surviving.insert(
                idx,
                _SurvivingLine(
                    revision_id=commit.revision_id,
                    timestamp=commit.revision_timestamp,
                    gen_ratio=gr,
                    gen_method=gm,
                    file_name=new_file_name,
                    line_location=event.new_line,
                ),
            )
            idx += 1


def _renumber_file(surviving: list[_SurvivingLine]) -> None:
    """After applying all hunks of one commit, refresh each entry's line_location
    to match its position in the list (1-based)."""
    for i, entry in enumerate(surviving):
        if entry.line_location != i + 1:
            surviving[i] = _SurvivingLine(
                revision_id=entry.revision_id,
                timestamp=entry.timestamp,
                gen_ratio=entry.gen_ratio,
                gen_method=entry.gen_method,
                file_name=entry.file_name,
                line_location=i + 1,
            )


def _retarget_file_name(surviving: list[_SurvivingLine], new_file_name: str) -> None:
    """When a file is renamed, update the current file_name for all surviving
    lines while preserving ownership (revision/timestamp/genRatio)."""
    for i, entry in enumerate(surviving):
        if entry.file_name != new_file_name:
            surviving[i] = _SurvivingLine(
                revision_id=entry.revision_id,
                timestamp=entry.timestamp,
                gen_ratio=entry.gen_ratio,
                gen_method=entry.gen_method,
                file_name=new_file_name,
                line_location=entry.line_location,
            )


def run_algorithm_b(
    commits: Iterable[AlgBCommit],
    *,
    start_time: datetime,
    end_time: datetime,
    threshold: int,
    on_missing: OnMissing = OnMissing.ZERO,
) -> AlgBResult:
    if start_time > end_time:
        raise ValidationError(f"startTime {start_time} must be <= endTime {end_time}")

    ordered = sorted(commits, key=lambda c: c.revision_timestamp)
    ordered = [c for c in ordered if c.revision_timestamp <= end_time]

    state: dict[str, list[_SurvivingLine]] = {}
    warnings: list[str] = []

    for commit in ordered:
        # AC-010-2: DEBUG per-commit replay decision — count add/delete events
        # across all hunks of all files in this commit's patch.
        if _log.isEnabledFor(logging.DEBUG):
            adds = 0
            deletes = 0
            for fp in commit.patch_files:
                for hunk in fp.hunks:
                    for ev in hunk.events:
                        if ev.kind is HunkEventKind.ADD:
                            adds += 1
                        elif ev.kind is HunkEventKind.DELETE:
                            deletes += 1
            _log.debug(
                "REPLAY revisionId=%s files=%d adds=%d deletes=%d",
                commit.revision_id, len(commit.patch_files), adds, deletes,
            )
        for fp in commit.patch_files:
            if fp.is_deleted_file:
                # File removed wholesale: drop all surviving lines for old_path.
                if fp.old_path is not None:
                    state.pop(fp.old_path, None)
                continue
            assert fp.new_path is not None  # parser invariant
            new_path = fp.new_path
            if fp.is_new_file:
                state[new_path] = []
            else:
                if fp.old_path is not None and fp.old_path != new_path:
                    # Rename/move: carry the surviving-line list to the new path.
                    moved = state.pop(fp.old_path, [])
                    _retarget_file_name(moved, new_path)
                    if new_path in state and state[new_path]:
                        raise ValidationError(
                            f"patch: rename target already exists in replay state: {new_path!r}"
                        )
                    state[new_path] = moved
                else:
                    state.setdefault(new_path, [])

            file_list = state[new_path]
            for hunk in fp.hunks:
                _apply_hunk_to_file(
                    file_list,
                    hunk,
                    commit=commit,
                    new_file_name=new_path,
                    on_missing=on_missing,
                    warnings=warnings,
                )
            _renumber_file(file_list)

    surviving: list[_SurvivingLine] = []
    for file_list in state.values():
        surviving.extend(file_list)

    in_window = tuple(
        s for s in surviving if start_time <= s.timestamp <= end_time
    )
    metrics = compute_metrics([s.gen_ratio for s in in_window], threshold=threshold)

    return AlgBResult(
        metrics=metrics,
        surviving=tuple(surviving),
        in_window_adds=in_window,
        warnings=tuple(warnings),
    )
