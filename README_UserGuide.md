# User Guide — `aggregateGenCodeDesc` (Python, Copilot+Opus4.7 fork)

End-user facing guide for the Python implementation of `aggregateGenCodeDesc`.
Defines **WHEN** you run it, **WHERE** inputs/outputs live, and **HOW** to invoke each of the 12 (VCS × access × algorithm) cells.

- Related docs: [README.md](README.md) · [README_UserStories.md](README_UserStories.md) · [README_AlgABC.md](README_AlgABC.md) · [README_Protocol.md](README_Protocol.md)

---

## 1. Install

```bash
# from this fork
pip install -e .
# or one-shot
python -m aggregateGenCodeDesc --help
```

Requires Python 3.11+. `git` on PATH for Alg A/B over Git; `svn` on PATH for Alg A/B over SVN. Alg C requires neither.

---

## 2. Inputs

### 2.1 Required arguments

| Flag | Meaning |
|---|---|
| `--repo-url URL` | Git or SVN repository URL. For **local** mode pass a filesystem path or `file://` URL. |
| `--repo-branch NAME` | Git branch name, or SVN path (e.g. `trunk`, `branches/rel-1.0`). |
| `--start-time ISO8601` | Window start, inclusive (`2026-01-01T00:00:00Z`). |
| `--end-time ISO8601` | Window end, inclusive. |
| `--threshold N` | Integer 0..100. Used by the *Mostly AI* mode. |
| `--algorithm {A,B,C}` | Line-origin discovery strategy (see [README_AlgABC.md](README_AlgABC.md)). |
| `--scope {A,B,C,D}` | File/path filter (see [README_AlgABC.md](README_AlgABC.md)). |
| `--gen-code-desc-dir PATH` | Directory containing the sequence of genCodeDesc JSON files for this window. See §2.2. |
| `--output-dir PATH` | Directory where both output artifacts are written (created if missing). See §3. |

### 2.2 `--gen-code-desc-dir` contract

The directory contains **a sequence of genCodeDesc JSON files**, one per revision, covering `[startTime, endTime]` on `repoBranch`.

- **One protocol version per directory.** All files MUST be **v26.03** OR all **v26.04**. Mixed versions are rejected with exit code `2`.
- **Discovery** — every `*.json` file in the directory is loaded, parsed, and validated.
- **Ordering** — sorted by `revisionTimestamp` ascending (Alg C). Alg A/B use the repo's own topological order; the dir only provides `genRatio` lookup.
- **Identity** — each file's `REPOSITORY.repoURL` + `repoBranch` + `revisionId` must match the window's repo + branch. Mismatches → validation error per AC-006-2.
- **Algorithm compatibility**:

  | Algorithm | v26.03 | v26.04 |
  |---|---|---|
  | A (live blame) | ✅ | ✅ |
  | B (diff replay) | ✅ | ✅ |
  | C (embedded blame) | ❌ reject | ✅ required |

- **Missing revision policy** — controlled by `--on-missing {error,zero}` (default `error` for Alg C, `zero` for A/B). See AC-006-1.
- **Duplicate revisionId policy** — `--on-duplicate {error,last-wins}` (default `error`). See AC-006-3.
- **Clock-skew policy** (Alg C only) — `--on-clock-skew {error,warn}` (default `error`). See AC-006-4.

### 2.3 Optional arguments

| Flag | Default | Meaning |
|---|---|---|
| `--protocol-version {auto,26.03,26.04}` | `auto` | Force a single version; `auto` infers from the first file and requires all others to match. |
| `--workdir PATH` | tmpdir | Where Alg A/B may clone/checkout a remote repo. Ignored by Alg C. |
| `--blame-whitespace {respect,ignore}` | `respect` | Alg A only. Maps to `git blame -w` when `ignore`. See AC-004-3. |
| `--rename-detection {off,basic,aggressive}` | `basic` | Alg A/B Git only. Maps to `-M` / `-M -C -C`. |
| `--commit-patch-dir PATH` | none | **Alg B only.** Directory holding pre-computed per-revision diff files used for offline replay. See §2.4. |
| `--log-level {Debug,Info,Warning}` | `Info` | Stderr logging verbosity. See §2.5. |
| `--report PATH` | none | Write a human-readable summary report next to the JSON output. |

### 2.4 `--commit-patch-dir` contract (Alg B)

- **Only consumed by Alg B.** Ignored (with a warning) by Alg A and Alg C.
- One file per revision in `[startTime, endTime]`, named `<revisionId>.patch`, covering that revision's full change set against its parent on `repoBranch`.
- The directory is scanned for `*.patch` files.
- Ordering: Alg B replays in the repo's topological/parent order; the file names map revisions to diffs, not to a sort key.
- Missing revisions fall under `--on-missing`; duplicates under `--on-duplicate`.
- Makes Alg B reproducible and network-free once this directory is populated.

