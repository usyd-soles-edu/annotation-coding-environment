# ACE Codebase Audit Coverage

Generated: 2026-07-17
Branch: `audit/codebase-optimisation`
Baseline commit: `8ec4e8bd23d1f4e42076b6704d65e5832e0953f4`
Plan: local uncommitted `CODEBASE_AUDIT_PLAN.md`

## Progress Dashboard

| Pass | Scope | Assigned files | Reviewed | Findings | Status |
|---|---|---:|---:|---:|---|
| P0 | Baseline and inventory | Repository-wide | 228/228 inventoried | 0 | Complete |
| P1 | Architecture and integration seams | 6 | 6/6 | 4 | Complete |
| P2 | Persistence, models, and services | 25 | 25/25 | 8 | Complete |
| P3 | Routes, templates, and HTMX contracts | 18 | 18/18 | 7 | Complete |
| P4 | Frontend JavaScript and CSS | 14 | 0/14 | 0 | Pending |
| P5 | Desktop, packaging, and release engineering | 17 | 0/17 | 0 | Pending |
| P6 | Tests and developer feedback loops | 76 | 0/76 | 0 | Pending |
| P7 | Docs, dependencies, and synthesis | 72 | 0/72 | 0 | Pending |

## P0 Baseline Checklist

- [x] Create the fresh audit branch from current `main`.
- [x] Generate a coverage row from `git ls-files` for every tracked file.
- [x] Assign each tracked file a primary audit pass.
- [x] Classify generated, vendored, lock, binary, configuration, documentation, and authored files.
- [x] Record environment and tool versions.
- [x] Run and record the full Python test baseline.
- [x] Record slow-test durations for prioritisation.
- [x] Verify the generated headless-tree bundle is in sync.
- [x] Verify launcher packaging configuration.
- [x] Run the Rust launcher check.
- [x] Render the website where the local Quarto toolchain is available.
- [x] Record browser-matrix availability and the authoritative UI verification route.
- [x] Map major user workflows to code owners and verification surfaces.
- [x] Review every exclusion/provenance reason.
- [x] Complete and commit P0 artifacts.

## Baseline Environment

| Surface | Version or availability |
|---|---|
| Host | macOS Darwin 25.5.0, Apple Silicon (`arm64`) |
| uv | 0.10.0 |
| Python | 3.12.12 |
| pytest | 9.0.2 |
| Rust | `rustc` 1.94.0; Cargo 1.94.0 |
| Quarto | 1.9.37 |
| Playwright Chromium | Installed |
| Playwright Firefox | Installed |
| Playwright WebKit | Installed |

## Baseline Checks

| Check | Result | Evidence |
|---|---|---|
| Generated headless-tree synchronisation | Pass | `uv run python scripts/check_headless_tree_sync.py` → `headless-tree-contract-ok` |
| Launcher package configuration | Pass with expected pre-build note | `uv run python scripts/build_launcher_package.py --check`; launcher resources are generated only during the full sidecar build |
| Rust launcher | Pass | `cargo check --manifest-path desktop/launcher/Cargo.toml` |
| Website | Pass | `quarto render website`; 17 pages rendered to `website/_site/index.html` |
| Browser availability | Pass | Chromium, Firefox, and WebKit executables are installed locally |
| Python dependency lock | Pass | `uv lock --check`; 36 packages resolved without changing `uv.lock` |
| Rust dependency lock | Pass | `cargo metadata --manifest-path desktop/launcher/Cargo.toml --locked --no-deps --format-version 1`; launcher version 1.6.1 resolved from the committed lock |
| Coverage and provenance classification | Pass | All 226 baseline paths plus the two subsequently committed audit trackers are represented once; no missing, extra, duplicate, or unreasoned generated/vendored/lock/binary rows. Vendored version markers: Sortable 1.15.6, fuzzysort 3.0.2, htmx 2.0.4 |
| Full pytest baseline and durations | Pass | `uv run pytest --durations=25 -q`; 1,158 passed in 862.57 s (14:22) |

### Slowest Baseline Tests

