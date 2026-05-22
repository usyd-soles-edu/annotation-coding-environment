#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$ROOT/tmp/headless-tree-build"

mkdir -p "$BUILD_DIR"
cat > "$BUILD_DIR/package.json" <<'JSON'
{
  "private": true,
  "dependencies": {
    "@headless-tree/core": "1.7.0"
  },
  "devDependencies": {
    "esbuild": "0.28.0"
  }
}
JSON

npm install --silent --prefix "$BUILD_DIR"

cd "$ROOT"
ESBUILD="$BUILD_DIR/node_modules/.bin/esbuild"
HEADLESS_TREE="./tmp/headless-tree-build/node_modules/@headless-tree/core/dist/index.mjs"

"$ESBUILD" spikes/headless-tree/spike.js \
  --bundle \
  --format=iife \
  --global-name=AceHeadlessTreeSpike \
  --alias:@headless-tree/core="$HEADLESS_TREE" \
  --outfile=spikes/headless-tree/spike.bundle.js

"$ESBUILD" src/ace/static/js/codebook_headless_tree_source.js \
  --bundle \
  --format=iife \
  --global-name=AceHeadlessTreePreview \
  --alias:@headless-tree/core="$HEADLESS_TREE" \
  --outfile=src/ace/static/js/codebook_headless_tree.js
