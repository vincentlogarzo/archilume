---
description: Fan out 4 parallel hypothesis-driven subagents to triage a bug, synthesise, present the best candidate fix
argument-hint: "<bug description>"
allowed-tools: Task, Read, Grep, Glob, Bash(git diff:*), Bash(git worktree list:*), Bash(git -C *:*), Bash(git log:*)
---

# /triage-bugs

Bug report from user (passed as `$ARGUMENTS`):

> $ARGUMENTS

## Your job

You are the **triage coordinator**. You do **not** investigate the bug yourself. Instead you fan out four parallel investigators, each bound to a distinct root-cause hypothesis category, then synthesise their reports and present the strongest candidate to the user.

### Step 1 — Validate input

If `$ARGUMENTS` is empty or less than ~10 characters of meaningful description, stop and ask the user for a bug report. Do not proceed with an empty investigation.

### Step 2 — Fan out (single message, 4 parallel Task calls)

In **one message**, emit four `Task` tool calls in parallel. One call per investigator. Each call MUST set:

- `subagent_type` — exactly one of the four agent names below (no duplicates, no omissions)
- `isolation: "worktree"` — each investigator works in its own git worktree so fixes do not collide
- `description` — short label, e.g. `"Reflex state triage"`
- `prompt` — self-contained briefing using the template in §Investigator Prompt Template below

The four agents and their categories:

| `subagent_type` | Category |
|---|---|
| `triage-reflex-state` | Reflex state / var dependency |
| `triage-event-dispatch` | Event dispatch / capture phase |
| `triage-async-race` | Async / race conditions |
| `triage-css-dom` | CSS / DOM layout interference |

**Do not launch them sequentially.** Parallel fan-out is the point of this command.

### Step 3 — Parse reports

Each investigator returns markdown matching the §Report Contract. For each:

1. Extract confidence with regex `### Confidence: (\d+)/10` → integer 0–10.
2. Count evidence bullets under `### Evidence`.
3. Extract worktree path from `### Proposed fix` → `**Worktree**:` line.
4. If any report is malformed (no confidence line, no worktree), still include it in the ranking but flag it as `MALFORMED` — do not drop silently.

### Step 4 — Rank

Sort by `confidence × evidence_count` descending. Tie-break by specificity (evidence bullets with `file:line` references score higher than vague area references). Record the ordering.

### Step 5 — Retrieve winning diff

For the top-ranked report:

```bash
git -C <winning_worktree_path> diff
```

Also run `git -C <winning_worktree_path> diff --stat` to summarise.

### Step 6 — Present

Output to the user, in this order:

1. **Ranking table**:

   | Rank | Category | Confidence | Evidence | Hypothesis (one line) |
   |---|---|---|---|---|

2. **Winning report** (full, verbatim from the top investigator).

3. **Winning diff**, fenced as ` ```diff `.

4. **Alternative worktrees** — bullet list of the other three worktree paths + one-line hypothesis each, so the user can `cd` in and inspect.

5. **Next steps** — one short line: "Review the diff above. If you accept it, I can cherry-pick from `<branch>` into main and clean up the other three worktrees."

### Step 7 — Stop

Do **not** merge, commit, push, or delete any worktree. The user reviews and decides. If they accept, they will tell you.

---

## Investigator Prompt Template

Use this exact template when composing each `Task` prompt. Substitute `{{CATEGORY}}` with the agent's category name from the table above. Substitute `{{BUG}}` with `$ARGUMENTS`.

```
You are investigating this bug EXCLUSIVELY through the lens of {{CATEGORY}}:

> {{BUG}}

Three other agents are investigating in parallel under different hypothesis categories. Do not try to cover their ground. Stay in your lane.

You are running in an isolated git worktree. You may edit, test, and leave the fix uncommitted — the coordinator will retrieve your diff via `git diff` once you return.

Repo root: c:\Projects\archilume (the worktree mirrors this structure).

Procedure:
1. Locate the code paths relevant to {{CATEGORY}} for this bug.
2. Form one concrete hypothesis for the root cause WITHIN your category.
3. Gather evidence by reading source, grepping, and running read-only commands. Prefer file:line citations.
4. If your category does NOT explain the bug, return confidence ≤ 2/10 with a brief note and do NOT attempt a fix.
5. If it DOES, attempt a minimal fix in the worktree. Do not commit — leave changes in the working tree.
6. Return a report matching the Report Contract below EXACTLY. The coordinator parses it with regex.

Report Contract (copy this structure, do not rename headings):

## Triage Report — {{CATEGORY}}

### Hypothesis
<one sentence>

### Confidence: N/10
<integer 0-10. Rubric: 0-2 bug is not in my category; 3-5 plausible but not verified; 6-8 verified by evidence; 9-10 reproduced or fix validated>

### Evidence
- [file.ext:LINE](relative/path#LLINE) — what this shows
- ...

### Root cause
<1-3 sentences>

### Proposed fix
- **Worktree**: <absolute path of this worktree>
- **Files changed**: <bullet list>
- **Diff summary**: <2-3 lines of prose, not the diff itself>

### Verification plan
<how to confirm the fix works — commands, UI steps, test to run>

End of contract. Return only the report, no preamble.
```

---

## Report Contract (authoritative copy for parsing)

```
## Triage Report — <category>

### Hypothesis
<sentence>

### Confidence: N/10

### Evidence
- [file:LINE](path) — note
- ...

### Root cause
<text>

### Proposed fix
- **Worktree**: <path>
- **Files changed**: <list>
- **Diff summary**: <text>

### Verification plan
<text>
```

The confidence regex is `### Confidence: (\d+)/10`. Keep the heading and separator exactly as written so the parser never misses.
