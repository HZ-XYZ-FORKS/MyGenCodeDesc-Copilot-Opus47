"""Thin wrapper around `svn` CLI for Algorithm A (live blame, SVN flavour).

Exposes only what AlgA-SVN needs:
  - list_tracked_files_svn(path, rev) → files tracked at a given revision
  - blame_file_svn(path, rev, file)   → per-line BlameEntry
  - commit_timestamp_svn(path, rev)   → datetime of a revision

Notes vs the git backend:
  - SVN blame does NOT natively follow renames/moves the way `git blame
    -M -C` does. For rename-aware attribution the project uses AlgB/C.
    AlgA-SVN is therefore correct for repositories where line ownership
    is stable at the file path, which is the normal case in practice
    and is what the scale matrix exercises.
  - `origin_file` is always equal to the blamed path; `origin_line`
    equals the final line number (SVN blame is line-stable at the file).
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.core.git import BlameEntry  # reuse dataclass
from aggregateGenCodeDesc.core.validation import ValidationError


class SvnError(ValidationError):
    """svn subprocess returned a non-zero exit status."""


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise SvnError(f"svn executable not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise SvnError(
            f"svn {' '.join(cmd[1:])} failed (rc={exc.returncode}): "
            f"{exc.stderr.strip()}"
        ) from exc
    return proc.stdout


def list_tracked_files_svn(wc: Path, rev: str = "HEAD") -> list[str]:
    """Return paths tracked at `rev` in the SVN working copy `wc`, sorted.

    Uses `svn list -R -r REV` which emits one entry per line; directories
    are distinguished by a trailing '/'. We keep only files.
    """
    out = _run(["svn", "list", "-R", "-r", rev, str(wc)])
    files: list[str] = []
    for line in out.splitlines():
        if not line or line.endswith("/"):
            continue
        files.append(line)
    return sorted(files)


def blame_file_svn(wc: Path, rev: str, path: str) -> list[BlameEntry]:
    """Run `svn blame --xml -r REV` on `path` inside `wc`.

    Returns one BlameEntry per line. `origin_file` = `path` and
    `origin_line` = final line number (SVN blame is line-stable).
    """
    out = _run(
        ["svn", "blame", "--xml", "-r", rev, str(wc / path)],
    )
    return _parse_blame_xml(out, file_path=path)


def _parse_blame_xml(xml_text: str, *, file_path: str) -> list[BlameEntry]:
    root = ET.fromstring(xml_text)
    entries: list[BlameEntry] = []
    target = root.find("target")
    if target is None:
        return entries
    for entry in target.findall("entry"):
        line_no_str = entry.get("line-number")
        if not line_no_str:
            raise SvnError("blame entry missing line-number")
        line_no = int(line_no_str)
        commit = entry.find("commit")
        if commit is None:
            raise SvnError(f"blame entry for line {line_no} missing commit")
        rev_str = commit.get("revision")
        if not rev_str:
            raise SvnError(f"blame entry for line {line_no} missing revision")
        date_el = commit.find("date")
        if date_el is None or not date_el.text:
            raise SvnError(f"blame entry for line {line_no} missing date")
        ts = _parse_svn_date(date_el.text)
        entries.append(
            BlameEntry(
                file_path=file_path,
                line_number=line_no,
                origin_revision=rev_str,
                origin_timestamp=ts,
                origin_file=file_path,
                origin_line=line_no,
            )
        )
    return entries


def commit_timestamp_svn(wc: Path, rev: str) -> datetime:
    out = _run(["svn", "info", "--xml", "-r", rev, str(wc)])
    root = ET.fromstring(out)
    commit = root.find(".//commit")
    if commit is None:
        raise SvnError(f"could not resolve commit for rev {rev!r}")
    date_el = commit.find("date")
    if date_el is None or not date_el.text:
        raise SvnError(f"could not resolve commit timestamp for rev {rev!r}")
    return _parse_svn_date(date_el.text)


def _parse_svn_date(text: str) -> datetime:
    """Parse SVN's ISO-8601 timestamp (e.g. '2026-01-01T00:00:00.123456Z').

    Python's fromisoformat since 3.11 accepts the trailing 'Z'. We
    normalize defensively for older runtimes.
    """
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    # Strip excessive fractional digits (SVN may emit 6+ digits).
    if "." in t:
        head, _, tail = t.partition(".")
        # tail looks like "123456+00:00" or "123456789+00:00"
        frac = ""
        rest = tail
        for ch in tail:
            if ch.isdigit():
                frac += ch
            else:
                rest = tail[len(frac):]
                break
        else:
            rest = ""
        frac = frac[:6]  # microseconds max
        t = head + ("." + frac if frac else "") + rest
    return datetime.fromisoformat(t)
