# test_algorithm_c

## Purpose
Exercises `run_algorithm_c_full` — the hermetic blame-replay engine that consumes v26.04 records (each line carries its own `blameRevisionId` + `blameTimestamp`). No VCS access; ordering is purely by embedded blame metadata.

## Status
✅ 10 / 10 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| AC-AlgC-1 Typical | `test_ac_algc_1_in_window_adds_are_summed` | all adds inside window |
| AC-AlgC-2 Typical | `test_ac_algc_2_delete_removes_prior_add` | later delete drops earlier line |
| AC-AlgC-3 Typical | `test_ac_algc_3_sorts_out_of_order_input` | input unsorted → correct replay |
| AC-AlgC-4 Typical | `test_ac_algc_4_filters_by_blame_timestamp` | per-line blame filters, not record ts |
| AC-AlgC-5 Edge | `test_ac_algc_5_ignores_records_after_endtime` | post-window commits ignored |
| AC-AlgC-6 Typical | `test_ac_algc_6_add_lineRange_expands` | bulk adds via lineRange |
| AC-006-4 Fault | `test_ac_006_4_clock_skew_abort` | skew → ABORT raises |
| AC-006-4 Edge | `test_ac_006_4_clock_skew_ignore_sorts_and_continues` | skew → IGNORE sorts and runs |
| loader | `test_load_rejects_non_v2604` | wrong protocolVersion rejected |
| loader | `test_load_returns_typed_record` | `V2604Record` dataclass |

## Manual Run
```bash
python3 -m pytest tests/test_algorithm_c.py -v
```
