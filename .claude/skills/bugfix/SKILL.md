# Bug Fix Checklist
1. Read the error/bug description carefully
2. Grep for ALL related TypedDict/dataclass definitions before editing
3. Identify the coordinate system (pixels vs fractions vs percentages) if UI-related
4. Make the minimal fix, then grep for all construction sites of modified types
5. List all files changed and verify no orphaned imports
6. Do NOT use Playwright for verification unless explicitly asked