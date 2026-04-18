"""Thin wrapper around `git` CLI for Algorithm A (live blame).

Exposes only what AlgA needs:
  - list_tracked_files(rev)    → files tracked at a given revision
  - blame_file(rev, path)      → per-line BlameEntry (revisionId, orig_line)
  - commit_timestamp(rev)      → datetime of a commit

The wrapper uses `git blame --line-porcelain -M -C` so line ownership
follows renames and cross-file moves (AC-009-1, AC-009-2, AC-002-1/2).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aggregateGenCodeDesc.core.validation import ValidationError


class GitError(ValidationError):
    """git subprocess returned a non-zero exit status."""


@dataclass(frozen=True)
class BlameEntry:
    """One line of `git blame` output."""

    file_path: str            # path of the file we blamed (current name)
    line_number: int          # 1-based line number in the current file
    origin_revision: str      # 40-hex revision id that introduced the line
    origin_timestamp: datetime
    origin_file: str          # filename at the origin commit
    origin_line: int          # line number at the origin commit


def _run(cmd: list[str], *, cwd: Path) -> str:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise GitError(f"git executable not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(
            f"git {' '.join(cmd[1:])} failed (rc={exc.returncode}): "
            f"{exc.stderr.strip()}"
        ) from exc
    return proc.stdout


def list_tracked_files(cwd: Path, rev: str = "HEAD") -> list[str]:
    """Return the files tracked at `rev`, sorted.

    Gitlinks (submodules, mode 160000) are excluded — AC-005-5 specifies
    that submodule content is not part of the parent repository's metric
    scope, and `git blame` cannot operate on a gitlink anyway.
    """
    out = _run(["git", "ls-tree", "-r", rev], cwd=cwd)
    files: list[str] = []
    for line in out.splitlines():
        if not line:
            continue
        # Format: "<mode> <type> <sha>\t<path>"
        meta, _, path = line.partition("\t")
        if not path:
            continue
        mode = meta.split(" ", 1)[0]
        if mode == "160000":  # gitlink → submodule
            continue
        files.append(path)
    return sorted(files)


def commit_timestamp(cwd: Path, rev: str) -> datetime:
    out = _run(
        ["git", "show", "-s", "--format=%cI", rev],
        cwd=cwd,
    ).strip()
    if not out:
        raise GitError(f"could not resolve commit timestamp for {rev!r}")
    # git --format=%cI emits strict ISO-8601 with timezone.
    return datetime.fromisoformat(out)


def blame_file(cwd: Path, rev: str, path: str) -> list[BlameEntry]:
    """Run `git blame --line-porcelain -M -C -C -C` on `path` at `rev`.

    Three `-C` flags enable aggressive copy detection across all commits,
    which is required to trace pure file-copy scenarios (AC-002-4).
    """
    out = _run(
        ["git", "blame", "--line-porcelain",
         "-M", "-C", "-C", "-C", rev, "--", path],
        cwd=cwd,
    )
    return _parse_line_porcelain(out, file_path=path)


# ---------------------------------------------------------------------------
# Porcelain parser.
# ---------------------------------------------------------------------------
def _parse_line_porcelain(text: str, *, file_path: str) -> list[BlameEntry]:
    """Parse `git blame --line-porcelain` output into BlameEntry records.

    Each blame block starts with:
        <40-hex> <orig-line> <final-line> [<num-lines-in-group>]
    followed by header lines and then a content line prefixed with a tab.
    Git omits repeated header fields for successive lines from the same
    commit; we remember the last-seen values to fill them in.
    """
    entries: list[BlameEntry] = []
    commits: dict[str, dict[str, str]] = {}

    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        header = lines[i]
        parts = header.split(" ")
        if len(parts) < 3 or len(parts[0]) != 40:
            raise GitError(f"unexpected blame header line: {header!r}")
        sha = parts[0]
        orig_line = int(parts[1])
        final_line = int(parts[2])
        commit_meta = commits.setdefault(sha, {})
        i += 1

        # Header fields until a "\tcontent" line.
        orig_filename = commit_meta.get("filename", file_path)
        author_time = commit_meta.get("author-time")
        author_tz = commit_meta.get("author-tz", "+0000")
        while i < n and not lines[i].startswith("\t"):
            field, _, value = lines[i].partition(" ")
            if field == "filename":
                orig_filename = value
                commit_meta["filename"] = value
            elif field == "author-time":
                author_time = value
                commit_meta["author-time"] = value
            elif field == "author-tz":
                author_tz = value
                commit_meta["author-tz"] = value
            # other fields (author, summary, previous, boundary) ignored
            i += 1
        # Consume the "\tcontent" line.
        if i < n and lines[i].startswith("\t"):
            i += 1

        if author_time is None:
            raise GitError(f"blame for {sha} missing author-time")
        ts = _posix_with_tz(int(author_time), author_tz)

        entries.append(
            BlameEntry(
                file_path=file_path,
                line_number=final_line,
                origin_revision=sha,
                origin_timestamp=ts,
                origin_file=orig_filename,
                origin_line=orig_line,
            )
        )

    return entries


def _posix_with_tz(epoch: int, tz: str) -> datetime:
    """Convert (epoch, "+0800"-style tz) into a timezone-aware datetime."""
    sign = 1 if tz[0] != "-" else -1
    hh = int(tz[1:3])
    mm = int(tz[3:5])
    offset_minutes = sign * (hh * 60 + mm)
    tzinfo = timezone(__import__("datetime").timedelta(minutes=offset_minutes))
    return datetime.fromtimestamp(epoch, tz=tzinfo)
