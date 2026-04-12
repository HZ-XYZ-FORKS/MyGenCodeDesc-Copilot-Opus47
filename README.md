# MyGenCodeDescBase

- BASE of genCodeDesc, used to PlayKata with CodeAgent&LLM such as Copilot+[GPT,Opus,Sonnet].
  - which means: we have WHAT&WHY of genCodeDesc in this BASE, then we fork genCodeDesc for different CodeAgent&LLM to implement WHEN&WHERE&HOW to genCodeDesc.
  - use method: CaTDD(Comment-alive Test-Driven Development) from:
    - UserStory+UserGuide -> AcceptanceCriteria -> TestCase.
    - ArchDesign -> DetailDesign -> Implementation.

- Example:
  - `fork` MyGenCodeDescBase -> MyGenCodeDesc_Copilot_GPT-5.4-Xhigh_Python

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
- Details: [README_Protocol.md](README_Protocol.md) | [README_AlgABC.md](README_AlgABC.md) | [Protocols/](Protocols/)

## ======>>>WHAT WE WANT<<<======

- We want to answer one question precisely:

  > **At `endTime`, what percentage of live code lines whose current version was added or modified in `[startTime, endTime]` is attributable to AI generation?**

- The metric is defined on the **live snapshot** at `endTime` — deleted lines do not count, old versions do not count.
- The metric is **weighted** by `genRatio`, not a binary AI-or-human count.
- We want a tool named **`aggregateGenCodeDesc`** to compute this metric.
  - Language: **Python** or **C++** or **Rust** — each fork chooses one.
  - Input: `repoURL + repoBranch + startTime + endTime` + genCodeDesc metadata.
  - Output: aggregate result in genCodeDesc protocol-shaped JSON.
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
| **Line moved within file** | Cut-paste to different line number | Blame attributes to the commit that moved it. In v26.04: delete at old position + add at new position. |

### Branch/History Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Long-lived branch** | Branch diverges far from main | Blame works correctly — traces each line to its actual origin commit on whichever branch. |
| **Multiple merges in window** | Several branches merged during `[startTime, endTime]` | Each line still has exactly one blame origin. Merge itself doesn't change line content. |
| **Commit outside window** | Line's origin commit is before `startTime` | Line is **excluded** from metric — it's live but not "changed within the window". |
| **SVN path-copy** | SVN's branch/tag mechanism | Blame behavior depends on SVN's mergeinfo handling — less reliable than Git. Edge cases exist. |
| **SVN mergeinfo** | SVN tracks merge metadata differently | `svn blame` may return imprecise results for lines from merged branches. Known limitation. |

### Destructive / Edge Conditions

| Condition | What happens | Attribution impact |
|---|---|---|
| **Lost genCodeDesc** | One revision's genCodeDesc is missing | AlgA/B: lines treated as `genRatio=0` (unattributed). AlgC: **chain broken**, result corrupted. |
| **Corrupted genCodeDesc** | Wrong revisionId or wrong line mappings | Validation rules should catch mismatched `REPOSITORY` fields. Line-level errors are **silent**. |
| **Binary file in scope** | Binary file passes source extension filter | Should be excluded by scope definition — but scope only checks extension, not content. |
| **Generated code** (e.g., protobuf output) | Machine-generated code, not AI-generated | Not handled by genCodeDesc — genCodeDesc tracks AI attribution, not all code generation. Policy decision per fork. |
