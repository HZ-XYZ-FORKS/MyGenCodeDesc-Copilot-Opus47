"""Write aggregate result as genCodeDescProtoV26.03-shaped JSON.

Per README_UserGuide.md §3.1. DETAIL is best-effort: this first milestone
emits a single-file "aggregate" DETAIL block per (origin_file) bucket,
collapsing contiguous runs with identical genRatio into lineRange entries.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aggregateGenCodeDesc.core.metric import Metrics


@dataclass(frozen=True)
class SurvivingLineView:
    original_file: str
    original_line: int
    gen_ratio: int
    gen_method: str = "unknown"


def _group_to_detail(surviving: Iterable[SurvivingLineView]) -> list[dict]:
    by_file: dict[str, list[SurvivingLineView]] = defaultdict(list)
    for s in surviving:
        by_file[s.original_file].append(s)

    detail: list[dict] = []
    for file_name in sorted(by_file):
        lines = sorted(by_file[file_name], key=lambda x: x.original_line)
        entries: list[dict] = []
        # Collapse contiguous same-genRatio runs into lineRange.
        i = 0
        while i < len(lines):
            j = i
            while (
                j + 1 < len(lines)
                and lines[j + 1].original_line == lines[j].original_line + 1
                and lines[j + 1].gen_ratio == lines[i].gen_ratio
                and lines[j + 1].gen_method == lines[i].gen_method
            ):
                j += 1
            if j == i:
                entries.append(
                    {
                        "lineLocation": lines[i].original_line,
                        "genRatio": lines[i].gen_ratio,
                        "genMethod": lines[i].gen_method,
                    }
                )
            else:
                entries.append(
                    {
                        "lineRange": {
                            "from": lines[i].original_line,
                            "to": lines[j].original_line,
                        },
                        "genRatio": lines[i].gen_ratio,
                        "genMethod": lines[i].gen_method,
                    }
                )
            i = j + 1
        detail.append({"fileName": file_name, "codeLines": entries})
    return detail


def build_output_json(
    *,
    metrics: Metrics,
    surviving: Iterable[SurvivingLineView],
    repo_url: str,
    repo_branch: str,
    vcs_type: str,
    start_time: datetime,
    end_time: datetime,
    algorithm: str,
    scope: str,
    input_protocol_version: str,
    diagnostics: dict | None = None,
) -> dict:
    surviving_list = list(surviving)
    full_generated = sum(1 for s in surviving_list if s.gen_ratio == 100)
    partial_generated = sum(1 for s in surviving_list if 0 < s.gen_ratio < 100)

    def _iso(t: datetime) -> str:
        return t.isoformat().replace("+00:00", "Z")

    return {
        "protocolName": "generatedTextDesc",
        "protocolVersion": "26.03",
        "codeAgent": "aggregateGenCodeDesc",
        "SUMMARY": {
            "totalCodeLines": metrics.total_lines,
            "fullGeneratedCodeLines": full_generated,
            "partialGeneratedCodeLines": partial_generated,
            "totalDocLines": 0,
            "fullGeneratedDocLines": 0,
            "partialGeneratedDocLines": 0,
        },
        "DETAIL": _group_to_detail(surviving_list),
        "REPOSITORY": {
            "vcsType": vcs_type,
            "repoURL": repo_url,
            "repoBranch": repo_branch,
            "revisionId": f"aggregate:{_iso(start_time)}..{_iso(end_time)}",
        },
        "AGGREGATE": {
            "window": {"startTime": _iso(start_time), "endTime": _iso(end_time)},
            "parameters": {
                "algorithm": algorithm,
                "scope": scope,
                "threshold": metrics.mostly_ai_threshold,
                "inputProtocolVersion": input_protocol_version,
            },
            "metrics": {
                "weighted": {
                    "value": round(metrics.weighted_value, 6),
                    "numerator": round(metrics.weighted_numerator, 6),
                },
                "fullyAI": {
                    "value": round(metrics.fully_ai_value, 6),
                    "numerator": metrics.fully_ai_numerator,
                },
                "mostlyAI": {
                    "value": round(metrics.mostly_ai_value, 6),
                    "numerator": metrics.mostly_ai_numerator,
                    "threshold": metrics.mostly_ai_threshold,
                },
            },
            "diagnostics": diagnostics
            or {
                "missingRevisions": [],
                "duplicateRevisions": [],
                "clockSkewDetected": False,
                "warnings": [],
            },
        },
    }


def write_output_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
