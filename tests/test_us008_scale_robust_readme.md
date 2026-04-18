# test_us008_scale_robust — US-008 scale, performance, robustness

## Coverage

| Test | AC | Scenario |
|---|---|---|
| `test_ac_008_3_alg_a_empty_window` | AC-008-3 | AlgA: all commits pre-window → metrics all zero, `in_window_adds` empty, no error. |
| `test_ac_008_3_alg_b_empty_window` | AC-008-3 | AlgB: only pre-window commits passed to `run_algorithm_b` → metrics all zero. |
| `test_ac_008_3_alg_c_empty_window` | AC-008-3 | AlgC: single record with `revisionTimestamp` outside window → metrics all zero. |
| `test_ac_008_3_alg_c_no_records_at_all` | AC-008-3 | AlgC with `[]` records → metrics all zero, no error. |
| `test_ac_008_4_malformed_json_reports_file_path` | AC-008-4 | CLI given a `.json` file with invalid JSON: exits 2, error message includes the file name, no output files are written. |
| `test_ac_008_4_unreadable_file_reports_file_path` | AC-008-4 | CLI given a `chmod 0` file: CLI catches `OSError`, error message includes the file name and `cannot read file`, no partial output. POSIX-only; skipped on Windows and when running as root. |
| `test_ac_008_1_alg_a_small_scale_smoke` | AC-008-1 | Regression-guard smoke: 20 commits × 10 lines via AlgA must complete in under 15 s on a developer laptop and produce the correct per-line counts. |

## Notes

- AC-008-2 (AlgC streaming over ~200 GB genCodeDesc) is not covered here: today's `run_algorithm_c_full` loads all records into memory. Streaming support is future work.
- CLI hardening for AC-008-4 lives in `cli.py`: each `read_text()` is wrapped in `try/except OSError` that re-raises as `ValidationError` with the file path (and revisionId, for AlgB patch reads).
- "No partial output is written" is guaranteed by the CLI's structure: `output_dir.mkdir(...)` runs *after* all input-side loading has succeeded, so any failure during loading exits before any output file is touched.
