# Changelog

## 1.3.0

### Changes

- **Applied codes sidebar** — made the right-side applied-codes panel collapsible, with a compact rail that stays updated as codes are applied or removed.
- **Coding shortcuts** — added keyboard support for opening and collapsing the applied-codes sidebar while preserving existing source, codebook, and applied-code navigation shortcuts.
- **Undo navigation** — source navigation through ACE controls, including the source grid, now participates in the undo/redo sequence so coding and source jumps can be walked back in order.

### Fixes

- **Browser history** — kept browser Back/Forward separate from ACE undo while ensuring source-history entries point at explicit source indexes.
- **Release metadata** — updated version, citation, desktop packaging, and changelog metadata for the 1.3.0 release.

## 1.2.0

### Changes

- **Codebook sidebar** — unified the coding and coded-text audit sidebars around the same Headless Tree codebook, with mode-specific keyboard behaviour for applying, browsing, renaming, and editing codes.
- **Keyboard coding workflow** — simplified source/codebook navigation and made no-match codebook search states expose direct create-code and create-folder actions that are reachable by keyboard.
- **Coded-text audit view** — added audit-safe codebook editing, undo/redo handling, current-code fallback after delete, and faster in-place switching between viewed codes.
- **Project setup** — moved new-project creation to a minimal focused screen and kept recent-project resume, open-project, and tools actions clearer on the front page.
- **Agreement workflow** — added a review step for selected files and preserved browser back/forward behaviour around review, compute, stale results, and errors.
- **Codebook drag and drop** — restored native drag previews and clearer insertion/folder drop affordances for code and folder moves.

### Fixes

- **Exports** — corrected ACE export handling so exported annotation spans and source notes better match the saved project data.
- **Slash search** — removed the old `/folder` command behaviour so slash-prefixed text is treated as normal code search/create input.
- **Release metadata** — updated citation and archive metadata for the 1.2.0 release.

## 1.1.3

### Changes

- **Codebook import** — added a compact column-mapping dialog so CSV codebooks can use flexible column names, include optional folders, and import read-only dictionary definitions.
- **Code definitions** — imported dictionary definitions now appear as hover and focus help in the codebook without making the definitions editable.
- **Project setup** — made the new-project flow a focused screen with a back control instead of leaving the front-page project links active.

### Fixes

- **First-code prompt** — clarified that slash commands such as `/code` are needed when creating a code from the empty codebook prompt.

## 1.1.2

### Changes

- **Release metadata** — corrected the Zenodo release metadata so DOI records carry the stable ACE description and the current release version.
- **Codebook maintenance** — removed the old headless-tree spike harness now that the production codebook tree is covered by app-level tests.
- **Brand assets** — refreshed the packaged brand assets.

### Fixes

- **Internal cleanup** — removed stale audit and import paths that were no longer used by the app.

## 1.1.1

### Changes

- **Coding text width** — added presets for adjusting the coding text column width.
- **Codebook sidebar** — made the headless-tree sidebar the only codebook sidebar path, removing the old fallback implementation.
- **Coding and review polish** — improved codebook navigation, shortcut feedback, undo stability, agreement summaries, and setup keyboard handling.

### Fixes

- **Desktop release metadata** — aligned the packaged app version metadata for the 1.1.1 installer release.

## 1.1.0

### Changes

- **Applied codes display** — removed applied-code labels from the coding text itself so the reading surface stays cleaner.
- **Citation metadata** — added Zenodo DOI citation details to the project metadata and README.

### Fixes

- **Codebook rename** — kept inline codebook renaming editable instead of dropping focus during rename.

## 1.0.0

### Changes

- **Desktop app** — replaced the embedded Tauri webview shell with a browser-launcher desktop app backed by a local ACE server.
- **Codebook folders** — added nested folders, code-to-folder conversion, clearer folder labels, and the headless-tree sidebar foundation.
- **Desktop coding controls** — improved packaged-app coding controls and macOS picker flows.
- **Release packaging** — added citation metadata, install documentation, licensing, and a more reliable desktop release workflow.

### Fixes

- **Recent project link** — dismissed recent-project links now stay hidden on the landing page.

## 0.15.0

### Changes

- **Coding text size** — added a subtle `Aa` control for changing only the main coding text size.
- **Coding scrollbar** — moved long-text scrolling to the coding text panel so the scrollbar sits before the applied-codes column.

### Fixes

- **Mac folder imports** — the desktop app now uses Tauri's native folder picker for folder imports instead of routing the picker through the Python sidecar.
- **Mac project pickers** — New project and Open existing now use Tauri's native pickers instead of the Python sidecar picker path.
- **Mac folder import completion** — folder imports now accept Tauri file URIs and reliably advance to the imported-files review screen.
- **Mac app quit** — the desktop sidecar now shuts down if the Tauri wrapper exits, preventing orphaned ACE servers on port 18080.
- **Recent project link** — dismissing the last-opened project on the front page now hides the resume link immediately.

## 0.14.7

### Fixes

- **Project setup** — existing-project warnings now open as a centred overwrite dialog instead of appearing below the page.
- **Import flow** — matched the import choice and completion screens to the approved redesign mockup.
- **Folder import preview** — kept the random sample browser as the main review surface after importing text files.

## 0.14.6

### Changes