These timings prioritise later feedback-loop review; they are not performance findings by themselves.

| Duration | Test |
|---:|---|
| 11.31 s | `tests/test_launcher_lifecycle.py::TestIdleShutdown::test_server_exits_after_idle_timeout` |
| 5.06 s | `tests/e2e/test_agreement_file_review.py::test_agreement_back_while_compute_pending_ignores_late_result[firefox]` |
| 5.03 s | `tests/test_launcher_lifecycle.py::TestServerStartsReachable::test_server_reachable_after_launch` |
| 4.97 s | `tests/e2e/test_agreement_file_review.py::test_agreement_review_removes_file_and_recomputes_match_count[webkit]` |
| 4.22 s | `tests/e2e/test_agreement_file_review.py::test_agreement_back_while_compute_pending_ignores_late_result[webkit]` |
| 3.93 s | `tests/e2e/test_agreement_file_review.py::test_agreement_back_while_compute_pending_ignores_late_result[chromium]` |
| 3.91 s | `tests/e2e/test_agreement_file_review.py::test_agreement_review_removes_file_and_recomputes_match_count[firefox]` |
| 3.45 s | `tests/e2e/test_code_view_edit_mode.py::test_edit_mode_save_button_persists_code_details[firefox]` |
| 2.94 s | `tests/e2e/test_codebook_cues.py::test_wording_cues_discard_stale_responses[firefox]` |
| 2.89 s | `tests/e2e/test_note_drawer_status.py::test_note_autosave_does_not_replace_long_note_warning[firefox]` |
| 2.87 s | `tests/e2e/test_agreement_file_review.py::test_agreement_review_removes_file_and_recomputes_match_count[chromium]` |
| 2.73 s | `tests/e2e/test_coding_keyboard_navigation.py::test_shift_arrow_reports_source_navigation_boundaries[firefox]` |
| 2.64 s | `tests/e2e/test_note_drawer_status.py::test_note_autosave_shows_saved_status[firefox]` |
| 2.48 s | `tests/e2e/test_codebook_cues.py::test_wording_cues_fetch_after_focus_and_stop_when_disabled[firefox]` |
| 2.41 s | `tests/e2e/test_import_desktop_picker.py::test_import_folder_shows_http_errors[firefox]` |
| 2.40 s | `tests/e2e/test_coding_notification_receipt.py::test_undoable_delete_uses_receipt_button[firefox]` |
| 2.38 s | `tests/e2e/test_codebook_cues.py::test_wording_cues_menu_item_toggles_and_persists[firefox]` |
| 2.33 s | `tests/e2e/test_codebook_cues.py::test_wording_cues_clear_and_stop_while_codebook_filter_is_active[firefox]` |
| 2.32 s | `tests/e2e/test_codebook_sidebar_controller.py::test_coded_text_view_codebook_supports_editing_without_text_apply[firefox]` |
| 2.30 s | `tests/e2e/test_coding_text_preferences.py::test_coding_text_width_control_supports_presets_and_reload[firefox]` |
| 2.28 s | `tests/e2e/test_coding_keyboard_navigation.py::test_source_right_focuses_applied_rail_when_collapsed[firefox]` |
| 2.26 s | `tests/e2e/test_codebook_zone_indicator.py::test_headless_folder_double_click_rename_saves_on_blur[firefox]` |
| 2.25 s | `tests/e2e/test_codebook_zone_indicator.py::test_headless_folder_double_click_rename_accepts_typing[firefox]` |
| 2.25 s | `tests/e2e/test_coding_keyboard_navigation.py::test_codebook_right_returns_to_source_from_folder[firefox]` |
| 2.25 s | `tests/e2e/test_code_view_edit_mode.py::test_metadata_saves_are_single_flight_and_keep_latest_draft[firefox]` |

## User Workflow Map

