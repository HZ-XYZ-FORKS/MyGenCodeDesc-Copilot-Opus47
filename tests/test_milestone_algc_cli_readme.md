# test_milestone_algc_cli

## Purpose
End-to-end milestone test: drives the `aggregateGenCodeDesc` CLI with `--algorithm C` and a temp directory of v26.04 JSON files, then asserts the emitted `genCodeDescV26.03.json` + `commitStart2EndTime.patch` are correct, and that guard-rail error paths exit with code 2.

## Status
✅ 4 / 4 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| Milestone-AlgC | `test_milestone_algc_end_to_end` | canonical scenario, asserts SUMMARY + AGGREGATE metrics + patch shape |
| AC-006-2 Fault | `test_milestone_rejects_mixed_protocol_versions` | mixed v26.03+v26.04 → exit 2 |
| AC-006-2 Fault | `test_milestone_rejects_repository_mismatch` | `REPOSITORY` ≠ CLI target → exit 2 |
| US-002 gate | `test_milestone_alg_a_not_implemented` | `--algorithm A` → exit 2 with clear message |

## Manual Run
```bash
python3 -m pytest tests/test_milestone_algc_cli.py -v
```

Reproduce the end-to-end case from a shell (after `pip install -e '.[dev]'`):
```bash
aggregateGenCodeDesc \
  --repo-url https://x/r --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-12-31T00:00:00Z \
  --threshold 60 --algorithm C \
  --gen-code-desc-dir <dir-of-v26.04.json> \
  --output-dir ./out
```
Expect `out/genCodeDescV26.03.json` and `out/commitStart2EndTime.patch`.
