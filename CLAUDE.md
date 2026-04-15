# CLAUDE.md — Data Pipeline Project

## Current Status

See `docs/STATUS.md` for latest session handoff.

## User Preferences
- Don't rewrite code unless necessary — tweak existing
- No git commits unless explicitly asked
- Full autonomy on implementation when given permission

## Python Environment (CRITICAL)
- ALWAYS use the project venv at `.venv/` — never install packages to system Python
- Activate with: `source .venv/bin/activate`
- Install packages with: `.venv/bin/pip install ...`
- Run scripts with: `.venv/bin/python scripts/...`
- Reason: user explicitly prohibits system Python contamination

## Execution Rules (CRITICAL)

- Always start by checking docs/ for latest progress before taking action
- Do NOT scan entire repo — use targeted file discovery (LS, Grep, Glob)
- Prefer concise, actionable outputs over long explanations
- Default to Sonnet-level reasoning unless deep architecture is required
- Never assume implementation — verify against code or docs
- **Before running any script against a live DB or large dataset: test on a 3-row sample first, verify output, THEN run full ingest. Never run the whole thing in one go blind.**

## Full-Stack Integrity Rules

- Never rely on mock JSON or hardcoded data
- Always verify frontend → backend → database flow
- Ensure GraphQL queries match backend schema
- Validate that UI reflects real data, not placeholders
- If data is missing, generate realistic seed data (not dummy text)

## Testing Rules

- Always generate tests alongside code using pytest and httpx
- Cover CRUD flows, edge cases, and failure states
- Prefer integration tests over shallow unit tests
- For migration code: always test validation (row counts, checksums) and rollback paths

## Security

- Never expose secrets, tokens, or credentials in code
- Use environment variables for all connection strings and API keys
- Validate all inputs at API boundaries

## Token Efficiency (CRITICAL)

- Do NOT read large files unless necessary
- Use Grep/Glob before Read
- Summarize instead of dumping large outputs
- Avoid redundant explanations
- Focus on actions, not verbosity

## Skill Usage Rules

- Use codebase-sync-planner before major refactors
- Use production-feature-builder for new features
- Use e2e-testing-review after implementation
- Use fullstack-wiring-validator before deployment

## Code Documentation Rules (CRITICAL — applies to every generated file)

Every file generated in this project must include three layers of documentation:

### Layer 1 — File header (brief summary block at top of file)
```
# What this file does
# Which services it connects to
# Where it sits in the tech layer (source DB / migration / API / deployment)
# How it contributes to the project goal (refer to docs/interview-prep/TRUTH_SOURCE.md)
```

### Layer 2 — Function docstrings (one line per function)
Each function must have a single-line docstring stating:
- What the method does
- Its goal
- Which other methods or services it connects to (if any)

### Layer 3 — Inline comments on complex operations
Any non-obvious operation inside a function gets a short inline comment (half-line max):
- What the operation does
- Why this approach was chosen over the obvious alternative

### CLI Commands Reference
All useful Azure and AWS CLI commands discovered during the project are stored in:
`docs/cli-reference/azure-commands.md` and `docs/cli-reference/aws-commands.md`
Update these files as new commands are used — do not let them go stale.

## Learning Focus

This project is explicitly for learning debugging, framework navigation, and cloud service usage. Documentation and comments are not optional — they are how learning happens. Prioritise clarity of intent over brevity in code comments.
