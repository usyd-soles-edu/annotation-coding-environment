"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../../src/ace/static/js/code_view.js"), "utf8"
);
const start = source.indexOf("  const navAbort =");
const end = source.indexOf("\n  const dataCache =", start);
assert(start >= 0 && end > start, "loadCode must be present in code_view.js");
const navigationCode = source.slice(start, end);
const popStart = source.indexOf('  window.addEventListener("popstate", () => {');
const popEnd = source.indexOf("\n  // --- Cheat sheet", popStart);
assert(popStart >= 0 && popEnd > popStart, "popstate handler must be present");
const popstateCode = source.slice(popStart, popEnd);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function viewData(id) {
  return { code: { id } };
}

function harness(fetch, transitionCallbacks = null) {
  const renders = [];
  const historyCalls = [];
  const location = { href: "/code/initial/view", pathname: "/code/initial/view" };
  const listeners = new Map();
  function recordHistory(kind, url) {
    historyCalls.push([kind, url]);
    location.href = url;
    location.pathname = url;
  }
  const context = {
    AbortController,
    data: viewData("initial"),
    dataCache: new Map(),
    fetch,
    location,
    window: {
      location,
      addEventListener(name, listener) { listeners.set(name, listener); },
    },
    document: transitionCallbacks ? {
      startViewTransition(callback) {
        transitionCallbacks.push(callback);
      },
    } : {},
    history: {
      pushState(_state, _title, url) { recordHistory("push", url); },
      replaceState(_state, _title, url) { recordHistory("replace", url); },
    },
    confirmAndDiscardMetadataEdits() { return true; },
    renderForData(json) {
      context.data = json;
      renders.push(json.code.id);
    },
    _cacheTouch() {},
    _cacheEvictIfFull() {},
  };
  vm.runInNewContext(`${navigationCode}\n${popstateCode}\nglobalThis.loadCode = loadCode;`, context);
  return { context, renders, historyCalls, location, listeners };
}

async function main() {
  // A prefetched response can settle after a newer code has rendered.
  {
    const pendingA = deferred();
    const h = harness(async () => ({ ok: true, json: async () => viewData("B") }));
    h.context.dataCache.set("A", pendingA.promise);
    const first = h.context.loadCode("A", { viewTransition: false });
    await h.context.loadCode("B", { viewTransition: false });
    pendingA.resolve(viewData("A"));
    await first;
    assert.deepEqual(h.renders, ["B"]);
    assert.deepEqual(h.historyCalls, [["push", "/code/B/view"]]);
  }

  // An uncached response may ignore abort; a newer back/forward selection wins.
  {
    const pendingA = deferred();
    const h = harness(async (url) => url.includes("/A/")
      ? pendingA.promise
      : { ok: true, json: async () => viewData("B") });
    const first = h.context.loadCode("A", { pushHistory: false, viewTransition: false });
    await h.context.loadCode("B", { pushHistory: false, viewTransition: false });
    pendingA.resolve({ ok: true, json: async () => viewData("A") });
    await first;
    assert.deepEqual(h.renders, ["B"]);
    assert.deepEqual(h.historyCalls, [["replace", "/code/B/view"]]);
  }

  // A superseded prefetch failure must not navigate away from the newer code.
  {
    const pendingA = deferred();
    const h = harness(async () => ({ ok: true, json: async () => viewData("B") }));
    h.context.dataCache.set("A", pendingA.promise);
    const first = h.context.loadCode("A", { viewTransition: false });
    await h.context.loadCode("B", { viewTransition: false });
    pendingA.reject(new Error("prefetch failed"));
    await first;
    assert.equal(h.location.href, "/code/B/view");
    assert.deepEqual(h.renders, ["B"]);
  }

  // Returning to the currently displayed code also supersedes pending work.
  {
    const pendingA = deferred();
    const h = harness(async () => { throw new Error("unexpected fetch"); });
    h.context.dataCache.set("A", pendingA.promise);
    const first = h.context.loadCode("A", { viewTransition: false });
    await h.context.loadCode("initial", { viewTransition: false });
    pendingA.resolve(viewData("A"));
    await first;
    assert.deepEqual(h.renders, []);
    assert.deepEqual(h.historyCalls, []);
  }

  // View transitions can defer their render callback beyond a newer request.
  {
    const callbacks = [];
    const h = harness(async (url) => ({
      ok: true,
      json: async () => viewData(url.includes("/A/") ? "A" : "B"),
    }), callbacks);
    await h.context.loadCode("A");
    await h.context.loadCode("B");
    callbacks[0]();
    callbacks[1]();
    assert.deepEqual(h.renders, ["B"]);
    assert.deepEqual(h.historyCalls.at(-1), ["push", "/code/B/view"]);
  }

  // Re-selecting the displayed code before a deferred render keeps its URL.
  {
    const callbacks = [];
    const h = harness(async () => ({ ok: true, json: async () => viewData("A") }), callbacks);
    await h.context.loadCode("A");
    await h.context.loadCode("initial");
    callbacks[0]();
    assert.deepEqual(h.renders, []);
    assert.deepEqual(h.historyCalls, []);
    assert.equal(h.location.pathname, "/code/initial/view");
  }

  // Actual Back/Forward handler: Forward to the displayed code cancels Back.
  {
    const pendingA = deferred();
    const h = harness(async () => { throw new Error("unexpected fetch"); });
    h.context.data = viewData("B");
    h.context.dataCache.set("A", pendingA.promise);
    h.location.pathname = "/code/A/view";
    h.location.href = h.location.pathname;
    h.listeners.get("popstate")();
    h.location.pathname = "/code/B/view";
    h.location.href = h.location.pathname;
    h.listeners.get("popstate")();
    pendingA.resolve(viewData("A"));
    await new Promise(setImmediate);
    assert.equal(h.context.data.code.id, "B");
    assert.deepEqual(h.renders, []);
    assert.equal(h.location.pathname, "/code/B/view");
  }

  // Clicking the displayed code during a pending Back restores its URL.
  {
    const pendingA = deferred();
    const h = harness(async () => { throw new Error("unexpected fetch"); });
    h.context.data = viewData("B");
    h.context.dataCache.set("A", pendingA.promise);
    h.location.pathname = "/code/A/view";
    h.location.href = h.location.pathname;
    h.listeners.get("popstate")();
    await h.context.loadCode("B");
    pendingA.resolve(viewData("A"));
    await new Promise(setImmediate);
    assert.equal(h.context.data.code.id, "B");
    assert.deepEqual(h.renders, []);
    assert.deepEqual(h.historyCalls, [["push", "/code/B/view"]]);
    assert.equal(h.location.pathname, "/code/B/view");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
