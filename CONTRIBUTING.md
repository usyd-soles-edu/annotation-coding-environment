# Contributing to ACE

Thanks for your interest in contributing. This guide covers how we work together on this project.

## Setting up

You'll need [uv](https://docs.astral.sh/uv/) installed. Then:

```bash
git clone https://github.com/usyd-soles-edu/annotation-coding-environment.git
cd annotation-coding-environment
uv sync
```

To run the app locally: `uv run ace` (opens at http://127.0.0.1:8080).
To run the tests: `uv run pytest`.

## How we work with branches

The `main` branch should always be in a working state. Don't push broken code to it.

For anything beyond a trivial fix, create a branch first. We use prefixes to keep things tidy:

- `feat/` for new features (e.g. `feat/grouped-codes`)
- `fix/` for bug fixes (e.g. `fix/44-text-overflow`)
- `refactor/` for internal restructuring

For genuinely small changes — a typo, a one-line config tweak — committing straight to `main` is fine.

## Writing commit messages

We follow [conventional commits](https://www.conventionalcommits.org/). In short, start the first line with a prefix like `feat:`, `fix:`, `refactor:`, etc., followed by a brief summary in plain English. If you want to explain the reasoning, add a longer description after a blank line.

Example:

```
feat(codebook): add group support to CSV import

Read the optional 'group' column from CSV files and store as
group_name on each code. Colours are always auto-assigned.
```

The common prefixes are: `feat`, `fix`, `style`, `refactor`, `test`, `build`, `docs`.

## Pull requests

Open a pull request for each piece of work. Keep it to one logical change — don't bundle unrelated things together.

Write the PR title in the same conventional commit format as above, because when we merge it becomes the commit message on `main`. We squash merge everything:

```bash
gh pr merge N --squash --delete-branch
```

Then switch back to main and pull: `git checkout main && git pull`.

## Testing

Please make sure all tests pass before you push. Run `uv run pytest` and check.

If you're adding new behaviour, write a test for it. If you're fixing a bug, write a test that reproduces it first, then fix it.

## Releasing a new version

We use semantic versioning. Bump the minor number for larger user-facing features and the patch number for fixes or smaller improvements.

To release:

1. Add a new section at the top of `CHANGELOG.md` describing what changed
2. Bump the release number in `src/ace/__init__.py`, `desktop/launcher/Cargo.toml`, `desktop/launcher/Cargo.lock`, `desktop/launcher/Packager.toml`, `.zenodo.json`, `CITATION.cff`, the README citation, and the website citation on `website/index.qmd`
3. Check `CITATION.cff` has the intended `version`, `date-released`, DOI, authors, license, and repository URL. Zenodo reads citation metadata from the tagged archive, so stale or uncommitted metadata changes can appear on the DOI record.
4. Run `uv run python scripts/check_release_metadata.py` and `uv lock --check`
5. Stage only the release metadata files, then commit them: `git commit -m "chore(release): X.Y.Z"`
6. Push `main`: `git push origin main`
7. Create an annotated tag from the release commit on `main`: `git tag -a vX.Y.Z -m "X.Y.Z"`
8. Push the tag: `git push origin vX.Y.Z`
9. Confirm the `Release Desktop App` GitHub Actions workflow succeeds, audits the locked runtime dependencies, and publishes a draft GitHub release using the matching changelog section

### Writing the changelog

The changelog is for users, not developers. Only mention things that someone using the app would notice or care about. Internal refactors, test changes, and code cleanup don't belong here.

Use these categories:

- **Changes** — user-visible features, capabilities, workflow changes, or removed behaviour
- **Fixes** — bugs, corrections, release metadata updates, or other user-facing repairs

Example:

```markdown
## 0.2.0

### Changes

- **Codebook sidebar** — added grouped codes with collapsible sidebar headers.
- **CSV import** — simplified imports by removing the colour column.

### Fixes

- **Source panel** — kept the panel from expanding when annotating long text.
```

## Project layout

```
src/ace/
├── app.py               — FastAPI app factory, middleware, server config
├── routes/
│   ├── pages.py         — GET pages (/, /new-project, /import, /code, /code/{id}/view, /agreement)
│   ├── api.py           — aggregates the API routers below
│   ├── api_coding.py    — coding, annotations, undo/redo, flags, notes
│   ├── api_codebook.py  — codebook tree CRUD and reordering
│   ├── api_agreement.py — agreement computation and exports
│   ├── api_project_import.py — project create/open, source and codebook import
│   ├── api_support.py   — shared HTMX helpers and support endpoints
│   └── runtime.py       — browser-launcher runtime routes
├── templates/           — Jinja2 templates (base, landing, import, coding, code_view, agreement)
├── models/              — database operations (one file per table)
├── services/            — business logic (undo, importer, exporter, agreement, text_splitter)
├── db/                  — schema, migrations, connection management
└── static/              — CSS, JavaScript (bridge.js, coding_keyboard.js, code_view.js), vendored libs (htmx, Sortable, fuzzysort)
```

The desktop app lives in `desktop/launcher`: a small native launcher (Rust) that starts a bundled ACE server and opens the default browser. `uv run python scripts/build_launcher_package.py` builds the bundled server (via `scripts/build_sidecar.py`) and packages the installers with cargo-packager.

## Code conventions

A few things to know if you're working in the code:

- The UI is built with FastAPI + Jinja2 templates + HTMX for server-rendered HTML
- Custom CSS classes are prefixed with `ace-` (e.g. `ace-sentence`, `ace-code-chip`)
- Data is stored in `.ace` files, which are SQLite databases
- The colour scheme is monochrome slate — the only colour comes from the annotation palette
