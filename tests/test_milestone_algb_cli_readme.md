# test_milestone_algb_cli

## Purpose
End-to-end milestone test for Algorithm B: drives the `aggregateGenCodeDesc` CLI with `--algorithm B` against a temp `--gen-code-desc-dir` (v26.03 records) + `--commit-patch-dir` (per-revision `.patch` files). Asserts the emitted JSON and concatenated patch, plus guard-rail failure modes.

## Status
✅ 3 / 3 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| Milestone-AlgB | `test_milestone_algb_cli_end_to_end` | 2-commit scenario (add 3 lines, then modify 1), asserts `SUMMARY.totalCodeLines == 3`, `fullyAI = weighted = 2/3`, cumulative patch contains both commit headers |
| AC-006-1 Fault | `test_milestone_algb_missing_patch_file_errors` | record without matching `<revisionId>.patch` → exit 2 |
| CLI guard | `test_milestone_algb_requires_commit_patch_dir` | `--commit-patch-dir` missing → exit 2 |

## Manual Run
```bash
python3 -m pytest tests/test_milestone_algb_cli.py -v
```

Reproduce end-to-end from a shell (after `pip install -e '.[dev]'`):
```bash
# Directory layout expected by Algorithm B:
#   gcd/<anything>.json        — v26.03 record, each has REPOSITORY.revisionId
#                                and REPOSITORY.revisionTimestamp
#   patches/<revisionId>.patch — unified diff for that commit
aggregateGenCodeDesc \
  --repo-url https://x/r --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-12-31T00:00:00Z \
  --threshold 60 --algorithm B \
  --gen-code-desc-dir ./gcd \
  --commit-patch-dir ./patches \
  --output-dir ./out
```
Expect `out/genCodeDescV26.03.json` + `out/commitStart2EndTime.patch` (cumulative, per-commit blocks in ascending `revisionTimestamp` order).
