# test_us003_commit_level — US-003 commit-level attribution

Validates that Algorithm A (live `git blame`) attributes lines correctly
across common Git history-rewriting operations. Each test builds a tiny
disposable Git repo under `tmp_path` and drives `run_algorithm_a`.

## Coverage

| Test | AC | Scenario |
|---|---|---|
| `test_ac_003_1_merge_preserves_origin` | AC-003-1 | `--no-ff` merge: feature-branch lines still trace to the feature commit, not the merge commit. |
| `test_ac_003_2_squash_merge_reattributes` | AC-003-2 | `--squash` merge: all squashed lines are attributed to the new squash commit on `main`. |
| `test_ac_003_3_cherry_pick_new_attribution` | AC-003-3 | Cherry-pick produces a new SHA; blame reports the cherry-pick commit, not the original. |
| `test_ac_003_4_revert_removes_ai_lines` | AC-003-4 | `git revert` removes the AI-generated lines from the live snapshot; `total_lines` drops accordingly. |
| `test_ac_003_5_amend_orphans_old_revision` | AC-003-5 | `commit --amend` creates a new SHA; the pre-amend revisionId becomes orphaned and its record is ignored (line gets `gen_ratio=0` + warning). |
| `test_ac_003_6_rebase_changes_revision_id` | AC-003-6 | Rebase rewrites commit SHAs; records for old SHAs are orphaned, records for new SHAs win. |

## Mechanism

- Uses the `_git_fixture` helpers: `init_repo`, `commit_file`, `checkout_new_branch`, `merge_no_ff`, `merge_squash`, `cherry_pick`, `revert`.
- AC-003-5 and AC-003-6 drive `git commit --amend` / `git rebase` via the raw `git(...)` helper since those operations are low-frequency in the fixture layer.
- All tests share a `_WINDOW` with a wide Jan-Dec 2026 window and a `_rec(rev, file, lines)` helper for building protocol records.
