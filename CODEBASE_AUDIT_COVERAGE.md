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
| P4 | Frontend JavaScript and CSS | 14 | 14/14 | 5 | Complete |
| P5 | Desktop, packaging, and release engineering | 17 | 17/17 | 6 | Complete |
| P6 | Tests and developer feedback loops | 76 | 76/76 | 4 | Complete |
| P7 | Docs, dependencies, and synthesis | 72 | 72/72 | 8 | Complete |

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
| Generated headless-tree marker check | Pass but shallow | `uv run python scripts/check_headless_tree_sync.py` → `headless-tree-contract-ok`; P5 proved this mode does not compare source with the bundle, and the real `--rebuild` comparison currently fails (BUILD-001) |
| Launcher package configuration | Pass with expected pre-build note | `uv run python scripts/build_launcher_package.py --check`; launcher resources are generated only during the full sidecar build |
| Rust launcher | Pass | `cargo check --manifest-path desktop/launcher/Cargo.toml` |
| Website | Pass | `quarto render website`; 17 pages rendered to `website/_site/index.html` |
| Browser availability | Pass | Chromium, Firefox, and WebKit executables are installed locally |
| Python dependency lock | Pass | `uv lock --check`; 36 packages resolved without changing `uv.lock` |
| Rust dependency lock | Pass | `cargo metadata --manifest-path desktop/launcher/Cargo.toml --locked --no-deps --format-version 1`; launcher version 1.6.1 resolved from the committed lock |
| Coverage and provenance classification | Pass | All 226 baseline paths plus the two subsequently committed audit trackers are represented once; no missing, extra, duplicate, or unreasoned generated/vendored/lock/binary rows. Vendored version markers: Sortable 1.15.6, fuzzysort 3.0.2, htmx 2.0.4 |
| Full pytest baseline and durations | Pass | `uv run pytest --durations=25 -q`; 1,158 passed in 862.57 s (14:22) |

## Focused Pass Verification

