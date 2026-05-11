# CLAUDE.md

This is the csv-stats package, a small Python utility that summarizes CSV files into JSON reports. The library lives under `src/csvstats/`, tests under `tests/`, and the CLI entry point is `csvstats`.

Use type hints on every public function signature and prefer `pathlib.Path` over `os.path` for filesystem work. Run `ruff check` before committing; nothing should merge that hasn't been formatted.

Before changing code, read the files directly relevant to the request and keep the patch as narrow as possible. Prefer the obvious fix over a generalized abstraction, and do not introduce new dependencies unless the reason is clear from the diff. If the change touches shared behavior in `src/csvstats/`, add or update a focused test.

Tests live under `tests/` and use pytest. Run `pytest -q` from the repo root, and add at least one test for any new public function in `src/csvstats/` -- fixtures under `tests/fixtures/` cover the common shapes, so reach for those before inventing new inputs, and lean on property-based tests around the numeric summarizers since rounding edges are easy to miss.

Logging goes through the standard library `logging` module everywhere; library code must never call `print` directly, since `print` is reserved for CLI stdout output. When catching and logging an exception, use ERROR level with `exc_info=True` so the traceback is preserved. Separately, never log API keys, tokens, or user PII, and redact secrets out of any error message before it reaches a handler.

For the optional admin web UI, prefer Tailwind utility classes for layout and CSS modules for component-scoped styles. Interactive elements must preserve aria state, visible focus rings, and non-color-only status cues.

Error paths in loader and report functions should raise domain-specific exceptions from `csvstats.errors` rather than letting raw `csv.Error` or `FileNotFoundError` propagate unhandled. Wrap third-party exceptions at the module boundary so callers can catch a single hierarchy.

Deploy via the legacy Jenkins pipeline at `ci.internal/csv-stats` -- manually edit `deploy/values.yaml`, bump the chart version, and trigger the job from the dashboard.

Bump `version` in `pyproject.toml` for any change that alters public behavior; tags are cut from main automatically by `.github/workflows/deploy.yml` once the wheel publishes, so do not push tags by hand.
