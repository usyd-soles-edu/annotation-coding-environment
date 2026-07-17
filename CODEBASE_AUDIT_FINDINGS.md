# ACE Codebase Audit Findings

Generated: 2026-07-17
Branch: `audit/codebase-optimisation`
Baseline commit: `8ec4e8bd23d1f4e42076b6704d65e5832e0953f4`
Scope: Whole tracked repository, following `CODEBASE_AUDIT_PLAN.md`

## Current Summary

| Priority | Open | Accepted | Rejected | Completed |
|---|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 |
| High | 13 | 2 | 0 | 0 |
| Medium | 18 | 0 | 0 | 0 |
| Low | 9 | 0 | 0 | 0 |

Batch 0 has been reviewed. `DEP-001` and `DOC-001` are accepted; the remaining findings are open. P0 records the baseline and coverage map; P1-P7 record the complete audit across architecture, persistence, models, services, routes, templates, HTMX, frontend, desktop, packaging, release, tests, documentation, dependencies, and repository assets.

## Proposed Implementation Sequence

This sequence is for review only. It does not accept any finding or authorise production changes.

| Batch | Theme | Finding IDs | Reason for order |
|---:|---|---|---|
| 0 | Immediate dependency and public-record repair | DEP-001, DOC-001 | Remove known vulnerable locked packages and correct the live release/citation mismatch before structural work |
| 1 | Data-integrity characterisation and fixes | DB-001, ANN-001, IMPORT-001, TEXT-001, UNDO-001, AGREEMENT-001, PROJECT-001, EXPORT-001, DATA-001 | Establish failure, concurrency, Unicode, import, and source-identity contracts before moving their owners |
| 2 | Response and browser correctness | HTMX-001, NOTE-001, TREE-001, HTMX-002, A11Y-001, CODEBOOK-001, ROUTE-002 | Repair concrete user-facing lifecycle, accessibility, and response defects with focused three-engine coverage |
| 3 | Test, generated-build, and CI foundation | TEST-002, TEST-003, TEST-001, BUILD-001, CI-002 | Make the full contract discoverable and affordable, then enforce it; preserve isolation before reusing infrastructure |
| 4 | Main architectural refactor | ARCH-001, MODEL-001, ROUTE-001, FRONT-001, ARCH-002 | Move context, CSV-adapter, route, and frontend-entry ownership only after the behavioural gates are dependable |
| 5 | Release and packaging hardening | PACK-001, REL-001, REL-002, CI-001, ICON-001 | Establish semantic package validation, then make tag/version, draft notes, permissions, and Windows assets one reproducible release contract |
| 6 | User and contributor documentation | DOC-002, DOC-003, DOC-004, DOC-005 | Update commands, screenshots, alternative text, and project-file guidance after their owning workflows settle |
| 7 | Low-risk retirement and cleanup | ARCH-003, ARCH-004, FRONT-002, CSS-001, REPO-001 | Remove obsolete state, watchdog, Sortable compatibility, unresolved styling, and local-ignore residue last |

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
- Dependencies: DB-001
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
- Dependencies: None
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
- Dependencies: None
- Timing: Needs tests first
- Confidence: High

### REL-001. Refuse to publish when the tag and packaged versions disagree

- Status: Open
- Priority: High
- Category: Correctness risk
- Where: `.github/workflows/release.yml`; `src/ace/__init__.py`; `desktop/launcher/Cargo.toml`; `desktop/launcher/Packager.toml`; `scripts/build_launcher_package.py`
- Evidence: ACE's version is repeated in the Python package, launcher crate, and packager manifest; all three currently read `1.6.1`, and one test compares only Cargo with Packager. The release workflow accepts any `v*` tag, or any existing tag supplied to `workflow_dispatch`, derives `VERSION="${TAG#v}"` only for the release name, and never reads or compares the three packaged versions. Tagging the current commit as `v1.6.2` would therefore create `ACE v1.6.2` while cargo-packager and the sidecar still identify the payload as 1.6.1. The live v1.6.1 release is aligned, but that alignment is manual rather than enforced.
- Current contract: A release tag, GitHub release name, Python package version, launcher binary metadata, installer filenames, and installed application version all describe the same valid semantic version before any draft or binary is published.
- Why it matters: A single missed bump or tag typo can publish misleading installers that cannot be reliably diagnosed, upgraded, or reproduced from their release label.
- Recommendation: Choose one authoritative version or implement one shared semantic validator. Run it before the stateful release preflight and before local packaging; require an exact `v<version>` tag match, validate all manifests, and make both tag-push and manual-dispatch paths use the same checked value.
- Expected simplification or measured benefit: Replace three manually coordinated values and an unchecked tag-derived fourth value with one explicit release invariant used by tests, local builds, and CI.
- Tests required first: Add version-parser tests for equal values, one-file drift, malformed tags, missing `v`, prerelease versions if supported, and manual-dispatch/tag-push parity.
- Verification: Run the version contract locally, package configuration tests, a non-publishing workflow test or action fixture for matching and mismatching tags, launcher/package checks, and the full suite.
- Dependencies: PACK-001 should reuse the same semantic validator rather than create another version parser
- Timing: Safe now
- Confidence: High

### CI-002. Put the existing test suite on the path to merge and release

