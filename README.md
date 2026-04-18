# MyGenCodeDesc-Copilot-Opus47

- Based on genCodeDesc, PlayKata with Copilot+Opus47.
  - here we implement WHEN&WHERE&HOW to genCodeDesc.
  - use method: CaTDD(Comment-alive Test-Driven Development) from:
    - UserStory+UserGuide -> AcceptanceCriteria -> TestCase.
    - ArchDesign -> DetailDesign -> Implementation.

---

## ======>>>WHAT WE HAVE<<<======

- We commit code to an existing **Git or SVN repository** — online or local.
  - After each revision is created, a separate process generates one `genCodeDesc` record for that revision.
- `genCodeDesc` is **external revision-level metadata** describing which lines in a commit are AI-generated.
  - It is NOT repository content — it is produced by a `codeAgent` after each revision is created.
  - One record per revision, indexed by `repoURL + repoBranch + revisionId`.
  - Each record carries per-line `genRatio` (0–100) and `genMethod` (e.g., `codeCompletion`, `vibeCoding`).
- Two protocol versions:
  - **v26.03** — records AI-attributed lines only; blame discovered at analysis time from live VCS.
  - **v26.04** — incremental add/delete with embedded blame; self-sufficient without VCS access.
- Three algorithms (A, B, C) that answer the same metric question using different line-origin discovery strategies.
- Details: [README_Protocol.md](README_Protocol.md) | [README_AlgABC.md](README_AlgABC.md) | [Protocols/](Protocols/) | [README_UserStories.md](README_UserStories.md) | [README_UserGuide.md](README_UserGuide.md)

## ======>>>WHAT WE WANT<<<======

- We want to answer one question precisely:

  > **At `endTime`, what percentage of live code lines whose current version was added or modified in `[startTime, endTime]` is attributable to AI generation?**

- The metric is defined on the **live snapshot** at `endTime` — deleted lines do not count, old versions do not count.
- The metric supports **three modes**, controlled by a threshold parameter:

  | Mode | Threshold | Question it answers | Formula (on in-window live lines) |
  |---|---|---|---|
  | **Weighted** | N/A | "How much total AI contribution?" | `Sum(genRatio/100) / totalLines` |
  | **Fully AI** | `genRatio == 100` | "How many lines are fully AI-generated?" | `Count(genRatio == 100) / totalLines` |
  | **Mostly AI** | `genRatio >= T` (e.g., 60) | "How many lines are mostly AI-generated?" | `Count(genRatio >= T) / totalLines` |

  Example — 10 in-window live lines: 5 lines at genRatio=100, 3 at 80, 1 at 30, 1 at 0:

  | Mode | Result |
  |---|---|
  | Weighted | (5×1.0 + 3×0.8 + 1×0.3 + 1×0.0) / 10 = **77%** |
  | Fully AI (==100) | 5 / 10 = **50%** |
  | Mostly AI (>=60) | 8 / 10 = **80%** |

- We want a tool named **`aggregateGenCodeDesc`** to compute this metric.
  - Language: **Python**.
  - Input: `repoURL + repoBranch + startTime + endTime + threshold` + genCodeDesc metadata.
  - Output: aggregate result in genCodeDesc protocol-shaped JSON, including all three mode values.
  - Must support Algorithm A/B/C and Scope A/B/C/D as defined in this BASE.
- This BASE defines the WHAT & WHY. Each fork implements the WHEN & WHERE & HOW for a specific CodeAgent & LLM.

## ======>>>WHY Protocol v26.03 & v26.04<<<======

- **v26.03 exists** because measuring AI ratio requires per-revision metadata that the repository itself cannot provide — the repo knows which lines survive and who last changed them, but NOT whether a line was AI-generated.
- **v26.04 exists** because v26.03 still depends on live VCS blame at analysis time. By embedding real blame into the protocol at write time, v26.04 makes the file set **self-sufficient** — enabling air-gapped, edge, and large-scale batch deployments where repository access is expensive or impossible.
- The cost of v26.04: correctness is fully trusted from the codeAgent's write-time blame. No independent VCS verification at analysis time.

