---
description: Delegate a Python task (refactor, optimize, idiomatic rewrite, testing) to the python-expert subagent
argument-hint: "<task description>"
allowed-tools: Task, Read, Grep, Glob
---

# /python-expert

Task from user (passed as `$ARGUMENTS`):

> $ARGUMENTS

## Your job

Delegate to the `python-expert` subagent. Do **not** attempt the work yourself.

### Step 1 — Validate input

If `$ARGUMENTS` is empty or lacks a concrete Python target (file, function, behaviour), stop and ask the user what they want done. Do not dispatch an empty task.

### Step 2 — Gather minimal context

Before dispatch, do a quick read of anything the user referenced by path. If they named a function or symbol, grep for its definition. Keep this to one or two tool calls — the subagent does deep work, not you.

### Step 3 — Dispatch

Emit a single `Task` call:

- `subagent_type: python-expert`
- `description` — short label (e.g. `"Refactor workflow orchestrator"`)
- `prompt` — self-contained briefing. Include:
  - The verbatim user request
  - Relevant file paths and line ranges discovered in Step 2
  - Repo root: `c:\Projects\archilume`
  - Project constraints: Python 3.12, `uv` for deps, SI units only, `pathlib.Path`, UTF-8 I/O, imports at top of module
  - Whether the user expects code changes or analysis/advice (infer from wording; if ambiguous, ask them)
  - Expected deliverables: code + type hints + pytest tests where applicable

### Step 4 — Relay

Return the subagent's report to the user verbatim. Do not re-summarise or edit. If the subagent wrote code, surface the file paths it touched as clickable links.

### Step 5 — Stop

Do not commit or push. User reviews.
