# test_us009_algorithm_specific

Covers US-009 (Algorithm-Specific Behavior) acceptance criteria that were not
already exercised by the per-algorithm suites (`test_algorithm_a`,
`test_algorithm_b`, `test_algorithm_c`) or by US-002.

## Tests

| Test | AC | Category | Notes |
|---|---|---|---|
| `test_ac_009_3_alga_reports_unreachable_vcs` | AC-009-3 | Fault | Monkeypatches `list_tracked_files` to raise `GitError` with a "Could not resolve host" message and asserts it propagates through `run_algorithm_a` with the server URL preserved. |
| `test_ac_009_5_algb_rename_chain_is_rejected` | AC-009-5 | Edge | Rename is rejected at patch-parse time with "rename ... not supported" — documents current fork policy. |
| `test_ac_009_6_algb_cli_missing_patch_names_revision` | AC-009-6 | Fault | CLI-level end-to-end: 3 v26.03 records, only 2 patches on disk. CLI exits 2 and the missing revisionId `c3` is named in the ERROR log. No partial output dir. |
| `test_ac_009_8_algc_duplicate_add_later_wins` | AC-009-8 | Edge | Two records emit an add for the same `(blame.revisionId, originalFilePath, originalLine)` key; later genRatio overwrites the earlier. Single surviving line. |
| `test_ac_009_9_algc_summary_detail_mismatch_is_rejected` | AC-009-9 | Fault | v26.04 input with `SUMMARY.lineCount=5` but DETAIL has 2 add entries → `ValidationError` mentions revisionId and both numbers. |
| `test_ac_009_9_algc_summary_matching_lineCount_is_accepted` | AC-009-9 | Typical-guard | Matching `SUMMARY.lineCount` passes cleanly. |

## AC coverage map

- AC-009-1 (rename via `-M`): covered in `test_algorithm_a.py` and `test_us002_file_level.py`.
- AC-009-2 (cross-file move via `-C -C`): covered in `test_us002_file_level.py::test_ac_002_4_file_copied`.
- AC-009-3: this file.
- AC-009-4 (AlgB topological replay): covered in `test_algorithm_b.py` (commits applied in ascending timestamp order).
- AC-009-5: this file.
- AC-009-6: this file.
- AC-009-7 (AlgC add/delete surviving set): covered in `test_algorithm_c.py`.
- AC-009-8: this file.
- AC-009-9: this file.

## Production-code touches

- `src/aggregateGenCodeDesc/algorithms/alg_c.py`: `load_v2604_record` now
  validates `SUMMARY.lineCount` against the number of expanded add entries
  when the field is present (AC-009-9 ABORT policy).
