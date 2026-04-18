# test_us002_file_level — US-002 file-level conditions

File-rename AC-002-1 is covered in `test_algorithm_a.py`. This suite
covers the remaining file-level acceptance criteria.

## Coverage

| Test | AC | Scenario |
|---|---|---|
| `test_ac_002_2_rename_plus_modify` | AC-002-2 | Rename + line modification in the same commit: unchanged lines retain seed origin; modified line transfers to the rename commit. |
| `test_ac_002_3_deleted_file_contributes_zero` | AC-002-3 | `git rm` removes the file from the live snapshot; no surviving line references the deleted path. |
| `test_ac_002_4_file_copied` | AC-002-4 | File copied to a new path: original keeps its seed attribution, copy is attributed to the copy commit. |

## Notes

- `git blame` is invoked with `-M -C -C -C` so copy detection works across commits that do nothing but add the copy (required by AC-002-4).
- Uses `_git_fixture` helpers: `commit_file`, `delete_file`, `copy_file`, plus raw `git(...)` for the rename+modify single-commit scenario.
