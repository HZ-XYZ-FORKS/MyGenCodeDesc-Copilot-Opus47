# test_us005_branch_history — US-005 branch & history conditions

Validates multi-branch / time-window behavior against Algorithm A.

## Coverage

| Test | AC | Scenario |
|---|---|---|
| `test_ac_005_1_pre_window_line_excluded` | AC-005-1 | Line committed before `startTime` is excluded from the metric even though alive at `endTime`. |
| `test_ac_005_2_multiple_merges_single_origin_each` | AC-005-2 | Three feature branches merged in sequence: each line attributes to exactly one originating commit, no double-counting. |
| `test_ac_005_3_long_lived_branch_divergence` | AC-005-3 | 6-month divergent `feature` branch touching a disjoint file: after merge, each line traces to its actual origin commit across both branches. |

AC-005-4 (shallow clone) and AC-005-5 (submodule) are documented policy
edges; they are not code-enforced.

## Mechanism

- `checkout_new_branch`, `checkout`, `merge_no_ff` from `_git_fixture.py` drive branch/merge topology.
- `in_window_adds` from `run_algorithm_a` is filtered by origin-commit timestamp, so pre-window lines are naturally excluded.
- Branch divergence test uses disjoint files to avoid merge conflicts unrelated to the AC.