| Workflow | Primary implementation owners | Representative verification surfaces |
|---|---|---|
| Browser launch, session tracking, Quick Resume, and shutdown | `src/ace/app.py`, `src/ace/routes/runtime.py`, `src/ace/services/browser_runtime.py`, `src/ace/static/js/runtime.js`, `src/ace/templates/landing.html`, `desktop/launcher/src/main.rs` | `tests/test_app.py`, `tests/test_browser_runtime.py`, `tests/test_runtime_routes.py`, `tests/test_launcher_lifecycle.py`, `tests/e2e/test_landing_desktop_picker.py`, `tests/e2e/test_setup_keyboard.py` |
| Project creation/opening, file selection, import, and annotation export | `src/ace/routes/api_project_import.py`, `src/ace/routes/pages.py`, `src/ace/services/importer.py`, `src/ace/services/exporter.py`, project/source models, landing/import templates | `tests/test_project.py`, `tests/test_import.py`, `tests/test_importer_lazy_openpyxl.py`, `tests/test_services/test_importer.py`, `tests/test_services/test_exporter.py`, import/setup E2E tests |
| Coding, annotation mutation, navigation, notes, flags, cues, and undo/redo | `src/ace/routes/api_coding.py`, annotation and source-note models, `src/ace/services/undo.py`, `coding_render.py`, `code_cues.py`, `src/ace/static/js/bridge.js`, coding templates/CSS | Coding route/model/service tests, `tests/routes/test_coding_annotations.py`, `test_coding_notes.py`, keyboard/navigation/notification/note E2E tests |
| Codebook editing, hierarchy, shortcuts, import/export, and coded-text audit | `src/ace/routes/api_codebook.py`, codebook models/invariants, undo service, `bridge.js`, `code_view.js`, headless-tree source, codebook/code-view templates and CSS | Codebook model/route tests, static-asset contracts, code-view edit-mode and codebook E2E suites |
| Agreement file review, computation, verdicts, and exports | `src/ace/routes/api_agreement.py`, agreement services/types/loader/computer/verdict, agreement templates/CSS | Agreement route/service/computer/verdict tests and `tests/e2e/test_agreement_file_review.py` |
| Desktop packaging, website, CI, and release publication | `desktop/launcher/`, `scripts/`, `.github/workflows/`, `website/`, manifests and locks | Desktop/packager/static-asset tests, Rust check, launcher configuration check, website render, release workflow |

## Status Definitions

- **Pending:** Assigned but not yet directly reviewed.
- **Reviewed:** Direct evidence has been examined and the outcome recorded.
- **Excluded:** Direct code review is inappropriate; the provenance or exclusion check is complete.
- **Needs follow-up:** Initial review found a question that must be resolved before the row is complete.

## Coverage Ledger