- Status: Open
- Priority: High
- Category: Tooling
- Where: `.github/workflows/pages.yml`; `.github/workflows/release.yml`; `pyproject.toml`; repository ruleset `default`
- Evidence: The baseline collects 1,158 Python test items and the Rust launcher has six passing tests, but neither tracked workflow runs `pytest`, `cargo test`, the semantic package tests, or the real generated-bundle comparison. `pages.yml` builds the Quarto site on pull requests and the default branch; `release.yml` builds launcher packages for tags or manual dispatch. Live GitHub inspection on 2026-07-17 found no classic protection on `main`; the active `default` ruleset applies only `deletion` and `non_fast_forward` rules, with no pull-request, required-workflow, or required-status-check rule. A regression can therefore reach `main` or a release tag without any automated product-test result.
- Current contract: Local test commands, Pages publication, tag-triggered draft releases, and the three-platform release matrix remain available and keep their current behaviour.
- Why it matters: The repository has substantial regression coverage, but its signal depends entirely on a maintainer remembering and waiting for local checks. Release success currently proves that packaging completed, not that the application or launcher tests passed.
- Recommendation: Add a dedicated verification workflow with explicit fast Python, Rust, static/configuration, and browser lanes. Make release preflight depend on the appropriate green checks or rerun the release-critical lanes at the tag. Once the workflow is stable, require at least the fast deterministic check through the default-branch ruleset; add the real bundle-parity check only after BUILD-001 is resolved.
- Expected simplification or measured benefit: Replace an undocumented manual gate with one visible, repeatable result for pull requests, `main`, and release tags, while keeping expensive browser work separable from fast checks.
- Tests required first: No new product behaviour test is required. First define complete, non-overlapping test lanes and prove their union collects the same 1,158 items; characterise browser isolation before changing its harness.
- Verification: Run every workflow lane on a branch, confirm their collected-item union and Rust lockfile use, exercise a controlled failing check, then verify the required status blocks merging and a failed release-critical lane blocks publication.
- Dependencies: TEST-003 and BUILD-001
- Timing: Needs design
- Confidence: High

### DEP-001. Replace the vulnerable locked runtime dependency set

- Status: Accepted
- Priority: High
- Category: Correctness risk
- Where: `pyproject.toml`; `uv.lock`; FastAPI/Starlette request handling and form parsing
- Evidence: `uv lock --check` resolves 36 packages, but a 2026-07-17 `pip-audit` query against a `uv export --no-dev --no-emit-project` snapshot reports 12 unique published advisories: Click 8.3.1 (`CVE-2026-7246`), IDNA 3.11 (`CVE-2026-45409`), python-multipart 0.0.22 (`CVE-2026-40347`, `CVE-2026-53538`, `CVE-2026-53539`, `CVE-2026-53540`, `CVE-2026-42561`), and Starlette 0.52.1 (`CVE-2026-48710`, `CVE-2026-54282`, `CVE-2026-54283`, `CVE-2026-48818`, `CVE-2026-48817`). The python-multipart and Starlette packages are directly on ACE's form/request path. ACE binds to loopback and applies Origin/CSRF checks, which reduces remote exposure but does not make vulnerable parsers a safe release dependency. A compatible overlay using FastAPI 0.139.2, Starlette 1.3.1, python-multipart 0.0.32, Click 8.3.3, and IDNA 3.15 resolves successfully and passes 234 focused app, route, import, picker, project, note, and runtime tests in 9.07 seconds.
- Current contract: ACE remains loopback-only, preserves its Origin/CSRF policy, parses existing URL-encoded and multipart requests, accepts current imports, and produces the same route responses on Python 3.11 and newer.
- Why it matters: Shipped desktop bundles freeze the vulnerable versions into a local HTTP application. Several advisories concern parser denial of service, parser differentials, malformed requests, or request reconstruction, which are more relevant to ACE than a merely outdated library version.
- Recommendation: Upgrade the direct FastAPI and python-multipart constraints and regenerate `uv.lock` so the resolved Starlette, Click, and IDNA versions include the listed fixes; avoid adding permanent direct pins for transitives unless the resolver needs them. Add a reproducible exported-lock vulnerability audit to the verification workflow because `pip-audit --locked .` does not understand `uv.lock` directly.
- Expected simplification or measured benefit: Return the runtime vulnerability audit to zero known advisories while keeping one resolver-owned dependency graph rather than accumulating manual transitive pins.
- Tests required first: Preserve focused form, import, CSRF, Host/origin, error-response, lifespan, and launcher smoke contracts; add only advisory-relevant malformed/body-limit cases that exercise ACE-owned behaviour rather than duplicating upstream suites.
- Verification: Re-export the locked runtime and require a zero-advisory audit, run all 1,158 Python tests in the supported browser matrix, run the six locked Rust tests, build launcher packages, and smoke-test project creation/import/open on macOS and Windows.
- Progress: Implemented on `refactor/codebase-optimisation`. The exported runtime audit reports zero known vulnerabilities; all 459 browser tests, all 702 non-browser tests, all six Rust tests, and the macOS launcher package build pass. Windows packaging and smoke testing remain for CI.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### DOC-001. Make each release's archive, changelog, and scholarly metadata identify the same version

