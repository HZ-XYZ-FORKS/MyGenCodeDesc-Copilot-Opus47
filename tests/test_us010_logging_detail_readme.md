# test_us010_logging_detail

Closes the remaining US-010 gaps that complement `test_us010_logging.py`.

| Test | AC | Category | Notes |
|---|---|---|---|
| `test_ac_010_2_debug_surfaces_per_file_detail` | AC-010-2 | Typical | Under `--log-level Debug`, CLI emits `algorithm=C start`, and per-file `LOAD file=... revisionId=... adds=N deletes=M` lines naming each input. |
| `test_ac_010_3_warn_on_duplicate_records` | AC-010-3 | Typical | Two files with the same revisionId + `--on-duplicate last-wins` → WARN-level record names the offending revisionId. |
| `test_ac_010_6_format_and_stderr_routing` | AC-010-6 | Observability | End-to-end subprocess run: phase lines appear on **stderr**, not stdout, and every phase line matches the structured pattern `<timestamp> <LEVEL> aggregateGenCodeDesc <message>`. |

## Production-code touches

- `src/aggregateGenCodeDesc/cli.py`:
  - `_run_alg_a`/`_run_alg_b`/`_run_alg_c` emit a DEBUG `algorithm=X start` marker.
  - `_load_v2604_payload` emits per-file DEBUG records with revisionId + add/delete counts.
  - `_dedup_records` now emits WARN via `log.warning` in addition to appending to the diagnostics list.