| Path | Kind | Audit pass | Status | Evidence reviewed | Finding IDs | Exclusion or provenance reason |
|---|---|---|---|---|---|---|
| `.github/workflows/pages.yml` | Configuration | P5 | Pending | — | — | — |
| `.github/workflows/release.yml` | Configuration | P5 | Pending | — | — | — |
| `.gitignore` | Configuration | P7 | Pending | — | — | — |
| `.zenodo.json` | Configuration | P7 | Pending | — | — | — |
| `CHANGELOG.md` | Documentation | P7 | Pending | — | — | — |
| `CITATION.cff` | Asset/support | P7 | Pending | — | — | — |
| `CODEBASE_AUDIT_COVERAGE.md` | Documentation | P7 | Pending | Audit tracker created after the 226-file baseline; coverage self-checks run after every pass | None | Audit artifact; review completeness and internal consistency during synthesis |
| `CODEBASE_AUDIT_FINDINGS.md` | Documentation | P7 | Pending | Audit tracker created after the 226-file baseline; schema and summary checks run after every pass | None | Audit artifact; review evidence and decision status during synthesis |
| `CONTRIBUTING.md` | Documentation | P7 | Pending | — | — | — |
| `INSTALL.md` | Documentation | P7 | Pending | — | — | — |
| `LICENSE` | Documentation | P7 | Pending | — | — | — |
| `README.md` | Documentation | P7 | Pending | — | — | — |
| `brand/favicon.svg` | Asset/support | P7 | Pending | — | — | — |
| `brand/logo-hex.svg` | Asset/support | P7 | Pending | — | — | — |
| `brand/logo-light.svg` | Asset/support | P7 | Pending | — | — | — |
| `brand/logo.svg` | Asset/support | P7 | Pending | — | — | — |
| `desktop/.gitignore` | Asset/support | P5 | Pending | — | — | — |
| `desktop/launcher/Cargo.lock` | Lockfile | P5 | Pending | — | — | Generated dependency lock; verify manifest consistency and reproducibility |
| `desktop/launcher/Cargo.toml` | Configuration | P5 | Pending | — | — | — |
| `desktop/launcher/Packager.toml` | Configuration | P5 | Pending | — | — | — |
| `desktop/launcher/icons/128x128.png` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/icons/128x128@2x.png` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/icons/32x32.png` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/icons/icon.icns` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/icons/icon.ico` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/icons/icon.png` | Binary asset | P5 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `desktop/launcher/src/main.rs` | Authored | P5 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/README.md` | Documentation | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/codebook.csv` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources.csv` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P01.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P02.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P03.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P04.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P05.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P06.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P07.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P08.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P09.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P10.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P11.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P12.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P13.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P14.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P15.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P16.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P17.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P18.txt` | Asset/support | P7 | Pending | — | — | — |
| `examples/ace-guide-manchester-folk-methods/sources/P19.txt` | Asset/support | P7 | Pending | — | — | — |
| `pyproject.toml` | Configuration | P7 | Pending | — | — | — |
| `scripts/build_codebook_tree.sh` | Authored | P5 | Pending | — | — | — |
| `scripts/build_launcher_package.py` | Authored | P5 | Pending | — | — | — |
| `scripts/build_sidecar.py` | Authored | P5 | Pending | — | — | — |
| `scripts/check_headless_tree_sync.py` | Authored | P5 | Pending | — | — | — |
| `src/ace/__init__.py` | Authored | P1 | Reviewed | Version source and packaging call sites | None | — |
| `src/ace/__main__.py` | Authored | P1 | Reviewed | CLI-to-`run` argument map; launcher invocation; call-site and history scans | ARCH-004 | — |
| `src/ace/app.py` | Authored | P1 | Reviewed | Factory, middleware, lifespan, DB ownership, app-state inventory, server/runtime call graph, lifecycle tests | ARCH-003, ARCH-004 | — |
| `src/ace/db/__init__.py` | Authored | P2 | Reviewed | Package-boundary and import scan | None | — |
| `src/ace/db/connection.py` | Authored | P2 | Reviewed | Connection lifecycle, application ID, WAL/FK setup, version-gate reproduction, and tests | DB-001 | — |
| `src/ace/db/migrations.py` | Authored | P2 | Reviewed | v1-v10 migration graph, schema probes, migration tests, and future-version reproduction | DB-001 | — |
| `src/ace/db/schema.py` | Authored | P2 | Reviewed | Schema, index, trigger, constraint, and migration-parity review | DB-001 | — |
| `src/ace/models/__init__.py` | Authored | P2 | Reviewed | Package-boundary and import scan | None | — |
| `src/ace/models/annotation.py` | Authored | P2 | Reviewed | CRUD, merge/replay SQL, transaction map, concurrency reproduction, Unicode-offset reproduction, and tests | ANN-001, TEXT-001 | — |
| `src/ace/models/assignment.py` | Authored | P2 | Reviewed | CRUD transaction, uniqueness, ordering, caller, and test review | None | — |
| `src/ace/models/codebook.py` | Authored | P2 | Reviewed | Tree invariants, ordering, transaction ownership, CSV adapter, rollback tests, and failure injection | UNDO-001, MODEL-001 | — |
| `src/ace/models/codebook_invariants.py` | Authored | P2 | Reviewed | Parent/cycle guards, schema defence, call sites, and tests | None | — |
| `src/ace/models/project.py` | Authored | P2 | Reviewed | Project/coder CRUD, uniqueness, callers, and tests | None | — |
| `src/ace/models/source.py` | Authored | P2 | Reviewed | Two-table insert, hash/order queries, commit ownership, import failure reproduction, and tests | IMPORT-001 | — |
| `src/ace/models/source_note.py` | Authored | P2 | Reviewed | Upsert/delete/read/export queries, constraints, callers, and tests | None | — |
| `src/ace/routes/__init__.py` | Authored | P1 | Reviewed | Empty package marker; import and registration map | None | — |
| `src/ace/routes/api.py` | Authored | P1 | Reviewed | Structural router composition; 63-route registration check; import/name-use and test call-site scans | ARCH-002 | — |
| `src/ace/routes/api_agreement.py` | Authored | P3 | Reviewed | Eight-route state/generation/export matrix, response and error paths, focused tests, and three-engine E2E traces | HTMX-002, ROUTE-001 | — |
| `src/ace/routes/api_codebook.py` | Authored | P3 | Reviewed | Fourteen-route guard/mutation/undo/response map, OOB validation reproduction, legacy refresh call graph, and tests | HTMX-001, CODEBOOK-001, ROUTE-001 | — |
| `src/ace/routes/api_coding.py` | Authored | P3 | Reviewed | Twelve-route guard, OOB ordering, undo/redo, note/export, sentence-action, error-path, and test review | HTMX-001, ROUTE-001 | — |
| `src/ace/routes/api_project_import.py` | Authored | P3 | Reviewed | Picker/create/open/import/export route matrix, overwrite failure injection, missing-project reproduction, and tests | PROJECT-001, HTMX-001, ROUTE-001, ROUTE-002 | — |
| `src/ace/routes/api_support.py` | Authored | P3 | Reviewed | Seventy-one-function domain/call map, fragment and header contracts, live OOB reproduction, agreement lifecycle trace, and tests | ARCH-001, HTMX-001, HTMX-002, ROUTE-001, ROUTE-002 | — |
| `src/ace/routes/pages.py` | Authored | P3 | Reviewed | Page-route redirects/guards, context and template-key contracts, render outputs, ID/ARIA checks, and tests | ARCH-001 | — |
| `src/ace/routes/runtime.py` | Authored | P3 | Reviewed | Five endpoint token/session/shutdown contracts, caller map, and runtime route tests | None | — |
| `src/ace/services/__init__.py` | Authored | P2 | Reviewed | Package-boundary and import scan | None | — |
| `src/ace/services/agreement_computer.py` | Authored | P2 | Reviewed | Sparse event algorithm, metric contracts, benchmark, Unicode-offset dependency, and tests | TEXT-001, AGREEMENT-001 | — |
| `src/ace/services/agreement_loader.py` | Authored | P2 | Reviewed | Read-only loading, schema probes, matching logic, duplicate-hash reproduction, and tests | AGREEMENT-001 | — |
| `src/ace/services/agreement_types.py` | Authored | P2 | Reviewed | Dataclass contracts, consumers, and test fixtures | AGREEMENT-001 | — |
| `src/ace/services/agreement_verdict.py` | Authored | P2 | Reviewed | Threshold, paradox, overall, pairwise, caller, and test review | None | — |
| `src/ace/services/browser_runtime.py` | Authored | P1 | Reviewed | Tracker/monitor responsibility and thread-safety map; runtime route, JavaScript, launcher, and lifecycle-test traces | None | — |
| `src/ace/services/chord_assignment.py` | Authored | P2 | Reviewed | Candidate generation, fallback, uniqueness, callers, and tests | None | — |
| `src/ace/services/code_cues.py` | Authored | P2 | Reviewed | Temporary FTS index, fallback ranking, benchmark, callers, and tests | None | — |
| `src/ace/services/coding_render.py` | Authored | P2 | Reviewed | Escaping, overlap, paragraph, sentence-offset flow, callers, and tests | TEXT-001 | — |
| `src/ace/services/exporter.py` | Authored | P2 | Reviewed | Query order, metadata collision handling, merge grouping reproduction, callers, and tests | EXPORT-001 | — |
| `src/ace/services/importer.py` | Authored | P2 | Reviewed | CSV/XLSX/text parsing, duplicate and empty handling, transaction reproduction, callers, and tests | IMPORT-001 | — |
| `src/ace/services/notes_exporter.py` | Authored | P2 | Reviewed | Query, writer, Unicode, caller, and test review | None | — |
| `src/ace/services/text_splitter.py` | Authored | P2 | Reviewed | pySBD, paragraph offsets, Unicode convention comparison, callers, and tests | TEXT-001 | — |
| `src/ace/services/undo.py` | Authored | P2 | Reviewed | Operation/handler parity, transaction map, composite failure injection, callers, and tests | UNDO-001 | — |
| `src/ace/static/agreement_methodology.md` | Documentation | P7 | Pending | — | — | — |
| `src/ace/static/agreement_references.bib` | Documentation | P7 | Pending | — | — | — |
| `src/ace/static/code_palette.json` | Configuration | P7 | Pending | — | — | — |
| `src/ace/static/css/ace.css` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/css/agreement.css` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/css/code_view.css` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/css/coding.css` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/favicon.svg` | Asset/support | P7 | Pending | — | — | — |
| `src/ace/static/js/Sortable.min.js` | Vendored | P4 | Pending | — | — | Third-party asset; verify version, integrity, loading, and replacement path |
| `src/ace/static/js/ace_notes.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/js/bridge.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/js/code_view.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/js/codebook_headless_tree.js` | Generated | P4 | Pending | — | — | Built from `codebook_headless_tree_source.js`; verify synchronisation |
| `src/ace/static/js/codebook_headless_tree_source.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/js/coding_keyboard.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/js/fuzzysort.min.js` | Vendored | P4 | Pending | — | — | Third-party asset; verify version, integrity, loading, and replacement path |
| `src/ace/static/js/htmx.min.js` | Vendored | P4 | Pending | — | — | Third-party asset; verify version, integrity, loading, and replacement path |
| `src/ace/static/js/runtime.js` | Authored | P4 | Pending | — | — | — |
| `src/ace/static/logo-light.svg` | Asset/support | P7 | Pending | — | — | — |
| `src/ace/static/logo.svg` | Asset/support | P7 | Pending | — | — | — |
| `src/ace/templates/_cheatsheet_coded_text_view.html` | Authored | P3 | Reviewed | Dialog semantics, ID references, focus/action contract, inclusion map, and rendered-page checks | None | — |
| `src/ace/templates/_sidebar_codebook.html` | Authored | P3 | Reviewed | Shared include contexts, headless-tree mount/actions, menu/export controls, ID/ARIA checks, and route traces | CODEBOOK-001 | — |
| `src/ace/templates/agreement.html` | Authored | P3 | Reviewed | Selection/compute sequencing, HTMX swap and progress contracts, history restoration, and three-engine E2E tests | HTMX-002 | — |
| `src/ace/templates/agreement_results.html` | Authored | P3 | Reviewed | Result semantics, inline listener ownership, repeated-initialisation/history Chromium reproductions, and keyboard audit | HTMX-002, A11Y-001 | — |
| `src/ace/templates/agreement_review.html` | Authored | P3 | Reviewed | Review markup, escaped JSON path payload, pending-removal state, and three-engine E2E tests | None | — |
| `src/ace/templates/base.html` | Authored | P3 | Reviewed | Block/script order, global status and live-region roots, referenced assets, and rendered-page checks | None | — |
| `src/ace/templates/code_view.html` | Authored | P3 | Reviewed | Shared sidebar, editor/data payload, dialog inclusion, rendered ID/ARIA checks, and route tests | CODEBOOK-001 | — |
| `src/ace/templates/coding.html` | Authored | P3 | Reviewed | Fragment block roots, OOB targets, data payloads, note/inspector layout, rendered ID/ARIA checks, and route tests | HTMX-001 | — |
| `src/ace/templates/import.html` | Authored | P3 | Reviewed | Wizard state/targets, OOB error recognition, native picker flow, keyboard behaviour, and three-engine E2E tests | HTMX-001, ROUTE-001 | — |
| `src/ace/templates/landing.html` | Authored | P3 | Reviewed | Open/resume/dialog flow, localStorage filename escaping, keyboard shortcuts, rendered semantics, and E2E tests | None | — |
| `src/ace/templates/new_project.html` | Authored | P3 | Reviewed | Name/folder/overwrite flow, dialog/error handling, keyboard behaviour, rendered semantics, and E2E tests | PROJECT-001 | — |
| `tests/conftest.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/__init__.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/conftest.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_agreement_file_review.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_applied_code_removal.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_code_view_edit_mode.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_context_menu.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_cues.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_import_ledger.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_menu_a11y.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_sidebar_controller.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_codebook_zone_indicator.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_coding_keyboard_navigation.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_coding_notification_receipt.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_coding_text_preferences.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_headless_tree_preview.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_import_desktop_picker.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_landing_desktop_picker.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_note_drawer_status.py` | Authored | P6 | Pending | — | — | — |
| `tests/e2e/test_setup_keyboard.py` | Authored | P6 | Pending | — | — | — |
| `tests/fixtures/make_agreement_files.py` | Authored | P6 | Pending | — | — | — |
| `tests/routes/test_code_cue_routes.py` | Authored | P6 | Pending | — | — | — |
| `tests/routes/test_coding_annotations.py` | Authored | P6 | Pending | — | — | — |
| `tests/routes/test_coding_codebook.py` | Authored | P6 | Pending | — | — | — |
| `tests/routes/test_coding_notes.py` | Authored | P6 | Pending | — | — | — |
| `tests/services/test_code_cues.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_agreement_computer.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_agreement_routes.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_agreement_verdict.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_app.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_browser_runtime.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_chord_keys_e2e.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_code_view.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_codebook_palette.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_coding_routes.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_cohens_kappa.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_db/__init__.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_db/test_chord_migration.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_db/test_connection.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_db/test_migrations.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_db/test_schema.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_desktop_config.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_e2e_plan_a.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_import.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_importer_lazy_openpyxl.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_launcher_lifecycle.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_launcher_packager_config.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/__init__.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_annotation.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_assignment.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_codebook.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_codebook_chord.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_codebook_folder.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_source.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_models/test_source_note.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_native_picker.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_project.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_render_colour_css.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_route_registration.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_runtime_routes.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/__init__.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_agreement_computer.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_agreement_e2e.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_agreement_loader.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_agreement_types.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_chord_assignment.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_coding_render.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_exporter.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_importer.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_notes_exporter.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_text_splitter.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_undo.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_services/test_undo_codebook.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_source_note_routes.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_static_asset_contracts.py` | Authored | P6 | Pending | — | — | — |
| `tests/test_status_helpers.py` | Authored | P6 | Pending | — | — | — |
| `uv.lock` | Lockfile | P7 | Pending | — | — | Generated dependency lock; verify manifest consistency and reproducibility |
| `website/.gitignore` | Asset/support | P7 | Pending | — | — | — |
| `website/_quarto.yml` | Configuration | P7 | Pending | — | — | — |
| `website/assets/ace-landing-page-2026-06.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/coding-view-with-codebook.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/folder-import-review.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/import-options.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/landing.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/new-project-folder-selected.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/guide/review-coded-text.png` | Binary asset | P7 | Pending | — | — | Verify provenance, use sites, duplication, and packaging |
| `website/assets/logo.svg` | Asset/support | P7 | Pending | — | — | — |
| `website/getting-started.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/index.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/install.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/reference/faq.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/reference/file-format.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/reference/index.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/reference/shortcuts.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/review-export.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/sample-data.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/styles.css` | Authored | P7 | Pending | — | — | — |
| `website/user-guide/agreement.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/audit.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/codebooks.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/coding.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/export.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/import.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/user-guide/notes.qmd` | Documentation | P7 | Pending | — | — | — |
| `website/workflow.qmd` | Documentation | P7 | Pending | — | — | — |
