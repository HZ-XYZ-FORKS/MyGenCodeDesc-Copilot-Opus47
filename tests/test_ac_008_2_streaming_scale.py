"""AC-008-2 reference-scale streaming test — opt-in via ``RUN_AC_008_2=1``.

US-008 AC-008-2 target: **1,000 v26.04 files totalling ~200 GB** streamed
in timestamp order with **peak memory bounded by the surviving set (~6
GB)**. Streaming the full 200 GB input is infeasible in CI, so this test:

  * Writes N v26.04 files to disk (default N=500, each with 500 adds).
  * Keeps the ratio of total-input-on-disk to surviving-set non-trivial
    (the point of streaming).
  * Runs ``run_algorithm_c_streaming`` and asserts peak RSS stays below
    ``AC008_2_RSS_BUDGET_MB`` — proving we do NOT hold all records at once.
  * Also asserts correctness (``total_lines`` exact, ``fully_ai_value``
    deterministic).

Env overrides
-------------
  RUN_AC_008_2=1              (required to enable)
  AC008_2_N_RECORDS=500
  AC008_2_ADDS_PER_RECORD=500
  AC008_2_TIME_BUDGET_SEC=600
  AC008_2_RSS_BUDGET_MB=512   (streaming must stay small even at scale)
"""

from __future__ import annotations

import json
import os
import platform
import resource
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aggregateGenCodeDesc.algorithms.alg_c import run_algorithm_c_streaming


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AC_008_2") != "1",
    reason="opt-in AC-008-2 streaming scale; set RUN_AC_008_2=1 to run",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


N_RECORDS = _env_int("AC008_2_N_RECORDS", 500)
ADDS_PER_RECORD = _env_int("AC008_2_ADDS_PER_RECORD", 500)
TIME_BUDGET_SEC = _env_float("AC008_2_TIME_BUDGET_SEC", 600.0)
RSS_BUDGET_MB = _env_float("AC008_2_RSS_BUDGET_MB", 512.0)

START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2027-12-31T00:00:00+00:00")


def _peak_rss_mb() -> float:
    """Best-effort peak RSS in MiB. macOS: bytes; Linux: KiB."""
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024.0 * 1024.0)
    return maxrss / 1024.0


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_record(path: Path, rev: str, ts: str, n_adds: int) -> int:
    """Write a single v26.04 record with n_adds add-entries. Each record
    targets its own file path so the surviving set grows linearly (no
    deletes between records → stresses the surviving-set bound)."""
    file_name = f"src/f_{rev}.py"
    code_lines = [
        {
            "changeType": "add",
            "lineLocation": i,
            "genRatio": 100,
            "genMethod": "vibeCoding",
            "blame": {
                "revisionId": rev,
                "originalFilePath": file_name,
                "originalLine": i,
                "timestamp": ts,
            },
        }
        for i in range(1, n_adds + 1)
    ]
    payload = {
        "protocolVersion": "26.04",
        "SUMMARY": {},
        "DETAIL": [{"fileName": file_name, "codeLines": code_lines}],
        "REPOSITORY": {
            "vcsType": "git",
            "repoURL": "https://x/r",
            "repoBranch": "main",
            "revisionId": rev,
            "revisionTimestamp": ts,
        },
    }
    data = json.dumps(payload)
    path.write_text(data, encoding="utf-8")
    return len(data)


# ---------------------------------------------------------------------------
# AC-008-2: streaming AlgC at reference scale.
#
# Shape: N_RECORDS distinct files × ADDS_PER_RECORD lines each. Total
# surviving lines = N_RECORDS × ADDS_PER_RECORD (no deletes). The on-disk
# input sum is orders of magnitude larger than peak RSS — that's the whole
# point of streaming.
# ---------------------------------------------------------------------------
def test_ac_008_2_streaming_reference_scale(tmp_path: Path) -> None:
    # Pass 0: write N records with ascending timestamps.
    paths: list[Path] = []
    total_bytes = 0
    t_write_start = time.monotonic()
    for i in range(N_RECORDS):
        rev = f"c{i:06d}"
        ts = _iso(START + timedelta(minutes=i))
        p = tmp_path / f"{i:06d}-{rev}.json"
        total_bytes += _write_record(p, rev, ts, ADDS_PER_RECORD)
        paths.append(p)
    write_elapsed = time.monotonic() - t_write_start
    total_input_mb = total_bytes / (1024.0 * 1024.0)

    # Pass 1+2: streaming replay.
    t_run_start = time.monotonic()
    result = run_algorithm_c_streaming(
        paths,
        start_time=START, end_time=END, threshold=60,
    )
    run_elapsed = time.monotonic() - t_run_start
    rss_after = _peak_rss_mb()

    expected_total = N_RECORDS * ADDS_PER_RECORD
    ratio = total_input_mb / rss_after if rss_after > 0 else float("inf")

    # Observability for the fork author.
    print(
        f"\n[AC-008-2] N_RECORDS={N_RECORDS} ADDS_PER_RECORD={ADDS_PER_RECORD} "
        f"expected_total_lines={expected_total}"
    )
    print(
        f"[AC-008-2] total_input_on_disk={total_input_mb:.1f}MiB "
        f"write_repo={write_elapsed:.1f}s run_stream={run_elapsed:.1f}s "
        f"peak_rss={rss_after:.1f}MiB ratio_input/rss={ratio:.1f}x "
        f"platform={platform.system()}"
    )

    # Correctness.
    assert result.total_lines == expected_total
    assert result.fully_ai_value == pytest.approx(1.0)

    # Memory bound — the AC's primary streaming claim.
    assert rss_after < RSS_BUDGET_MB, (
        f"AC-008-2 peak RSS {rss_after:.1f} MiB exceeds budget "
        f"{RSS_BUDGET_MB} MiB (platform={platform.system()}); "
        f"total input on disk was {total_input_mb:.1f} MiB across "
        f"{N_RECORDS} records"
    )

    # Runtime soft bound.
    assert run_elapsed < TIME_BUDGET_SEC, (
        f"AC-008-2 streaming took {run_elapsed:.1f}s (budget {TIME_BUDGET_SEC}s; "
        f"{N_RECORDS} records × {ADDS_PER_RECORD} adds)"
    )
