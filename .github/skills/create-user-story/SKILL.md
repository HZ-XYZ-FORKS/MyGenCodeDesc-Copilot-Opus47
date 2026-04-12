---
name: create-user-story
description: >-
  Create BDD-style user stories with GIVEN/WHEN/THEN acceptance criteria.
  Use when starting a new feature, defining requirements, or translating
  a rough idea into testable specifications before implementation.
---

# Create User Story (BDD Style)

## Overview

Turn a rough feature idea into a structured user story with BDD-style
acceptance criteria. Every story must be testable — if you can't write
GIVEN/WHEN/THEN scenarios for it, the requirement is too vague.

**Core principle:** A user story without acceptance criteria is a wish,
not a requirement.

## When to Use

- New feature request
- Bug report that needs specification
- Refactoring that changes observable behavior
- Any work item before `test-driven-development` kicks in

## When NOT to Use

- Pure internal refactoring with no behavior change
- Configuration-only changes
- Documentation updates

## Workflow

```
1. CAPTURE    Who wants what and why?
2. SPLIT      Too big? Break into smaller stories.
3. SPECIFY    Write GIVEN/WHEN/THEN scenarios.
4. VALIDATE   Can each scenario become a test?
5. OUTPUT     Save the story file.
```

## Step 1 — CAPTURE the Story

Use the canonical format:

```
AS A <role>,
I WANT <capability>,
SO THAT <benefit>.
```

**Rules:**
- `<role>` MUST be a role already defined in one of these project files:
  `README.md`, `README_ArchDesign.md`, or `README_Stakeholders.md`.
  If the role is NOT found in any of these files, **STOP immediately** and
  ask the user to define and document the role before proceeding.
  Do NOT invent or accept undefined roles.
- `<role>` is a real user or system actor, not "a user"
- `<capability>` is a concrete action, not a vague goal
- `<benefit>` explains WHY — if you can't state the benefit, question the story

<Good>
```
AS A codebase maintainer,
I WANT to see what percentage of each file was AI-generated,
SO THAT I can prioritize review effort on high-AI-ratio files.
```
Concrete role, specific action, clear business value
</Good>

<Bad>
```
AS A user,
I WANT the system to be better,
SO THAT it is more useful.
```
Vague role, no concrete action, circular benefit
</Bad>

## Step 2 — SPLIT if Too Big

A story is too big if:
- It takes more than a few days to implement
- It has more than 5 Acceptance Criteria (AC)
- It contains "and" connecting unrelated capabilities

Split by:
| Strategy | Example |
|----------|---------|
| By operation | "CRUD" → separate Create, Read, Update, Delete stories |
| By data variation | "support all formats" → one story per format |
| By persona | "users and admins" → separate stories |
| By happy/sad path | "login" → successful login + failed login stories |

## Step 3 — SPECIFY with GIVEN/WHEN/THEN

### AC Categories

Design Acceptance Criteria from these categories:

| Group | Category | Description |
|-------|----------|-------------|
| **ValidFunc** | Typical / HappyPath | Normal usage, expected inputs, standard flow |
| **ValidFunc** | Edge | Boundary values, empty collections, max limits, off-by-one |
| **InvalidFunc** | Misuse | Wrong input types, unauthorized access, invalid sequences |
| **InvalidFunc** | Fault | Network failure, timeout, corrupt data, disk full, OOM |
| — | StateMachine | State transitions, illegal transitions, terminal states |
| — | Concurrency | Race conditions, deadlocks, parallel mutations |
| — | Performance | Latency thresholds, throughput limits, resource bounds |
| — | Robust | Recovery, retry, graceful degradation, idempotency |
| — | Observability | Logging, audit trail, metrics emission, traceability |
| — | Testability | Mock-friendly boundaries, deterministic output, test isolation |

**Rules for category coverage:**
- Every US MUST have at least 1 AC from **Typical** (ValidFunc)
- Every US MUST have at least 1 AC from **Edge** OR **Misuse** OR **Fault**
- Pick additional categories as relevant — not every US needs all 8
- Tag each AC with its category: `[Typical]`, `[Edge]`, `[Misuse]`, `[Fault]`,
  `[StateMachine]`, `[Concurrency]`, `[Performance]`, `[Robust]`,
  `[Observability]`, `[Testability]`

Each acceptance criterion is a **scenario** in BDD format:

```gherkin
Scenario: <descriptive name>
  GIVEN <precondition — the world before the action>
  AND <additional precondition if needed>
  WHEN <action — what the actor does>
  AND <additional action if needed>
  THEN <outcome — observable result>
  AND <additional outcome if needed>
```

**Rules:**
- **GIVEN** — testable precondition, not implementation detail
- **WHEN** — a single user/system action
- **THEN** — observable outcome, not internal state
- Each scenario tests ONE behavior
- Use concrete values, not "valid input"