- Status: Accepted
- Priority: High
- Category: Documentation
- Where: `.zenodo.json`; `CITATION.cff`; `CHANGELOG.md`; `README.md`; `website/index.qmd`; `CONTRIBUTING.md`; the live Zenodo record for DOI `10.5281/zenodo.20488468`
- Evidence: The current repository tag is v1.6.1. Its release commit changed only the Python, Cargo, Cargo lock, and Packager versions, whereas the v1.6.0 release commit also updated `.zenodo.json`, `CHANGELOG.md`, `CITATION.cff`, the README, and website citation. Those five tracked public surfaces still say 1.6.0 and the changelog has an empty `Unreleased` section with no 1.6.1 entry. The live DOI record currently labels itself `Version 1.6.0` but serves `annotation-coding-environment-v1.6.1.zip`, links to the v1.6.1 GitHub tree, and identifies the external release as v1.6.1. `cffconvert --validate` confirms the CFF syntax is valid, so this is semantic release drift rather than malformed metadata.
- Current contract: Every tag has one user-facing changelog entry; package manifests, release assets, citations, DOI metadata, dates, and source archive all identify the same released version and preserve the existing concept DOI.
- Why it matters: Researchers following the citation cannot tell whether the DOI denotes 1.6.0 or 1.6.1, and the released archive is publicly described with the wrong version. The same omission also caused the initial v1.6.1 GitHub draft to lack a repository-backed changelog.
- Recommendation: Correct the v1.6.1 metadata in the repository and manually amend the already-published Zenodo record. Then define one release-metadata checklist or validator that compares the tag with package versions, `.zenodo.json`, CFF, changelog heading, README citation, and website citation before tagging; have release notes consume the matching changelog section.
- Expected simplification or measured benefit: Replace the split manual release paths with one version contract and make the GitHub release, archived source, DOI, and citations mutually verifiable.
- Tests required first: Add a read-only release-metadata contract test covering every version-bearing file and the changelog heading; keep live Zenodo verification as a release checklist because it is external state.
- Verification: Validate CFF and JSON, render all 17 website pages, run the release preflight, inspect the draft release body/assets, and confirm the amended Zenodo page displays 1.6.1 beside the v1.6.1 archive and source link.
- Progress: The repository metadata, v1.6.1 changelog, consistency validator, contract tests, and release-workflow integration are implemented on `refactor/codebase-optimisation`. CFF validation and all 17 website pages pass. Amending and confirming the published Zenodo record remains an external manual action.
- Dependencies: None
- Timing: Safe now
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
- Dependencies: None
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
- Dependencies: HTMX-001
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

### REL-002. Build the draft release notes from the real version, assets, and changelog

- Status: Open
- Priority: Medium
- Category: Documentation
- Where: `.github/workflows/release.yml::prepare_release` and artifact upload; GitHub release publication workflow
- Evidence: The workflow creates a draft body with literal `ACE_x.x.x_aarch64.dmg` and `ACE_x.x.x_x64-setup.exe` placeholders, omits the MSI that the Windows job uploads, and provides no changelog input or generated-notes step. Live GitHub evidence shows v1.6.0 still carries those incorrect placeholders despite assets named `ACE_1.6.0_aarch64.dmg`, `ace-launcher_1.6.0_x64-setup.exe`, and `ace-launcher_1.6.0_x64_en-US.msi`. The v1.6.1 release has corrected filenames and two changelog entries, but those details are absent from the workflow template and were supplied during the 25-minute draft-review window after the successful build.
- Current contract: Every draft is reviewable before publication and lists the exact uploaded files, platform/install guidance, signing warning, and a curated user-facing changelog for the tagged changes.
- Why it matters: The normal automated path repeatedly produces an incomplete release page, so publication quality depends on remembering undocumented manual repair; the wrong filename can send users looking for an asset that does not exist.
- Recommendation: Make release-note preparation an explicit, testable step. Generate the asset table from the validated version and expected platform formats, seed a changelog from a committed release-note fragment or GitHub generated notes, and fail the publish hand-off if placeholders remain or the changelog is empty. Keep final human review of the draft.
- Expected simplification or measured benefit: Replace ad hoc post-build editing with one repeatable draft contract while retaining editorial review.
- Tests required first: Add a renderer/fixture for a version with DMG, NSIS, and MSI assets; assert exact filenames, no placeholders, non-empty changelog, and safe reruns of an existing draft.
- Verification: Exercise the renderer locally, run a dry-run workflow against a test tag or fixture, confirm the draft body and three assets, and verify rerunning does not erase curated notes.
- Dependencies: REL-001 supplies the validated version; final artifact names should come from the packaging contract
- Timing: Needs design
- Confidence: High

