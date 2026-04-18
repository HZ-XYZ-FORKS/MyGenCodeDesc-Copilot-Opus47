# test_algorithm_a

## Purpose
Exercises Algorithm A (live `git blame -M -C` against a working repo). Uses tiny throw-away git repositories (via `tests/_git_fixture.py`) to drive real blame output. Covers rename-preserves-blame (AC-009-1 / AC-002-1), human-edit transfers ownership (AC-004-1), pre-window exclusion (AC-005-1), and the `OnMissing` policy branches (AC-006-1).

## Status
✅ 8 / 8 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| AC-AlgA-1 Typical | `test_ac_alga_1_canonical_ten_lines` | canonical 10-line scenario in one commit |
| AC-004-1 Typical | `test_ac_alga_2_human_edit_transfers_ownership` | later human edit replaces AI attribution |
| AC-009-1 / AC-002-1 Typical | `test_ac_alga_rename_preserves_blame` | `git blame -M` follows pure rename to origin commit |
| AC-005-1 Typical | `test_ac_alga_prewindow_excluded` | pre-startTime lines excluded from metric |
| AC-006-1 Edge | `test_ac_alga_missing_record_zero_default` | unknown revision ⇒ genRatio 0 + warning |
| AC-006-1 Fault | `test_ac_alga_missing_record_abort` | `OnMissing.ABORT` raises |
| AC-006-1 Typical | `test_ac_alga_missing_record_skip` | `OnMissing.SKIP` drops line |
| Guard | `test_rejects_non_git_directory` | non-git path rejected |

## Manual Run
```bash
python3 -m pytest tests/test_algorithm_a.py -v
```

> Requires `git` on PATH. Fixture repos are created under pytest's `tmp_path` and cleaned up automatically.
