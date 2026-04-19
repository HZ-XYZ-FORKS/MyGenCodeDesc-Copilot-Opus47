"""CLI entrypoint for aggregateGenCodeDesc.

First milestone wires the Algorithm C path end-to-end:
  load v26.04 records → validate REPOSITORY → dedup → run_algorithm_c_full
  → write genCodeDescV26.03.json + commitStart2EndTime.patch

Algorithms A and B are not yet implemented and return a clear error.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.algorithms.alg_b import (
    build_commit as build_algb_commit,
    run_algorithm_b,
)
from aggregateGenCodeDesc.algorithms.alg_a import run_algorithm_a
from aggregateGenCodeDesc.algorithms.alg_c import (
    V2604Record,
    load_v2604_record,
    run_algorithm_c_full,
)
from aggregateGenCodeDesc.core.protocol import (
    OnClockSkew,
    OnDuplicate,
    OnMissing,
)
from aggregateGenCodeDesc.core.validation import (
    DuplicateRevisionError,
    ValidationError,
)
from aggregateGenCodeDesc.output.json_writer import (
    SurvivingLineView,
    build_output_json,
    write_output_json,
)
from aggregateGenCodeDesc.output.patch_writer import (
    PatchAddLine,
    build_patch_algc,
    write_patch,
)

log = logging.getLogger("aggregateGenCodeDesc")


def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {s!r}") from exc


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aggregateGenCodeDesc",
        description="Aggregate genCodeDesc records over a time window.",
    )
    p.add_argument("--repo-url", required=True)
    p.add_argument("--repo-branch", required=True)
    p.add_argument("--start-time", required=True, type=_parse_iso)
    p.add_argument("--end-time", required=True, type=_parse_iso)
    p.add_argument("--threshold", required=True, type=int)
    p.add_argument("--algorithm", required=True, choices=["A", "B", "C"])
    p.add_argument("--scope", default="A", choices=["A", "B", "C", "D"])
    p.add_argument("--gen-code-desc-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--commit-patch-dir", type=Path, default=None)
    p.add_argument("--repo-path", type=Path, default=None,
                   help="Path to the working git repository (Algorithm A).")
    p.add_argument("--end-rev", default="HEAD",
                   help="Revision to blame at (Algorithm A). Default: HEAD.")
    p.add_argument(
        "--log-level",
        default="Info",
        choices=["Debug", "Info", "Warning", "Error"],
    )
    p.add_argument(
        "--on-missing",
        default=OnMissing.ZERO.value,
        choices=[m.value for m in OnMissing],
    )
    p.add_argument(
        "--on-duplicate",
        default=OnDuplicate.REJECT.value,
        choices=[m.value for m in OnDuplicate],
    )
    p.add_argument(
        "--on-clock-skew",
        default=OnClockSkew.IGNORE.value,
        choices=[m.value for m in OnClockSkew],
    )
    return p


def _configure_logging(level: str) -> None:
    mapping = {
        "Debug": logging.DEBUG,
        "Info": logging.INFO,
        "Warning": logging.WARNING,
        "Error": logging.ERROR,
    }
    lvl = mapping[level]
    # Only install a default handler when the host process hasn't already
    # configured logging (e.g. pytest's caplog installs its own). In all
    # cases, enforce our requested level on the package logger so that
    # tests invoking main() a second time with a different --log-level
    # see the new threshold.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    log.setLevel(lvl)


def _load_v2604_payload(dir_path: Path) -> list[tuple[Path, dict, V2604Record]]:
    if not dir_path.is_dir():
        raise ValidationError(f"--gen-code-desc-dir not found: {dir_path}")
    files = sorted(dir_path.glob("*.json"))
    if not files:
        raise ValidationError(f"no *.json files in {dir_path}")

    payloads: list[tuple[Path, dict, V2604Record]] = []
    versions: set[str] = set()
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"{f}: cannot read file: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{f}: invalid JSON: {exc}") from exc
        versions.add(str(data.get("protocolVersion")))
        rec = load_v2604_record(data)
        log.debug(
            "LOAD file=%s revisionId=%s adds=%d deletes=%d",
            f.name, rec.revision_id, len(rec.adds), len(rec.deletes),
        )
        payloads.append((f, data, rec))

    if versions != {"26.04"}:
        raise ValidationError(
            f"Algorithm C requires a homogeneous v26.04 --gen-code-desc-dir; found versions {sorted(versions)}"
        )
    log.info("LOAD phase: %d v26.04 records from %s", len(payloads), dir_path)
    return payloads


def _check_repository_fields(
    payloads: list[tuple[Path, dict, V2604Record]],
    args: argparse.Namespace,
) -> str:
    """AC-006-2: reject records whose REPOSITORY contradicts the CLI target.
    Returns the common vcsType."""
    vcs_types: set[str] = set()
    for path, data, _rec in payloads:
        repo = data.get("REPOSITORY") or {}
        mismatches: list[str] = []
        if repo.get("repoURL") != args.repo_url:
            mismatches.append(f"repoURL(record={repo.get('repoURL')!r})")
        if repo.get("repoBranch") != args.repo_branch:
            mismatches.append(f"repoBranch(record={repo.get('repoBranch')!r})")
        if mismatches:
            raise ValidationError(
                f"{path.name}: REPOSITORY mismatch vs CLI target: {', '.join(mismatches)}"
            )
        vcs_types.add(str(repo.get("vcsType") or ""))
    if len(vcs_types) != 1 or "" in vcs_types:
        raise ValidationError(f"inconsistent/missing REPOSITORY.vcsType: {sorted(vcs_types)}")
    return next(iter(vcs_types))


def _dedup_records(
    records: list[V2604Record],
    policy: OnDuplicate,
) -> tuple[list[V2604Record], list[str]]:
    seen: dict[str, V2604Record] = {}
    warnings: list[str] = []
    for rec in records:
        rev = rec.revision_id
        if rev not in seen:
            seen[rev] = rec
            continue
        if policy is OnDuplicate.REJECT:
            raise DuplicateRevisionError(f"duplicate genCodeDesc for revisionId {rev}")
        log.warning("duplicate revisionId %s: last-wins applied", rev)
        warnings.append(f"duplicate revisionId {rev}: last-wins applied")
        seen[rev] = rec
    kept: list[V2604Record] = []
    emitted: set[str] = set()
    for rec in records:
        if rec.revision_id in emitted:
            continue
        kept.append(seen[rec.revision_id])
        emitted.add(rec.revision_id)
    return kept, warnings


# ---------------------------------------------------------------------------
# Algorithm C orchestration (v26.04 embedded blame).
# ---------------------------------------------------------------------------
def _run_alg_c(args: argparse.Namespace) -> int:
    log.debug("algorithm=C start")
    payloads = _load_v2604_payload(args.gen_code_desc_dir)
    vcs_type = _check_repository_fields(payloads, args)
    records = [rec for (_p, _d, rec) in payloads]
    records, dup_warnings = _dedup_records(records, OnDuplicate(args.on_duplicate))

    result = run_algorithm_c_full(
        records,
        start_time=args.start_time,
        end_time=args.end_time,
        threshold=args.threshold,
        on_clock_skew=OnClockSkew(args.on_clock_skew),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    surviving_view = [
        SurvivingLineView(
            original_file=s.file_name,
            original_line=s.line_location,
            gen_ratio=s.gen_ratio,
            gen_method=s.gen_method or "unknown",
        )
        for s in result.in_window_adds
    ]
    payload = build_output_json(
        metrics=result.metrics,
        surviving=surviving_view,
        repo_url=args.repo_url,
        repo_branch=args.repo_branch,
        vcs_type=vcs_type,
        start_time=args.start_time,
        end_time=args.end_time,
        algorithm=args.algorithm,
        scope=args.scope,
        input_protocol_version="26.04",
        diagnostics={
            "missingRevisions": [],
            "duplicateRevisions": [],
            "clockSkewDetected": False,
            "warnings": dup_warnings,
        },
    )
    write_output_json(args.output_dir / "genCodeDescV26.03.json", payload)

    patch = build_patch_algc(
        adds=[
            PatchAddLine(
                file_name=s.file_name,
                line_location=s.line_location,
                gen_ratio=s.gen_ratio,
            )
            for s in result.in_window_adds
        ],
        repo_url=args.repo_url,
        repo_branch=args.repo_branch,
        start_time=args.start_time,
        end_time=args.end_time,
        algorithm=args.algorithm,
        scope=args.scope,
    )
    write_patch(args.output_dir / "commitStart2EndTime.patch", patch)
    _log_done(result.metrics)
    return 0


# ---------------------------------------------------------------------------
# Algorithm B orchestration (offline diff replay against v26.03 + *.patch).
# ---------------------------------------------------------------------------
def _run_alg_b(args: argparse.Namespace) -> int:
    log.debug("algorithm=B start")
    if args.commit_patch_dir is None:
        raise ValidationError("Algorithm B requires --commit-patch-dir")

    gcd_dir: Path = args.gen_code_desc_dir
    patch_dir: Path = args.commit_patch_dir
    if not gcd_dir.is_dir():
        raise ValidationError(f"--gen-code-desc-dir not found: {gcd_dir}")
    if not patch_dir.is_dir():
        raise ValidationError(f"--commit-patch-dir not found: {patch_dir}")

    # 1. Load v26.03 records and pair each with <revisionId>.patch.
    record_files = sorted(gcd_dir.glob("*.json"))
    if not record_files:
        raise ValidationError(f"no *.json files in {gcd_dir}")

    versions: set[str] = set()
    vcs_types: set[str] = set()
    commits = []
    for rf in record_files:
        try:
            text = rf.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"{rf}: cannot read file: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{rf}: invalid JSON: {exc}") from exc
        versions.add(str(data.get("protocolVersion")))

        repo = data.get("REPOSITORY") or {}
        if repo.get("repoURL") != args.repo_url or repo.get("repoBranch") != args.repo_branch:
            raise ValidationError(
                f"{rf.name}: REPOSITORY mismatch vs CLI target"
            )
        vcs_types.add(str(repo.get("vcsType") or ""))

        rev = repo.get("revisionId")
        patch_path = patch_dir / f"{rev}.patch"
        if not patch_path.exists():
            raise ValidationError(
                f"no patch file for revision {rev!r}: expected {patch_path}"
            )
        try:
            patch_text = patch_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(
                f"{patch_path}: cannot read patch for revisionId {rev!r}: {exc}"
            ) from exc
        commits.append(build_algb_commit(data, patch_text))

    if versions != {"26.03"}:
        raise ValidationError(
            f"Algorithm B requires a homogeneous v26.03 --gen-code-desc-dir; found {sorted(versions)}"
        )
    if len(vcs_types) != 1 or "" in vcs_types:
        raise ValidationError(f"inconsistent/missing REPOSITORY.vcsType: {sorted(vcs_types)}")
    vcs_type = next(iter(vcs_types))

    log.info("LOAD phase: %d (record, patch) pairs for Algorithm B", len(commits))

    # 2. Replay.
    result = run_algorithm_b(
        commits,
        start_time=args.start_time,
        end_time=args.end_time,
        threshold=args.threshold,
        on_missing=OnMissing(args.on_missing),
    )

    # 3. Concatenate input patches (in timestamp order) as the cumulative
    #    commitStart2EndTime.patch — sufficient for first-milestone auditing.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sorted_commits = sorted(commits, key=lambda c: c.revision_timestamp)
    sorted_commits = [c for c in sorted_commits if c.revision_timestamp <= args.end_time]
    cumulative_parts: list[str] = [
        "# commitStart2EndTime.patch (aggregateGenCodeDesc, algorithm=B)\n",
        f"# repoURL:     {args.repo_url}\n",
        f"# repoBranch:  {args.repo_branch}\n",
        f"# startTime:   {_iso(args.start_time)}\n",
        f"# endTime:     {_iso(args.end_time)}\n",
        f"# scope:       {args.scope}\n",
        "# NOTE: Algorithm B concatenates per-commit patches in ascending\n",
        "#       revisionTimestamp order.\n",
    ]
    for c in sorted_commits:
        patch_path = patch_dir / f"{c.revision_id}.patch"
        cumulative_parts.append(
            f"\n# --- commit {c.revision_id} @ {_iso(c.revision_timestamp)} ---\n"
        )
        cumulative_parts.append(patch_path.read_text(encoding="utf-8"))
        if not cumulative_parts[-1].endswith("\n"):
            cumulative_parts.append("\n")
    write_patch(args.output_dir / "commitStart2EndTime.patch", "".join(cumulative_parts))

    # 4. JSON output.
    surviving_view = [
        SurvivingLineView(
            original_file=s.file_name,
            original_line=s.line_location,
            gen_ratio=s.gen_ratio,
            gen_method=s.gen_method or "unknown",
        )
        for s in result.in_window_adds
    ]
    payload = build_output_json(
        metrics=result.metrics,
        surviving=surviving_view,
        repo_url=args.repo_url,
        repo_branch=args.repo_branch,
        vcs_type=vcs_type,
        start_time=args.start_time,
        end_time=args.end_time,
        algorithm=args.algorithm,
        scope=args.scope,
        input_protocol_version="26.03",
        diagnostics={
            "missingRevisions": [],
            "duplicateRevisions": [],
            "clockSkewDetected": False,
            "warnings": list(result.warnings),
        },
    )
    write_output_json(args.output_dir / "genCodeDescV26.03.json", payload)
    _log_done(result.metrics)
    return 0


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _log_done(metrics) -> None:  # type: ignore[no-untyped-def]
    log.info(
        "SUMMARY phase: totalLines=%d weighted=%.4f fullyAI=%.4f mostlyAI=%.4f",
        metrics.total_lines,
        metrics.weighted_value,
        metrics.fully_ai_value,
        metrics.mostly_ai_value,
    )


# ---------------------------------------------------------------------------
# Algorithm A orchestration (live git blame).
# ---------------------------------------------------------------------------
def _run_alg_a(args: argparse.Namespace) -> int:
    log.debug("algorithm=A start")
    if args.repo_path is None:
        raise ValidationError("Algorithm A requires --repo-path")

    gcd_dir: Path = args.gen_code_desc_dir
    if not gcd_dir.is_dir():
        raise ValidationError(f"--gen-code-desc-dir not found: {gcd_dir}")
    record_files = sorted(gcd_dir.glob("*.json"))
    if not record_files:
        raise ValidationError(f"no *.json files in {gcd_dir}")

    records: list[dict] = []
    versions: set[str] = set()
    vcs_types: set[str] = set()
    for rf in record_files:
        try:
            text = rf.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"{rf}: cannot read file: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{rf}: invalid JSON: {exc}") from exc
        versions.add(str(data.get("protocolVersion")))
        repo = data.get("REPOSITORY") or {}
        if repo.get("repoURL") != args.repo_url or repo.get("repoBranch") != args.repo_branch:
            raise ValidationError(f"{rf.name}: REPOSITORY mismatch vs CLI target")
        vcs_types.add(str(repo.get("vcsType") or ""))
        records.append(data)

    if versions != {"26.03"}:
        raise ValidationError(
            f"Algorithm A requires a homogeneous v26.03 --gen-code-desc-dir; found {sorted(versions)}"
        )
    if vcs_types not in ({"git"}, {"svn"}):
        raise ValidationError(
            f"Algorithm A requires vcsType=git or vcsType=svn (homogeneous); found {sorted(vcs_types)}"
        )
    vcs_type = next(iter(vcs_types))
    log.info("LOAD phase: %d v26.03 records for Algorithm A (vcsType=%s) from %s",
             len(records), vcs_type, gcd_dir)
    if vcs_type == "git":
        result = run_algorithm_a(
            args.repo_path,
            records,
            start_time=args.start_time,
            end_time=args.end_time,
            end_rev=args.end_rev,
            threshold=args.threshold,
            on_missing=OnMissing(args.on_missing),
        )
    else:
        from aggregateGenCodeDesc.algorithms.alg_a_svn import run_algorithm_a_svn
        result = run_algorithm_a_svn(
            args.repo_path,
            records,
            start_time=args.start_time,
            end_time=args.end_time,
            end_rev=args.end_rev,
            threshold=args.threshold,
            on_missing=OnMissing(args.on_missing),
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    surviving_view = [
        SurvivingLineView(
            original_file=s.origin_file,
            original_line=s.origin_line,
            gen_ratio=s.gen_ratio,
            gen_method=s.gen_method or "unknown",
        )
        for s in result.in_window_adds
    ]
    payload = build_output_json(
        metrics=result.metrics,
        surviving=surviving_view,
        repo_url=args.repo_url,
        repo_branch=args.repo_branch,
        vcs_type=vcs_type,
        start_time=args.start_time,
        end_time=args.end_time,
        algorithm=args.algorithm,
        scope=args.scope,
        input_protocol_version="26.03",
        diagnostics={
            "missingRevisions": [],
            "duplicateRevisions": [],
            "clockSkewDetected": False,
            "warnings": list(result.warnings),
        },
    )
    write_output_json(args.output_dir / "genCodeDescV26.03.json", payload)

    patch = build_patch_algc(
        adds=[
            PatchAddLine(
                file_name=s.origin_file,
                line_location=s.origin_line,
                gen_ratio=s.gen_ratio,
            )
            for s in result.in_window_adds
        ],
        repo_url=args.repo_url,
        repo_branch=args.repo_branch,
        start_time=args.start_time,
        end_time=args.end_time,
        algorithm=args.algorithm,
        scope=args.scope,
    )
    write_patch(args.output_dir / "commitStart2EndTime.patch", patch)
    _log_done(result.metrics)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    try:
        if args.start_time > args.end_time:
            raise ValidationError("--start-time must be <= --end-time")
        if not 0 <= args.threshold <= 100:
            raise ValidationError("--threshold must be in [0, 100]")

        if args.algorithm == "C":
            return _run_alg_c(args)
        if args.algorithm == "B":
            return _run_alg_b(args)
        if args.algorithm == "A":
            return _run_alg_a(args)
        raise NotImplementedError(f"Unknown algorithm {args.algorithm!r}")

    except ValidationError as exc:
        log.error("validation error: %s", exc)
        return 2
    except NotImplementedError as exc:
        log.error("%s", exc)
        return 1