### BUILD-001. Make source-to-bundle parity the default headless-tree check

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: `scripts/check_headless_tree_sync.py`; `scripts/build_codebook_tree.sh`; `tests/test_static_asset_contracts.py`; `src/ace/static/js/codebook_headless_tree_source.js` and generated `codebook_headless_tree.js`
- Evidence: The default check verifies only that three files exist and that the generated bundle contains a source-path comment; the test named `test_headless_tree_distribution_matches_source` calls that shallow mode without `--rebuild`. A controlled fixture with deliberately unrelated source and bundle content returned 0 and printed `headless-tree-contract-ok`. On the real checkout, the default check passes but `uv run python scripts/check_headless_tree_sync.py --rebuild` fails. A temporary-output comparison found a 114,273-byte committed bundle versus a 127,312-byte rebuild; after normalising bundler wrappers, the committed source section still calls `flashStatus("Saved")` in two paths and defines the timer helper, while the authored source calls `setStatus("")` and has no helper. The check restores the tracked file correctly, so the audit left production unchanged.
- Current contract: The committed distribution is a reproducible build of the reviewed source and declared dependency versions; tests fail whenever source, dependency output, or the generated artifact drifts.
- Why it matters: Browsers execute the generated file, while developers review and edit the source. A green test can currently ship behaviour that the authored source no longer contains and can hide future security or correctness fixes.
- Recommendation: Make a deterministic rebuild-and-compare the only meaning of the parity test, run it in CI, and give the cheap existence/marker probe a different name if it remains useful. Track an npm lockfile or equivalent immutable dependency resolution for the build, and regenerate the bundle in the eventual implementation commit.
- Expected simplification or measured benefit: Establish one authoritative generated-asset contract and remove the misleading distinction between a green marker check and an optional real sync check.
- Tests required first: Preserve a fast unit fixture proving stale content fails, add dependency-lock validation, and retain restoration-on-build-failure coverage so the check never dirties the worktree.
- Verification: Run the parity check from a clean checkout twice, confirm byte-identical output and a clean `git status`, then run static asset and codebook E2E suites in all three engines.
- Dependencies: TREE-001
- Timing: Safe now
- Confidence: High

### CI-001. Give publishing credentials only to publishing jobs

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: top-level `permissions` in `.github/workflows/pages.yml` and `.github/workflows/release.yml`
- Evidence: The Pages workflow grants `pages: write` and `id-token: write` at workflow scope, so its pull-request build job receives the same requested capability even though upload/deploy steps are skipped on pull requests. The release workflow grants `contents: write` to every matrix build step that checks out and executes repository build code, although only the API preflight, draft preparation, and release upload need it. Live repository settings currently grant the workflow token write permission, so the release workflow's broad request is effective rather than merely declarative.
- Current contract: Pull requests can render documentation without publishing; release builds can compile untrusted-by-the-publisher source inputs without release-write authority; only narrowly scoped jobs can mutate Pages or GitHub releases.
- Why it matters: Broad workflow permissions increase the impact of a compromised dependency, action, or build script and make read-only validation jobs harder to reason about.
- Recommendation: Default both workflows to `contents: read`. Grant `pages: write` and `id-token: write` only on the Pages deploy job. Split release compilation from publication: build with read access, pass installers through Actions artifacts, and let a small publisher job with `contents: write` upload them to the validated draft.
- Expected simplification or measured benefit: Make credential ownership match job responsibility and isolate state-changing GitHub API calls from repository build execution.
- Tests required first: Add workflow-policy checks that assert job-level permissions and dependency flow; retain pull-request rendering, tag builds, manual dispatch, draft reuse, and asset upload behaviour.
- Verification: Validate workflow syntax, run a Pages pull request and deployment, run a test-tag release, and query the effective workflow permissions after deployment.
- Dependencies: REL-001 and REL-002 define the preflight and publisher inputs
- Timing: Needs design
- Confidence: High

### TEST-001. Reuse browser infrastructure without weakening test isolation

- Status: Open
- Priority: Medium
- Category: Performance
- Where: `tests/e2e/conftest.py::ace_server`, `browser_params`; all 17 `tests/e2e/test_*.py` modules
- Evidence: The browser suite contains 153 test functions; every function calls `sync_playwright()` and launches a browser, and every function is parametrised across Chromium, Firefox, and WebKit, producing 459 collected browser items and up to 459 browser launches. The function-scoped `ace_server` fixture also creates a fresh project and starts a fresh uvicorn process for each item; its own module note measures server startup at about 1.5-2 seconds per test. The representative full-suite baseline is 1,158 passes in 862.57 seconds, while the three focused P4 browser groups took 159.43, 222.70, and 59.62 seconds for 268 items. This finding concerns repeated infrastructure startup, not the substantive browser assertions.
- Current contract: Every browser item receives a fresh project database, independent browser storage and DOM state, deterministic server state, and coverage in all three engines; failures must remain attributable to one test.
- Why it matters: Hundreds of process launches dominate the feedback loop and make the complete local suite expensive enough to discourage routine use, while adding no product-state coverage by themselves.
- Recommendation: Prototype session- or engine-scoped Playwright/browser processes with a fresh browser context per test. Reuse an ACE server only behind an explicit reset/open-project contract that clears project, coder, undo, agreement, and runtime state; do not introduce parallel execution while the application remains intentionally single-user and stateful.
- Expected simplification or measured benefit: Centralise 153 repeated Playwright launch blocks and remove hundreds of browser/server startups. Measure the prototype against the 459-item baseline before adopting it; no speed-up target is assumed in advance.
- Tests required first: Add isolation sentinels that deliberately leave project, undo, local-storage, session, and agreement state behind and prove the next test starts clean in every engine.
- Verification: Run the complete browser matrix twice, including a randomised-order run, compare failures and wall time with the recorded baseline, then run all 1,158 Python tests.
- Dependencies: None
- Timing: Needs tests first
- Confidence: High

### TEST-002. Bring chord-key browser coverage into the shared three-engine matrix

