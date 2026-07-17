# ACE Codebase Audit Findings

Generated: 2026-07-17
Branch: `audit/codebase-optimisation`
Baseline commit: `8ec4e8bd23d1f4e42076b6704d65e5832e0953f4`
Scope: Whole tracked repository, following `CODEBASE_AUDIT_PLAN.md`

## Current Summary

| Priority | Open | Accepted | Rejected | Completed |
|---|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 |
| High | 1 | 0 | 0 | 0 |
| Medium | 0 | 0 | 0 | 0 |
| Low | 3 | 0 | 0 | 0 |

No findings have been accepted yet. P0 records the baseline and coverage map; P1 records architecture and integration-seam findings.

## Rules

- Record only evidence-backed findings.
- Preserve existing behaviour, data compatibility, and user workflows.
- File size, complexity, or duplication is a prompt to investigate, not a finding by itself.
- Performance findings require a representative workload and baseline.
- Keep stable finding IDs once assigned.
- Do not change production code on the audit branch before the user reviews the complete findings.
- Preserve the existing untracked `DESLOPPIFY.md`; reconcile it only after findings review.

## Critical Findings

- None.

## High-Priority Findings

### ARCH-001. Give coding-page context assembly a neutral, explicit boundary

- Status: Open
- Priority: High
- Category: Simplification
- Where: `src/ace/routes/pages.py::_coding_context`; `src/ace/routes/api_support.py::_render_full_coding_oob`, `_annotation_only_response`, and `_render_code_sidebar`
- Evidence: `_coding_context` is a 193-line private function in the page-route module with 18 imported dependencies. It performs database reads, auto-creates assignments, renders sentence HTML, derives inspector geometry, serialises client payloads, and returns 28 template values. The page route calls it directly, while three API rendering helpers import it lazily from `ace.routes.pages` to avoid a module-level route cycle. `_render_code_sidebar` therefore invokes the full page-context builder even though the sidebar blocks consume only the codebook, source-summary, mode, branding, and version subset. The full baseline passes, so this is a responsibility and dependency-direction finding rather than evidence of incorrect behaviour; no performance benefit is claimed without a representative benchmark.
- Current contract: Initial coding-page access creates missing source assignments; page and HTMX responses retain the same template keys, ordering, escaped payloads, project filename, annotation geometry, codebook tree, notes, flags, and source counts.
- Why it matters: A central coding-workflow change currently crosses persistence mutation, rendering, serialisation, page routing, and API fragment assembly. Private reverse imports make ownership unclear and make smaller render paths depend on unrelated work.
- Recommendation: Move the context/presentation logic to a neutral module, make assignment initialisation an explicit preserved step, and define named context builders for the full page and narrower fragment surfaces. Share query results where that avoids duplication. Benchmark representative sidebar and annotation mutations before treating reduced work as a performance outcome.
- Expected simplification or measured benefit: Remove three lazy private imports from API support into the page router, give four call sites one stable owner, separate the hidden write from read/formatting work, and make each fragment's data contract visible.
- Tests required first: Characterise first-load assignment creation and the full-page, full-OOB, annotation-only, and sidebar-only context contracts, especially `project_file_stem`, `tree_codes`, `sources_json`, annotation payload escaping, and source ordering.
- Verification: Run focused coding route/context tests, `uv run pytest`, the headless-tree synchronisation check, and coding/codebook E2E tests in Chromium, Firefox, and WebKit.
- Dependencies: None
- Timing: Needs design
- Confidence: High

## Medium-Priority Findings

- None.

## Low-Priority Findings

