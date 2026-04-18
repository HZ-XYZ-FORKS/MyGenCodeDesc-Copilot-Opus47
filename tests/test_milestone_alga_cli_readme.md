# test_milestone_alga_cli

## Purpose
End-to-end milestone test for Algorithm A: drives the `aggregateGenCodeDesc` CLI with `--algorithm A --repo-path <git-repo>` against a fixture repo + v26.03 record dir. Asserts the emitted JSON/patch, plus the guard that a non-git `--repo-path` exits with code 2.

## Status
✅ 2 / 2 passing (2026-04-18)

## Covered
| US / AC | Test | Notes |
|---|---|---|
| Milestone-AlgA | `test_milestone_alga_cli_end_to_end` | 2-commit repo (pre-window seed, in-window add), asserts only the in-window line counts, payload `algorithm=A` |
| Guard | `test_milestone_alga_rejects_non_git_repo_path` | plain directory ⇒ exit 2 |

## Manual Run
```bash
python3 -m pytest tests/test_milestone_alga_cli.py -v
```

Reproduce end-to-end from a shell (after `pip install -e '.[dev]'`):
```bash
# Directory layout:
#   ./repo/.git                 — working git repository
#   ./gcd/*.json                — one v26.03 record per commit,
#                                 REPOSITORY.revisionId matches the actual SHA
aggregateGenCodeDesc \
  --repo-url https://x/r --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-12-31T00:00:00Z \
  --threshold 60 --algorithm A \
  --repo-path ./repo \
  --gen-code-desc-dir ./gcd \
  --output-dir ./out
```
Optional: `--end-rev <sha-or-ref>` to blame at a revision other than `HEAD`.
