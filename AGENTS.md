# CSS Architecture

## Rules

1. **Simple class selectors only.** No complex selectors, nesting, or chaining.
   Just `.class-name {}`.
2. **No `!important`.** Ever.
3. Each page gets its own CSS file in `static/<app>/css/` loaded via
   `{% static %}`.

# Testing

- Do NOT run pytest from the repo root (both packages have a top-level
  `tests` package — collection clashes). Run per package:
- whospital suite: `uv run pytest -q` in `packages/whospital/`
  (~10s, needs Docker/testcontainers, timeout 120000ms)
- whealth suite: `uv run pytest -q` in `packages/whealth/`
  (~2s, timeout 60000ms)
- Static: `uv run ruff format --check .`, `uv run ruff check .`,
  `uv run mypy packages/whealth/src packages/whospital/src` (from root)
- Venv setup: `uv sync --all-packages --all-extras` (plain `uv sync` strips
  extras like sentry-sdk and breaks whospital tests).
- Always: redirect output to a temp file; silent on success; dump failures only.
- Last measured: 2026-08-24, whospital 111 tests in 14s, whealth 7 in 3s.

# How to Git commit

Here is how to Git commit:

1. DO NOT FUCKING COMMIT WITHOUT ASKING
2. IT IS FORBIDDEN TO COMMIT WITHOUT ASKING
3. UNLESS EXPLICITLY ASKED IN THE **PREVIOUS** LITERAL LINE OF TEXT ABSOLUTELY
   DO NOT COMMIT
4. IN DOUBT ASK FOR CONFIRMATION BEFORE COMMIT
5. IF YOU COMMIT WITHOUT ASKING I'M GOING TO FUCKING KILL YOU