### 2.5 `--log-level` semantics

Stderr logging is tiered. Each level is cumulative (higher level suppresses lower detail).

| Level | What is logged |
|---|---|
| `Debug` | Everything in `Info` **plus internal debugging detail** (parser tokens, raw VCS command lines, per-file timings, hash-map stats, rejected candidates). Intended for tool developers diagnosing issues; very verbose. |
| `Info` (default) | **File loading** events (each genCodeDesc / diff file opened, parsed, accepted or rejected), **line-by-line state transfer** (per-line origin lookups, add/delete set transitions in Alg C, diff-hunk line-position tracking in Alg B), and the **final summary** (denominator, three metrics, diagnostics). |
| `Warning` | Only warnings and errors (missing/duplicate revisions, clock skew, mixed versions, degraded results). No per-file or per-line output. |

---

## 3. Output

`--output-dir PATH` receives **two artifacts**:

| File (fixed name) | What it is |
|---|---|
| `genCodeDescV26.03.json` | Aggregate result in genCodeDescProtoV26.03-shaped JSON (§3.1). |
| `commitStart2EndTime.patch` | Single cumulative unified diff covering `[startTime, endTime]` on `repoBranch` (§3.2). |

Both files are produced by **all three algorithms** (A / B / C). The patch is generated even for Alg C — see §3.2 for how Alg C obtains it without live VCS.

### 3.1 `genCodeDescV26.03.json`

Shape follows **[`Protocols/genCodeDescProtoV26.03.json`](Protocols/genCodeDescProtoV26.03.json)** (same field names, same SUMMARY / DETAIL / REPOSITORY structure). The aggregate result reuses the protocol so downstream consumers that already understand a per-revision genCodeDesc record also understand the aggregate.

Mapping from metric to protocol fields:

| Protocol field | Aggregate meaning |
|---|---|
| `protocolVersion` | `"26.03"` (the **output envelope** version; independent of the input `--gen-code-desc-dir` version). |
| `codeAgent` | `"aggregateGenCodeDesc"`. |
| `REPOSITORY.repoURL` / `repoBranch` | Echoed from `--repo-url` / `--repo-branch`. |
| `REPOSITORY.revisionId` | `"aggregate:<startTime>..<endTime>"` — a synthetic id identifying the window. |
| `SUMMARY.totalCodeLines` | Denominator — count of in-window live code lines. |
| `SUMMARY.fullGeneratedCodeLines` | Count of lines with `genRatio == 100` (numerator of *Fully AI*). |
| `SUMMARY.partialGeneratedCodeLines` | Count of lines with `0 < genRatio < 100`. |
| `SUMMARY.totalDocLines` / `fullGeneratedDocLines` / `partialGeneratedDocLines` | Same, restricted to doc files (markdown etc.). |
| `DETAIL[].fileName` | Each in-window live file. |
| `DETAIL[].codeLines[]` / `docLines[]` | Per-line `{lineLocation, genRatio, genMethod}` (or `lineRange` when contiguous), copied from the origin revision's genCodeDesc. |

Aggregate-only extensions (added as sibling top-level keys, ignored by vanilla v26.03 consumers):

| Field | Meaning |
|---|---|
| `AGGREGATE.window` | `{startTime, endTime}`. |
| `AGGREGATE.parameters` | `{algorithm, scope, threshold, inputProtocolVersion}`. |
| `AGGREGATE.metrics.weighted` | `{value, numerator}` — `Σ(genRatio/100) / totalCodeLines`. |
| `AGGREGATE.metrics.fullyAI` | `{value, numerator}` — `fullGeneratedCodeLines / totalCodeLines`. |
| `AGGREGATE.metrics.mostlyAI` | `{value, numerator, threshold}` — `count(genRatio >= T) / totalCodeLines`. |
| `AGGREGATE.diagnostics` | `{missingRevisions[], duplicateRevisions[], clockSkewDetected, warnings[]}`. |

Example (10 in-window live code lines, `genRatio = [100,100,100,100,100, 80,80,80, 30, 0]`, threshold 60):