- Status: Open
- Priority: Medium
- Category: Tests
- Where: `tests/test_chord_keys_e2e.py`; `tests/e2e/conftest.py`; `tests/e2e/`
- Evidence: `tests/test_chord_keys_e2e.py` contains five real Playwright tests but sits outside the browser-test directory, starts its own module-scoped server, and launches Chromium directly rather than using `browser_params()`. Consequently, the normal `pytest tests/e2e` browser run does not collect these tests, and Firefox and WebKit never exercise chord application, chord allocation, dialog use, reserved-key behaviour, or case handling. The shared browser harness already provides installed-engine skips and parametrises every in-directory browser test across Chromium, Firefox, and WebKit.
- Current contract: Chord assignment and application, reserved single-key shortcuts, case handling, and the code-creation dialog continue to behave exactly as the five tests specify.
- Why it matters: ACE ships Chromium- and WebKit-based desktop surfaces and supports Firefox in the browser. A keyboard feature with browser-specific event handling currently has only Chromium regression coverage and is easy to omit from a focused browser run.
- Recommendation: Move the five tests into `tests/e2e/`, replace the bespoke server/browser scaffolding with the shared fixtures and `browser_params()` contract, and keep their assertions unchanged unless cross-engine behaviour exposes a real product defect.
- Expected simplification or measured benefit: Remove the second browser harness for this feature and turn five Chromium-only checks into fifteen consistently discovered matrix items.
- Tests required first: The existing five tests are the characterisation suite; record their current Chromium result before moving them.
- Verification: Run the migrated module in Chromium, Firefox, and WebKit, then run the complete `tests/e2e` collection and confirm all fifteen parametrised items are present.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### TEST-003. Define explicit fast, browser, and release verification lanes

- Status: Open
- Priority: Medium
- Category: Tooling
- Where: `pyproject.toml::tool.pytest.ini_options`; `tests/e2e/`; desktop and static-contract test modules
- Evidence: Pytest configuration defines only `testpaths = ["tests"]` and `pythonpath = ["src"]`; it registers no markers or named lanes. The default command therefore mixes fast model/service tests, 459 browser items, launcher lifecycle waits, packaging checks, and generated-asset contracts into the 14-minute baseline. Focused audit checks had to use hand-maintained path lists, and `pytest tests/e2e` still misses the five browser tests in TEST-002. There is no supported command that both runs quickly and proves it selected the intended contract tier.
- Current contract: `uv run pytest` continues to collect and run the complete suite, and no test is silently dropped from default discovery.
- Why it matters: Contributors must know repository layout to choose feedback of the right cost. That makes quick checks inconsistent, complicates CI design, and increases the risk that a narrow local command omits a relevant contract.
- Recommendation: Register a small marker or command vocabulary for fast Python, browser matrix, launcher/release, and generated-contract checks. Keep the all-tests default, document the exact lane union, and make collection-count assertions or CI reporting expose accidental omissions.
- Expected simplification or measured benefit: Replace repeated bespoke path lists with stable commands whose cost and coverage are obvious, providing the foundation for CI-002 without changing product code.
- Tests required first: Capture the current 1,158-item collection and classify every item exactly once for execution ownership, allowing intentionally overlapping smoke checks only when documented.
- Verification: Compare `--collect-only` output for each lane with the baseline, assert the union has no unexplained gaps, run each lane independently, then run the unchanged full-suite command.
- Dependencies: TEST-002
- Timing: Needs design
- Confidence: High

### DATA-001. Keep the two sample-data import routes byte-identical

- Status: Open
- Priority: Medium
- Category: Correctness risk
- Where: `examples/ace-guide-manchester-folk-methods/sources.csv`; `examples/ace-guide-manchester-folk-methods/sources/P01.txt`; `sources/P19.txt`; sample-data documentation
- Evidence: The sample README and website state that `sources.csv` and `sources/` contain the same 19 transcripts. Parsing the CSV with Python's `csv.DictReader` and comparing each `text` field with its UTF-8 file finds 17 exact matches, but P01 is 56,409 characters in the text file and 56,410 in CSV because CSV has one trailing space; P19 is 37,092 versus 37,093 because CSV has one trailing newline. `_combine_text_columns` and `_read_text_file` preserve these characters, `source_content` hashes exact content, and agreement matches sources across projects by `content_hash`. If coders choose different advertised import routes, P01 and P19 can therefore be classified as unmatched source texts.
- Current contract: CSV and folder imports of the guide sample create P01-P19 with identical display IDs, content text, hashes, sentence offsets, and agreement eligibility.
- Why it matters: The sample is meant to teach interchangeable import routes and collaborative comparison. A one-character generation drift is invisible during reading but changes the identity ACE deliberately uses for agreement.
- Recommendation: Choose the text files as the canonical source and generate the CSV text column from them, or generate both from one canonical dataset. Normalise only in that generation step; do not silently strip arbitrary user imports to repair a sample-data defect.
- Expected simplification or measured benefit: Give the sample one source of truth and eliminate two route-dependent source identities without changing importer behaviour.
- Tests required first: Add a sample-integrity test that parses the CSV and asserts exact text equality, ordered IDs P01-P19, UTF-8 decoding, and the expected codebook header/count.
- Verification: Import the CSV and folder into separate fresh projects, compare all 19 stored display IDs/content hashes, and run agreement loader validation to confirm all 19 texts match.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### DOC-002. Replace obsolete developer and desktop instructions with the current architecture

