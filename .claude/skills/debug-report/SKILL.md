---
name: debug-report
description: Read the full archilume_app debug log + trace history (not just the last N lines), group by correlation ID, surface design observations and verify-fix evidence. Invoke when the user asks "what's happening?", "show me the trace", "is X firing?", or as the data-gathering step before proposing a fix.
origin: local
---

# Debug Report Skill

`verify-ui` is for "did this single change behave correctly". This skill is for "what is the app actually doing right now" — the broader read across the full log + trace history that informs design decisions and recurring-bug detection.

## When to use

- The user reports a bug and you need to see what fired before proposing a fix.
- The user asks "is `<handler>` firing?" / "did the event reach the backend?".
- After a fix, to compare current behaviour against the previous trace shape.
- When you suspect a design issue (e.g. handler firing 100× per drag) and need data.
- When `verify-ui`'s last-100-lines window has dropped the relevant events.

## Inputs — locating the logs folder

Logs land in **one folder** that contains everything you need:

- `archilume_app.log` and rotations `archilume_app.log.1` … `archilume_app.log.5`
- `debug_trace.json` — active ring buffer
- `debug_trace.archive.jsonl` — overflow archive

Resolution order — use the first that exists:

1. **Explicit path** if the user supplied one (e.g. `/debug-report /tmp/uploaded-cowles-logs`). This is how a user's zipped & re-uploaded session is consumed off-line.
2. **Loaded-project logs**: `<project_dir>/logs/`. The user's currently-open Reflex project — usually what's wanted during live debugging.
3. **User-profile fallback**: `~/.archilume/logs/` (Linux/macOS) or `%USERPROFILE%\.archilume\logs\` (Windows). Where logs live before any project has been loaded.

To discover the active project dir while the app is running, grep the log
for the most recent `[debug] log relocated to project: <path>` breadcrumb.

Optional user hint: a tag, handler name, or time window to filter on.

## Steps

### 1. Concatenate the log

Read every available rotated log file in the resolved logs folder
(oldest-first, so the merged view runs in chronological order):

```bash
# Linux / macOS
LOGS=<resolved logs folder>
cat "$LOGS"/archilume_app.log.5 "$LOGS"/archilume_app.log.4 \
    "$LOGS"/archilume_app.log.3 "$LOGS"/archilume_app.log.2 \
    "$LOGS"/archilume_app.log.1 "$LOGS"/archilume_app.log 2>/dev/null
# Windows PowerShell
$LOGS = "<resolved logs folder>"
Get-Content "$LOGS\archilume_app.log.5","$LOGS\archilume_app.log.4", `
            "$LOGS\archilume_app.log.3","$LOGS\archilume_app.log.2", `
            "$LOGS\archilume_app.log.1","$LOGS\archilume_app.log" `
            -ErrorAction SilentlyContinue
```

Missing files are fine — skip them.

### 2. Concatenate the trace

Read `debug_trace.json` (active ring) AND `debug_trace.archive.jsonl` (overflow). The archive is line-delimited JSON, one entry per line:

```bash
cat "$LOGS"/debug_trace.archive.jsonl 2>/dev/null
cat "$LOGS"/debug_trace.json 2>/dev/null
```

Merge into a single ordered list by `ts`.

### 3. Group by correlation ID

Every entry and every log line carries `rid=<8 hex>`. Group entries with the same `rid` to reconstruct multi-step handler chains (e.g. a click that yielded into `recompute_df` → `auto_save` → `save_session`). Display each group as a timeline:

```
rid=a1b2c3d4  (12:43:01.220 → 12:43:01.247)
  +0ms   handle_canvas_click  args=[{"x":120,"y":80,...}]    elapsed=2.1ms
  +3ms   _drawing_add_vertex  args=[120,80]                   elapsed=0.8ms
  +5ms   _push_undo            changes={undo_stack:[len 4→5]}  elapsed=1.4ms
  +8ms   auto_save             elapsed=18.0ms
  total: 22.3ms across 4 events
```

### 4. Filter (if the user gave a hint)

If the user mentioned a tag (`zoom`), handler name (`handle_canvas_drag`), or time window, filter both log lines and trace entries to matches plus a small context window (±2 events around each match).

### 5. Surface aggregates

Always include these aggregates over the merged data, regardless of filter:

- **Top 5 longest handlers by elapsed_ms** (mean across calls, with N).
- **Top 5 most-frequently-fired handlers** (count + p95 elapsed).
- **Top 5 most-recently-changed state fields** (verbose tier only — `changes` map).
- **Error count**: `[ERROR]` lines, `js_error` and `js_unhandled_rejection` trace tags.
- **Tier observed**: scrape the `tier=...` line emitted at log init.

### 6. Design observations

Generate a "design observations" section listing patterns that look like design issues, not bugs. Examples:

- "`handle_canvas_drag` fired 142× in 2.1s with no debounce — drags push every pixel."
- "`recompute_df` runs after every `set_room_type` call — could batch on multi-select."
- "`auto_save` p95 is 180ms and runs on the request thread — felt as input lag."
- "`handle_key_event` chain has 5 steps for arrow-key nudge — could collapse."

These feed into `informing design decisions` — they are observations, not action items. Recommend where data warrants it.

### 7. Report

Output template (kept under one screen):

```
DEBUG REPORT
============
Window:    {first_ts} → {last_ts}  ({n_events} events, {n_log_lines} log lines)
Tier:      {light|verbose|off}
Errors:    {count} backend, {count} JS

Filter:    {none | tag=X | handler=Y}
Matched:   {n} events / {n} log lines

Top handlers by elapsed_ms (mean):
  1. handler_a    18.2ms  (n=3)
  2. handler_b     6.4ms  (n=11)
  ...

Most-frequent handlers:
  1. handle_mouse_move  214 calls
  2. ...

Recently-changed fields (verbose):
  draw_mode      false → true
  selected_room_idx  3 → 5
  ...

Correlation timelines (top 3 by total elapsed):
  rid=a1b2c3d4   22.3ms  4 events  [click → _drawing_add_vertex → ...]
  ...

Errors (chronological):
  12:43:14  [JS:js_error]  msg=Cannot read properties of null...  src=overlay.js:42
  ...

Design observations:
  - ...
  - ...
```

If the user asked a specific question ("is X firing?"), answer it directly first, then include the report below as evidence.

## Things to avoid

- Don't read a single file in isolation — always concatenate rotated logs and the archive.
- Don't summarise away the timestamps — `rid` grouping with relative offsets is the most useful view.
- Don't use this skill for "did my one-line change work" — that's `verify-ui`. This skill is broader.
- Don't propose a fix from this report alone unless the cause is unambiguous; first share the report so the user can confirm the diagnosis matches what they observed.