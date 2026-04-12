# Algorithm A, B, and C — WHAT & WHY

## ======>>>SHARED GOAL<<<======

All three algorithms answer the **same question**:

> For the source-code lines that survive in the final repository snapshot at `endTime` and whose current form originated inside `[startTime, endTime]`, how much is attributable to AI?

The algorithms differ in **how they discover line origins** — not in what they measure.

---

## ======>>>ONE-GLANCE COMPARISON<<<======

| | **Algorithm A** | **Algorithm B** | **Algorithm C** |
|---|---|---|---|
| **Core technique** | Live `git`/`svn` blame | Offline diff replay | Embedded blame in genCodeDesc |
| **Repository access at runtime** | Required | Not required | Not required |
| **genCodeDesc version** | v26.03 | v26.03 | v26.04 |
| **Needs per-commit diff patch** | No | Yes | No |
| **Correctness authority** | VCS blame (highest) | Rebuilt partial blame (medium) | codeAgent write-time (trusted) |
| **Production status** | Production quality | Narrow paths active | Planned |

---

## ======>>>ALGORITHM A — Blame-Based End-Snapshot Attribution<<<======

### WHAT It Is

Algorithm A is the **primary, production-quality baseline**. It starts from the live file snapshot at `endTime`, runs `git blame` or `svn blame` on every surviving source line, and uses the blame result to discover which commit last introduced the current form of each line. Lines whose origin commit falls inside `[startTime, endTime]` are in scope. For each in-scope line, it looks up `genRatio` from the matching per-revision genCodeDesc (v26.03) record.

### WHY It Works

- **Directly answers the P0 metric** on the live snapshot.
- Rename and move detection is handled by **mature VCS blame implementations**.
- Low logical risk: blame is the **authoritative source** of line origin — no partial reconstruction needed.
- Works for both Git and SVN.

### Known Pitfalls

- Requires **live repository access** — a local checkout must be present at runtime.
- Blame performance can be slow on **very large repositories** with many large files.
- Correctness depends on VCS blame quality — SVN with complex mergeinfo may return imprecise results.
- One v26.03 file must exist for every origin revision discovered by blame.

---

## ======>>>ALGORITHM B — Incremental Lineage Reconstruction Without Blame<<<======

### WHAT It Is

Algorithm B replays an ordered sequence of **commit diff patches** (`commitDiffSet`) to reconstruct line ownership incrementally. Instead of asking the VCS "who last changed this line?", it simulates the history by applying diffs in order and tracking which commit introduced each surviving line. **No live repository access** is needed at runtime.

### WHY It Exists

- Enables **offline analysis** without a live repository checkout.
- Useful when blame is operationally slow or unavailable.
- Diff artifacts can be **pre-indexed and queried cheaply**.
- Can compute **history-process metrics** beyond live-snapshot attribution (e.g., added-then-deleted AI lines, churn, survival rate).
- Enables **deterministic replay** in test environments.

### Known Pitfalls

- Effectively **rebuilds a partial blame engine** — any gap in replay logic produces wrong attributions silently.
- One unified-diff patch file per replayed revision must exist before the run.
- Merge-aware lineage replay is **complex** — production readiness for merge-heavy histories requires explicit TDD.
- SVN path-copy and mergeinfo semantics introduce replay edge cases not yet fully covered.
- Still needs per-revision genCodeDesc v26.03 — only the blame step is removed.

---

## ======>>>ALGORITHM C — Embedded Blame, Pure genCodeDesc<<<======

### WHAT It Is

Algorithm C is a planned offline algorithm that requires **no repository access** and **no diff artifacts** at runtime. The codeAgent records only the lines added or deleted in each commit, with real VCS blame info per line, into a `genCodeDescProtoV26.04.json` file. Because each add entry carries embedded blame (`revisionId`, `originalFilePath`, `originalLine`, `timestamp`), a downstream consumer can accumulate the full surviving-line set across all files up to `endTime`, apply the `[startTime, endTime]` filter, and read `genRatio` directly.

### WHY It Exists