- Status: Open
- Priority: Medium
- Category: Documentation
- Where: `CONTRIBUTING.md`; `website/install.qmd`; current split route modules, headless-tree frontend, and `desktop/launcher/`
- Evidence: The website tells developers that the desktop app is a Tauri wrapper and to run `cd desktop; cargo tauri dev`, but the tracked desktop implementation is the Rust `desktop/launcher` packaged with cargo-packager and the repository has no Tauri manifest. `CONTRIBUTING.md` still presents `api.py` as the sole HTMX endpoint owner, names Sortable as the vendored drag library, and uses a `group_name` codebook example even though routes are split, the headless-tree controller owns drag/reorder, Sortable is unused, and folders use `kind`/`parent_id`. Its only test instruction is the 14-minute all-tests command, and its release checklist was not followed by v1.6.1. These are concrete false commands and ownership claims, not requests to document every internal detail.
- Current contract: A new contributor can start the web app, choose the correct desktop development path, run an appropriately scoped verification lane, find the actual owner of a change, and follow one release checklist that produces the documented result.
- Why it matters: The current desktop command cannot work in this checkout, and stale layout/library guidance sends changes toward compatibility surfaces the audit is proposing to remove.
- Recommendation: Make one concise contributor guide the authoritative source for development, testing, project ownership, generated assets, and release steps; have the website link to it instead of restating volatile internals. Update ownership and commands after the approved route/frontend/test/release batches so the guide describes the resulting architecture once.
- Expected simplification or measured benefit: Remove contradictory setup/release narratives and prevent contributors from learning the retired Tauri, Sortable, group-name, and monolithic-router designs.
- Tests required first: No product test is needed; add command/file-existence checks for literal developer commands where practical and reuse release/test contract validators rather than testing prose copies.
- Verification: Execute every documented command on a clean checkout, render all 17 website pages, validate links, and have a second reviewer follow the setup/test/release path without undocumented repository knowledge.
- Dependencies: ROUTE-001, TEST-003, REL-001, and REL-002
- Timing: Wait
- Confidence: High

### DOC-003. Recapture public screenshots without personal paths or obsolete UI

- Status: Open
- Priority: Medium
- Category: Documentation
- Where: `website/assets/guide/new-project-folder-selected.png`; `website/assets/ace-landing-page-2026-06.png`; `website/user-guide/import.qmd`; `website/index.qmd`
- Evidence: Visual inspection of all seven referenced PNGs found that the new-project guide image publishes the full local path `/Users/jhar8696/Sydney Uni Dropbox/Januar Harianto/projects/...` in both the selected folder and project-file preview. The website home hero is a separate June screenshot of the retired purple-gradient landing design and omits current destinations shown by the newer `guide/landing.png`. Asset-reference mapping confirms both images are rendered on public pages; the remaining guide images are referenced and broadly reflect current workflows.
- Current contract: Public documentation screenshots show the workflow accurately, contain no developer-specific paths or unrelated local information, and use the public sample data only where content is visible.
- Why it matters: A published local filesystem path leaks unnecessary personal/workplace context and teaches users from a UI that no longer matches the app.
- Recommendation: Recapture the two images from a deterministic documentation profile using a neutral synthetic home/project path, or crop/redact path fields when the path itself is not instructional. Keep a short capture checklist with viewport, sample project, route, and required redactions so future updates are repeatable.
- Expected simplification or measured benefit: Remove one privacy leak and one obsolete duplicate landing representation while retaining the seven-image guide structure.
- Tests required first: No production characterisation is needed; record the current use sites and intended visual state before replacing the binaries.
- Verification: Inspect the replacement images at original resolution, render the website, confirm every asset is referenced once or intentionally reused, and search rendered image text manually/OCR for usernames and absolute local roots.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### DOC-004. Give instructional website images meaningful alternative text

- Status: Open
- Priority: Medium
- Category: Documentation
- Where: `website/index.qmd`; `website/getting-started.qmd`; `website/sample-data.qmd`; `website/workflow.qmd`; `website/user-guide/codebooks.qmd`, `coding.qmd`, and `import.qmd`
- Evidence: The 17-page website renders successfully, all local image references resolve, and all seven PNG assets have valid signatures. However, 10 of the 11 Markdown image uses have an empty `![](...)` label; only `user-guide/audit.qmd` describes its screenshot. The empty images are instructional views of landing, import choices/review, new-project path selection, coding, and the website hero rather than decorative spacers, and no adjacent figure attributes supply replacement text.
- Current contract: A reader who cannot see the screenshots receives the same workflow-relevant information without forcing decorative detail into the reading order; repeated images use context-appropriate descriptions.
- Why it matters: The public guide currently removes information from screen-reader and text-only users at the exact points where screenshots demonstrate controls and layout.
- Recommendation: Add concise, purpose-led alternative text at each use site. Mark an image decorative only when the surrounding prose already conveys everything and the image adds no instructional information.
- Expected simplification or measured benefit: Close ten explicit image-accessibility gaps without changing layout or adding a separate caption system.
- Tests required first: Add a small rendered-site assertion that instructional `img` elements have non-empty `alt` values, with an explicit allowlist for truly decorative images.
- Verification: Render all pages, inspect the generated `img` elements, run an accessibility scan, and read the affected pages with images disabled or a screen reader.
- Dependencies: DOC-003 for replacement image content
- Timing: Safe now
- Confidence: High

