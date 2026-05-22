# Headless Tree Codebook Spike

This spike checks whether `@headless-tree/core` can take over the hard parts of
ACE's codebook tree without moving ACE to React.

Open `index.html` directly in a browser. The page uses a bundled copy of the
spike script so the browser test does not need npm at runtime.

## What It Proves

- Headless Tree core works from a vanilla DOM adapter.
- The core tree model handles ACE-shaped data: folder > folder > code.
- Built-in tree navigation works across Chromium, Firefox, and WebKit.
- Collapse state, ARIA treeitem props, levels, and focused item state can come
  from Headless Tree instead of hand-written DOM traversal.
- Reparenting and same-folder reordering can be driven through Headless Tree's
  drop utilities and then mapped back to ACE-style API operations.
- Nested rows can be converted from ACE's current codebook shape into the
  Headless Tree item map without adding a React layer.
- Cross-parent drops can emit the same contract the production sidebar now
  needs: `parent_id` plus the target scope's ordered ids.
- Renaming can use Headless Tree state, but ACE should override the default
  blur-to-abort behaviour.

## Migration Notes

A production migration should not bolt Headless Tree onto the existing
server-rendered sidebar DOM. The cleaner path is a small codebook tree island:
server provides JSON, the island renders rows, and HTMX still handles the
surrounding coding page.

The spike found two adapter requirements:

- After a state change that re-renders rows, restore focus to the Headless Tree
  focused item. Otherwise WebKit and Chromium can lose keyboard flow.
- Treat rename as Enter-to-commit and Escape-to-cancel. WebKit can blur the
  input during text entry, so default blur-to-abort is too fragile for ACE.
- Keep the persistence layer outside Headless Tree. The adapter should translate
  library drop targets into ACE's existing HTMX endpoints instead of letting the
  library know about routes.

Run:

```bash
bash spikes/headless-tree/build-assets.sh
uv run pytest tests/e2e/test_headless_tree_spike.py -q
```

The build script installs pinned npm tooling under ignored `tmp/` and rebuilds
both `spike.bundle.js` and the dev-gated preview bundle in
`src/ace/static/js/codebook_headless_tree.js`.