<Good>
```gherkin
Scenario: [Typical] Calculate weighted AI ratio for a file with mixed authorship
  GIVEN a file "auth.py" with 100 lines
  AND line 1-40 have genRatio 100 (fully AI-generated)
  AND line 41-70 have genRatio 60 (AI-assisted)
  AND line 71-100 have genRatio 0 (human-written)
  WHEN the weighted AI ratio is calculated
  THEN the result is 58.0%

Scenario: [Edge] Report file as "Fully AI" when all lines are genRatio 100
  GIVEN a file "utils.py" with 50 lines
  AND all lines have genRatio 100
  WHEN the AI classification is determined
  THEN the file is classified as "Fully AI"
  AND the weighted ratio is 100.0%

Scenario: [Edge] Handle file with no genCodeDesc records
  GIVEN a file "legacy.c" exists in the repository
  AND no genCodeDesc records exist for this file
  WHEN the AI ratio is requested
  THEN the result is 0.0%
  AND the file is classified as "No AI Attribution"

Scenario: [Misuse] Reject genRatio outside valid range
  GIVEN a genCodeDesc record with genRatio 150
  WHEN the record is validated
  THEN the record is rejected with error "genRatio must be 0-100"

Scenario: [Fault] Handle corrupt genCodeDesc JSON gracefully
  GIVEN a genCodeDesc file with malformed JSON
  WHEN the file is parsed
  THEN a descriptive parse error is returned
  AND no partial data is committed
```
Concrete values, observable outcomes, one behavior each, category-tagged
</Good>

<Bad>
```gherkin
Scenario: It works correctly
  GIVEN the system is running
  WHEN the user does something
  THEN the correct result is shown

Scenario: Test all edge cases
  GIVEN various inputs
  WHEN processed
  THEN all outputs are valid
```
Untestable, vague, multiple behaviors
</Bad>

### Scenario Outline for Data Variations

When the same behavior applies to multiple inputs, use a Scenario Outline:

```gherkin
Scenario Outline: Classify file by AI ratio threshold
  GIVEN a file with weighted AI ratio <ratio>
  WHEN classified with threshold <threshold>
  THEN the classification is "<classification>"

  Examples:
    | ratio | threshold | classification |
    | 100.0 | 60        | Fully AI       |
    | 75.0  | 60        | Mostly AI      |
    | 45.0  | 60        | Mixed          |
    | 0.0   | 60        | No AI          |
```

## Step 4 — VALIDATE Each Scenario

For each scenario, confirm:

- [ ] Can a developer write a test from this scenario alone?
- [ ] Is the GIVEN state achievable in a test setup?
- [ ] Is the WHEN action a single trigger?
- [ ] Is the THEN outcome observable without inspecting internals?
- [ ] Does it test exactly one behavior?

**Fails validation?** Rewrite the scenario. Don't proceed with vague specs.

## Step 5 — OUTPUT the Story

Save to `docs/stories/<story-id>.md` with this structure:

```markdown
# <Story ID>: <Short Title>

## User Story

AS A <role>,
I WANT <capability>,
SO THAT <benefit>.

## Acceptance Criteria

### Scenario 1: [Typical] <name>
```gherkin
GIVEN ...
WHEN ...
THEN ...
```

### Scenario 2: [Edge] <name>
```gherkin
GIVEN ...
WHEN ...
THEN ...
```

### Scenario 3: [Misuse|Fault|...] <name>
```gherkin
GIVEN ...
WHEN ...
THEN ...
```

## Notes

- <any constraints, assumptions, or open questions>

## Dependencies

- <other stories this depends on, if any>
```

## Minimum Viable Story (US)

Every User Story (US) MUST have:
- [ ] Role, capability, benefit (no blanks)
- [ ] At least 3 Acceptance Criteria (AC):
  - At least 1 × **Typical** (ValidFunc)
  - At least 1 × **Edge** or **Misuse** or **Fault** (ValidFunc/InvalidFunc)
  - At least 1 more from any category
- [ ] Each AC tagged with category: `[Typical]`, `[Edge]`, `[Misuse]`, `[Fault]`,
  `[StateMachine]`, `[Concurrency]`, `[Performance]`, `[Robust]`,
  `[Observability]`, `[Testability]`
- [ ] All ACs pass Step 4 validation
- [ ] No AC with vague terms ("correct", "valid", "appropriate")

## Connecting to TDD

After a story is accepted:
1. Each GIVEN/WHEN/THEN scenario becomes a test case
2. `test-driven-development` skill takes over
3. RED: write a failing test from the scenario
4. GREEN: implement minimal code to pass
5. REFACTOR: clean up

The story IS the test specification. No gap between requirements and tests.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Technical story | "As a developer, I want to refactor the database" | Stories describe user-visible behavior |
| Solution in story | "I want a Redis cache" | Describe the need, not the solution |
| Epic disguised as story | "I want a complete admin panel" | Split into individual capabilities |
| No acceptance criteria | US without AC | Not a US yet — keep specifying |
| Implementation in GIVEN | "GIVEN the HashMap is initialized" | Use domain language, not code |
| Multiple WHENs | "WHEN I click A and then B and then C" | One action per scenario |
| Untestable Then | "Then the system is fast" | Quantify: "responds within 200ms" |

## Final Rule

```
No implementation without a US.
No US without acceptance criteria.
No AC without GIVEN/WHEN/THEN.
No US with fewer than 3 AC.
```
