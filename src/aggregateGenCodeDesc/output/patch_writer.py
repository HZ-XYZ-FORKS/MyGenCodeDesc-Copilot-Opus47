"""Write commitStart2EndTime.patch.

First-milestone implementation for Algorithm C: synthesises a unified-diff
shell from the accumulated surviving add-set. Line contents are placeholders
(`<AI-generated genRatio=N>`) since v26.04 does not store raw source. Hunk
ranges and per-file diff headers are accurate — suitable for auditing
"which files / which line ranges changed in the window".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PatchAddLine:
    file_name: str
    line_location: int  # new-file line number
    gen_ratio: int


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def build_patch_algc(
    *,
    adds: Iterable[PatchAddLine],
    repo_url: str,
    repo_branch: str,
    start_time: datetime,
    end_time: datetime,
    algorithm: str,
    scope: str,
) -> str:
    header = (
        f"# commitStart2EndTime.patch (aggregateGenCodeDesc)\n"
        f"# repoURL:     {repo_url}\n"
        f"# repoBranch:  {repo_branch}\n"
        f"# startTime:   {_iso(start_time)}\n"
        f"# endTime:     {_iso(end_time)}\n"
        f"# algorithm:   {algorithm}\n"
        f"# scope:       {scope}\n"
        f"# aggregateId: aggregate:{_iso(start_time)}..{_iso(end_time)}\n"
        f"# NOTE: Algorithm C reconstructs this patch from v26.04 embedded\n"
        f"#       blame; line contents are placeholders.\n"
    )

    by_file: dict[str, list[PatchAddLine]] = defaultdict(list)
    for a in adds:
        by_file[a.file_name].append(a)

    body_parts: list[str] = []
    for file_name in sorted(by_file):
        lines = sorted(by_file[file_name], key=lambda x: x.line_location)
        body_parts.append(f"diff --git a/{file_name} b/{file_name}\n")
        body_parts.append(f"--- a/{file_name}\n")
        body_parts.append(f"+++ b/{file_name}\n")
        # Group contiguous line ranges into a single hunk.
        i = 0
        while i < len(lines):
            j = i
            while j + 1 < len(lines) and lines[j + 1].line_location == lines[j].line_location + 1:
                j += 1
            start = lines[i].line_location
            count = j - i + 1
            body_parts.append(f"@@ -{start},0 +{start},{count} @@\n")
            for line in lines[i : j + 1]:
                body_parts.append(f"+<AI-generated genRatio={line.gen_ratio}>\n")
            i = j + 1

    return header + "".join(body_parts)


def write_patch(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
