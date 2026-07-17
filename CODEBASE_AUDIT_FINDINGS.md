# ACE Codebase Audit Findings

Generated: 2026-07-17
Branch: `audit/codebase-optimisation`
Baseline commit: `8ec4e8bd23d1f4e42076b6704d65e5832e0953f4`
Scope: Whole tracked repository, following `CODEBASE_AUDIT_PLAN.md`

## Current Summary

| Priority | Open | Accepted | Rejected | Completed |
|---|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 |
| High | 7 | 0 | 0 | 0 |
| Medium | 2 | 0 | 0 | 0 |
| Low | 3 | 0 | 0 | 0 |

No findings have been accepted yet. P0 records the baseline and coverage map; P1-P2 record architecture, persistence, model, and service findings.

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

### DB-001. Reject project files created by a newer schema before opening them for use

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/db/migrations.py::check_and_migrate`; `src/ace/db/connection.py::open_project`; project-open routes
- Evidence: `check_and_migrate` advances versions only while `current < SCHEMA_VERSION` and returns a greater version unchanged. A temporary valid ACE file stamped with `PRAGMA user_version = 20` was accepted by ACE schema version 10: the reproduction reported `runtime_schema=10 file_schema=20 open_project=accepted`. Existing migration tests cover old-to-current and current schemas but not future schemas.
- Current contract: Current files open unchanged, older supported files migrate sequentially, non-ACE files are rejected, and a failed open does not leave an owned connection or imply that the project is safe to edit.
- Why it matters: An older ACE can expose a newer file to reads and writes based on obsolete schema assumptions, which is a direct forward-compatibility and data-integrity risk.
- Recommendation: Detect `user_version > SCHEMA_VERSION` before enabling the project for normal use, close the connection on every failed open, and return a distinct error that tells the user to update ACE rather than calling the file invalid.
- Expected simplification or measured benefit: Establish one explicit supported-version gate and remove the current ambiguous fall-through for future files.
- Tests required first: Add connection and route tests for a valid ACE application ID with a future `user_version`, including connection cleanup and the user-facing update message.
- Verification: Run `tests/test_db`, project/open route tests, launcher file-open E2E coverage, and `uv run pytest`.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### ANN-001. Serialise same-code annotation merge decisions across connections

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/models/annotation.py::add_annotation_merging`; `/api/code/apply`
- Evidence: The function checks for overlapping annotations before beginning a write transaction, and its no-overlap branch inserts and commits without acquiring an earlier write lock. A deterministic two-connection reproduction paused both calls after their overlap query; both returned success with `replaced_ids=[]`, leaving two active annotations at the identical `(1, 5)` range. Per-tab HTMX queuing does not serialise separate browser tabs.
- Current contract: For one source, coder, and code, overlapping or touching active annotations collapse to one union annotation, and undo records either a simple add or the complete replaced-ID set.
- Why it matters: Concurrent tabs can silently violate the merge invariant that the rest of rendering, deletion, export, and undo logic assumes.
- Recommendation: Acquire the SQLite write transaction before validating/querying the merge set, keep the decision and all writes in one transaction, and translate lock/busy failures into a retryable user-facing response.
- Expected simplification or measured benefit: Make the documented merge invariant true at the database transaction boundary instead of relying on client-side request ordering.
- Tests required first: Add a deterministic two-connection race test for identical and partially overlapping ranges, plus undo/redo characterisation for the winning merged result.
- Verification: Run annotation model tests, coding annotation route tests, rapid-apply E2E coverage in all three engines, and `uv run pytest`.
- Dependencies: None
- Timing: Needs tests first
- Confidence: High

