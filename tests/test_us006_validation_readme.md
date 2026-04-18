# test_us006_validation

## Purpose
Validates input-guard rails for v26.03 records: genRatio range (AC-006-5), REPOSITORY consistency (AC-006-2), duplicate revisionId policy (AC-006-3), plus the `lineRange` expansion path in `load_record_from_dict`.

## Status
✅ 12 / 12 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| AC-006-5 Fault | `test_ac_006_5_rejects_out_of_range_genratio` | -1 and 101 rejected |
| AC-006-5 Edge | `test_ac_006_5_accepts_boundary_values` | 0 and 100 accepted |
| AC-006-2 Fault | `test_ac_006_2_rejects_repoURL_mismatch` | wrong repoURL |
| AC-006-2 Fault | `test_ac_006_2_rejects_vcsType_mismatch` | wrong vcsType |
| AC-006-2 Typical | `test_ac_006_2_accepts_matching_repository` | happy path |
| AC-006-3 Fault | `test_ac_006_3_detect_duplicate_raises_when_policy_reject` | REJECT policy |
| AC-006-3 Typical | `test_ac_006_3_detect_duplicate_last_wins_keeps_second` | LAST_WINS policy |
| AC-006-3 Edge | `test_ac_006_3_no_duplicate_returns_all` | no duplicates |
| shape | `test_policy_enums_exposed` | `OnMissing`/`OnDuplicate`/`OnClockSkew` enums |
| loader | `test_load_expands_lineRange` | `lineRange` → per-line entries |
| loader | `test_load_rejects_invalid_lineRange` | from > to rejected |
| loader | `test_load_returns_typed_record` | `GenCodeDescRecord` dataclass |

## Manual Run
```bash
python3 -m pytest tests/test_us006_validation.py -v
```