```json
{
  "protocolName": "generatedTextDesc",
  "protocolVersion": "26.03",
  "codeAgent": "aggregateGenCodeDesc",

  "SUMMARY": {
    "totalCodeLines": 10,
    "fullGeneratedCodeLines": 5,
    "partialGeneratedCodeLines": 4,
    "totalDocLines": 0,
    "fullGeneratedDocLines": 0,
    "partialGeneratedDocLines": 0
  },

  "DETAIL": [
    {
      "fileName": "src/auth.py",
      "codeLines": [
        {"lineRange": {"from": 1, "to": 5}, "genRatio": 100, "genMethod": "codeCompletion"},
        {"lineRange": {"from": 6, "to": 8}, "genRatio":  80, "genMethod": "vibeCoding"},
        {"lineLocation": 9,                    "genRatio":  30, "genMethod": "vibeCoding"},
        {"lineLocation": 10,                   "genRatio":   0, "genMethod": "human"}
      ]
    }
  ],

  "REPOSITORY": {
    "vcsType": "git",
    "repoURL": "https://github.com/acme/foo",
    "repoBranch": "main",
    "revisionId": "aggregate:2026-01-01T00:00:00Z..2026-04-01T00:00:00Z"
  },

  "AGGREGATE": {
    "window": {
      "startTime": "2026-01-01T00:00:00Z",
      "endTime":   "2026-04-01T00:00:00Z"
    },
    "parameters": {
      "algorithm": "C",
      "scope": "A",
      "threshold": 60,
      "inputProtocolVersion": "26.04"
    },
    "metrics": {
      "weighted":  {"value": 0.77, "numerator": 7.7},
      "fullyAI":   {"value": 0.50, "numerator": 5},
      "mostlyAI":  {"value": 0.80, "numerator": 8, "threshold": 60}
    },
    "diagnostics": {
      "missingRevisions": [],
      "duplicateRevisions": [],
      "clockSkewDetected": false,
      "warnings": []
    }
  }
}
```

### 3.2 `commitStart2EndTime.patch`

A **single cumulative unified diff** representing the net change from the window's first parent to the window's end revision on `repoBranch`. Equivalent to:

```text
git diff <revJustBeforeStartTime>..<revAtEndTime> -- <scope paths>
```

- **Format**: standard unified diff (`diff --git ...` / `---` / `+++` / `@@` hunks). Applyable with `git apply` or `patch -p1`.
- **Scope**: filtered by `--scope` (same file filter applied to the JSON denominator).
- **Rename/binary**: rename detection per `--rename-detection`; binary files appear as `Binary files differ`.
- **Generated by all three algorithms**:

  | Algorithm | How the patch is produced |
  |---|---|
  | A | `git diff` / `svn diff` invoked against the working copy or remote. |
  | B | Synthesised by concatenating and squashing the per-revision diffs from `--commit-patch-dir` (topological order) into one cumulative diff. |
  | C | Synthesised from the v26.04 embedded add/delete entries: accumulated add/delete state over `[startTime, endTime]` is serialised as a unified diff. No VCS access required. |

- **Purpose**: pairs with the JSON \u2014 JSON answers *"what ratio?"*, the patch answers *"what exactly changed?"*, so the pair is auditable and reproducible without re-accessing the repo.
- **Header**: the patch begins with a comment block identifying `repoURL`, `repoBranch`, `startTime`, `endTime`, `algorithm`, `scope`, and the synthetic `aggregate:<start>..<end>` id.

Exit codes: `0` success \u00b7 `1` runtime error \u00b7 `2` input/validation error \u00b7 `3` degraded result (warnings present with `--fail-on-warn`).

---

## 4. Scenario matrix — 12 cells

Axes: **VCS** = `git` | `svn` · **Access** = `local` | `remote` · **Algorithm** = `A` | `B` | `C`.

The cells below describe prerequisites, a minimal example, and known limits. All cells consume the same `--gen-code-desc-dir` sequence described in §2.2.

### 4.1 git × local

#### git · local · A (live blame)

- **Prereqs**: working copy on disk; `git` on PATH; genCodeDescDir is v26.03 or v26.04.
- **Example**:
  ```bash
  python -m aggregateGenCodeDesc \
    --repo-url file:///srv/repos/foo.git \
    --repo-branch main \
    --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
    --threshold 60 \
    --algorithm A --scope A \
    --gen-code-desc-dir ./gcd/ \
    --output-dir ./out/
  ```
- **Limits**: shallow clone invalidates blame (AC-005-4).

#### git · local · B (offline diff replay)

- **Prereqs**: working copy with full object DB in window.
- **Limits**: deep rename chains inflate state (README scale table).

#### git · local · C (embedded blame, v26.04 only)

- **Prereqs**: **none from VCS** — `--repo-url` / `--repo-branch` are used for validation only. `--gen-code-desc-dir` must contain v26.04.
- **Limits**: trust shifts fully to codeAgent write-time correctness.

### 4.2 git × remote

#### git · remote · A

