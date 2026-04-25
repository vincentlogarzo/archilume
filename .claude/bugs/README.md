# Bug Tracker

Cross-session record of bugs in the archilume_app — keeps Claude grounded
across sessions so a regression of a previously-fixed bug is recognised, not
re-discovered. Mirrors `.claude/features/` in spirit (one markdown per item,
status frontmatter).

## Folders

- `open/` — bugs that are reproducible right now. SessionStart surfaces these.
- `fixed/` — verified-fixed bugs. Kept for pattern-matching when a similar
  issue appears later. Move a file here once `Status: fixed` and a
  regression test exists.

## Filename

`<short-id>-<kebab-slug>.md` — e.g. `b001-zoom-handle-jitter.md`. Short id is
sequential within the project; never reuse.

## Frontmatter

```yaml
---
status: open | investigating | fixed | regressed
first_seen: YYYY-MM-DD
last_seen: YYYY-MM-DD
severity: low | medium | high | critical
tags: [reflex-state, css-dom, async-race, event-dispatch, geometry, io]
files: [archilume/apps/archilume_app/archilume_app/state/editor_state.py, ...]
---
```

`tags` align with the four `triage-*` agents so `/triage-bugs` can route by
hypothesis. `files` lets the SessionStart hook (and a future PostToolUse hook)
surface the bug when the user edits a touched file.

## Body sections

```markdown
# {Title}

## Repro
Concrete steps. Include the trigger, the expected outcome, and the actual
outcome. Note OS, tier (light/verbose), and project context if relevant.

## Diagnosis
What was investigated. Hypotheses ruled in/out. Linked correlation IDs from
the trace.

## Root cause
The actual cause. Once known.

## Fix
Commit hash + one-line summary of the change.

## Regression test
Path to the test that catches a re-occurrence. Required before moving to fixed/.

## Trace excerpts
Copy of the smoking-gun lines from the log/trace. Helps future-you recognise
the same shape if it returns.
```

## Workflow

1. User reports a bug → create `open/<id>-<slug>.md`, fill `Repro` and any
   trace excerpts, status `open`.
2. While investigating, append to `Diagnosis`, status → `investigating`.
3. When fixed, fill `Root cause` / `Fix` / `Regression test`, status →
   `fixed`, then `mv` the file to `fixed/`.
4. If the bug returns later, status → `regressed` and move back to `open/`
   (keep the prior diagnosis history — append, don't overwrite).

## Sharing a session for off-line analysis

After hitting an issue, the user can ship the entire debug bundle in one
zip — Claude consumes the zip via the `/debug-report` skill, pointing it
at the extracted folder.

```bash
# Active project loaded in the app (logs at <project>/logs/):
python -m archilume_app.scripts.share_debug_bundle <project_dir>
# Produces:  <project_dir>/logs-YYYYMMDD-HHMMSS.zip

# Pre-project session (logs at ~/.archilume/logs/):
python -m archilume_app.scripts.share_debug_bundle
# Produces:  ~/.archilume/logs-YYYYMMDD-HHMMSS.zip
```

When Claude receives an extracted bundle, invoke `/debug-report
/path/to/extracted-logs/` — the skill resolves the explicit path first
before falling back to the live project / user-profile locations.