| Pass | Result | Evidence |
|---|---|---|
| P3 routes, templates, and HTMX | Pass | Focused route suite: 280 passed in 10.52 s. Agreement, import-picker, and setup E2E suite: 90 passed in 146.52 s across Chromium, Firefox, and WebKit |
| P4 frontend JavaScript and CSS | Pass with generated-asset follow-up | The shallow script mode reported `headless-tree-contract-ok`; P5 later identified the separate bundle-parity failure as BUILD-001. Static asset and focused frontend E2E suites were split into three response-safe runs: 103 passed in 159.43 s, 132 passed in 222.70 s, and 33 passed in 59.62 s (268 total), across Chromium, Firefox, and WebKit |
| P5 desktop, packaging, and release | Pass except documented bundle parity | Launcher/runtime/config suite: 41 passed in 26.39 s. Rust launcher: 6 passed with the lockfile. Package `--check` and 16 semantic config tests passed on the real manifests. The rebuild comparison failed as recorded in BUILD-001. Live GitHub checks found write permissions configured, eight recent release workflows successful, and complete DMG/NSIS/MSI assets for v1.6.0 and v1.6.1 |
| P6 tests and developer feedback loops | Pass with enforcement and test-cost findings | Full baseline: 1,158 passed in 862.57 s. Collection review found 459 browser items from 153 functions, each with its own Playwright/browser launch and function-scoped ACE server; five additional Chromium-only browser tests sit outside `tests/e2e`. Tracked workflows run no Python or Rust tests, and live default-branch rules require no status checks |
| P7 docs, dependencies, assets, and synthesis | Pass with documented metadata, dependency, sample, and accessibility gaps | Quarto rendered 17 pages; CFF validated; `uv lock --check` resolved 36 packages; 234 focused tests passed under the secure dependency overlay. All local links and 11 image use sites were checked; seven PNGs, eight SVGs, two JSON files, the 12-entry bibliography, and the 19-source sample were validated. The live DOI, vulnerability service, import parity, screenshots, and documentation were checked against current repository behaviour |

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
| `.github/workflows/pages.yml` | Configuration | P5 | Reviewed | Trigger/path matrix, PR/deploy conditions, workflow-wide permissions, concurrency, action pins, and live Pages ownership | CI-001 | — |
| `.github/workflows/release.yml` | Configuration | P5 | Reviewed | Tag/manual triggers, stateful preflight, version/draft body flow, build matrix, artifact discovery/upload, permissions, live runs, releases, assets, and repository settings | REL-001, REL-002, CI-001 | — |
| `.gitignore` | Configuration | P7 | Reviewed | Repository/global ignore boundaries, WAL/SHM patterns, generated/test output ownership, and over-broad local docs rules | REPO-001 | — |
| `.zenodo.json` | Configuration | P7 | Reviewed | Valid JSON, authors/licence/DOI/repository fields, v1.6.0 value, tag history, and live v1.6.1 archive mismatch | DOC-001 | — |
| `CHANGELOG.md` | Documentation | P7 | Reviewed | Release headings, empty Unreleased section, v1.6.1 omission, historical terminology, and release-note consumers | DOC-001, REL-002 | — |
| `CITATION.cff` | Asset/support | P7 | Reviewed | CFF 1.2.0 schema validation, authors/licence/DOI/date, and stale v1.6.0 release value | DOC-001 | — |
| `CODEBASE_AUDIT_COVERAGE.md` | Documentation | P7 | Reviewed | 228-path one-to-one ledger, pass/status arithmetic, evidence completeness, provenance, and final P0-P7 consistency | None | Audit artifact; all tracked paths reviewed and validated during synthesis |
| `CODEBASE_AUDIT_FINDINGS.md` | Documentation | P7 | Reviewed | Finding schema, severity/status arithmetic, ID/reference integrity, rejected candidates, dependencies, and proposed sequence | None | Audit artifact; complete review package with no accepted findings |
| `CONTRIBUTING.md` | Documentation | P7 | Reviewed | Setup/testing/release commands, changelog policy, architecture map, live tag history, and comparison with route/frontend/launcher owners | DOC-001, DOC-002, TEST-003 | — |
| `INSTALL.md` | Documentation | P7 | Reviewed | Git/uv/source-install commands, platform steps, local links, and current `uv run ace` entrypoint | None | — |
| `LICENSE` | Documentation | P7 | Reviewed | MIT licence text, copyright, and consistency with CFF/Zenodo metadata | None | — |
| `README.md` | Documentation | P7 | Reviewed | Feature/download/install/docs links, current asset naming, unsigned-build guidance, and stale v1.6.0 citation | DOC-001 | — |
| `brand/favicon.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, exact application-copy relationship, and use-site/provenance map | None | Intentional brand source mirrored into the Python package |
| `brand/logo-hex.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, unique hex-logo role, and repository use/provenance map | None | Distinct brand variant retained as source asset |
| `brand/logo-light.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, exact application-copy relationship, and use-site/provenance map | None | Intentional brand source mirrored into the Python package |
| `brand/logo.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, exact application/website-copy relationships, and use-site/provenance map | None | Intentional brand source mirrored into package and website roots |
| `desktop/.gitignore` | Asset/support | P5 | Reviewed | Generated launcher target/resources boundaries and tracked-file comparison | None | — |
| `desktop/launcher/Cargo.lock` | Lockfile | P5 | Reviewed | Locked metadata, root version, dependency resolution, and `cargo test --locked` | REL-001 | Generated dependency lock is consistent; 6 Rust tests pass with `--locked` |
| `desktop/launcher/Cargo.toml` | Configuration | P5 | Reviewed | Package/version contract, dependency/target matrix, locked metadata, Rust call graph, and tests | REL-001 | — |
| `desktop/launcher/Packager.toml` | Configuration | P5 | Reviewed | Semantic TOML parse, versions, formats, resources, associations, icon references, platform sections, live artifact names, and tests | REL-001, REL-002, PACK-001, ICON-001 | — |
| `desktop/launcher/icons/128x128.png` | Binary asset | P5 | Reviewed | Binary type/dimensions/checksum, manifest reference, source-set comparison, and tests | None | 128×128 RGB PNG referenced by cargo-packager |
| `desktop/launcher/icons/128x128@2x.png` | Binary asset | P5 | Reviewed | Binary type/dimensions/checksum, manifest reference, source-set comparison, and tests | None | 256×256 RGB PNG referenced by cargo-packager |
| `desktop/launcher/icons/32x32.png` | Binary asset | P5 | Reviewed | Binary type/dimensions/checksum, manifest reference, source-set comparison, and tests | None | 32×32 RGB PNG referenced by cargo-packager |
| `desktop/launcher/icons/icon.icns` | Binary asset | P5 | Reviewed | Binary container type/checksum, manifest reference, macOS packaging owner, and live DMG evidence | None | macOS ICNS referenced by cargo-packager |
| `desktop/launcher/icons/icon.ico` | Binary asset | P5 | Reviewed | ICO directory/type/dimensions/checksum, manifest reference, Windows packaging owner, live installer evidence, and test gap | ICON-001 | 495-byte ICO contains only one 16×16 representation |
| `desktop/launcher/icons/icon.png` | Binary asset | P5 | Reviewed | Binary type/dimensions/alpha/checksum, manifest reference, and source-set comparison | ICON-001 | 1024×1024 RGBA source available for reproducible platform icon generation |
| `desktop/launcher/src/main.rs` | Authored | P5 | Reviewed | Twenty-nine-function process/runtime/lock/path/security map, structural search, six Rust tests, and 41-test launcher/runtime suite | None | — |
| `examples/ace-guide-manchester-folk-methods/README.md` | Documentation | P7 | Reviewed | Import routes, flattening rules, ID normalisation, DOI attribution, CC BY 4.0 licence, and same-content claim | DATA-001 | — |
| `examples/ace-guide-manchester-folk-methods/codebook.csv` | Asset/support | P7 | Reviewed | UTF-8 parse, `name,group,definition` import contract, 132 data lines, folder mapping, and README attribution | None | Derived CC BY 4.0 codebook with import-compatible flattened hierarchy |
| `examples/ace-guide-manchester-folk-methods/sources.csv` | Asset/support | P7 | Reviewed | CSV parse, P01-P19 IDs, 19 multiline transcript rows, text-file parity, encoding, and trailing-character differences | DATA-001 | Derived CC BY 4.0 transcripts; two rows drift from folder copies |
| `examples/ace-guide-manchester-folk-methods/sources/P01.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV comparison | DATA-001 | CSV representation adds one trailing space |
| `examples/ace-guide-manchester-folk-methods/sources/P02.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P03.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P04.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P05.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P06.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P07.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P08.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P09.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P10.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P11.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P12.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P13.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P14.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P15.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P16.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P17.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P18.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV text parity | None | Derived CC BY 4.0 transcript; matches CSV exactly |
| `examples/ace-guide-manchester-folk-methods/sources/P19.txt` | Asset/support | P7 | Reviewed | UTF-8 readability, filename/ID order, CC BY attribution, and exact CSV comparison | DATA-001 | CSV representation adds one trailing newline |
| `pyproject.toml` | Configuration | P7 | Reviewed | Runtime/dev dependency ownership, AST import/use map, Python/build/entrypoint metadata, test config, freshness, and advisory resolution | DEP-001, TEST-003 | — |
| `scripts/build_codebook_tree.sh` | Authored | P5 | Reviewed | Dependency/build command, generated-output owner, rebuild execution, normalised bundle diff, and lock/reproducibility review | BUILD-001 | — |
| `scripts/build_launcher_package.py` | Authored | P5 | Reviewed | Host format selection, temporary config, cleanup/error paths, semantic false-positive injection, callers, local check, and live platform builds | REL-001, PACK-001 | — |
| `scripts/build_sidecar.py` | Authored | P5 | Reviewed | Host triples, Nuitka standalone/onefile modes, output validation/copy, manifest consumers, and successful live macOS/Windows builds | None | — |
| `scripts/check_headless_tree_sync.py` | Authored | P5 | Reviewed | Default/rebuild control flow, stale fixture, real rebuild failure, restoration behaviour, callers, and tests | BUILD-001 | — |
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
| `src/ace/static/agreement_methodology.md` | Documentation | P7 | Reviewed | AC1 rationale, pooled verdict thresholds, prevalence rule, insufficient-data threshold, and implementation/test comparison | None | — |
| `src/ace/static/agreement_references.bib` | Documentation | P7 | Reviewed | Twelve unique BibTeX keys, methodology coverage, template consumer, and bibliographic structure | None | — |
| `src/ace/static/code_palette.json` | Configuration | P7 | Reviewed | Valid JSON, 36-entry palette, colour format/uniqueness tests, and application consumer | None | — |
| `src/ace/static/css/ace.css` | Authored | P4 | Reviewed | Token definitions, cascade layers, shared components, responsive rules, and reduced-motion contract | None | — |
| `src/ace/static/css/agreement.css` | Authored | P4 | Reviewed | Agreement layout, result-table states, focus styles, responsive rules, token use, and template interaction trace | A11Y-001, HTMX-002 | — |
| `src/ace/static/css/code_view.css` | Authored | P4 | Reviewed | Audit-view layout, state selectors, focus treatment, token use, and code-view controller trace | None | — |
| `src/ace/static/css/coding.css` | Authored | P4 | Reviewed | Coding layout/state selectors, custom-property definition/use scan, responsive rules, and reduced-motion contract | CSS-001 | — |
| `src/ace/static/favicon.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, template use, and exact brand-source relationship | None | Intentional package copy of `brand/favicon.svg` |
| `src/ace/static/js/Sortable.min.js` | Vendored | P4 | Reviewed | Version marker, template/import/load scan, adapter call graph, replacement owner, and test references | FRONT-002 | Third-party asset; version 1.15.6 is tracked but not loaded by current templates or bundles |
| `src/ace/static/js/ace_notes.js` | Authored | P4 | Reviewed | Drawer state machine, debounce/flush ownership, controlled reverse-completion reproduction, failure path, and test gaps | NOTE-001, FRONT-001 | — |
| `src/ace/static/js/bridge.js` | Authored | P4 | Reviewed | Function/listener/request inventory, page-global registration trace, HTMX/OOB ownership, stale-DOM guards, innerHTML escaping, and call graph | TEXT-001, HTMX-001, CODEBOOK-001, NOTE-001, TREE-001, FRONT-001, FRONT-002 | — |
| `src/ace/static/js/code_view.js` | Authored | P4 | Reviewed | Listener/key ownership, JSON rendering/escaping, navigation cache, metadata single-flight queue, and three-engine tests | None | — |
| `src/ace/static/js/codebook_headless_tree.js` | Generated | P4 | Reviewed | Shallow marker check, failing rebuild comparison and normalised diff, plus controlled two-mount reverse-completion reproduction | TREE-001, FRONT-002, BUILD-001 | Built from `codebook_headless_tree_source.js`; actual rebuild comparison currently fails |
| `src/ace/static/js/codebook_headless_tree_source.js` | Authored | P4 | Reviewed | Controller lifecycle, fetch/mount ownership, event/action map, reverse-completion reproduction, generated parity, and legacy adapter scan | TREE-001, FRONT-002, BUILD-001 | — |
| `src/ace/static/js/coding_keyboard.js` | Authored | P4 | Reviewed | Zone/shortcut state machine, listener ownership, editable-target guards, bridge overlap map, and tests | FRONT-001 | — |
| `src/ace/static/js/fuzzysort.min.js` | Vendored | P4 | Reviewed | Version marker, template load, production reference, and replacement-path scan | None | Third-party asset; version 3.0.2 is loaded and used by current codebook search |
| `src/ace/static/js/htmx.min.js` | Vendored | P4 | Reviewed | Version marker, template load, extension removal contract, OOB/programmatic-swap use, and replacement-path scan | HTMX-001 | Third-party asset; version 2.0.4 is loaded and used throughout route interactions |
| `src/ace/static/js/runtime.js` | Authored | P4 | Reviewed | Browser-session heartbeat/shutdown lifecycle, token handling, page guards, request failures, and runtime route/launcher tests | None | — |
| `src/ace/static/logo-light.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, template use, and exact brand-source relationship | None | Intentional package copy of `brand/logo-light.svg` |
| `src/ace/static/logo.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, template use, and exact brand/website relationship | None | Intentional package copy of `brand/logo.svg` |
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
| `tests/conftest.py` | Authored | P6 | Reviewed | Shared database, app-client, project, and import fixtures; fixture scopes and collected consumers | None | — |
| `tests/e2e/__init__.py` | Authored | P6 | Reviewed | Browser-suite package and path-based discovery boundary | TEST-002, TEST-003 | — |
| `tests/e2e/conftest.py` | Authored | P6 | Reviewed | Engine detection, three-engine parameters, function-scoped project/server setup, startup cost, and consumers | TEST-001, TEST-002, TEST-003 | — |
| `tests/e2e/test_agreement_file_review.py` | Authored | P6 | Reviewed | Three-engine agreement lifecycle contracts, per-item browser/server setup, timing, and stale-result coverage | HTMX-002, TEST-001, TEST-003 | — |
| `tests/e2e/test_applied_code_removal.py` | Authored | P6 | Reviewed | Three-engine applied-code removal contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_code_view_edit_mode.py` | Authored | P6 | Reviewed | Three-engine code-view edit/save contracts, single-flight coverage, and per-item setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_context_menu.py` | Authored | P6 | Reviewed | Three-engine context-menu interaction contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_cues.py` | Authored | P6 | Reviewed | Three-engine cue lifecycle/stale-response contracts, timings, and per-item setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_import_ledger.py` | Authored | P6 | Reviewed | Three-engine codebook import-ledger contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_menu_a11y.py` | Authored | P6 | Reviewed | Three-engine menu keyboard/ARIA contract and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_sidebar_controller.py` | Authored | P6 | Reviewed | Three-engine tree/controller lifecycle contracts, collection weight, and per-item setup | TREE-001, TEST-001, TEST-003 | — |
| `tests/e2e/test_codebook_zone_indicator.py` | Authored | P6 | Reviewed | Three-engine focus/rename/reorder contracts and per-item browser/server setup | CODEBOOK-001, TEST-001, TEST-003 | — |
| `tests/e2e/test_coding_keyboard_navigation.py` | Authored | P6 | Reviewed | Three-engine keyboard/focus/navigation contracts, collection weight, and per-item setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_coding_notification_receipt.py` | Authored | P6 | Reviewed | Three-engine notification/undo receipt contracts and per-item browser/server setup | HTMX-001, TEST-001, TEST-003 | — |
| `tests/e2e/test_coding_text_preferences.py` | Authored | P6 | Reviewed | Three-engine text-preference persistence contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_headless_tree_preview.py` | Authored | P6 | Reviewed | Ninety-nine collected live tree/controller items, source/bundle use, and per-item setup | TREE-001, BUILD-001, TEST-001, TEST-003 | — |
| `tests/e2e/test_import_desktop_picker.py` | Authored | P6 | Reviewed | Three-engine import-picker error/success contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_landing_desktop_picker.py` | Authored | P6 | Reviewed | Three-engine landing picker contracts and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/e2e/test_note_drawer_status.py` | Authored | P6 | Reviewed | Three-engine note-status/autosave contracts, timing, and missing reverse-completion case | NOTE-001, TEST-001, TEST-003 | — |
| `tests/e2e/test_setup_keyboard.py` | Authored | P6 | Reviewed | Forty-five collected setup/keyboard items and per-item browser/server setup | TEST-001, TEST-003 | — |
| `tests/fixtures/make_agreement_files.py` | Authored | P6 | Reviewed | Agreement fixture schema/data construction and loader/computer consumers | AGREEMENT-001 | — |
| `tests/routes/test_code_cue_routes.py` | Authored | P6 | Reviewed | Cue route request, response, and project/coder precondition contracts | None | — |
| `tests/routes/test_coding_annotations.py` | Authored | P6 | Reviewed | Annotation/navigation/undo route matrix, transaction boundaries, and response headers | ANN-001, UNDO-001, HTMX-001 | — |
| `tests/routes/test_coding_codebook.py` | Authored | P6 | Reviewed | Eighty collected codebook route contracts, rename refresh flow, undo, and imports | CODEBOOK-001, UNDO-001, HTMX-001 | — |
| `tests/routes/test_coding_notes.py` | Authored | P6 | Reviewed | Note-aware coding and undo route contracts; client queue remains E2E-owned | NOTE-001 | — |
| `tests/services/test_code_cues.py` | Authored | P6 | Reviewed | Cue ranking, tokenisation, stop-state, and scale smoke contracts | None | — |
| `tests/test_agreement_computer.py` | Authored | P6 | Reviewed | Pooled/per-code/pairwise public computation contracts and overlap comparison | None | — |
| `tests/test_agreement_routes.py` | Authored | P6 | Reviewed | Agreement upload/compute/export/result route contracts and private compatibility imports | ARCH-002, HTMX-002 | — |
| `tests/test_agreement_verdict.py` | Authored | P6 | Reviewed | Threshold, pairwise, and guidance-text classification contracts | None | — |
| `tests/test_app.py` | Authored | P6 | Reviewed | Lifespan, app-state initialisation, shutdown, origin, and stale-server contracts | ARCH-003, ARCH-004 | — |
| `tests/test_browser_runtime.py` | Authored | P6 | Reviewed | Tracker/monitor concurrency, idle, heartbeat, shutdown, and lifecycle ownership | ARCH-003 | — |
| `tests/test_chord_keys_e2e.py` | Authored | P6 | Reviewed | Five Chromium-only Playwright tests, bespoke module server, and exclusion from shared E2E path | TEST-002, TEST-003 | — |
| `tests/test_code_view.py` | Authored | P6 | Reviewed | Code-view data assembly, ordering, source excerpts, and page contracts | None | — |
| `tests/test_codebook_palette.py` | Authored | P6 | Reviewed | Palette defaults, uniqueness, cycling, and explicit colour contracts | None | — |
| `tests/test_coding_routes.py` | Authored | P6 | Reviewed | Legacy/top-level coding route contracts, route-module overlap, and private compatibility imports | ARCH-002, ROUTE-001 | — |
| `tests/test_cohens_kappa.py` | Authored | P6 | Reviewed | Private kappa helper edge cases and comparison with public agreement tests | None | — |
| `tests/test_db/__init__.py` | Authored | P6 | Reviewed | Database-test package and discovery boundary | None | — |
| `tests/test_db/test_chord_migration.py` | Authored | P6 | Reviewed | Chord migration forward/backfill and compatibility contracts | None | — |
| `tests/test_db/test_connection.py` | Authored | P6 | Reviewed | Connection pragmas, schema version/application identity, open/create, and future-schema gap | DB-001 | — |
| `tests/test_db/test_migrations.py` | Authored | P6 | Reviewed | Sequential migrations, legacy fixtures, schema versions, and rollback expectations | DB-001 | — |
| `tests/test_db/test_schema.py` | Authored | P6 | Reviewed | Schema constraints, tables, indexes, triggers, and version contract | DB-001 | — |
| `tests/test_desktop_config.py` | Authored | P6 | Reviewed | Semantic desktop manifest/version/format/icon/resource assertions and collected lane ownership | REL-001, REL-002, ICON-001, TEST-003 | — |
| `tests/test_e2e_plan_a.py` | Authored | P6 | Reviewed | Three TestClient import/project flows; name and location are not browser E2E | TEST-003 | — |
| `tests/test_import.py` | Authored | P6 | Reviewed | Import preview/commit route flows, identifier handling, and batch-rollback gaps | IMPORT-001 | — |
| `tests/test_importer_lazy_openpyxl.py` | Authored | P6 | Reviewed | Optional spreadsheet dependency and lazy-import contracts | None | — |
| `tests/test_launcher_lifecycle.py` | Authored | P6 | Reviewed | Launcher reachability, heartbeat, idle shutdown, subprocess timing, and release-lane ownership | TEST-003 | — |
| `tests/test_launcher_packager_config.py` | Authored | P6 | Reviewed | Semantic packager configuration, shallow-command contrast, and release-lane ownership | PACK-001, REL-001, TEST-003 | — |
| `tests/test_models/__init__.py` | Authored | P6 | Reviewed | Model-test package and discovery boundary | None | — |
| `tests/test_models/test_annotation.py` | Authored | P6 | Reviewed | Annotation CRUD/merge/overlap contracts and missing cross-connection race case | ANN-001 | — |
| `tests/test_models/test_assignment.py` | Authored | P6 | Reviewed | Assignment creation, lookup, uniqueness, and coder/source ownership contracts | None | — |
| `tests/test_models/test_codebook.py` | Authored | P6 | Reviewed | Codebook CRUD/tree/import/export/delete/restore contracts and model adapter boundary | MODEL-001, UNDO-001 | — |
| `tests/test_models/test_codebook_chord.py` | Authored | P6 | Reviewed | Chord allocation/backfill/collision/reserved-key model contracts | TEST-002 | — |
| `tests/test_models/test_codebook_folder.py` | Authored | P6 | Reviewed | Folder invariants, depth cap, moves, ordering, and soft-delete contracts | None | — |
| `tests/test_models/test_source.py` | Authored | P6 | Reviewed | Source/content CRUD, ordering, metadata, and assignment interactions | None | — |
| `tests/test_models/test_source_note.py` | Authored | P6 | Reviewed | Atomic note upsert/delete and timestamp contracts; browser queue remains uncovered | NOTE-001 | — |
| `tests/test_native_picker.py` | Authored | P6 | Reviewed | Platform picker dispatch, async thread offload, cancellation, and path contracts | None | — |
| `tests/test_project.py` | Authored | P6 | Reviewed | Project create/open/overwrite validation and replacement-failure gap | PROJECT-001 | — |
| `tests/test_render_colour_css.py` | Authored | P6 | Reviewed | Colour CSS filtering/escaping contracts and private compatibility import | ARCH-002 | — |
| `tests/test_route_registration.py` | Authored | P6 | Reviewed | Router inclusion, unique route identity, and split-module registration contracts | ROUTE-001 | — |
| `tests/test_runtime_routes.py` | Authored | P6 | Reviewed | Session heartbeat/close/shutdown route contracts and launcher-focused lane ownership | TEST-003 | — |
| `tests/test_services/__init__.py` | Authored | P6 | Reviewed | Service-test package and fragmented test-layout comparison | None | — |
| `tests/test_services/test_agreement_computer.py` | Authored | P6 | Reviewed | Sparse/public agreement metrics, overlap clipping, pairwise, and duplicate-name comparison | AGREEMENT-001 | — |
| `tests/test_services/test_agreement_e2e.py` | Authored | P6 | Reviewed | Database-loader-computer integration across coders/sources and source-identity gap | AGREEMENT-001 | — |
| `tests/test_services/test_agreement_loader.py` | Authored | P6 | Reviewed | Legacy schema probing, source matching, coder labels, and duplicate-content gap | AGREEMENT-001 | — |
| `tests/test_services/test_agreement_types.py` | Authored | P6 | Reviewed | Agreement dataclass invariants, serialisation, and result-shape contracts | None | — |
| `tests/test_services/test_chord_assignment.py` | Authored | P6 | Reviewed | Chord assignment capacity, reserved keys, collisions, and deterministic ordering | TEST-002 | — |
| `tests/test_services/test_coding_render.py` | Authored | P6 | Reviewed | Sentence/annotation HTML, escaping, offset attributes, and Unicode contract gap | TEXT-001 | — |
| `tests/test_services/test_exporter.py` | Authored | P6 | Reviewed | Annotation/codebook export ordering, grouping, filenames, and interleaved-coder gap | EXPORT-001 | — |
| `tests/test_services/test_importer.py` | Authored | P6 | Reviewed | Text/document/spreadsheet import parsing, identifiers, errors, and atomicity gap | IMPORT-001 | — |
| `tests/test_services/test_notes_exporter.py` | Authored | P6 | Reviewed | Note export ordering, escaping, empty data, and filename contracts | None | — |
| `tests/test_services/test_text_splitter.py` | Authored | P6 | Reviewed | Sentence segmentation, whitespace, abbreviations, and Python/browser offset gap | TEXT-001 | — |
| `tests/test_services/test_undo.py` | Authored | P6 | Reviewed | Annotation undo/redo/merge replay, stack recovery, and composite atomicity gap | UNDO-001 | — |
| `tests/test_services/test_undo_codebook.py` | Authored | P6 | Reviewed | Codebook/folder undo composites, replay, ordering, and failure-injection gap | UNDO-001 | — |
| `tests/test_source_note_routes.py` | Authored | P6 | Reviewed | Note PUT/GET/delete/export route contracts; autosave ordering remains browser-owned | NOTE-001 | — |
| `tests/test_static_asset_contracts.py` | Authored | P6 | Reviewed | Static asset presence/markers, deliberately stale bundle fixture, and shallow parity acceptance | BUILD-001, FRONT-002, TEST-003 | — |
| `tests/test_status_helpers.py` | Authored | P6 | Reviewed | OOB status/announce headers, escaping, private compatibility imports, and no-reswap gap | ARCH-002, HTMX-001 | — |
| `uv.lock` | Lockfile | P7 | Reviewed | `uv lock --check`, 36-package graph, manifest consistency, direct/transitive owners, outdated scan, advisory audit, and secure overlay | DEP-001 | Generated dependency lock is reproducible but contains 12 unique published advisories |
| `website/.gitignore` | Asset/support | P7 | Reviewed | Quarto output/cache ownership and comparison with repository ignore rules | None | Website-only generated output boundary |
| `website/_quarto.yml` | Configuration | P7 | Reviewed | Seventeen-page navigation, output directory, theme/CSS/logo references, local link map, and successful render | None | — |
| `website/assets/ace-landing-page-2026-06.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, homepage use, and comparison with current landing screenshot | DOC-003 | Referenced 3002×1703 legacy landing screenshot |
| `website/assets/guide/coding-view-with-codebook.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, public-sample provenance, and three guide use sites | DOC-004 | Referenced 1365×900 instructional screenshot |
| `website/assets/guide/folder-import-review.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, public-sample provenance, and three guide use sites | DOC-004 | Referenced 1365×900 instructional screenshot |
| `website/assets/guide/import-options.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, workflow accuracy, and quick-start use site | DOC-004 | Referenced 1365×900 instructional screenshot |
| `website/assets/guide/landing.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, current landing destinations, and quick-start use site | DOC-004 | Referenced 1365×900 instructional screenshot |
| `website/assets/guide/new-project-folder-selected.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, import-guide use, and exposed absolute developer path | DOC-003, DOC-004 | Referenced 1365×900 screenshot containing local path data |
| `website/assets/guide/review-coded-text.png` | Binary asset | P7 | Reviewed | PNG signature/dimensions/checksum, visual inspection, audit-view accuracy, public-sample provenance, and described use site | None | Referenced 1365×900 screenshot with meaningful alternative text |
| `website/assets/logo.svg` | Asset/support | P7 | Reviewed | SVG structure, checksum, Quarto navbar use, and exact brand/package relationship | None | Intentional website copy of `brand/logo.svg` |
| `website/getting-started.qmd` | Documentation | P7 | Reviewed | New/open/import/codebook/coding/export sequence, current controls, image references, links, and empty alternatives | DOC-004 | — |
| `website/index.qmd` | Documentation | P7 | Reviewed | Homepage links, stale v1.6.0 citation, legacy hero use, empty alternative, and successful render | DOC-001, DOC-003, DOC-004 | — |
| `website/install.qmd` | Documentation | P7 | Reviewed | Release assets, unsigned-build warnings, source commands, current entrypoint, and obsolete Tauri desktop command | DOC-002 | — |
| `website/reference/faq.qmd` | Documentation | P7 | Reviewed | Local/cloud/privacy/collaboration/cue/agreement claims, issue link, and missing WAL/cloud operational guidance | DOC-005 | — |
| `website/reference/file-format.qmd` | Documentation | P7 | Reviewed | Stored-data, backup/privacy claims, SQLite connection/shutdown comparison, and missing WAL/SHM sidecar guidance | DOC-005 | — |
| `website/reference/index.qmd` | Documentation | P7 | Reviewed | Reference-page links, labels, and rendered navigation | None | — |
| `website/reference/shortcuts.qmd` | Documentation | P7 | Reviewed | Source/applied/codebook/search/audit shortcut tables compared with current keyboard contracts and render | None | — |
| `website/review-export.qmd` | Documentation | P7 | Reviewed | Review/agreement/export workflow claims and links to current audit/agreement/export owners | None | — |
| `website/sample-data.qmd` | Documentation | P7 | Reviewed | Import instructions, 19-source/132-code claims, DOI/licence, route-equivalence claim, image use, and empty alternative | DATA-001, DOC-004 | — |
| `website/styles.css` | Authored | P7 | Reviewed | Website selectors/tokens, Quarto integration, asset use, and successful 17-page render | None | — |
| `website/user-guide/agreement.qmd` | Documentation | P7 | Reviewed | Source/coder eligibility, AC1 bands, insufficient threshold, workflow, export, methodology, and implementation comparison | None | — |
| `website/user-guide/audit.qmd` | Documentation | P7 | Reviewed | Code-view modes, source tracks, edits/saves/undo, shortcuts, return flows, links, and the sole meaningful screenshot alternative | None | — |
| `website/user-guide/codebooks.qmd` | Documentation | P7 | Reviewed | Codes/folders/reorder/import/share claims, CSV schema aliases, cue links, image use, and empty alternative | DOC-004 | — |
| `website/user-guide/coding.qmd` | Documentation | P7 | Reviewed | Navigation/cues/apply/merge/inspector/undo claims, SQLite FTS references, image use, and empty alternative | DOC-004 | — |
| `website/user-guide/export.qmd` | Documentation | P7 | Reviewed | Annotation/codebook/note/agreement export scope and preservation checklist compared with current exporters | None | — |
| `website/user-guide/import.qmd` | Documentation | P7 | Reviewed | CSV/folder requirements, new-project flow, preview checks, archive advice, two image uses, local-path exposure, and empty alternatives | DOC-003, DOC-004 | — |
| `website/user-guide/notes.qmd` | Documentation | P7 | Reviewed | Source-note scope, open/edit/delete/export claims, persistence, and current note model/route comparison | None | — |
| `website/workflow.qmd` | Documentation | P7 | Reviewed | Project/import/codebook/note sequence, one-file/cloud claims, image use, links, and missing sidecar guidance | DOC-004, DOC-005 | — |
