# MyGenCodeDescBase

- BASE of genCodeDesc, used to PlayKata with CodeAgent&LLM such as Copilot+[GPT,Opus,Sonnet].
  - which means: we have WHAT&WHY of genCodeDesc in this BASE, then we fork genCodeDesc for different CodeAgent&LLM to implement WHEN&WHERE&HOW to genCodeDesc.

- Example:
  - `fork` MyGenCodeDescBase -> MyGenCodeDesc_Copilot_GPT-5.4-Xhigh

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