### IMPORT-001. Validate and commit each source-import batch atomically

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/services/importer.py::import_csv` and `import_text_files`; `src/ace/models/source.py::add_source`; import commit/folder routes
- Evidence: `add_source` commits every source independently, so the import services cannot roll back a batch. Failure injection on the second CSV row left the first source persisted (`persisted_sources=['a']`) even though the import raised before returning `created_ids`, so the route cannot expose that partial batch through “Remove last import”. Separately, a row with a blank selected ID imports successfully as the literal display label `'None'` because `str(row[id_column])` is applied before validation.
- Current contract: A successful batch preserves row/file order, skips existing and intra-batch duplicate labels, reports created/duplicate/empty counts, stores metadata and content hashes, and records exactly the created IDs for removal. A failed batch must not leave unreported sources.
- Why it matters: Mid-batch I/O or database failures can leave hidden partial data, while blank labels create sources users cannot meaningfully identify.
- Recommendation: Parse and validate the candidate rows first, explicitly handle missing/blank source labels, then insert the batch through a no-commit model primitive inside one transaction with rollback on any failure. Keep the public single-source helper's existing commit contract for independent callers.
- Expected simplification or measured benefit: Give source imports one transaction owner and one validation boundary, with result counts that describe the committed database state exactly.
- Tests required first: Add failure-on-second-row/file rollback tests, blank/whitespace/`None` label tests, and retain duplicate, empty-text, metadata, encoding, and remove-last-import coverage.
- Verification: Run importer service tests, import route tests, desktop-picker import E2E coverage, and `uv run pytest`.
- Dependencies: None
- Timing: Needs tests first
- Confidence: High

### TEXT-001. Define one Unicode offset convention across Python and the browser

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/services/text_splitter.py`, `coding_render.py`, `src/ace/static/js/bridge.js::_sourceOffset`, `_buildTextIndex`, and `_findDOMPosition`; annotation merge/excerpt and agreement computations
- Evidence: Python `len` and slicing use Unicode code points, while DOM Range offsets and JavaScript `textContent.length` use UTF-16 code units. For `"😀 Alpha. Beta."`, Python reports 14 characters and the browser reports 15 code units; the second sentence starts at Python/data offset 9 but global UTF-16 offset 10. Simulating the browser's `(3, 8)` selection for `Alpha` and applying the same code twice caused merge re-slicing to persist `'lpha.'` instead of `'Alpha'`. Existing annotation/render/agreement tests contain no non-BMP text cases.
- Current contract: Stored offsets, selected text, SVG highlights, sentence membership, coded-text positions, exports, merge/undo, and agreement vectors refer to the same characters for all valid Unicode source text.
- Why it matters: Emoji and other non-BMP characters can shift or overlap coordinates, corrupt merged selected text, mispaint highlights, and alter position-based agreement results.
- Recommendation: Specify a canonical offset unit and convert explicitly at the DOM/Python boundary. Prefer a versioned design that also addresses existing files whose annotations may contain the current mixed offsets; do not silently reinterpret stored coordinates.
- Expected simplification or measured benefit: Replace implicit language-dependent offset arithmetic with one documented, testable coordinate contract shared by every consumer.
- Tests required first: Add model, splitter/render, export, coded-view, and agreement cases with emoji before and inside selections, multiple sentences, merge/undo/reload, and cross-sentence ranges; define a compatibility fixture for a pre-fix `.ace` file.
- Verification: Run the focused Unicode contract tests, `uv run pytest`, and visual/DOM verification in Chromium, Firefox, WebKit, and real Safari for highlight painting.
- Dependencies: None
- Timing: Needs design
- Confidence: High

