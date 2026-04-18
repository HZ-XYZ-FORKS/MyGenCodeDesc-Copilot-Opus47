"""Algorithm C — hermetic, v26.04 embedded-blame aggregation.

Contract (from README_UserGuide.md and Protocols/genCodeDescProtoV26.04.json):

  1. Consume only v26.04 records from --gen-code-desc-dir.
  2. Sort records ascending by REPOSITORY.revisionTimestamp, keep those with
     revisionTimestamp <= endTime.
  3. For each record, apply DETAIL entries: deletes first, then adds.
     Identity key: (blame.revisionId, blame.originalFilePath, blame.originalLine).
  4. After accumulation, filter the surviving-line set by
     blame.timestamp in [startTime, endTime] and pass the retained genRatio
     list to core.metric.compute_metrics.

This module is VCS-free: no git/svn invocation, no network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.core.metric import Metrics, compute_metrics
from aggregateGenCodeDesc.core.protocol import OnClockSkew
from aggregateGenCodeDesc.core.validation import ValidationError


@dataclass(frozen=True)
class _SurvivingLine:
    revision_id: str
    original_file: str
    original_line: int
    gen_ratio: int
    gen_method: str
    timestamp: datetime
    file_name: str         # current-state file (from DETAIL block)
    line_location: int     # current-state line number


@dataclass(frozen=True)
class _AddEntry:
    revision_id: str
    original_file: str
    original_line: int
    gen_ratio: int
    gen_method: str
    timestamp: datetime
    file_name: str
    line_location: int


@dataclass(frozen=True)
class AlgCResult:
    """Full AlgC output: metric + surviving view + in-window add list for patch."""

    metrics: "Metrics"
    surviving: tuple[_SurvivingLine, ...]
    in_window_adds: tuple[_SurvivingLine, ...]


@dataclass(frozen=True)
class _DeleteKey:
    revision_id: str
    original_file: str
    original_line: int


@dataclass(frozen=True)
class V2604Record:
    """Parsed v26.04 record ready for AlgC replay."""

    revision_id: str
    revision_timestamp: datetime
    deletes: tuple[_DeleteKey, ...]
    adds: tuple[_AddEntry, ...]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_ts(s: str, field: str) -> datetime:
    try:
        # Support trailing Z.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValidationError(f"invalid timestamp in {field}: {s!r}") from exc


def _expand_delete(file_name: str, blame: dict) -> list[_DeleteKey]:
    rev = blame.get("revisionId")
    orig_file = blame.get("originalFilePath")
    if not rev or not orig_file:
        raise ValidationError(f"delete entry missing blame.revisionId/originalFilePath in {file_name}")

    if "originalLine" in blame:
        loc = blame["originalLine"]
        if not isinstance(loc, int) or loc < 1:
            raise ValidationError(f"invalid blame.originalLine {loc!r} in {file_name}")
        return [_DeleteKey(rev, orig_file, loc)]

    if "originalLineRange" in blame:
        rng = blame["originalLineRange"]
        lo, hi = rng.get("from"), rng.get("to")
        if not (isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi):
            raise ValidationError(f"invalid blame.originalLineRange {rng!r} in {file_name}")
        return [_DeleteKey(rev, orig_file, n) for n in range(lo, hi + 1)]

    raise ValidationError(f"delete blame missing originalLine/originalLineRange in {file_name}")


def _expand_add(file_name: str, entry: dict) -> list[_AddEntry]:
    gr = entry.get("genRatio")
    if not isinstance(gr, int) or not 0 <= gr <= 100:
        raise ValidationError(f"genRatio must be 0..100 in {file_name}, got {gr!r}")

    gen_method = entry.get("genMethod", "")

    blame = entry.get("blame") or {}
    rev = blame.get("revisionId")
    orig_file = blame.get("originalFilePath")
    ts_raw = blame.get("timestamp")
    if not rev or not orig_file or not ts_raw:
        raise ValidationError(
            f"add entry missing blame.revisionId/originalFilePath/timestamp in {file_name}"
        )
    ts = _parse_ts(ts_raw, f"{file_name}:blame.timestamp")

    orig_start = blame.get("originalLine")
    if not isinstance(orig_start, int) or orig_start < 1:
        raise ValidationError(f"invalid blame.originalLine {orig_start!r} in {file_name}")

    if "lineLocation" in entry:
        loc = entry["lineLocation"]
        if not isinstance(loc, int) or loc < 1:
            raise ValidationError(f"invalid lineLocation {loc!r} in {file_name}")
        return [_AddEntry(rev, orig_file, orig_start, gr, gen_method, ts, file_name, loc)]

    if "lineRange" in entry:
        rng = entry["lineRange"]
        lo, hi = rng.get("from"), rng.get("to")
        if not (isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi):
            raise ValidationError(f"invalid lineRange {rng!r} in {file_name}")
        count = hi - lo + 1
        return [
            _AddEntry(
                rev, orig_file, orig_start + i, gr, gen_method, ts, file_name, lo + i
            )
            for i in range(count)
        ]

    raise ValidationError(f"add entry needs lineLocation or lineRange in {file_name}")


def load_v2604_record(data: dict) -> V2604Record:
    if data.get("protocolVersion") != "26.04":
        raise ValidationError(
            f"Algorithm C requires protocolVersion 26.04, got {data.get('protocolVersion')!r}"
        )
    repo = data.get("REPOSITORY") or {}
    rev = repo.get("revisionId")
    ts_raw = repo.get("revisionTimestamp")
    if not rev or not ts_raw:
        raise ValidationError("REPOSITORY.revisionId and revisionTimestamp are required in v26.04")
    rev_ts = _parse_ts(ts_raw, "REPOSITORY.revisionTimestamp")

    deletes: list[_DeleteKey] = []
    adds: list[_AddEntry] = []
    for file_block in data.get("DETAIL") or []:
        file_name = file_block.get("fileName")
        if not file_name:
            raise ValidationError("DETAIL entry missing fileName")
        for key in ("codeLines", "docLines"):
            for entry in file_block.get(key, []) or []:
                change = entry.get("changeType")
                if change == "delete":
                    deletes.extend(_expand_delete(file_name, entry.get("blame") or {}))
                elif change == "add":
                    adds.extend(_expand_add(file_name, entry))
                else:
                    raise ValidationError(
                        f"v26.04 entry must have changeType add|delete, got {change!r} in {file_name}"
                    )

    # AC-009-9: if SUMMARY.lineCount is present, require it matches the
    # number of add entries expanded from DETAIL. Fork policy here: ABORT.
    summary = data.get("SUMMARY") or {}
    if "lineCount" in summary:
        declared = summary["lineCount"]
        actual = len(adds)
        if not isinstance(declared, int) or declared != actual:
            raise ValidationError(
                f"SUMMARY/DETAIL mismatch in record {rev!r}: "
                f"SUMMARY.lineCount={declared!r} but DETAIL has {actual} add entries"
            )

    return V2604Record(
        revision_id=str(rev),
        revision_timestamp=rev_ts,
        deletes=tuple(deletes),
        adds=tuple(adds),
    )


# ---------------------------------------------------------------------------
# Replay + metric
# ---------------------------------------------------------------------------
def run_algorithm_c(
    records: Iterable[V2604Record],
    *,
    start_time: datetime,
    end_time: datetime,
    threshold: int,
    on_clock_skew: OnClockSkew = OnClockSkew.IGNORE,
) -> Metrics:
    """Accumulate surviving lines across v26.04 records and compute metrics.

    Args:
        records: parsed v26.04 records (unsorted).
        start_time, end_time: inclusive window on blame.timestamp.
        threshold: mostlyAI threshold (0..100).
        on_clock_skew: AC-006-4 policy for non-monotonic input order.
    """
    if start_time > end_time:
        raise ValidationError(f"startTime {start_time} must be <= endTime {end_time}")

    rec_list = list(records)

    # AC-006-4: detect input-order clock skew (i.e. records provided out of
    # revisionTimestamp order). We always sort for correctness; the policy
    # only controls whether we tolerate or abort on detection.
    for a, b in zip(rec_list, rec_list[1:], strict=False):
        if b.revision_timestamp < a.revision_timestamp:
            if on_clock_skew is OnClockSkew.ABORT:
                raise ValidationError(
                    "clock skew detected: records are not in ascending revisionTimestamp order"
                )
            break

    sorted_records = sorted(rec_list, key=lambda r: r.revision_timestamp)
    sorted_records = [r for r in sorted_records if r.revision_timestamp <= end_time]

    surviving: dict[tuple[str, str, int], _SurvivingLine] = {}

    for rec in sorted_records:
        # Deletes before adds (standard diff order).
        for d in rec.deletes:
            surviving.pop((d.revision_id, d.original_file, d.original_line), None)
        for a in rec.adds:
            key = (a.revision_id, a.original_file, a.original_line)
            surviving[key] = _SurvivingLine(
                revision_id=a.revision_id,
                original_file=a.original_file,
                original_line=a.original_line,
                gen_ratio=a.gen_ratio,
                gen_method=a.gen_method,
                timestamp=a.timestamp,
                file_name=a.file_name,
                line_location=a.line_location,
            )

    in_window = [
        s.gen_ratio
        for s in surviving.values()
        if start_time <= s.timestamp <= end_time
    ]
    return compute_metrics(in_window, threshold=threshold)


def run_algorithm_c_full(
    records: Iterable[V2604Record],
    *,
    start_time: datetime,
    end_time: datetime,
    threshold: int,
    on_clock_skew: OnClockSkew = OnClockSkew.IGNORE,
) -> AlgCResult:
    """Like run_algorithm_c but returns surviving view + in-window adds too."""
    if start_time > end_time:
        raise ValidationError(f"startTime {start_time} must be <= endTime {end_time}")

    rec_list = list(records)
    for a, b in zip(rec_list, rec_list[1:], strict=False):
        if b.revision_timestamp < a.revision_timestamp:
            if on_clock_skew is OnClockSkew.ABORT:
                raise ValidationError(
                    "clock skew detected: records are not in ascending revisionTimestamp order"
                )
            break

    sorted_records = sorted(rec_list, key=lambda r: r.revision_timestamp)
    sorted_records = [r for r in sorted_records if r.revision_timestamp <= end_time]

    surviving: dict[tuple[str, str, int], _SurvivingLine] = {}
    for rec in sorted_records:
        for d in rec.deletes:
            surviving.pop((d.revision_id, d.original_file, d.original_line), None)
        for a in rec.adds:
            key = (a.revision_id, a.original_file, a.original_line)
            surviving[key] = _SurvivingLine(
                revision_id=a.revision_id,
                original_file=a.original_file,
                original_line=a.original_line,
                gen_ratio=a.gen_ratio,
                gen_method=a.gen_method,
                timestamp=a.timestamp,
                file_name=a.file_name,
                line_location=a.line_location,
            )

    in_window = tuple(
        s for s in surviving.values() if start_time <= s.timestamp <= end_time
    )
    metrics = compute_metrics([s.gen_ratio for s in in_window], threshold=threshold)
    return AlgCResult(
        metrics=metrics,
        surviving=tuple(surviving.values()),
        in_window_adds=in_window,
    
            )

    in_window = [
        s.gen_ratio
        for s in surviving.values()
        if start_time <= s.timestamp <= end_time
    ]
    return compute_metrics(in_window, threshold=threshold)


# ---------------------------------------------------------------------------
# Streaming replay (AC-008-2)
# ---------------------------------------------------------------------------
# Memory contract (design note):
#
#   The eager run_algorithm_c / run_algorithm_c_full APIs hold every parsed
#   V2604Record in memory simultaneously (sorted list). For aggregate inputs
#   larger than a few hundred MB that becomes prohibitive.
#
#   run_algorithm_c_streaming breaks the memory cost into two pieces:
#
#     Pass 1 (index): read each file once, extract only
#       REPOSITORY.revisionTimestamp, and discard the rest. Peak per-file
#       memory is bounded by a single record's JSON size, never the sum.
#
#     Pass 2 (replay): walk paths in ascending revisionTimestamp order.
#       For each path: parse the record → apply deletes → apply adds →
#       release. Peak live state is: one record being parsed + the
#       surviving-set dictionary (size = number of currently alive lines,
#       typically << total input size).
#
#   For genuinely streaming JSON parsing (single file >> RAM), a future
#   refactor could use ijson; today Pass 1/Pass 2 already gives O(peak
#   per-file + surviving set) instead of O(sum of all files).
# ---------------------------------------------------------------------------


def _peek_revision_timestamp(path: Path) -> datetime:
    """Pass-1 helper: load a v26.04 file and return only its REPOSITORY
    revisionTimestamp. The full dict is discarded on return."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ValidationError(f"{path}: cannot read file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc

    if data.get("protocolVersion") != "26.04":
        raise ValidationError(
            f"{path}: Algorithm C requires protocolVersion 26.04, "
            f"got {data.get('protocolVersion')!r}"
        )
    repo = data.get("REPOSITORY") or {}
    ts_raw = repo.get("revisionTimestamp")
    if not ts_raw:
        raise ValidationError(
            f"{path}: REPOSITORY.revisionTimestamp is required in v26.04"
        )
    return _parse_ts(ts_raw, f"{path}:REPOSITORY.revisionTimestamp")