### ARCH-002. Remove test-only compatibility exports from the API router aggregator

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `src/ace/routes/api.py:1-14`; `tests/test_status_helpers.py`, `tests/test_coding_routes.py`, `tests/test_render_colour_css.py`, and `tests/test_agreement_routes.py`
- Evidence: Structural and name-use scans show that `api.py` uses only `APIRouter` and the four child routers. Its `asyncio` import and four private imports from `api_support` are unused by production code. Tests still import those private helpers through `ace.routes.api`; agreement tests patch `api_mod.asyncio.to_thread`, which reaches `api_agreement.asyncio.to_thread` only because both names reference the same global `asyncio` module object. Production call-site scans found no consumer of these compatibility bindings. All 63 registered routes produce 62 non-HEAD method/path pairs with no duplicates.
- Current contract: The aggregate router registers the project/import, coding, codebook, and agreement routers with unchanged paths and methods; helper behaviour and agreement thread offloading remain covered.
- Why it matters: Tests encode an obsolete pre-split module boundary and can let the aggregator appear to own behaviour implemented elsewhere, making later route decomposition harder to reason about.
- Recommendation: Retarget tests to `api_support` or the owning route module, then remove the unused `asyncio` and private-helper compatibility imports from `api.py`.
- Expected simplification or measured benefit: Make the aggregator a route-registration module only and remove five misleading exported bindings.
- Tests required first: Retarget the existing helper and agreement-thread tests before removing the bindings; no new behavioural coverage is otherwise required.
- Verification: Run the affected helper/agreement tests, `tests/test_route_registration.py`, and `uv run pytest`.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### ARCH-003. Remove the obsolete application-level database cleanup path

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `src/ace/app.py::_lifespan`; `src/ace/app.py` import of `checkpoint_and_close`
- Evidence: Repository-wide AST and call-site scans find `app.state.db` only where lifespan initialises it to `None`, reads it during shutdown, and assigns `None` again. No production path stores a connection there. `get_db` opens a per-request SQLite connection and closes it in its own `finally` block; route helpers use their own scoped project connections. `checkpoint_and_close` is imported into `app.py` only for this unreachable non-`None` branch.
- Current contract: Per-request connections still validate the ACE application ID, enable foreign keys and WAL, and close after the request; active project shutdown/checkpoint behaviour elsewhere remains unchanged.
- Why it matters: The dead state suggests a second connection-ownership model that no longer exists and makes graceful-shutdown reasoning more difficult.
- Recommendation: Remove `app.state.db`, its shutdown branch, and the now-unused `checkpoint_and_close` import from `app.py`.
- Expected simplification or measured benefit: Eliminate an impossible lifecycle branch and leave one explicit connection-ownership model in the application factory.
- Tests required first: Existing `get_db` and lifespan tests cover the retained behaviour; add a test only if shutdown checkpoint ownership is moved at the same time.
- Verification: Run `tests/test_app.py`, project/open route tests, and `uv run pytest`.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### ARCH-004. Retire or explicitly support the unused parent-process watchdog

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `src/ace/__main__.py::main`; `src/ace/app.py::run`, `_start_parent_watchdog`, and `_parent_pid_exists`; related tests in `tests/test_app.py`
- Evidence: The hidden `--parent-pid` flag and watchdog entered with the former Tauri sidecar flow. The current Rust browser launcher starts the server with `--port`, `--launcher-token`, `--runtime-file`, `--idle-timeout-seconds`, and `--no-kill-stale`, but never supplies `--parent-pid`; its own process exits after opening the browser. A repository-wide scan finds no production caller of `run(parent_pid=...)` and no documentation for the flag—only the CLI forwarding code and unit tests of the optional path remain.
- Current contract: The browser launcher can reuse a healthy runtime, authenticate browser tabs, shut down after the idle timeout, and remove runtime metadata; these current lifecycle mechanisms must remain unchanged.
- Why it matters: The server retains threading, process-probing, signal, CLI, and test surface for a lifecycle model no current component uses.
- Recommendation: Confirm that the hidden flag is not an intentionally supported external integration, then remove the flag, `run` parameter, watchdog helpers, and tests. If it is supported, document the owner and add an integration test showing the real caller.
- Expected simplification or measured benefit: Remove an unowned legacy process-lifecycle path and make the launcher/runtime shutdown model unambiguous.
- Tests required first: No new tests if the path is confirmed obsolete; otherwise add the missing external-caller integration contract before retaining it.
- Verification: Run `tests/test_app.py`, `tests/test_browser_runtime.py`, `tests/test_runtime_routes.py`, `tests/test_launcher_lifecycle.py`, Rust launcher checks, and `uv run pytest`.
- Dependencies: None
- Timing: Needs design
- Confidence: Medium

## Rejected or Deferred Candidates

Record investigated candidates here when evidence does not support a change, or when work should wait. This prevents repeated rediscovery.

- **Typed wrapper for all FastAPI app state:** The audit found state shared across lifecycle, project, import, agreement, and coding flows, but no current failure or repeated state-shape bug. Replacing every `app.state` access would be broad and may add more abstraction than it removes. Reconsider only if later passes find concrete state-ownership defects.
- **Merge `BrowserSessionTracker` and `BrowserRuntimeMonitor`:** The tracker owns deterministic, lock-protected tab/idle state while the monitor owns background scheduling and shutdown dispatch. Focused tests exercise the tracker without starting threads, and the full lifecycle suite passes. The present separation is useful rather than accidental duplication.

## Finding Template

```markdown
### <area>-<number>. <short title>

- Status: Open
- Priority: Critical | High | Medium | Low
- Category: Correctness risk | Simplification | Performance | Tests | Tooling | Documentation
- Where: Exact paths, symbols, routes, selectors, commands, or flows
- Evidence: Direct observations and reproducible commands
- Current contract: Behaviour that must remain unchanged
- Why it matters: Maintenance, reliability, security, performance, or developer impact
- Recommendation: Smallest coherent change
- Expected simplification or measured benefit: Concrete outcome
- Tests required first: Characterisation or regression coverage
- Verification: Exact checks required after implementation
- Dependencies: Other finding IDs or None
- Timing: Safe now | Needs tests first | Needs design | Wait
- Confidence: High | Medium | Low
```
