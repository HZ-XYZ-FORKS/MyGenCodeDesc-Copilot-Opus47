# test_us005_shallow_and_submodule

Covers the two remaining US-005 acceptance criteria.

| Test | AC | Category | Notes |
|---|---|---|---|
| `test_ac_005_4_shallow_clone_blame_hits_boundary` | AC-005-4 | Edge | Builds a 5-commit origin repo, `git clone --depth 2` into a shallow mirror, runs AlgA. Asserts blame never reports origin SHAs outside the reachable set — pre-boundary lines are attributed to the boundary commit (git's documented behavior). |
| `test_ac_005_5_submodule_files_not_in_parent_scope` | AC-005-5 | Edge | Creates a submodule repo and a parent that embeds it at `libs/crypto`. Asserts `list_tracked_files` returns no files under `libs/crypto/` and AlgA never surfaces submodule-internal content. |

## Production-code touches

- `src/aggregateGenCodeDesc/core/git.py::list_tracked_files` now uses
  `git ls-tree -r` (without `--name-only`) and filters out mode `160000`
  gitlink entries. Without this, AlgA would crash trying to blame the
  submodule gitlink pointer.