## ======>>>WHY Algorithm A, B, and C<<<======

- **Algorithm A** (live blame) exists because VCS blame is the **most authoritative** source of line origin — it gives the strongest correctness guarantee and the simplest implementation path.
- **Algorithm B** (offline diff replay) exists because some environments cannot afford live repository access at analysis time, and because replaying diffs enables **history-process metrics** (churn, survival rate, added-then-deleted) that blame alone cannot provide.
- **Algorithm C** (embedded blame in v26.04) exists because it achieves **zero repository access AND zero diff replay** at runtime — the lightest possible runtime dependency, at the cost of shifting all correctness responsibility to the codeAgent at write time.
- Each algorithm is irreplaceable for its specific deployment scenario; none is universally superior.

## ======>>>WHAT WE WILL MEET<<<======

VCS conditions that affect line attribution and must be handled correctly by any fork.

### File-Level Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Pure rename** | File path changes, no content change | Blame traces through — all lines keep original origin. v26.04 has no DETAIL entries. |
| **Rename + modify** | File path changes + some lines changed | Unchanged lines keep origin via blame. Changed lines get new origin (delete old + add new in v26.04). |
| **File delete** | File removed from repo | All lines removed from live snapshot — **zero metric contribution**. v26.04 needs delete entries for every line. |
| **File copy** | File duplicated to new path | Conservative: all lines in the copy attributed to the copy commit. Lineage mode (optional): preserve origin. |
| **File move across directories** | Same as rename — path changes | Same as pure rename — blame follows it. |

### Commit-Level Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Normal commit** | Add/modify/delete lines | Straightforward: blame points to this commit for changed lines. |
| **Merge commit** | Two branches converge | Blame traces through to the **original revision** that wrote each line, regardless of merge topology. |
| **Squash merge** | Multiple commits collapsed into one | All lines attributed to the **squash commit** — original per-commit granularity is lost. genCodeDesc must describe the squash commit as a whole. |
| **Cherry-pick** | Commit applied to another branch | Creates a **new commit** with new revisionId. Blame points to the cherry-pick commit. genCodeDesc for both commits needed independently. |
| **Revert commit** | Undoes a previous commit | Reverted lines have a **new origin** (the revert commit). If AI lines are reverted, they're gone. |
| **Amend / force-push** | Rewrites published history | Old revisionId **disappears**. genCodeDesc written for the old revision is **orphaned**. v26.04 embedded blame becomes stale. |
| **Rebase** | Replays commits on new base | Every replayed commit gets a **new revisionId**. All genCodeDesc records must be regenerated. |

### Line-Level Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Line unchanged** | Same text across commits | Blame keeps pointing to the **original** origin revision. No v26.04 entries needed. |
| **AI line → human edit** | Human modifies AI-generated line | **Ownership transfers to human.** genRatio from old genCodeDesc no longer applies. |
| **Human line → AI rewrite** | AI rewrites a human line | **Ownership transfers to AI.** genRatio comes from the new genCodeDesc. |
| **Whitespace-only change** | Indentation, trailing space, etc. | Blame **may or may not** attribute to the new commit depending on VCS settings (`git blame -w`). Policy decision needed. |
| **Line ending change** | CRLF↔LF conversion (e.g., `.gitattributes` change) | Diff sees **every line** as changed. All lines get new blame origin in one commit — genCodeDesc must describe the entire file. |
| **Identical content re-added** | Line deleted in commit X, same text re-added in commit Y | **New origin** (commit Y). Same text does NOT mean same attribution — blame tracks revision, not content. |
| **Line moved within file** | Cut-paste to different line number | Blame attributes to the commit that moved it. In v26.04: delete at old position + add at new position. |

