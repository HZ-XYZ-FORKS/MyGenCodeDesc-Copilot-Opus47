# test_us001_core_metric

## Purpose
Verifies the three core metrics (`weightedGenRatio`, `fullyAILineCount`, `mostlyAILineCount`) produced by `core.metric.compute_metrics` against the canonical 10-line scenario and edge cases (all human, all AI, empty window, boundary genRatio/threshold).

## Status
✅ 12 / 12 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| AC-001-1 Typical | `test_ac_001_1_weighted_mode_typical` | canonical scenario → weighted = 0.77 |
| AC-001-2 Typical | `test_ac_001_2_fully_ai_mode_typical` | fullyAI = 0.50 |
| AC-001-3 Typical | `test_ac_001_3_mostly_ai_mode_typical` | mostlyAI = 0.80 (threshold 60) |
| AC-001-4 Edge | `test_ac_001_4_all_human_edge` | all genRatio 0 |
| AC-001-5 Edge | `test_ac_001_5_all_fully_ai_edge` | all genRatio 100 |
| AC-001-6 Edge | `test_ac_001_6_empty_window_edge` | empty → zeros, not NaN |
| shape | `test_metrics_shape_has_all_fields` | dataclass has all 8 fields |
| AC-006-5 Fault | `test_rejects_out_of_range_genratio` | parametrized ×3 (-1, 101, 150) |
| AC-006-5 Fault | `test_rejects_out_of_range_threshold` | parametrized ×2 (-1, 101) |

## Manual Run
```bash
python3 -m pytest tests/test_us001_core_metric.py -v
```
