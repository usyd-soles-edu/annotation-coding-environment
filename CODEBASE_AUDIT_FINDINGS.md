# ACE Codebase Audit Findings

Generated: 2026-07-17
Branch: `audit/codebase-optimisation`
Baseline commit: `8ec4e8bd23d1f4e42076b6704d65e5832e0953f4`
Scope: Whole tracked repository, following `CODEBASE_AUDIT_PLAN.md`

## Current Summary

| Priority | Open | Accepted | Rejected | Completed |
|---|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 |
| High | 11 | 0 | 0 | 0 |
| Medium | 7 | 0 | 0 | 0 |
| Low | 6 | 0 | 0 | 0 |

No findings have been accepted yet. P0 records the baseline and coverage map; P1-P4 record architecture, persistence, model, service, route, template, HTMX, JavaScript, and CSS findings.

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

### PROJECT-001. Replace an existing project only after its replacement is durable

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/routes/api_project_import.py::project_create`; `POST /api/project/create` with `overwrite=true`
- Evidence: The overwrite branch calls `file_path.unlink()` before `create_project(...)`. In a route-level failure injection where the target contained known bytes and `create_project` raised a simulated disk error, the response displayed the friendly failure message but `target_exists=False` and `original_preserved=False`. Current overwrite tests cover the successful replacement and confirmation dialog only.
- Current contract: Overwrite remains an explicit confirmed action, produces a fresh valid ACE project at the selected path, redirects to import on success, and leaves the existing project recoverable if replacement creation fails.
- Why it matters: A disk, permission, schema-creation, or unexpected failure after unlinking irreversibly deletes the project the user was trying to replace, even though no replacement exists.
- Recommendation: Create and fully initialise the replacement at a unique temporary path in the same directory, close and validate it, then atomically replace the target with `os.replace`. Clean up the temporary file on every failure and clear path-keyed undo/transient import state only after the replacement succeeds.
- Expected simplification or measured benefit: Give project replacement one commit point and remove the destructive gap between deleting the old file and creating the new one.
- Tests required first: Add failure injection before and after temporary project creation, assert byte-for-byte preservation of the original, assert temporary-file cleanup, and retain the existing confirmation/success tests.
- Verification: Run project route tests, setup E2E tests in Chromium, Firefox, and WebKit, the full suite, and a manual overwrite smoke test on macOS and Windows packages.
- Dependencies: DB-001 should define validation of the newly created project before replacement; ARCH-003 if obsolete lifecycle state is removed in the same batch
- Timing: Needs tests first
- Confidence: High

### HTMX-001. Mark every OOB-only status response as a no-primary-swap response

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/routes/api_support.py::_oob_status`; direct `_oob_status` returns throughout `api_codebook.py` and `api_project_import.py`; programmatic swaps in `codebook_headless_tree_source.js` and `bridge.js`
- Evidence: `_oob_status` returns only three OOB fragments but no `HX-Reswap` header. HTMX removes those fragments from the response before applying the requested primary swap, leaving an empty fragment. In a live Chromium reproduction on the coding page, `htmx.ajax('POST', '/api/codes', {target:'#code-sidebar', swap:'outerHTML', values:{name:' '}})` received the intended 200 status response and changed `#code-sidebar` count from 1 to 0 while updating the status bar. Existing tests explicitly assert `HX-Reswap: none` for annotation-only and undo/redo paths but not for `_oob_status`; duplicate-name races and other 200 validation paths can reach this response in normal multi-tab use.
- Current contract: Validation and operational errors update the global status, coding receipt, and live region without replacing the sidebar, text panel, modal, or wizard step that initiated the request.
- Why it matters: A recoverable validation conflict can erase a primary workspace region until reload, turning a friendly error path into apparent data/UI loss.
- Recommendation: Make `_oob_status` return `HX-Reswap: none` by default, then audit its callers for the rare response that intentionally owns a primary target and give that path an explicit primary fragment instead.
- Expected simplification or measured benefit: Encode the OOB-only contract once instead of relying on each caller to remember a response header; protect more than 30 direct error returns with one invariant.
- Tests required first: Add a helper-level header assertion, route tests for blank/duplicate/invalid codebook inputs, and a browser test proving the sidebar and text panel retain element identity after a 200 OOB validation response.
- Verification: Run route tests, coding notification and codebook E2E tests in all three engines, the headless-tree synchronisation check, and `uv run pytest`.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### NOTE-001. Serialise note autosaves and make navigation wait for the complete save queue

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/static/js/ace_notes.js::_doSaveNote` and `aceFlushNoteIfDirty`; `src/ace/static/js/bridge.js::aceNavigate`
- Evidence: `_doSaveNote` starts every `fetch` immediately and replaces the single `_noteInFlight` reference. If a debounced save is already in flight, a later edit followed by `aceFlushNoteIfDirty()` starts a second request and navigation awaits only that newer promise. A Chromium reproduction using the real `ace_notes.js` and a controlled `fetch` recorded requests for `['older', 'newer']`; resolving `newer` first allowed the navigation flush to resolve while `older` remained pending, then resolving `older` last left the simulated server value as `older`. The catch path also suppresses every non-abort save failure without restoring dirty state or presenting a sticky error. Existing model, route, and three-engine note tests cover successful persistence and status messages, not reversed completion or retry after failure.
- Current contract: The latest textarea value for the current source and coder is the value that survives debounce, HTMX swaps, source navigation, reload, and export. Navigation does not tear down the page until every earlier save that can still write has settled, and a failed save remains visible and retryable.
- Why it matters: A slower earlier request can overwrite a newer note after ACE has already allowed the user to leave the source, causing silent user-data loss with no remaining dirty indicator.
- Recommendation: Give note persistence a serialised, coalescing save queue. Keep at most one write in flight, retain only the latest queued draft, make flush await the complete queue, verify source identity before updating UI state, and keep failed content dirty with a sticky error and explicit retry path.
- Expected simplification or measured benefit: Replace one mutable promise that does not represent all outstanding work with one explicit single-flight state machine whose flush contract is testable.
- Tests required first: Add deterministic reversed-completion, edit-during-save, navigation-during-save, swap-during-save, failure/retry, and source-identity cases; retain current debounce, empty-note deletion, warning, and saved-status coverage.
- Verification: Run source-note model and route tests, note drawer and coding-navigation E2E tests in Chromium, Firefox, and WebKit, and `uv run pytest`.
- Dependencies: FRONT-001 if note ownership moves to a page-scoped entrypoint in the same work
- Timing: Needs tests first
- Confidence: High

### TREE-001. Ignore stale headless-tree initialisation after the sidebar mount changes

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `src/ace/static/js/codebook_headless_tree_source.js::init`; generated `codebook_headless_tree.js`; sidebar OOB replacement paths in `bridge.js`
- Evidence: `init` stores a module-global `mountedElement`, then awaits `GET /api/codes/tree` without an abort controller, generation token, or mount-identity check before replacing the global `items`, `tree`, controller, and rendered DOM. A Chromium reproduction using the real generated bundle mounted two successive sidebar elements and controlled the two fetches. Resolving the newer request first rendered `New`; resolving the older request last replaced the current global/UI state with `Old` and left the live mount showing `Old1`. The generated-source synchronisation check passes, so this is a source-design defect rather than bundle drift. Existing codebook E2E tests do not reverse two initialisation responses.
- Current contract: After an OOB sidebar replacement or rapid reinitialisation, only the newest live mount can own tree data, focus, drag state, and actions; detached mounts and their network completions cannot mutate current state.
- Why it matters: A slow response for a removed sidebar can roll the visible codebook back to stale data and attach controller state to the wrong generation, exposing users to incorrect rename, move, delete, or apply targets until another refresh.
- Recommendation: Abort the previous initialisation when a new mount starts and assign a monotonically increasing generation. Before applying fetched data or exposing a controller, require both the current generation and the same connected mount element; treat aborts and stale completions as silent no-ops.
- Expected simplification or measured benefit: Establish one owner for each tree generation and remove response-order dependence from the controller lifecycle.
- Tests required first: Add a deterministic two-mount reverse-completion browser test, a detached-mount case, and an assertion that actions and focus remain bound to the newer tree.
- Verification: Run the headless-tree synchronisation check, codebook controller/zone/context-menu E2E suites across Chromium, Firefox, and WebKit, and `uv run pytest`.
- Dependencies: FRONT-001 if controller mounting changes in the same batch
- Timing: Needs tests first
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

### HTMX-002. Give agreement-result interactions one repeatable lifecycle

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: `src/ace/templates/agreement_results.html:248-360`; `src/ace/templates/agreement.html` result swaps and history restoration
- Evidence: Each HTMX result insertion executes the partial's inline IIFE and adds another anonymous `document` click listener for row expansion, while sort listeners attach directly to the current table headers. A Chromium DOM reproduction evaluated the real result script twice: one row click ran both delegates and left the detail row hidden with `aria-expanded=false`. In a separate history-style `innerHTML` restoration, a live header click sorted `['B', 'A']` to `['A', 'B']`, but the restored header click left `['B', 'A']` and its icon unchanged because manual `innerHTML` does not execute or rebind the script. The 90 passing three-engine agreement/setup E2E tests do not exercise result-row expansion or sorting.
- Current contract: Recomputing, going back/forward, expanding guidance rows, and sorting columns continue to work once per action without accumulating handlers or losing keyboard/focus state.
- Why it matters: A normal second computation can make guidance rows appear unresponsive, and browser-history restoration silently disables sorting.
- Recommendation: Move agreement-result behaviour into an idempotent page-level controller. Use one delegated handler for replaceable result markup, keep sort state scoped to the current table, and call the same initialiser after HTMX swaps and history restoration rather than shipping executable script inside the partial.
- Expected simplification or measured benefit: Replace per-response script execution and mixed listener ownership with one explicit lifecycle that is safe across repeated swaps.
- Tests required first: Add three-engine cases for two consecutive computes, expand/collapse after recompute, sort after history back/forward, and exactly-one-toggle behaviour.
- Verification: Run agreement route/service tests, agreement file-review E2E tests in Chromium, Firefox, and WebKit, and `uv run pytest`.
- Dependencies: ROUTE-001 if agreement rendering helpers move at the same time
- Timing: Needs tests first
- Confidence: High

### A11Y-001. Make agreement-result rows and sort controls keyboard operable

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: `src/ace/templates/agreement_results.html:57-105` and its inline interaction script
- Evidence: The caption instructs users to click a row for guidance; expansion is attached to `.ace-code-row` `<tr>` elements and sorting to `.col-sortable` `<th>` elements. Neither element contains a button, has `tabindex`, nor has an Enter/Space keyboard handler. Static rendered-page checks found no missing ID/ARIA references, so the defect is specifically operability rather than broken labelling. Current agreement E2E tests contain no selector or assertion for result rows, sortable headers, or expanded rows.
- Current contract: Mouse behaviour, table semantics, visible sort direction, grouped-row ordering, expanded guidance, and screen-reader announcements remain understandable while every interactive action is reachable by keyboard.
- Why it matters: Keyboard and switch users cannot reveal per-code guidance or sort the main results table, despite ACE otherwise treating keyboard access as a core workflow.
- Recommendation: Put real buttons inside sortable headers and provide a focusable row disclosure control, or implement an equivalent semantic pattern with correct roles, `aria-expanded`, `aria-controls`, and Enter/Space handling. Prefer native buttons so focus and activation do not need to be recreated.
- Expected simplification or measured benefit: Align interaction semantics with the existing click behaviour and remove pointer-only controls.
- Tests required first: Add keyboard tab/Enter/Space tests, focus-visible assertions, `aria-sort` updates, expansion-state assertions, and a mouse-parity case in all engines.
- Verification: Run agreement E2E tests across Chromium, Firefox, and WebKit, inspect the accessibility tree, and complete a manual keyboard-only pass.
- Dependencies: HTMX-002 should establish the controller lifecycle before or alongside the keyboard handlers
- Timing: Needs design
- Confidence: High

### ROUTE-001. Split route support along the domains it already serves

- Status: Open
- Priority: Medium
- Category: Simplification
- Where: `src/ace/routes/api_support.py`; imports from `api_agreement.py`, `api_codebook.py`, `api_coding.py`, and `api_project_import.py`
- Evidence: `api_support.py` contains 71 functions across 1,776 lines. Call and import maps show distinct clusters for native pickers/import markup (lines 70-627), shared downloads/project connections (630-694), coding/codebook fragments and undo/audit responses (697-1464), and agreement state, workers, and rendering (1467-1776). Each domain router imports a broad private surface, while three coding render helpers also lazily import page-owned `_coding_context`. All support functions are referenced, so this is not a dead-code or file-size finding; the evidence is the number of independent owners and reverse dependency seam collected in ARCH-001.
- Current contract: Route paths, error/status fragments, exact OOB ordering, import previews, audit headers, agreement generation guards, and template contexts remain byte/behaviour compatible.
- Why it matters: Unrelated import, coding, undo, and agreement changes share one private namespace and make ownership, dependency direction, and focused tests harder to see.
- Recommendation: After extracting the neutral coding context from ARCH-001, split support into small domain modules with a deliberately tiny shared HTTP layer for `_project_db`, downloads, status fragments, and header composition. Move the 143-line import mapping renderer to an import-owned template/renderer rather than introducing a generic support framework.
- Expected simplification or measured benefit: Replace one 71-function grab bag with domain-owned APIs, remove the page-router reverse imports, and make each child router's dependency surface explicit.
- Tests required first: Characterise the exact status/download headers, fragment roots/order, import mapping HTML, coding OOB payloads, undo/audit headers, and agreement stale-generation behaviour before moving symbols.
- Verification: Run the 280-test focused route suite, the full suite, import/agreement/coding E2E tests in all engines, and the headless-tree synchronisation check.
- Dependencies: ARCH-001 first; MODEL-001 for final codebook import ownership; avoid combining with behavioural fixes unless their tests land separately
- Timing: Needs design
- Confidence: High

### CODEBOOK-001. Remove the no-op reorder request used only to refresh a rename

- Status: Open
- Priority: Medium
- Category: Simplification
- Where: `src/ace/static/js/bridge.js::_codeAction`, `_refreshSidebar`, and its sole inline-rename caller; `src/ace/routes/api_codebook.py::reorder_codes_route`
- Evidence: Structural call scans find one `_codeAction` call, for inline rename. `_codeAction` sends a raw `PUT /api/codes/{id}`, discards the route's already-rendered response, then `_refreshSidebar` sends `POST /api/codes/reorder` with `code_ids='[]'`. That 51-line route reads every active code's ordering before and after invoking the reorder model, records nothing because the list is unchanged, and renders the sidebar. `_refreshSidebar` is the only production caller of the legacy route; the current update route already returns the correct coding or audit mutation response.
- Current contract: Inline rename retains its validation, undo entry, audit metadata, focused row, sidebar counts/order, status handling, and coding/audit response modes.
- Why it matters: Every inline rename performs two requests and retains a legacy mutation endpoint whose empty-list side effect is actually rendering, obscuring the real response contract.
- Recommendation: Process the `PUT` response through `htmx.ajax` with the existing mutation swap options, remove `_refreshSidebar` and `_codeAction`, then remove `/api/codes/reorder` once tests and any compatibility consumers are confirmed absent.
- Expected simplification or measured benefit: Remove one request from every inline rename, one side-channel client helper, and a 51-line legacy endpoint without claiming an unmeasured latency improvement.
- Tests required first: Add a browser assertion that one inline rename issues one mutation request and preserves focus/audit mode; retarget or remove legacy-route registration tests.
- Verification: Run codebook route/model/undo tests, headless-tree synchronisation, codebook E2E tests across all engines, and `uv run pytest`.
- Dependencies: HTMX-001 for safe error responses; ROUTE-001 if response helpers move concurrently
- Timing: Needs tests first
- Confidence: High

### FRONT-001. Load coding controllers from an explicit page entrypoint

- Status: Open
- Priority: Medium
- Category: Simplification
- Where: `src/ace/templates/base.html`; `src/ace/static/js/bridge.js`, `ace_notes.js`, and `coding_keyboard.js`; coding and code-view templates
- Evidence: `base.html` loads the runtime, note, keyboard, and bridge scripts on every page. Instrumenting `EventTarget.prototype.addEventListener` before the real scripts ran showed `bridge.js` registering 52 listeners on both the landing and agreement pages, including 10 `keydown`, 8 `click`, three `htmx:beforeSwap`, two `htmx:afterSettle`, codebook custom-event, resize, and scroll handlers; the coding page registered 72. Many handlers guard internally on missing elements, so current behaviour passes, but unrelated pages still initialise a 5,604-line coding/codebook controller and expose its document-level keyboard ownership. The concrete request-order and lifecycle defects in NOTE-001, TREE-001, HTMX-002, and CODEBOOK-001 show that controller ownership is already a maintenance boundary, not merely a file-size concern.
- Current contract: Shared status/runtime behaviour remains available on every relevant page; coding, codebook, note, audit-view, landing, import, and agreement shortcuts fire exactly once only in their documented zones and survive HTMX replacement where required.
- Why it matters: Page-specific state machines share the global document lifecycle, which makes listener conflicts, stale DOM ownership, and repeat initialisation harder to constrain and test.
- Recommendation: Keep a small shared runtime/status entrypoint in the base template and load explicit page controllers from the templates that own them. Split by lifecycle and responsibility, not arbitrary line count: coding navigation/rendering, notes, codebook/tree, and audit view should each expose an idempotent mount/unmount contract with only deliberately shared globals.
- Expected simplification or measured benefit: Remove coding/codebook listener registration from unrelated landing, import, and agreement pages and give each replaceable controller one visible lifecycle owner. Do not claim a performance gain without a browser benchmark.
- Tests required first: Inventory template-to-global calls, characterise page-specific keyboard and HTMX-event ownership, and add assertions that repeated mount/unmount cycles register one effective handler while unrelated pages register none.
- Verification: Run static asset and route tests, the headless-tree synchronisation check, all page-specific E2E suites in Chromium, Firefox, and WebKit, and `uv run pytest`.
- Dependencies: HTMX-002 for agreement lifecycle; NOTE-001 and TREE-001 should retain their correctness fixes across the split
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

### ROUTE-002. Give annotation export the same missing-project guard as other project routes

- Status: Open
- Priority: Low
- Category: Correctness risk
- Where: `src/ace/routes/api_project_import.py::export_annotations`; `src/ace/routes/api_support.py::_csv_download` and `_project_db`; `GET /api/export/annotations`
- Evidence: The annotation export route calls `_csv_download`, which enters `_project_db` and passes `request.app.state.project_path` directly to `sqlite3.connect`. With a fresh application and no project open, a `TestClient` request to `/api/export/annotations` returns `500 Internal Server Error`. `/api/export/notes` and codebook exports fail through explicit project/coder guards instead. The annotation route appears only in registration tests; no route test covers its missing-project or download headers.
- Current contract: A valid open project still downloads the same timestamped UTF-8 CSV with its sanitised filename and all-coder contents; a missing project produces a deliberate redirect or user-facing client error rather than a server error.
- Why it matters: A stale bookmark, direct URL, or restored browser action reaches an avoidable 500 and bypasses ACE's normal project-opening guidance.
- Recommendation: Add an explicit project-required guard at the shared connection/download boundary, choosing the established redirect contract for browser downloads, and test the annotation and notes export routes together.
- Expected simplification or measured benefit: Make project ownership a precondition of the shared download helper instead of an implicit `sqlite3.connect` type requirement.
- Tests required first: Add no-project, valid-download, Unicode content, filename sanitisation, and response-header route cases.
- Verification: Run app/project/exporter/notes route tests and `uv run pytest`.
- Dependencies: ARCH-001 or ROUTE-001 only if the shared project guard moves as part of those changes
- Timing: Safe now
- Confidence: High

### FRONT-002. Remove the retired SortableJS asset and compatibility adapter

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `src/ace/static/js/Sortable.min.js`; `bridge.js::_initSortable`; `codebook_headless_tree_source.js::initSortable`; `CONTRIBUTING.md`
- Evidence: The tracked vendored asset identifies itself as SortableJS 1.15.6, but repository-wide template/import scans find no script load or module import for it. Excluding the asset itself, production references are the bridge adapter that passes `typeof Sortable === 'undefined' ? undefined : Sortable` and the headless-tree controller's no-op `initSortable` method; the remaining reference is a stale vendored-library note in `CONTRIBUTING.md`. Current drag and drop is implemented by `@headless-tree/core` in the generated bundle, and no test refers to Sortable or `initSortable`.
- Current contract: Headless-tree pointer and keyboard reordering, folder moves, focus restoration, OOB reinitialisation, and persisted order remain unchanged.
- Why it matters: The dead asset and adapter imply two drag-and-drop implementations and preserve reinitialisation branches that no current controller uses.
- Recommendation: Confirm the packaging/dependency pass finds no external bundling reference, then delete the vendored asset, remove the no-op adapter/callback and stale comments, and update contributor documentation to name the actual tree dependency.
- Expected simplification or measured benefit: Remove one unused third-party asset and the compatibility seam for a drag implementation that is no longer loaded.
- Tests required first: Existing headless-tree drag/reorder tests are the retained contract; add no new compatibility test for an unowned asset.
- Verification: Run static asset tests, the generated-bundle synchronisation check, codebook drag/reorder E2E suites in all three engines, packaging checks, and `uv run pytest`.
- Dependencies: P5 and P7 must confirm packaging and documentation references before implementation
- Timing: Safe after P5/P7 confirmation
- Confidence: High

### CSS-001. Replace or define the unresolved inspector background token

- Status: Open
- Priority: Low
- Category: Correctness risk
- Where: `src/ace/static/css/coding.css` rules for `.ace-right-inspector` and `.ace-applied-codes-panel`; shared tokens in `ace.css`
- Evidence: A repository-wide custom-property definition/use comparison found `--ace-bg-soft` used for two coding-panel background declarations but never defined and given no fallback. The neighbouring design system defines `--ace-bg` and `--ace-bg-muted`; dynamic `--undo-duration` and `--undo-progress` uses were excluded because JavaScript sets them and CSS supplies fallbacks. An unresolved `var()` invalidates the complete background declaration, so these panels currently render transparently rather than with an explicit design token.
- Current contract: The right inspector and applied-codes panel retain their intended visual hierarchy, contrast, sticky layout, focus states, and monochrome token system in every supported engine.
- Why it matters: The current appearance is an accidental cascade result that can change when the underlying container changes, and the undefined token makes an apparently valid style silently ineffective.
- Recommendation: Compare the intended panel treatment against the live design, then either replace both uses with the correct existing token or define `--ace-bg-soft` centrally with an explicit semantic role. Do not guess the colour during the audit.
- Expected simplification or measured benefit: Restore a fully resolved token graph and make the two panel backgrounds intentional rather than inherited by declaration failure.
- Tests required first: Add a lightweight custom-property resolution check or focused computed-style assertion that permits documented JavaScript-provided variables but rejects unresolved authored tokens without fallbacks.
- Verification: Run static asset tests and visually verify the coding layout in Chromium, Firefox, WebKit, and real Safari before committing the implementation.
- Dependencies: None
- Timing: Safe now
- Confidence: High

## Rejected or Deferred Candidates

Record investigated candidates here when evidence does not support a change, or when work should wait. This prevents repeated rediscovery.

- **Typed wrapper for all FastAPI app state:** The audit found state shared across lifecycle, project, import, agreement, and coding flows, but no current failure or repeated state-shape bug. Replacing every `app.state` access would be broad and may add more abstraction than it removes. Reconsider only if later passes find concrete state-ownership defects.
- **Merge `BrowserSessionTracker` and `BrowserRuntimeMonitor`:** The tracker owns deterministic, lock-protected tab/idle state while the monitor owns background scheduling and shutdown dispatch. Focused tests exercise the tracker without starting threads, and the full lifecycle suite passes. The present separation is useful rather than accidental duplication.
- **Persist or cache the code-cue FTS index:** The current request rebuilds a temporary FTS table, but direct measurements were small: median 0.50 ms for 31 codes, 1.18 ms for 300, and 8.52 ms for 3,000 on the baseline machine. The focused 1,000-code smoke test takes 0.13 s including setup. A persistent index would add schema/cache invalidation complexity without evidence of a user-visible bottleneck.
- **Optimise agreement computation:** The sparse event-based implementation completed a synthetic 50-source/10-code/1,000-annotation workload in 2.45 ms and a 200-source/30-code/12,000-annotation workload in 38.80 ms. The browser workflow's multi-second tests are dominated by browser/polling behaviour, not this pure computation, so no algorithm rewrite is justified by current evidence.
- **Narrow every broad exception in model and undo transactions:** All broad model catches found in P2 roll back and immediately re-raise. `UndoManager._replay` deliberately re-pushes the entry, logs, and re-raises. The concrete problem is commits inside composite handlers (UNDO-001), not exception breadth by itself.
- **Introduce one declarative dependency/response framework for all routes:** The route matrix found consistent coder/project guards on coder-owned coding and codebook mutations, and the 280-test focused route suite passes. The concrete outliers are the annotation-export precondition and OOB-only response header; fix those contracts directly rather than wrapping FastAPI in a new framework layer.
- **Create a generic template component system:** Every tracked template is referenced, rendered coding/audit pages had unique IDs with resolvable ARIA references, and conditional duplicate literals did not coexist in output. Domain-owned Jinja fragments are appropriate for the large import mapping builder, but a repository-wide component abstraction is not justified.
- **Rewrite code-view metadata autosave:** `code_view.js` already serialises metadata writes with one in-flight envelope and one coalesced queued envelope. The queued save starts only after the active request settles, and existing three-engine tests exercise single-flight latest-draft behaviour. The note race in NOTE-001 is not shared by this implementation.
- **Rebind every frontend listener after every HTMX swap:** Focused review found existing per-node dataset guards for grid resize, coding text controls, and undo affordances, plus a single global guard for coding text controls. The concrete stale lifecycle is the asynchronous tree initialisation in TREE-001; a blanket rebinding framework would obscure working ownership rather than simplify it.

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