### Branch/History Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Long-lived branch** | Branch diverges far from main | Blame works correctly — traces each line to its actual origin commit on whichever branch. |
| **Multiple merges in window** | Several branches merged during `[startTime, endTime]` | Each line still has exactly one blame origin. Merge itself doesn't change line content. |
| **Commit outside window** | Line's origin commit is before `startTime` | Line is **excluded** from metric — it's live but not "changed within the window". |
| **SVN path-copy** | SVN's branch/tag mechanism | Blame behavior depends on SVN's mergeinfo handling — less reliable than Git. Edge cases exist. |
| **SVN mergeinfo** | SVN tracks merge metadata differently | `svn blame` may return imprecise results for lines from merged branches. Known limitation. |
| **Shallow clone** | `git clone --depth N` limits history | AlgA: `git blame` hits boundary — lines beyond depth shown as originating from the boundary commit (wrong origin). AlgB: diffs beyond depth unavailable. AlgC: unaffected (self-sufficient). |
| **Submodule / subtree** | Code from another repo embedded in the tree | Parent repo blame does NOT trace into submodule history. Submodule has its own `repoURL` — needs its own genCodeDesc chain. Policy decision: include or exclude. |

### Destructive / Edge Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Lost genCodeDesc** | One revision's genCodeDesc is missing | AlgA/B: lines treated as `genRatio=0` (unattributed). AlgC: **chain broken**, result corrupted. |
| **Corrupted genCodeDesc** | Wrong revisionId or wrong line mappings | Validation rules should catch mismatched `REPOSITORY` fields. Line-level errors are **silent**. |
| **Duplicate genCodeDesc** | Two records for the same revisionId | Undefined behavior. Aggregator must detect and reject (or pick-last). AlgC is especially fragile — duplicate adds inflate the surviving set. |
| **Clock skew** | Commit timestamps not monotonically increasing | AlgC sorts by `revisionTimestamp`. Non-monotonic timestamps → wrong accumulation order → wrong surviving set. Git allows arbitrary author dates. |

### Git vs SVN Differences

Most conditions above apply to both Git and SVN, but some differ significantly:

| Condition | Git | SVN | Impact on genCodeDesc |
|---|---|---|---|
| **Rename detection** | Heuristic — `git log -M`, `git blame -C`. May miss renames if content changes too much. | Explicit — `svn move` is a first-class operation, always tracked. | Git: fork may need to tune `-M` threshold. SVN: rename is reliable. |
| **Merge commit** | True merge commit with 2+ parents. `git blame` traces through merge topology correctly. | No merge commits — merge is a regular commit with `svn:mergeinfo` property. `svn blame` may return imprecise results. | Git: authoritative. SVN: treat merge-originated lines with caution. |
| **Cherry-pick** | `git cherry-pick` creates a new commit. Blame points to the cherry-pick, not the original. | `svn merge -c` — behaves similarly but mergeinfo may confuse blame. | Same conceptually, but SVN blame may attribute to wrong revision. |
| **Rebase** | `git rebase` replays commits → new revisionIds. All genCodeDesc records must be regenerated. | **Does not exist.** SVN history is immutable. | Git-only condition. SVN forks can ignore. |
| **Amend / force-push** | `git commit --amend`, `git push --force` rewrite history. Old genCodeDesc is orphaned. | **Impossible.** SVN revisions are immutable once committed. | Git-only condition. SVN forks can ignore. |
| **Shallow clone** | `git clone --depth N` limits history. Blame hits boundary → wrong origins. | **N/A.** SVN checkouts always have access to full history via server. | Git-only condition. SVN forks can ignore. |
| **Submodule / subtree** | `git submodule` or `git subtree`. Parent blame doesn't trace into submodule. | `svn:externals` — similar concept, different semantics. Blame stays within each repo. | Both need separate genCodeDesc chains. SVN externals have additional path-resolution complexity. |
| **Branch model** | Branches are lightweight refs. Branching/merging is cheap and frequent. | Branches are path copies (`/trunk`, `/branches/X`). Branching is heavier. | SVN: `repoBranch` maps to a path, not a ref name. Fork must normalize. |
| **Blame quality** | `git blame` is highly reliable. `-w` ignores whitespace. `-C -C` detects cross-file moves. | `svn blame` is adequate for basic cases. Merge-heavy histories may return imprecise results. No cross-file move detection. | SVN forks should document reduced blame reliability as a known limitation. |
| **Revision identity** | SHA-1/SHA-256 hash (40/64 hex chars). Globally unique. | Sequential integer (1, 2, 3...). Unique per repository only. | `revisionId` format differs. Validation rules must handle both. |
| **Timestamps** | Author date can be set arbitrarily (`GIT_AUTHOR_DATE`). Clock skew is possible. | Server-assigned timestamp. Monotonically increasing (per server). | Git: clock skew is a real risk for AlgC. SVN: timestamps are reliable. |