- **Data import workflow** — simplified import choice screens so spreadsheet and folder imports start from direct native pickers.
- **Spreadsheet mapping** — replaced the old ID/Text role buttons with a three-column source label, text-to-code, and source preview layout.
- **Multi-column text imports** — selected text columns now combine into one labelled source per row instead of creating separate suffixed sources.
- **Folder import preview** — refreshed the imported-file preview browser and clearer random-sample refresh control.

### Fixes

- Native spreadsheet imports no longer delete the original file after import.

## 0.14.5

### Changes

- **Applied codes timeline** — moved applied codes into a persistent right-side timeline panel with compact rows, colour markers, and text-preview highlighting.
- **Notes drawer overlay** — the source note drawer now opens over the applied-codes panel so the right column keeps a stable footprint.
- **Coded-text selection polish** — the coded-text view now uses the same selected-code styling as the coding sidebar.

## 0.10.0

### Features

- **Keyboard-centric sidebar** — ARIA treeview with roving tabindex, arrow key navigation, Tab zone cycling (text → header → search → tree), Enter to apply codes, F2 to rename, Alt+arrows to indent/reorder, drag-and-drop for codes and groups
- **Top bar redesign** — ACE wordmark with subtitle over sidebar column, source name centred over text panel, clickable flag toggle with toast feedback, ? help button
- **Agreement overhaul** — streamlined flow (choose files → auto-compute → results), pooled overall computation, expanded pairwise metrics, minimalist tables with interpretation labels, bib-backed references, raw data CSV export for R/Python reproducibility
- **Codebook CSV import** — "Codebook ▾" sidebar menu with Import/Export, native file picker, sidebar-style preview dialog with new/exists badges, empty state link
- **Apply codes from sidebar** — click a code row or Enter on first search match to apply to focused sentence, with filter auto-clear and focus return

### Fixes

- CapsLock keyboard shortcut compatibility
- Focus restoration across HTMX sidebar swaps
- Search bar events bubble correctly for document-level listeners
- Flag toggle preserves header focus state across OOB swaps
- Agreement Overall metric now pooled (was misleading macro-average)

## 0.9.0

### Features

- **Codebook CSV import** — sidebar menu, native file picker, preview dialog
- **Apply codes from sidebar** — click code row, Enter on first search match, filtered ↓ navigation fix

## 0.8.0

### Features

- **Inter-coder agreement overhaul** — streamlined choose-files → auto-compute → results flow, pooled overall, expanded pairwise metrics, minimalist tables with interpretation labels, raw data CSV export, bib-backed references

## 0.7.0

### Features

- **Top bar redesign** — ACE wordmark with subtitle, source name centred, clickable flag toggle, ? help button

## 0.6.0

### Features

- **Keyboard-centric sidebar** — ARIA treeview with roving tabindex, arrow key navigation, Tab zone cycling, keyboard tree operations
- **Focus underline** — simple underline for focused sentence (no outline box)
- **Text panel** — 72ch max-width, centred

## 0.5.0

### Features

- **Bottom code bar** — sticky bar showing applied codes as coloured text chips with flash-highlight on click
- **Simplified sidebar** — single collapsible tree view, removed tabs
- **Source nav** — moved into text panel as breadcrumb line
- **Font size bump** — 10px→11px, 11px→12px for accessibility
- **Sidebar width** — saved and restored before CSS loads (no layout glitch)

## 0.4.0

### Features

- **CSS Custom Highlight API** — seamless cross-sentence annotation highlights
- **Margin panel** — positioned annotation cards with overlap grouping and click-flash
- **Centred navigation** — nav cluster centred in header bar

## 0.3.0

### Features

- **Highlighter-pen backgrounds** — seamless merged highlights replacing underlines
- **Resume last source** — coding page reopens to last viewed source

## 0.2.0

### Features

- **Direct manipulation** — inline rename (double-click), click-dot colour picker, drag-and-drop reorder via SortableJS
- **Delete confirmation** — double-press Delete, Move Up/Down, Move to Group
- **Removed management mode** — all code operations are now inline (no gear button/menus)

## 0.1.2

### Features

- **Search/create input** — filter codes by typing, Enter to create new code
- **Group management** — inline "New group" action, ungrouped codes section
- **Source navigation** — arrow left/right to navigate sources (Shift = jump 5)
- **Auto-merge** — adjacent sentences coded with same code merge automatically

### Fixes

- Sentence focus restoration after HTMX swaps
- Borderless search input until focused

## 0.1.1

### Changes

- Removed code tooltip, annotation click popup, and metadata tags

## 0.1.0

First release of ACE — Annotation Coding Environment.

### Features

- **Project management** — create, open, and resume `.ace` projects from the landing page
- **Source import** — import text sources from CSV files with column mapping
- **Annotation coding** — select text and apply codes with click or keyboard shortcuts (1–9, 0, a–z)
- **Codebook management** — create, rename, recolour, delete, and reorder codes via drag-and-drop
- **Grouped codes** — organise codes into collapsible groups; manage via "Move to Group" menu or CSV import
- **Code import/export** — import codes from CSV (`name,group` columns) with preview dialog; export codebook to CSV
- **Inter-coder agreement** — compute Krippendorff's alpha, Cohen's/Fleiss' kappa across multiple `.ace` files
- **Source navigation** — visual grid overview of all sources with density indicators and keyboard navigation (Alt+←/→)
- **Undo/redo** — undo and redo annotation actions
- **Header bar** — CSV export of all annotations, coder name management
- **Resizable code bar** — adjustable splitter between code list and source panel
