# test_algorithm_b

## Purpose
Exercises Algorithm B (offline diff replay): pairs v26.03 records (with fork extension `REPOSITORY.revisionTimestamp`) with per-commit unified-diff patches, applies them in timestamp order, and computes metrics. Also verifies the `OnMissing` policy branches (AC-006-1) and patch-parser rejection of rename / binary / invalid diffs.

## Status
✅ 12 / 12 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| AC-AlgB-1 Typical | `test_ac_algb_1_canonical_ten_lines` | canonical 10-line scenario via patch replay |
| AC-AlgB-2 Typical | `test_ac_algb_2_later_commit_deletes_prior_add` | delete drops earlier added line |
| AC-AlgB-3 Typical | `test_ac_algb_3_modify_transfers_ownership` | modify = delete + add ⇒ ownership to new commit |
| AC-AlgB-4 Edge | `test_ac_algb_4_prewindow_excluded` | pre-window survivors excluded from metric |
| AC-AlgB-5 Edge | `test_ac_algb_5_ignores_post_endtime_commits` | post-endTime commits ignored |
| AC-006-1 Edge | `test_ac_006_1_missing_entry_zero_default` | unattributed add ⇒ genRatio 0 + warning |
| AC-006-1 Fault | `test_ac_006_1_missing_entry_abort` | `OnMissing.ABORT` raises |
| AC-006-1 Typical | `test_ac_006_1_missing_entry_skip` | `OnMissing.SKIP` drops line |
| Loader Fault | `test_build_commit_requires_revisionTimestamp` | fork ext field required |
| AC-AlgB-6 Fault | `test_patch_rejects_rename` | rename unsupported |
| AC-AlgB-6 Fault | `test_patch_rejects_binary` | binary diff unsupported |
| Parser | `test_patch_parses_multiple_files` | multi-file unified diff |

## Manual Run
```bash
python3 -m pytest tests/test_algorithm_b.py -v
```
