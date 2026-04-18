# test_us010_logging

Covers US-010 (Diagnostics and Logging) acceptance criteria that are
code-enforceable today.

## Tests

| Test | AC | Category | Notes |
|---|---|---|---|
| `test_ac_010_1_info_default_emits_load_and_summary_phases` | AC-010-1 | Typical | Running `--log-level Info` (default) produces INFO-level records tagged with `LOAD phase` and `SUMMARY phase`. |
| `test_ac_010_4_error_on_fatal_file_failure` | AC-010-4 | Typical | Malformed JSON input yields exit code 2, ERROR record naming the file, and no partial output dir. |
| `test_ac_010_5_error_level_suppresses_info_and_warn` | AC-010-5 | Edge | Under `--log-level Error`, the package logger emits no INFO or WARN records even though `caplog` captures at DEBUG. |
| `test_ac_010_7_programmatic_log_level` | AC-010-7 | Testability | Library users can set the package logger's level directly via `logging.getLogger("aggregateGenCodeDesc").setLevel(...)`. |
| `test_ac_010_error_choice_is_accepted` | AC-010-5 side | Smoke | Confirms argparse accepts the new `Error` choice. |

## AC coverage map

- AC-010-1: this file.
- AC-010-2 (DEBUG per-file detail): partial — DEBUG emission works through
  the same logger; not asserted here because the tool's DEBUG coverage of
  individual lines is minimal.
- AC-010-3 (WARN on non-fatal anomaly): implicitly exercised by
  `test_algorithm_b.py` OnMissing.ZERO warnings path.
- AC-010-4: this file.
- AC-010-5: this file.
- AC-010-6 (structured format, stderr): current `logging.basicConfig` uses
  stderr by default; format string is set in `_configure_logging`. Not
  asserted byte-for-byte here because `caplog` intercepts at the record
  level, not the stream.
- AC-010-7: this file.

## Production-code touches

- `src/aggregateGenCodeDesc/cli.py`:
  - `--log-level` now also accepts `Error`.
  - `_configure_logging` no longer clobbers host-configured handlers
    (important for `pytest caplog`); it still raises the package-logger
    threshold per `--log-level`.
  - `_load_v2604_payload`, AlgB loader, and AlgA loader now emit a
    `"LOAD phase"` INFO record; `_log_done` emits a `"SUMMARY phase"`
    INFO record.