def _load_single_record(path: Path) -> V2604Record:
    """Pass-2 helper: load one v26.04 file and parse it into a V2604Record.
    Caller should let the record go out of scope immediately after replay."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ValidationError(f"{path}: cannot read file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    return load_v2604_record(data)


def run_algorithm_c_streaming(
    record_paths: Iterable[Path],
    *,
    start_time: datetime,
    end_time: datetime,
    threshold: int,
    on_clock_skew: OnClockSkew = OnClockSkew.IGNORE,
) -> Metrics:
    """Memory-bounded AlgC: load v26.04 records from disk one at a time.

    Produces the same Metrics as run_algorithm_c over an equivalent eager
    input. Peak memory is bounded by the surviving-set size plus one
    record being parsed.

    Args:
        record_paths: iterable of Path objects to v26.04 JSON files. Can be
            a generator; it is materialized into a list exactly once.
        start_time, end_time: inclusive window on blame.timestamp.
        threshold: mostlyAI threshold (0..100).
        on_clock_skew: AC-006-4 policy for non-monotonic input order.
    """
    if start_time > end_time:
        raise ValidationError(f"startTime {start_time} must be <= endTime {end_time}")

    paths = [Path(p) for p in record_paths]

    # Pass 1: index timestamps only.
    indexed: list[tuple[datetime, Path]] = []
    for p in paths:
        ts = _peek_revision_timestamp(p)
        indexed.append((ts, p))

    # AC-006-4: detect clock skew in the original iteration order.
    for (ts_a, _), (ts_b, _) in zip(indexed, indexed[1:]):
        if ts_b < ts_a:
            if on_clock_skew is OnClockSkew.ABORT:
                raise ValidationError(
                    "clock skew detected: records are not in ascending revisionTimestamp order"
                )
            break

    # Keep only paths whose revisionTimestamp falls at or before end_time,
    # then sort ascending by timestamp.
    indexed = [(ts, p) for ts, p in indexed if ts <= end_time]
    indexed.sort(key=lambda t: t[0])

    # Pass 2: streaming replay. `rec` goes out of scope each iteration.
    surviving: dict[tuple[str, str, int], _SurvivingLine] = {}
    for _ts, p in indexed:
        rec = _load_single_record(p)
        for d in rec.deletes:
            surviving.pop((d.revision_id, d.original_file, d.original_line), None)
        for a in rec.adds:
            key = (a.revision_id, a.original_file, a.original_line)
            surviving[key] = _SurvivingLine(
                revision_id=a.revision_id,
                original_file=a.original_file,
                original_line=a.original_line,
                gen_ratio=a.gen_ratio,
                gen_method=a.gen_method,
                timestamp=a.timestamp,
                file_name=a.file_name,
                line_location=a.line_location,
            )
        del rec

    in_window = [
        s.gen_ratio
        for s in surviving.values()
        if start_time <= s.timestamp <= end_time
    ]
    return compute_metrics(in_window, threshold=threshold)
