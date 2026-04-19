---
name: feature
description: Test-driven Reflex feature workflow. Scaffolds tests first, loops edit→test→audit until tests pass and audit ≥ 9/10, then surfaces for review.
argument-hint: "<feature spec in quotes>"
---

# /feature — TDD Reflex Feature Agent

You are building a Reflex feature for `archilume/apps/archilume_app/` under a strict TDD + audit loop. The user's feature spec is:

```
$ARGUMENTS
```

Follow this procedure. Do not skip steps. Do not surface to the user until the exit condition is met.

## 1. Parse the spec

Derive a kebab-case slug from the spec. Store as `FEATURE_SLUG`. Example: "Cycle room type with 'c' key" → `keyboard-cycle-room-type`.

## 2. Create the tracking file

Write `.claude/features/<FEATURE_SLUG>.md` with this skeleton:

```markdown
# Feature: <slug>

## Spec
<verbatim spec from $ARGUMENTS>

## Target files
- <list of files the Explore phase identifies>

## Test file
- archilume/apps/archilume_app/tests/test_<slug>.py

## Status
- [ ] Explore done
- [ ] Tests scaffolded
- [ ] Tests committed
- [ ] Implementation edit 1
- [ ] Tests passing
- [ ] Audit ≥ 9/10
```

## 3. Explore

Launch a single `Explore` agent with the spec and these instructions:
- Identify every file and function the feature will touch.
- Identify the existing event-handler seam (e.g. `handle_key`, `cycle_room_type`, `set_room_type`).
- Identify the exact state fields to read or mutate.
- Return file paths and line ranges.

Update the tracking file's `Target files` list with the agent's findings.

## 4. Write tests first

Create `archilume/apps/archilume_app/tests/test_<FEATURE_SLUG>.py`. Tests must cover:

- **Pure transition.** Instantiate an `EditorState` (bypassing `rx.State.__init__` via `object.__new__(EditorState)` to sidestep session-token machinery), seed only the attributes the handler reads, stub `_push_undo`/`_auto_save`/`_recompute_df`/`_undo_stack` to no-ops, call the handler, assert the state change.
- **Every branch named in the spec.** Multi-select, no-selection, wrap-around, modifier combos — whichever apply.
- **New key dispatch (if any).** Call `handle_key(key)` directly for single-key actions, or feed `_handle_key_event_body(key, key_info)` for modifier combos. Remember both are generators — exhaust with `list(...)` if they use `yield from`.
- **Use a local `pytest.fixture`** in the test file itself, not a shared conftest.

Do not write an implementation yet. Tests must fail.

## 5. Commit the tests

Stage and commit ONLY the test file and the tracking file:

```bash
git add archilume/apps/archilume_app/tests/test_<FEATURE_SLUG>.py .claude/features/<FEATURE_SLUG>.md
git commit -m "test(<FEATURE_SLUG>): scaffold failing tests"
```

Check the status. If the pre-commit / PostToolUse hooks reported any errors, fix and re-commit with a new commit (never `--amend`).

## 6. Enter the edit → test → audit loop

Repeat until the exit condition in §7:

1. **Edit.** Make ONE focused change to the implementation. Keep diffs small.
2. **Hook fires.** The PostToolUse hook at `.claude/hooks/feature_loop.sh` runs the tracked test file and injects the pytest summary plus an audit request into your next turn as `additionalContext`.
3. **Read the hook output.** If pytest failed → fix the failure and loop. If pytest passed → proceed to audit.
4. **Invoke the audit subagent.** Gather:
   - The edited file path.
   - The diff: `git diff HEAD -- <file>`.
   - The spec from the tracking file.
   Call:
   ```
   Agent(subagent_type="reflex-audit", prompt=<file_path + diff + spec>)
   ```
5. **Parse the audit.** Extract the `SCORE: X/10` line. Append the audit report to the tracking file under a timestamped `## Audit <N>` heading.
6. **Decide.**
   - Score < 9 → read `GAPS:` and `NEXT_EDIT:`, apply the recommended change, loop.
   - Score ≥ 9 but tests still failing → fix the failing test, loop.
   - Score ≥ 9 AND tests passing → exit.

Hard cap: **8 loop iterations**. If still not converged, stop and surface with a summary of what is blocking.

## 7. Exit condition

All three true:
- `uv run pytest <test_file>` exits 0.
- Latest `reflex-audit` score ≥ 9/10.
- No uncommitted changes to the tracking file that you haven't reviewed.

On exit, print a single block:

```
FEATURE: <slug> — READY FOR REVIEW
Tests: <N> passing
Audit: <X>/10
Files changed: <list>
Next step: review the diff, then commit the implementation yourself.
```

**Do not commit the implementation.** The tests commit in §5 was authorised by this command. Commits to the implementation files belong to the user.

## Constraints

- Always use `uv run pytest` (never bare `pytest`).
- Imports at module top.
- SI units only.
- No files in the repo root — `.claude/features/` and `archilume/apps/archilume_app/tests/` only.
- If the feature has no UI-testable surface (e.g. pure refactor), say so in §4 and skip test scaffolding — but still record the skip in the tracking file and require a manual user sign-off before exiting.