### DOC-005. Explain WAL and SHM sidecars in project-file and cloud-sync guidance

- Status: Open
- Priority: Medium
- Category: Documentation
- Where: `website/reference/file-format.qmd`; `website/reference/faq.qmd`; `website/workflow.qmd`; `src/ace/db/connection.py::open_project`, `create_project`, and `checkpoint_and_close`; `src/ace/app.py` shutdown
- Evidence: Public guidance says ACE stores each project in one `.ace` file and advises users to choose a backed-up or cloud-synced location, but never mentions SQLite sidecars. Every project connection enables WAL mode, which normally creates `<project>.ace-wal` and `<project>.ace-shm` beside the main file while ACE is open. On a clean application shutdown, `checkpoint_and_close` runs `wal_checkpoint(TRUNCATE)`, switches to DELETE journal mode, and closes; application shutdown calls it for the active project. Forced termination or a sync occurring while the project is open can still expose the sidecars, and they must not be treated as independent documents or deleted during use.
- Current contract: The `.ace` file remains the durable project artifact; WAL/SHM files are expected SQLite working files, clean shutdown consolidates committed data, and recovery semantics are not weakened.
- Why it matters: Users seeing unfamiliar files in OneDrive may delete, move, share, or open only part of an active SQLite database. The current “one file” wording and cloud-folder advice omit the operational rule needed to avoid that mistake.
- Recommendation: Document what the two sidecars are, that OneDrive or another sync client creates neither file but may sync them, and that users should close ACE before copying, moving, sharing, or opening the project elsewhere. State that sidecars may remain after a crash and should be left beside the `.ace` file until ACE has reopened and closed it cleanly; do not promise that every forced exit removes them.
- Expected simplification or measured benefit: Replace support-by-explanation with one accurate project-file contract and give users a safe response to the exact files they can observe.
- Tests required first: No implementation test is required for the documentation change; retain `checkpoint_and_close` WAL truncation/removal tests and lifecycle shutdown tests as the behavioural source of truth.
- Verification: Render the website, verify the file-format/FAQ/workflow pages agree, and manually create/open/close a project in a synced test folder to confirm the documented clean and forced-exit states.
- Dependencies: None
- Timing: Safe now
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
- Dependencies: None
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

### PACK-001. Replace the substring package check with the existing semantic validation

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `scripts/build_launcher_package.py::_check`; `tests/test_launcher_packager_config.py`; `tests/test_desktop_config.py`
- Evidence: `_check` treats `Packager.toml` as text and succeeds when the five field names appear anywhere, then checks only that Cargo.toml, main.rs, and the icons directory exist. Running the real function under ACE's Python 3.12 against an invalid TOML file whose comment contained `product-name identifier version binaries resources`, plus empty Cargo/Rust files, printed `Check passed` and returned successfully. The repository already has 16 focused tests that parse the real TOML, compare Cargo and Packager versions, and inspect formats, resources, sections, and icon paths; those tests pass, so the shallow command is duplicated weaker validation rather than the sole defence.
- Current contract: `--check` remains a cheap no-build preflight, but success means the manifests parse and agree, required paths are valid for the host, and configuration is ready for the requested package mode.
- Why it matters: A command presented and recorded as package validation can give a false green result for a configuration that cargo-packager cannot parse.
- Recommendation: Extract one semantic validator using `tomllib` and explicit path/version checks, call it from both tests and `--check`, or remove the redundant command and make the focused tests the documented preflight. Distinguish configuration validity from payload/build readiness in its output and exit status.
- Expected simplification or measured benefit: Remove two competing definitions of a valid launcher package and make every green preflight carry the same meaning.
- Tests required first: Add invalid TOML, commented field names, version drift, missing resource, wrong-host format, and config-only versus package-ready cases.
- Verification: Run the validator fixtures, desktop/packager tests, `--check`, Rust tests, and the platform packaging workflows.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### ICON-001. Generate a multi-resolution Windows application icon

- Status: Open
- Priority: Low
- Category: Correctness risk
- Where: `desktop/launcher/icons/icon.ico`; icon sources and `desktop/launcher/Packager.toml`
- Evidence: The packager explicitly consumes `icons/icon.ico`. Binary inspection reports a 495-byte Windows icon resource containing exactly one 16×16 PNG image, while the same tracked icon set includes a 1024×1024 RGBA source PNG and 32, 128, and 256 px PNGs. Existing desktop tests assert only that icon paths exist; the successful live Windows releases prove packaging accepts the ICO but do not validate its rendered quality at taskbar, Start menu, installer, or high-DPI sizes.
- Current contract: The installed Windows executable, NSIS installer, MSI, taskbar, shortcuts, and file association use a crisp ACE icon at the sizes Windows requests; macOS icon output remains unchanged.
- Why it matters: A single 16 px representation must be upscaled or substituted on common Windows surfaces, producing avoidable blur and making the released application look unfinished.
- Recommendation: Generate `icon.ico` reproducibly from the high-resolution source with the standard small and high-DPI representations, document the source/provenance command, and validate the ICO directory rather than file existence alone.
- Expected simplification or measured benefit: Make every platform icon derive from one reviewed source and remove the need for manual Windows visual guesswork during each release.
- Tests required first: Parse the ICO directory and assert required dimensions/bit depth; keep existence and Packager.toml reference checks.
- Verification: Run icon/config tests, build NSIS and MSI in CI, and inspect the executable, installer, Start menu, taskbar, shortcut, and `.ace` association on Windows at normal and high DPI.
- Dependencies: None
- Timing: Safe now
- Confidence: High