- **Prereqs**: network; tool clones to `--workdir` (or uses provider blame API if configured).
- **Example**:
  ```bash
  python -m aggregateGenCodeDesc \
    --repo-url https://github.com/acme/foo.git \
    --repo-branch main --start-time ... --end-time ... --threshold 60 \
    --algorithm A --scope A \
    --gen-code-desc-dir ./gcd/ \
    --workdir /tmp/agcd \
    --output-dir ./out/
  ```
- **Limits**: clone time dominates. Avoid `--depth` (see AC-005-4).

#### git · remote · B

- **Prereqs**: network; fetches diffs per revision in window.
- **Limits**: bandwidth-bound at scale (README scale table).

#### git · remote · C

- **Prereqs**: **no network access to the repo**. Pass `--repo-url`/`--repo-branch` only so the result JSON is self-identifying; the tool never contacts the remote.
- **Recommended** for air-gapped / batch scenarios.

### 4.3 svn × local

#### svn · local · A

- **Prereqs**: working copy; `svn` on PATH.
- **Limits**: `svn blame` imprecision on merge-originated lines (README Git-vs-SVN table).

#### svn · local · B

- **Prereqs**: working copy; uses `svn diff -rN:M`.
- **Limits**: no cross-file move detection.

#### svn · local · C

- Identical to `git · local · C` — VCS is not consulted.

### 4.4 svn × remote

#### svn · remote · A

- **Prereqs**: network; per-file `svn blame URL@REV` round-trips.
- **Limits**: server latency multiplies by file count. `repoBranch` must be the SVN path (e.g. `trunk`).

#### svn · remote · B

- **Prereqs**: network; `svn diff -rN:M URL`.
- **Limits**: large windows → many round-trips.

#### svn · remote · C

- Identical to `git · remote · C` — VCS is not consulted.

### 4.5 Cell summary

| # | VCS | Access | Alg | Needs repo at runtime? | Best for |
|---|---|---|---|---|---|
| 1 | git | local | A | yes | development loops |
| 2 | git | local | B | yes | reproducible offline replays |
| 3 | git | local | C | **no** | hermetic CI |
| 4 | git | remote | A | yes (clone) | on-demand audits |
| 5 | git | remote | B | yes (fetch) | bandwidth-OK batch |
| 6 | git | remote | C | **no** | air-gapped / large-scale |
| 7 | svn | local | A | yes | svn dev loops |
| 8 | svn | local | B | yes | svn offline replays |
| 9 | svn | local | C | **no** | hermetic CI (svn repo) |
| 10 | svn | remote | A | yes | on-demand audits (svn) |
| 11 | svn | remote | B | yes | bandwidth-OK batch (svn) |
| 12 | svn | remote | C | **no** | air-gapped (svn) |

---

## 5. Validation & error taxonomy

Mapped to [README_UserStories.md](README_UserStories.md) US-006:

| Condition | Flag | Default | Exit |
|---|---|---|---|
| Missing genCodeDesc for a revision in window | `--on-missing` | `error` (C) / `zero` (A/B) | 2 / 0 |
| `REPOSITORY` mismatch in a file | — | always reject | 2 |
| Duplicate `revisionId` | `--on-duplicate` | `error` | 2 / 0 |
| Non-monotonic `revisionTimestamp` (Alg C) | `--on-clock-skew` | `error` | 2 / 0 |
| `genRatio` outside 0..100 | — | always reject | 2 |
| Mixed protocol versions in dir | — | always reject | 2 |
| Alg C given v26.03 | — | always reject | 2 |

---

## 6. Examples

Minimal hermetic (Alg C, no VCS):
```bash
python -m aggregateGenCodeDesc \
  --repo-url https://github.com/acme/foo.git --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm C --scope A \
  --gen-code-desc-dir ./gcd-v26.04/ \
  --output-dir ./out/
```

Git local with live blame (Alg A):
```bash
python -m aggregateGenCodeDesc \
  --repo-url file:///srv/repos/foo --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm A --scope A \
  --gen-code-desc-dir ./gcd-v26.03/ \
  --blame-whitespace ignore \
  --rename-detection aggressive \
  --output-dir ./out/
```

Alg B with pre-computed diffs (no live VCS):
```bash
python -m aggregateGenCodeDesc \
  --repo-url https://github.com/acme/foo.git --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm B --scope A \
  --gen-code-desc-dir ./gcd-v26.03/ \
  --commit-patch-dir ./diffs/ \
  --log-level Debug \
  --output-dir ./out/
```

---

## 7. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime/IO error (network, disk, VCS CLI failure) |
| 2 | Input/validation error (bad args, bad genCodeDesc, mixed versions, alg/version mismatch) |
| 3 | Degraded result (warnings present and `--fail-on-warn` set) |