- **Zero VCS access** at analysis time — no checkout, no subprocess, no network.
- **Zero diff artifacts** needed — no commitDiffSet.
- Small per-commit files: only changed lines are recorded, not the full snapshot.
- Works for both Git-origin and SVN-origin blame (VCS type is embedded metadata).
- Ideal for **air-gapped, edge, or large-scale batch** deployments.

### Known Pitfalls

- Must process **every commit's file** from the beginning up to `endRevision` — a missing file in the chain corrupts the result.
- `REPOSITORY.revisionTimestamp` is **mandatory** for processing order.
- Delete entries must reference the **exact blame origin** — a mismatch silently leaves ghost lines.
- Embedded blame must be **real VCS blame** captured at write time. Synthetic, inferred, or manually edited blame breaks the contract.
- No independent VCS verification is possible during analysis — **correctness is fully trusted from the codeAgent**.
- If a force-push or amend happens after the file was written, the embedded blame is **silently stale**.

---

## ======>>>IRREPLACEABLE ADVANTAGES<<<======

Each algorithm has something the others **cannot substitute**:

- **Algorithm A** is irreplaceable for **authority and accountability** — it is the only one that relies directly on live VCS blame as the authoritative fact source, enabling trace-back to raw repository proof.
- **Algorithm B** is irreplaceable for **patch-driven historical replay** — deterministic re-execution from the same patch artifacts, history-window experiments, and process reconstruction that A and C cannot provide.
- **Algorithm C** is irreplaceable for **minimal-runtime-dependency offline scalability** — it simultaneously achieves zero repository access and zero diff replay, a deployment advantage the others cannot match.

---

## ======>>>HOW THEY RELATE<<<======

The three algorithms are **semantically equivalent** for the same scenario. The choice is driven by what is available and what trade-offs are acceptable:

| Decision Factor | Choose A | Choose B | Choose C |
|---|---|---|---|
| Live repo checkout available | Yes | — | — |
| Need authoritative VCS proof | Yes | — | — |
| Repo access is expensive/impossible | — | Yes | Yes |
| Have pre-exported diff patches | — | Yes | — |
| Want history-process metrics | — | Yes | — |
| Want minimal runtime dependencies | — | — | Yes |
| Air-gapped / edge deployment | — | — | Yes |
| codeAgent produces v26.04 with embedded blame | — | — | Yes |

---

## ======>>>HOLISTIC TRADE-OFFS<<<======

Scores 1–5, higher is better:

| Dimension | Alg A | Alg B | Alg C |
|---|---|---|---|
| Low Coupling | 2 | 4 | 5 |
| Low Complexity | 4 | 2 | 3 |
| Low Storage Footprint | 5 | 2 | 3 |
| High Maintainability | 4 | 2 | 3 |
| High Scalability | 3 | 3 | 5 |
| High Fault Tolerance | 3 | 2 | 3 |
| Correctness Explainability | 5 | 3 | 3 |

---

## ======>>>SOURCE<<<======

Distilled from [AggregateGenCodeDesc — README_IntroAlgABC.md](https://github.com/EnigmaWU/MyLLM_Arena/blob/main/MyStartups/AggregateGenCodeDesc/README_IntroAlgABC.md).

---

## ======>>>APPENDIX: WHAT IS BLAME<<<======

All three algorithms rely on **blame** — the concept that for any line in a file, you can ask: **which revision last introduced this line's current text content?**

Blame is **per-line**, not per-commit. In a file with 3 lines, each line may come from a different revision:

```
file at commit abc123:
  line 1: "int x = 0;"   → blame: revision 111aaa (3 months ago)
  line 2: "x += 1;"      → blame: revision 222bbb (1 week ago)
  line 3: "return x;"    → blame: revision abc123 (this commit)
```

This is why blame naturally handles **rename** (traces through file path changes), **merge** (traces through merged branches), and **rewrite** (points to the newer revision).

How each algorithm gets blame:

| Algorithm | Blame source |
|---|---|
| A | Live `git blame` / `svn blame` at analysis time |
| B | Reconstructed by replaying diffs (rebuilt partial blame) |
| C | Embedded in v26.04 at write time by the codeAgent |
