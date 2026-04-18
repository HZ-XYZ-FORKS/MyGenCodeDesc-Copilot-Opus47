# test_us004_line_level — US-004 line-level ownership

All tests drive Algorithm A (live `git blame -M -C -C -C`) against
throw-away repos and validate per-line ownership transfers.

## Coverage

| Test | AC | Scenario |
|---|---|---|
| `test_ac_004_1_ai_line_edited_by_human` | AC-004-1 | AI line edited by human: blame + genRatio move to the human commit. |
| `test_ac_004_2_human_line_rewritten_by_ai` | AC-004-2 | Human line rewritten by AI: blame + genRatio move to the AI commit. |
| `test_ac_004_3_whitespace_only_change_transfers_blame` | AC-004-3 | Whitespace-only change transfers blame under default `git blame` (no `-w`). Documented fork policy. |
| `test_ac_004_4_crlf_to_lf_reattributes_all_lines` | AC-004-4 | CRLF→LF conversion makes all lines attribute to the normalization commit. |
| `test_ac_004_5_deleted_and_readded_line` | AC-004-5 | Deleted then re-added identical text gets new attribution (the re-add commit). |
| `test_ac_004_6_line_moved_within_file` | AC-004-6 | Short single-line reorder falls below `-M`'s threshold; line attributes to the reorder commit. |

## Helpers

- Local `_edit_one_line(repo, path, line_no=, new_text=, ...)` rewrites a single 1-indexed line and commits with a deterministic date.
- `_rec(rev, file_name, lines)` builds a v26.03 record dict.