### UNDO-001. Make composite undo and redo handlers transactionally atomic

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/services/undo.py::_undo_codebook_import`, `_redo_codebook_import`, and `_undo_code_delete`; commit-owning mutation helpers in `src/ace/models/codebook.py`
- Evidence: The import handlers loop over `delete_code` or `restore_code`, each of which commits independently. Injecting a failure on the second deletion left `One` deleted and `Two` active while `_replay` re-pushed the original undo entry (`undo_stack=1`). `_undo_code_delete` similarly calls committing `restore_code` before a separate parent/order update, so its rollback cannot reverse the first commit. Other folder/move handlers already use no-commit primitives and one surrounding transaction, demonstrating the intended pattern.
- Current contract: One undo or redo entry is all-or-nothing; if replay fails, restoring the entry to its stack must leave the database exactly as it was before the attempt so retry is safe.
- Why it matters: A transient or invariant failure can partially mutate the project while the UI reports an undo failure and offers a retry against already-changed state.
- Recommendation: Expose the minimal no-commit codebook mutation primitives needed by composite handlers and put each handler's complete replay inside one transaction. Keep model-level public commit wrappers for single-operation callers.
- Expected simplification or measured benefit: Align all composite handlers with one transaction-ownership rule and remove raw/committing mixtures that make rollback claims false.
- Tests required first: Add second-item failure injection for import undo/redo and post-restore failure injection for code deletion, asserting both database state and stack state before retry.
- Verification: Run undo service tests, codebook model and route tests, coding undo/redo E2E coverage in all engines, and `uv run pytest`.
- Dependencies: None
- Timing: Needs tests first
- Confidence: High

### AGREEMENT-001. Preserve distinct sources that happen to contain identical text

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/services/agreement_loader.py` source matching and `build_dataset`; `agreement_computer.py::_build_sparse_counts`
- Evidence: Agreement identity is a single `content_hash`: validation uses sets of hashes and dataset construction maps each hash to one `MatchedSource`. In a two-file reproduction where each file contained two separately labelled, fully coded sources with identical text, validation reported one matched source and the dataset contained one source with all four annotations: `physical_sources_per_file=2 validation_matched_sources=1 dataset_sources=1 dataset_annotations=4`. No duplicate-content agreement test exists.
- Current contract: Every distinct source that can be matched across coder files contributes its own positions and source count; identical content must not silently halve the sample or merge annotations from separate records.
- Why it matters: Repeated short responses or duplicated source texts can change the number of coded positions, per-source results, sufficiency verdicts, and overall agreement without any warning.
- Recommendation: Introduce an unambiguous compound source identity. Preserve hash-only matching for unique texts, but disambiguate duplicate hashes using a stable secondary key such as display ID/occurrence and reject genuinely ambiguous file sets with a clear review message.
- Expected simplification or measured benefit: Make source matching explicit for both unique and duplicate content instead of relying on a lossy dictionary/set key.
- Tests required first: Add two- and three-coder fixtures with duplicate text under distinct labels, reordered sources, partial duplicates, and ambiguous labels; assert matched counts, annotation separation, warnings, and metrics.
- Verification: Run agreement loader/computer/verdict tests, agreement route tests, agreement file-review E2E tests in all engines, and `uv run pytest`.
- Dependencies: TEXT-001 for non-BMP position correctness, but duplicate-source identity can be fixed independently
- Timing: Needs design
- Confidence: High

## Medium-Priority Findings

### EXPORT-001. Group adjacent annotations independently of interleaved coders

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: `src/ace/services/exporter.py::export_annotations_csv` and `_EXPORT_QUERY`
- Evidence: The query orders by source then offset, but `itertools.groupby` groups the resulting rows by `(source_id, coder_name)` without first making each coder's rows contiguous. A reproduction with coder A at offsets 0-2 and 4-6 and coder B at 3-4 exported three rows instead of merging A's adjacent annotations into one; the coder sequence was `['default', 'second', 'default']`. Existing exporter tests use one coder.
- Current contract: With merge enabled, same-code annotations within five characters merge within each source and coder regardless of another coder's interleaved offsets; annotations from different coders never merge.
- Why it matters: Multi-coder project exports depend on incidental global row order and can disagree with the documented merge option.
- Recommendation: Select `coder_id`, group rows explicitly by `(source_id, coder_id)`, sort each group by offset, merge, then restore deterministic source/coder ordering for output.
- Expected simplification or measured benefit: Make grouping semantics explicit and remove the hidden pre-sorted-input requirement from `groupby`.
- Tests required first: Add interleaved two-coder cases, same-name safeguards, deterministic output-order assertions, and merge-disabled parity.
- Verification: Run exporter service tests, annotation export route tests, and `uv run pytest`.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### MODEL-001. Move codebook CSV adaptation out of the persistence model