### Scale / Performance Conditions

Reference scale: **1K commits × 100 files/commit × 10K lines/file add-or-delete** in `[startTime, endTime]`.

| Dimension | Value | Derived |
|---|---|---|
| Commits in window | 1,000 | — |
| Files touched per commit | 100 | 100K file-commit pairs total |
| Lines added or deleted per file | 10,000 | 1M line entries per commit; **1B line entries** over the window |
| Distinct files at endTime | ~10,000 (upper bound) | Depends on overlap across commits |
| Lines per file at endTime | ~10,000 | Surviving set ≈ **100M lines** (upper bound) |
| genCodeDesc file size (per commit) | ~1M DETAIL entries × ~200 bytes ≈ **200 MB JSON** | 1,000 files × 200 MB = **200 GB** total genCodeDesc storage |

| Concern | AlgA (live blame) | AlgB (diff replay) | AlgC (embedded blame) |
|---|---|---|---|
| **VCS calls** | ~10K `git blame` calls (one per file at endTime). Each walks full history — **bottleneck**. | ~1K `git diff` fetches. Each returns 100 files × 10K lines = **1M lines per diff**. | **Zero** — no VCS access. |
| **CPU** | Parsing 10K blame outputs × 10K lines each = **100M blame lines** to parse. Parallelizable per file. | 1K sequential diffs × 1M lines each = **1B lines** of diff-replay. Line-position tracking across chained diffs — **cannot parallelize across commits**. | Parsing 1K JSON files × 1M entries each = **1B JSON entries**. Set insert/delete operations: **1B hash-map ops**. Parallelizable by file if sharded. |
| **Memory** | One blame result at a time per file (10K lines) — **low** (~1 MB). Parallelism multiplies: 100 concurrent = ~100 MB. | Must track line identity through 1K chained diffs. Per-file state: 10K lines × commit chain. Peak: **~10 GB** for large files with heavy churn. | Surviving set: up to **100M keys** × ~64 bytes/key = **~6 GB** hash map. Plus one genCodeDesc in-flight (~200 MB parsed). |
| **I/O** | Network: 10K blame requests. Local disk: fast. Remote VCS: **latency-bound** (10K round trips or batch API). | Network: 1K diff requests. Payload: ~1K × 1M lines × ~50 bytes = **~50 GB** raw diff data over the wire. | Disk: read 1K genCodeDesc files totaling **~200 GB**. Sequential scan — **disk throughput-bound**. SSD: ~200 GB / 2 GB/s ≈ **100 seconds** I/O alone. |
| **Sorting** | N/A — blame is per-file, order-independent. | Commits must be in topological order. 1K commits — trivial. | Must sort 1K genCodeDescs by `revisionTimestamp`. O(N log N), N=1K — **trivial**. |
| **Worst case** | 10K files × deep rename chains — blame must trace through renames across 1K commits. `git blame -C -C` is **10× slower**. | 100 files renamed every commit → line-position tracker must follow 100K renames over 1K diffs. State explosion. | 1B set operations + 6 GB hash map. If genCodeDesc files have errors (duplicate keys), surviving set is **silently corrupted**. |
| **Mitigation** | Parallelize blame (100 concurrent). `git blame --incremental` for streaming. Cache blame results. Skip files unchanged since last run. | Limit window size. Stream diffs. Shard replay by file path. Pre-compute file rename graph. | Stream genCodeDescs in order — don't load all 200 GB at once. Shard surviving set by file path. Use mmap for large JSON. Validate entry counts against SUMMARY. |
