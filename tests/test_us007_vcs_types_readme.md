# test_us007_vcs_types — US-007 Git vs SVN revisionId format

Enforces `revisionId` shape per `vcsType` when the loader is invoked with
`strict_revision_id=True`. The flag defaults to `False` to keep internal
tests free to use short synthetic ids like `"r1"`; production CLI paths
should enable strict validation.

## Coverage

| Test class | AC | Scenario |
|---|---|---|
| `TestAc007_1GitRevisionId` | AC-007-1 | Git accepts 40-hex SHA-1 and 64-hex SHA-256; rejects numeric, wrong length, and non-hex revisionIds. Mixed-case hex is accepted. |
| `TestAc007_2SvnRevisionId` | AC-007-2 | SVN accepts any positive integer without leading zero; rejects zero, negatives, leading-zero, and SHA-shaped ids. |

AC-007-3, AC-007-4, AC-007-5 are documentation-only acceptance criteria
(SVN merge imprecision, rebase/amend Git-only, branch-as-path) and are
not code-enforced.

## Mechanism

- `_record(vcs_type, revision_id)` builds a minimal protocol v26.03 dict.
- `load_record_from_dict(record, strict_revision_id=True)` is the system under test.
- Invalid inputs raise `ValidationError`.