### REPO-001. Stop the repository ignore file from hiding the whole docs tree

- Status: Open
- Priority: Low
- Category: Simplification
- Where: `.gitignore` entries `.superpowers/` and `docs/`; local/global ignore policy for audit and planning artifacts
- Evidence: The repository ignore file excludes the entire `docs/` tree plus the retired-looking `.superpowers/` root. No file under either path is tracked, and the current local planning material lives under globally ignored/local-only paths. Ignoring all of `docs/` means `git status` cannot reveal an accidentally created legitimate documentation file anywhere under that conventional root; it is broader than the stated local-only `docs/superpowers/` boundary.
- Current contract: `AGENTS.md`, audit plans, Superpowers specifications/plans, `.Codex/`, and other local agent artifacts remain untracked and never enter commits; public documentation continues to live in the tracked root and `website/` unless the project deliberately changes that layout.
- Why it matters: A repository-wide ignore rule silently hides future documentation and leaves two competing mechanisms for the same local-only policy.
- Recommendation: Remove the obsolete `.superpowers/` rule and the broad `docs/` rule, relying on the configured global/local exclude for agent artifacts; if the repository must protect collaborators without that configuration, narrow the repository rule to the exact local-only subtree after confirming the policy with maintainers.
- Expected simplification or measured benefit: Replace two broad historical ignores with one explicit ownership rule and make accidental legitimate `docs/` files visible to normal git review.
- Tests required first: Use `git check-ignore -v` on representative agent-plan and legitimate-doc paths before changing the rules so the retained local exclusion is proven.
- Verification: Confirm local plans remain ignored, `git status` exposes a temporary legitimate `docs/example.md`, no existing tracked/generated path changes classification, and the two audit trackers remain the only committed audit artifacts.
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
- **Reuse the existing server when a launcher receives an `.ace` path:** The Rust launcher deliberately starts a fresh server for every file-open invocation, even before a heartbeat, and lifecycle tests assert that contract. This avoids retargeting the process behind a tab that has opened but has not registered yet. Any resource optimisation would need a stronger session handshake, not deletion of the apparent `active_tabs` branch in isolation.
- **Add code signing during this refactor:** Current DMG, NSIS, and MSI releases intentionally disclose that they are unsigned. Signing would materially improve installation trust, but it requires certificates, secret custody, platform accounts, and an external operating decision beyond a code-structure refactor. Keep it as a separately authorised release-security project; do not let it block the audit findings above.
- **Add checksum files without a signing/provenance model:** A checksum hosted beside an unsigned binary protects against accidental corruption but not compromise of the release account that serves both files. Revisit checksums together with signing or artifact attestations so the trust model and user verification instructions are explicit.
- **Merge all agreement tests because two modules reuse test names:** The duplicate `test_perfect_agreement` and `test_no_agreement` names exercise different layers: the private Cohen-kappa helper and the public sparse agreement computation. The remaining agreement modules cover pooled metrics, loader-to-computer integration, and verdict contracts without whole-file duplication. Consolidating them would blur those boundaries rather than remove repeated behaviour.
- **Rearrange the entire test tree before fixing its feedback loops:** Tests currently span top-level modules, `tests/routes`, `tests/services`, and `tests/test_services`, and `test_e2e_plan_a.py` is an integration-flow name rather than a browser test. Those labels are untidy, but moving dozens of stable modules produces review churn without fixing collection cost or coverage. Rename or relocate a module only when TEST-002, TEST-003, or an owning production change already touches it.
- **Delete duplicate logo files solely because their hashes match:** `brand/logo.svg`, `src/ace/static/logo.svg`, and `website/assets/logo.svg` are byte-identical, as are the brand/application favicon and light-logo pairs. They belong to separate brand-source, Python-package, and Quarto-site roots with direct consumers, and no observed release has drifted between them. Keep the explicit copies unless a later asset build can own and verify regeneration without adding a more fragile dependency.
- **Upgrade every package reported as merely outdated:** The dependency scan found newer versions for several runtime and developer packages, but age alone is not a defect. DEP-001 is limited to the locked packages with published advisories and a tested compatible resolution; evaluate unrelated major/minor upgrades separately with their own release notes and contract tests.
- **Rewrite historical changelog terminology:** Older entries accurately describe the UI and implementation shipped at those versions, including groups, SortableJS, alpha, and kappa. Correct current contributor/user guidance and new release metadata, but preserve historical entries unless a factual error prevents understanding that release.
- **Strip trailing whitespace from all user imports to repair the sample:** ACE currently preserves source text exactly, and offsets and exports rely on that contract. DATA-001 is a generation defect in two controlled sample representations; fix the sample source of truth instead of silently changing arbitrary research data during import.

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
