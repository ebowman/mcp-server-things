# Branch Coverage Report

- **Date:** 2026-08-20
- **Git SHA:** `0f4f1c63f3b9de0d03c63c250edfd697aa9bc86b`
- **Unit run:** `tests/unit` — 2024 passed, 1 skipped
- **Combined run:** `tests/regression` + `tests/live` (`THINGS_MCP_LIVE_TESTS=1`), coverage appended onto the unit run — 833 passed, 16 xfailed
- **Total branch coverage:** unit-only 72.29% / with live 73.50% (repo-wide `fail-under=80` gate is not met by either run; see gap beads below)

`reliable_scheduling.py` (`ReliableThingsScheduler`) is **excluded from this
report's gap analysis** — it is dead code (zero callers anywhere under
`src/things_mcp`, confirmed by grep; see CLAUDE.md's "Known, currently
out-of-scope exceptions" note) and shows 0.00% coverage in both runs because
nothing ever exercises it.

Two further modules were also found to have **zero non-test callers** and
0.00% coverage in both runs: `services/cache_manager.py` and
`shared_cache.py`. These are documented as dead-code candidates rather than
silently excluded (only `reliable_scheduling.py` was authorized for
exclusion) — see their gap beads for detail.

## Per-module coverage (branch), sorted by combined coverage ascending

| Module | Statements | Branches | Unit-only % | With-live % |
|---|---:|---:|---:|---:|
| reliable_scheduling.py *(excluded, dead code)* | 109 | 40 | 0.00% | 0.00% |
| services/cache_manager.py | 40 | 16 | 0.00% | 0.00% |
| shared_cache.py | 166 | 32 | 0.00% | 0.00% |
| services/applescript/formatters.py | 158 | 96 | 16.14% | 17.72% |
| services/validation_service.py | 84 | 34 | 24.58% | 24.58% |
| services/error_handler.py | 99 | 32 | 30.53% | 30.53% |
| operation_queue.py | 213 | 56 | 36.80% | 38.29% |
| utils/applescript_utils.py | 29 | 14 | 48.84% | 48.84% |
| config.py | 223 | 60 | 56.54% | 56.54% |
| main.py | 220 | 56 | 60.87% | 60.87% |
| scheduling/helpers.py | 50 | 20 | 62.86% | 62.86% |
| context_manager.py | 321 | 154 | 63.58% | 69.68% |
| scheduling/search.py | 146 | 78 | 70.09% | 70.09% |
| tools_helpers/helpers.py | 91 | 34 | 70.40% | 70.40% |
| pure_applescript_scheduler.py | 73 | 8 | 72.84% | 72.84% |
| models/response_models.py | 26 | 4 | 73.33% | 73.33% |
| models/things_models.py | 214 | 42 | 76.56% | 76.56% |
| services/tag_service.py | 131 | 54 | 73.51% | 78.38% |
| move_operations.py | 128 | 48 | 77.27% | 82.39% |
| parameter_validator.py | 280 | 168 | 80.13% | 80.13% |
| server.py | 899 | 206 | 79.46% | 82.62% |
| services/applescript_manager.py | 63 | 14 | 83.12% | 83.12% |
| scheduling/strategies.py | 79 | 24 | 86.41% | 86.41% |
| tools_helpers/write_operations.py | 337 | 102 | 86.10% | 86.79% |
| scheduling/todo_operations.py | 729 | 386 | 87.44% | 87.98% |
| tools_helpers/read_operations.py | 675 | 212 | 87.71% | 88.39% |
| locale_aware_dates.py | 259 | 120 | 89.97% | 89.97% |
| services/applescript/executor.py | 56 | 10 | 87.88% | 90.91% |
| doctor.py | 189 | 50 | 91.63% | 91.63% |
| tools_helpers/bulk_operations.py | 145 | 66 | 92.42% | 92.42% |
| client_config.py | 90 | 22 | 92.86% | 92.86% |
| things_import.py | 59 | 16 | 94.67% | 94.67% |
| tools.py | 106 | 6 | 98.21% | 98.21% |
| `__init__.py`, `boot_trace.py`, `models/__init__.py`, `scheduling/__init__.py`, `services/__init__.py`, `services/applescript/__init__.py`, `tools_helpers/__init__.py`, `tools_helpers/errors.py`, `utils/__init__.py` | small | 0 | 100.00% | 100.00% |

Modules from `services/applescript/executor.py` down (with-live % >= 90%) are
above the 90% gap-bead threshold this bead uses and have no bead filed.
Every module above that line (down through `services/cache_manager.py`) has
a corresponding gap bead — see "Coverage gap beads" below.

## Coverage gap beads

One bead per module below 90% branch coverage (with live), parented to
`hq-gbl`, priority 3, titled `Coverage gap: <module> - <N> uncovered
branches`. `reliable_scheduling.py` is excluded per the note above.

| Module | Bead |
|---|---|
| services/cache_manager.py | hq-gbl.20 |
| shared_cache.py | hq-gbl.21 |
| services/applescript/formatters.py | hq-gbl.22 |
| services/validation_service.py | hq-gbl.23 |
| services/error_handler.py | hq-gbl.24 |
| operation_queue.py | hq-gbl.25 |
| utils/applescript_utils.py | hq-gbl.26 |
| config.py | hq-gbl.27 |
| main.py | hq-gbl.28 |
| scheduling/helpers.py | hq-gbl.29 |
| context_manager.py | hq-gbl.30 |
| scheduling/search.py | hq-gbl.31 |
| tools_helpers/helpers.py | hq-gbl.32 |
| pure_applescript_scheduler.py | hq-gbl.33 |
| models/response_models.py | hq-gbl.34 |
| models/things_models.py | hq-gbl.35 |
| services/tag_service.py | hq-gbl.36 |
| parameter_validator.py | hq-gbl.37 |
| move_operations.py | hq-gbl.38 |
| server.py | hq-gbl.39 |
| services/applescript_manager.py | hq-gbl.40 |
| scheduling/strategies.py | hq-gbl.41 |
| tools_helpers/write_operations.py | hq-gbl.42 |
| scheduling/todo_operations.py | hq-gbl.43 |
| tools_helpers/read_operations.py | hq-gbl.44 |
| locale_aware_dates.py | hq-gbl.45 |

## How to regenerate

```
make coverage-regression
```

This runs the unit suite with `--cov-branch --cov-report=json:coverage-unit.json`,
then the regression + live suites (`THINGS_MCP_LIVE_TESTS=1`) with
`--cov-append --cov-report=json:coverage-all.json` on top of the same
`.coverage` data file, so `coverage-all.json` reflects unit + regression +
live combined. Requires a running, unlocked Things 3 on the host (the live
suites write throwaway objects prefixed `hq-gbl-reg ` and clean up after
themselves) and a configured Things URL-scheme auth token
(`.things-auth`/`things-auth.txt`/`~/.things-auth`) for the checklist/heading
write paths. Neither `coverage-*.json` nor `.coverage` is committed
(`.gitignore`); regenerate locally to refresh the numbers.
