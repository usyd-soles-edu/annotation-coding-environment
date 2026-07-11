# Changelog

## Unreleased

### Changes

- **Coded-text audit view** — made the review/edit switch more visible and documented how to update a code name, folder, or dictionary definition while reviewing excerpts.

## 1.5.0

### Changes

- **Wording cues** — added an optional local text-matching aid that can lightly mark codebook rows whose names or definitions overlap with the focused sentence. Cues use SQLite FTS5/BM25 ranking locally and do not apply codes or use an AI/cloud service.

## 1.4.3

### Fixes

- **Coding shortcuts** — made the inline legend show the core keyboard actions for applying codes, deleting, opening notes, viewing coded text, and help.
- **Codebook search** — removed the remaining internal slash-command wording so `/folder` stays ordinary search/create text while `Shift+Enter` remains the folder shortcut.
- **Source notes** — added brief saved feedback after note autosave and labelled the note drawer with the current source.
- **Sentence delete** — made `X` report when there is no code on the focused sentence instead of refreshing silently.
- **Source navigation** — made `Shift` + arrow navigation say when you are already at the first or last source.
- **Sidebar resizing** — made the main codebook splitter reachable and adjustable from the keyboard.
- **Imports** — made codebook CSV import handle common spreadsheet encodings and replaced raw import errors with clearer guidance.
- **Agreement exports** — replaced expired CSV export errors with a recovery screen that points back to agreement setup.

## 1.4.1

### Fixes

- **New project setup** — cleared the selected folder after a project-name conflict when choosing another folder, so the stale conflicting path cannot be submitted again.
- **Agreement results** — made insufficient-data verdicts show the actual number of coded positions and the 50-position threshold.

## 1.4.0

### Changes

- **Codebook import** — redesigned the import review so the column choices are easier to check before bringing a codebook into a project. ACE still guesses the code, folder/group, and definition columns, but the screen now makes it clearer that these are columns from your file.
- **Keyboard setup flows** — made the agreement file picker and new-project screen usable from the keyboard. You can move through the setup controls with arrow keys, choose files from the agreement page, remove selected files, and compute agreement without reaching for the mouse.
- **Website guide** — tightened the first steps in the guide so new users are pointed to the install page before the quick-start workflow.

### Fixes

- **Landing page navigation** — restored the User guide link to the front-page arrow-key cycle.
- **Agreement file review** — made Delete and Backspace ignore file rows without a valid row index instead of treating them as the first selected file.

## 1.3.0

### Changes

- **Applied codes sidebar** — made the right-side applied-codes panel collapsible. When it is closed, a compact rail still shows the applied codes and stays current as codes are added or removed.
- **Coding shortcuts** — added keyboard support for opening and closing the applied-codes sidebar without disrupting the existing source, codebook, and applied-code shortcuts.
- **Undo navigation** — source navigation through ACE controls, including the source grid, now sits in the undo/redo sequence, so coding and source jumps can be walked back in order.

### Fixes

- **Browser history** — kept browser Back/Forward separate from ACE undo, while making source-history entries point at explicit source indexes.

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

## 1.1.3

### Changes

- **Codebook import** — added a compact column-mapping dialog so CSV codebooks can use flexible column names, include optional folders, and import read-only dictionary definitions.
- **Code definitions** — imported dictionary definitions now appear as hover and focus help in the codebook without making the definitions editable.
- **Project setup** — made the new-project flow a focused screen with a back control instead of leaving the front-page project links active.

### Fixes

- **First-code prompt** — clarified that slash commands such as `/code` are needed when creating a code from the empty codebook prompt.

## 1.1.2

### Changes

- **Codebook maintenance** — removed the old headless-tree spike harness now that the production codebook tree is covered by app-level tests.
- **Brand assets** — refreshed the packaged brand assets.

### Fixes

- **Internal cleanup** — removed stale audit and import paths that were no longer used by the app.

## 1.1.1

### Changes

- **Coding text width** — added presets for adjusting the coding text column width.
- **Codebook sidebar** — made the headless-tree sidebar the only codebook sidebar path, removing the old fallback implementation.
- **Coding and review polish** — improved codebook navigation, shortcut feedback, undo stability, agreement summaries, and setup keyboard handling.

## 1.1.0

### Changes

- **Applied codes display** — removed applied-code labels from the coding text itself so the reading surface stays cleaner.

### Fixes

- **Codebook rename** — kept inline codebook renaming editable instead of dropping focus during rename.

## 1.0.0

### Changes

- **Desktop app** — replaced the embedded Tauri webview shell with a browser-launcher desktop app backed by a local ACE server.
- **Codebook folders** — added nested folders, code-to-folder conversion, clearer folder labels, and the headless-tree sidebar foundation.
- **Desktop coding controls** — improved packaged-app coding controls and macOS picker flows.
- **Release packaging** — added install documentation, licensing, and a more reliable desktop release workflow.

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
