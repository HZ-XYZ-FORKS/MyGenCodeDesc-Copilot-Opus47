"""Minimal unified-diff parser for Algorithm B.

Supports:
  diff --git a/PATH b/PATH
  --- a/PATH
  +++ b/PATH
  @@ -old_start,old_count +new_start,new_count @@ ...
  context / '+' / '-' body lines

Not supported (kept simple by design):
  - rename / copy / binary / mode-only changes: raised as ValidationError so
    the operator can detect and handle them explicitly.
  - combined diffs (3-way merges).

The parser emits per-file hunks with per-line events (keep | add | delete),
each carrying the current old_line / new_line number, which is exactly what
AlgB needs to replay onto an in-memory surviving-line list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from aggregateGenCodeDesc.core.validation import ValidationError


class HunkEventKind(Enum):
    KEEP = "keep"
    ADD = "add"
    DELETE = "delete"


@dataclass(frozen=True)
class HunkEvent:
    kind: HunkEventKind
    old_line: int  # 1-based line number in the pre-commit state (for KEEP / DELETE)
    new_line: int  # 1-based line number in the post-commit state (for KEEP / ADD)


@dataclass(frozen=True)
class Hunk:
    old_start: int
    new_start: int
    events: tuple[HunkEvent, ...]


@dataclass(frozen=True)
class FilePatch:
    old_path: str | None  # None when /dev/null (new file)
    new_path: str | None  # None when /dev/null (deleted file)
    hunks: tuple[Hunk, ...]

    @property
    def is_new_file(self) -> bool:
        return self.old_path is None

    @property
    def is_deleted_file(self) -> bool:
        return self.new_path is None


_HUNK_RE = re.compile(
    r"^@@ -(?P<os>\d+)(?:,(?P<oc>\d+))? \+(?P<ns>\d+)(?:,(?P<nc>\d+))? @@"
)


def parse_unified_diff(text: str) -> list[FilePatch]:
    """Parse a unified diff (possibly concatenating multiple files) into FilePatch objects.

    Raises ValidationError on unsupported constructs (rename, binary, mode-only).
    """
    lines = text.splitlines()
    files: list[FilePatch] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Skip empty lines / leading comment lines (patch header etc.).
        if not line or line.startswith("#") or line.startswith("From "):
            i += 1
            continue

        if line.startswith("diff --git "):
            # Parse one file block.
            i, file_patch = _parse_file_block(lines, i)
            if file_patch is not None:
                files.append(file_patch)
            continue

        # Bare `--- a/... / +++ b/...` block (no "diff --git" header).
        if line.startswith("--- "):
            i, file_patch = _parse_file_block(lines, i)
            if file_patch is not None:
                files.append(file_patch)
            continue

        # Unknown leading line — skip.
        i += 1

    return files


def _parse_file_block(lines: list[str], i: int) -> tuple[int, FilePatch | None]:
    n = len(lines)
    old_path: str | None = None
    new_path: str | None = None

    # Skip the diff --git / index / mode lines up to --- / +++
    # Raise on renames and binaries.
    while i < n:
        line = lines[i]
        if line.startswith("rename from ") or line.startswith("rename to "):
            raise ValidationError("patch: rename detection not supported by AlgB parser")
        if line.startswith("copy from ") or line.startswith("copy to "):
            raise ValidationError("patch: copy detection not supported by AlgB parser")
        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            raise ValidationError("patch: binary diff not supported by AlgB parser")
        if line.startswith("--- "):
            old_path = _extract_path(line[4:])
            i += 1
            if i < n and lines[i].startswith("+++ "):
                new_path = _extract_path(lines[i][4:])
                i += 1
            else:
                raise ValidationError(f"patch: missing +++ line after {line!r}")
            break
        i += 1
    else:
        return i, None

    hunks: list[Hunk] = []
    while i < n:
        line = lines[i]
        if line.startswith("diff --git ") or line.startswith("--- "):
            break
        if line.startswith("@@ "):
            i, hunk = _parse_hunk(lines, i)
            hunks.append(hunk)
            continue
        # Line outside a hunk inside a file block — skip (patch formatted trailers etc.).
        i += 1

    return i, FilePatch(
        old_path=None if old_path == "/dev/null" else old_path,
        new_path=None if new_path == "/dev/null" else new_path,
        hunks=tuple(hunks),
    )


def _extract_path(raw: str) -> str:
    """`a/path/to/file` → `path/to/file`; leaves `/dev/null` untouched."""
    raw = raw.strip()
    # Strip trailing tab-metadata (timestamp) that git/patch may append.
    raw = raw.split("\t", 1)[0].strip()
    if raw == "/dev/null":
        return raw
    if raw.startswith(("a/", "b/")):
        return raw[2:]
    return raw


def _parse_hunk(lines: list[str], i: int) -> tuple[int, Hunk]:
    header = lines[i]
    m = _HUNK_RE.match(header)
    if not m:
        raise ValidationError(f"patch: malformed hunk header {header!r}")
    old_start = int(m.group("os"))
    new_start = int(m.group("ns"))
    old_count = int(m.group("oc")) if m.group("oc") else 1
    new_count = int(m.group("nc")) if m.group("nc") else 1
    i += 1

    events: list[HunkEvent] = []
    old_cursor = old_start
    new_cursor = new_start
    old_seen = 0
    new_seen = 0

    n = len(lines)
    while i < n:
        body = lines[i]
        if body.startswith("@@ ") or body.startswith("diff --git ") or body.startswith("--- "):
            break
        if body == "":
            # Empty trailing line between hunks — treat as end of this hunk.
            i += 1
            break
        tag = body[0]
        if tag == " ":
            events.append(HunkEvent(HunkEventKind.KEEP, old_cursor, new_cursor))
            old_cursor += 1
            new_cursor += 1
            old_seen += 1
            new_seen += 1
        elif tag == "-":
            events.append(HunkEvent(HunkEventKind.DELETE, old_cursor, new_cursor))
            old_cursor += 1
            old_seen += 1
        elif tag == "+":
            events.append(HunkEvent(HunkEventKind.ADD, old_cursor, new_cursor))
            new_cursor += 1
            new_seen += 1
        elif tag == "\\":
            # "\ No newline at end of file" — ignore.
            pass
        else:
            # Unknown prefix; end of hunk.
            break
        i += 1
        if old_seen >= old_count and new_seen >= new_count:
            break

    return i, Hunk(old_start=old_start, new_start=new_start, events=tuple(events))
