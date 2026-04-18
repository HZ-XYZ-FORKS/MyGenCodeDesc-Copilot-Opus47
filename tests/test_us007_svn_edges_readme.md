# test_us007_svn_edges

Covers SVN-specific edge cases that have no SVN binary dependency; they
exercise the library's contract that SVN records flow through validation,
Algorithm C, and JSON output unchanged.

| Test | AC | Category | Notes |
|---|---|---|---|
| `test_ac_007_3_svn_merge_blame_accepted_as_is` | AC-007-3 | Edge | SVN merge commit whose blame points back to branch revisions is accepted without any "merge imprecision" warning. Fork policy: trust SVN blame as recorded. |
| `test_ac_007_4_svn_no_rebase_amend_flags` | AC-007-4 | Edge | Three monotonic SVN revisions process cleanly — no rebase/amend checks applied for SVN input. |
| `test_ac_007_5_svn_branch_path_roundtrips` | AC-007-5 | Edge | Parametrized over `/trunk`, `/branches/feature-x`, `/branches/release/2026.04`, `/tags/v1.2.3`. Each path-shaped repoBranch is accepted by the CLI and appears verbatim in the output's `REPOSITORY.repoBranch`. |
| `test_ac_007_5_svn_record_loads_under_default_policy` | AC-007-5 side | Smoke | Confirms `load_record_from_dict` accepts SVN records under the default (non-strict) policy. |