- Status: Open
- Priority: Medium
- Category: Simplification
- Where: `src/ace/models/codebook.py:503-972`; codebook import/export routes; `tests/test_models/test_codebook.py`
- Evidence: The first half of `codebook.py` owns codebook persistence, hierarchy invariants, ordering, deletion/restoration, and hashing. The second half owns CSV encodings, header aliases and detection, sample inspection, row normalisation, preview ledgers, file import orchestration, and export. Production routes call these file-adapter functions directly from the model, and approximately 40 CSV adapter/import/export assertions live in the model test module. This is a responsibility-boundary finding: file length alone is not the evidence.
- Current contract: Encoding fallback, selected-column mapping, folder reuse/creation, colour assignment, definition handling, preview ledger classifications, atomic imports, stable order, and round-trip exports remain byte/behaviour compatible.
- Why it matters: Changes to external file format UX and changes to database invariants share one module and test surface, while the existing source importer already establishes a service boundary for file adaptation.
- Recommendation: Move codebook CSV reading, detection, normalisation, preview, and export orchestration to a focused service/adapter module. Keep database mutation and tree invariants in the model, exposing no-commit primitives only where an orchestrating transaction requires them.
- Expected simplification or measured benefit: Give file formats and persistence separate owners, reduce route-to-model format coupling, and let tests describe adapter contracts separately from database CRUD.
- Tests required first: Preserve the current CSV encoding, mapping, preview-ledger, folder, definition, colour, atomic rollback, and round-trip cases while splitting them by responsibility.
- Verification: Run codebook model/service/route tests, codebook import E2E coverage in all engines, and `uv run pytest`.
- Dependencies: UNDO-001 if shared no-commit codebook primitives are changed in the same batch
- Timing: Needs design
- Confidence: High

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

### ARCH-003. Remove obsolete application-level lifecycle state

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `src/ace/app.py::_lifespan`; `src/ace/app.py` import of `checkpoint_and_close`; writes to `active_projects` in project-open/create routes
- Evidence: Repository-wide AST and call-site scans find `app.state.db` only where lifespan initialises it to `None`, reads it during shutdown, and assigns `None` again. No production path stores a connection there. `migrated_paths` is initialised and asserted by a test but never read or written by production code. `active_projects` is initialised and appended to by three open/create paths but never read. `get_db` opens a per-request SQLite connection and closes it in its own `finally` block; `checkpoint_and_close` is imported into `app.py` only for the unreachable non-`None` branch.
- Current contract: Per-request connections still validate the ACE application ID, enable foreign keys and WAL, and close after the request; active project shutdown/checkpoint behaviour elsewhere remains unchanged.
- Why it matters: The dead state suggests a second connection-ownership model that no longer exists and makes graceful-shutdown reasoning more difficult.
- Recommendation: Remove `app.state.db`, `migrated_paths`, `active_projects`, their dead shutdown/write paths, and the now-unused `checkpoint_and_close` import from `app.py`. If active-project tracking is intended for a future checkpoint feature, design and test that behaviour before retaining state that currently has no effect.
- Expected simplification or measured benefit: Eliminate three unconsumed state concepts and an impossible lifecycle branch, leaving one explicit connection-ownership model in the application factory.
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
- **Persist or cache the code-cue FTS index:** The current request rebuilds a temporary FTS table, but direct measurements were small: median 0.50 ms for 31 codes, 1.18 ms for 300, and 8.52 ms for 3,000 on the baseline machine. The focused 1,000-code smoke test takes 0.13 s including setup. A persistent index would add schema/cache invalidation complexity without evidence of a user-visible bottleneck.
- **Optimise agreement computation:** The sparse event-based implementation completed a synthetic 50-source/10-code/1,000-annotation workload in 2.45 ms and a 200-source/30-code/12,000-annotation workload in 38.80 ms. The browser workflow's multi-second tests are dominated by browser/polling behaviour, not this pure computation, so no algorithm rewrite is justified by current evidence.
- **Narrow every broad exception in model and undo transactions:** All broad model catches found in P2 roll back and immediately re-raise. `UndoManager._replay` deliberately re-pushes the entry, logs, and re-raises. The concrete problem is commits inside composite handlers (UNDO-001), not exception breadth by itself.

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
