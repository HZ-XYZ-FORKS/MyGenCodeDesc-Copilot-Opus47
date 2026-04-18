# test_us008_alg_c_streaming

Covers **AC-008-2** — the only code-enforceable acceptance criterion in
US-008 that was deferred in the earlier round. Exercises the new
`run_algorithm_c_streaming` public API added to
`src/aggregateGenCodeDesc/algorithms/alg_c.py`.

## Design recap (from `alg_c.py` docstring)

Memory cost is split into two passes:

- **Pass 1 (index)** — read each v26.04 file once, extract only
  `REPOSITORY.revisionTimestamp`, discard the rest. Peak per-file memory
  is bounded by a single record's JSON size, never the sum.
- **Pass 2 (replay)** — walk paths in ascending `revisionTimestamp` order.
  For each path: parse → apply deletes → apply adds → release. Peak live
  state is one record being parsed + the surviving-set dictionary.

Result: memory is O(peak per-file + surviving set), not O(sum of all files).

## Tests

| Test | What it proves |
|---|---|
| `test_streaming_matches_eager_metrics` | Functional parity with `run_algorithm_c` across 30 synthetic records. All four metrics agree (`total_lines`, `weighted_value`, `fully_ai_value`, `mostly_ai_value`). |
| `test_streaming_accepts_generator_input` | The public API takes an `Iterable[Path]`; passing a generator works. |
| `test_streaming_never_holds_more_than_one_record` | Via a monkeypatched `_load_single_record` wrapper, asserts that when each file is loaded, **zero** prior-record references are still alive (forced `gc.collect()` before the count). With 10 records, the alive-count series must be `[0, 0, …, 0]`. |
| `test_streaming_honors_clock_skew_abort` | AC-006-4 still fires under streaming: out-of-order input with `OnClockSkew.ABORT` raises `ValidationError("clock skew …")`. |
| `test_streaming_skips_post_endtime_records` | Records whose `revisionTimestamp > end_time` are filtered in Pass 1 and **never** opened for full parsing in Pass 2. |

## Production-code touches

- `src/aggregateGenCodeDesc/algorithms/alg_c.py`:
  - New helper `_peek_revision_timestamp(path)` — Pass 1.
  - New helper `_load_single_record(path)` — Pass 2.
  - New public API `run_algorithm_c_streaming(record_paths, *, start_time, end_time, threshold, on_clock_skew)`.

## Follow-up (not in this suite)

If aggregate input grows to the point where a **single** v26.04 file is
larger than RAM, Pass 1 and Pass 2 would need an incremental JSON parser
(`ijson` or similar). Current implementation handles the common case of
many medium-sized files with a bounded surviving set.
