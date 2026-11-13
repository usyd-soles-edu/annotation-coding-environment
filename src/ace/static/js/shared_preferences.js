/* Share user-adjustable UI settings across authenticated desktop runtimes. */
(function () {
  "use strict";

  const KEYS = [
    "ace-sidebar-width", "ace-grid-height", "ace-coding-text-size",
    "ace-coding-text-width", "ace-note-open", "ace-grid-collapsed",
    "ace-applied-codes-collapsed", "ace-codebook-cues-enabled",
  ];
  const PENDING_PREFIX = "ace-preference-pending:";
  const boot = window.__acePreferenceBootstrap || {};
  const entries = Object.assign({}, boot.shared || {});
  const legacy = boot.legacy || Object.fromEntries(KEYS.map(function (key) {
    try { return [key, localStorage.getItem(key)]; } catch (_) { return [key, null]; }
  }));
  const versions = Object.create(null);
  const localTokens = new Set();
  const pending = Object.fromEntries(KEYS.map(function (key) {
    return [key, readPending(key)];
  }));
  let enabled = false;
  let initialised = false;
  let networkQueue = Promise.resolve();
  let initPromise = null;

  function token() {
    try { return crypto.randomUUID(); } catch (_) {
      return String(Date.now()) + "-" + String(Math.random()).slice(2);
    }
  }

  function validPending(change) {
    if (!change || typeof change.token !== "string" ||
        !Number.isSafeInteger(change.revision) || change.revision < 0 ||
        !(change.value === null || typeof change.value === "string")) return null;
    return change;
  }

  function readPending(key) {
    try { return validPending(JSON.parse(localStorage.getItem(PENDING_PREFIX + key))); }
    catch (_) { return null; }
  }

  function currentPending(key) {
    try {
      pending[key] = validPending(JSON.parse(localStorage.getItem(PENDING_PREFIX + key)));
    } catch (_) {
      // Keep unsent changes in this page when browser storage is unavailable.
    }
    return pending[key];
  }

  function savePending(key, change) {
    pending[key] = change;
    try {
      if (change) {
        localStorage.setItem(PENDING_PREFIX + key, JSON.stringify(change));
      } else {
        localStorage.removeItem(PENDING_PREFIX + key);
      }
    } catch (_) {}
  }

  function mirror(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (_) {}
  }

  function get(key) {
    try { return localStorage.getItem(key); }
    catch (_) { return entries[key]?.value ?? null; }
  }

  async function post(action, key, value, revision) {
    const response = await fetch("/api/runtime/preferences", {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, key: key, value: value, revision: revision }),
    });
    if (!response.ok) throw new Error("Could not save shared UI preference");
    const result = await response.json();
    if (result.enabled !== true) throw new Error("Shared UI preferences unavailable");
    return result;
  }

  function queue(work) {
    networkQueue = networkQueue.catch(function () {}).then(work);
    return networkQueue;
  }

  function forget(key, change) {
    localTokens.delete(change.token);
    if (currentPending(key)?.token !== change.token) return;
    savePending(key, null);
  }

  function advanceLocalPending(key, change, revision) {
    const next = currentPending(key);
    if (!next || next.token === change.token ||
        !localTokens.has(next.token) || next.revision !== change.revision) return;
    next.revision = revision;
    savePending(key, next);
  }

  async function applyPending(key, change, version) {
    const current = currentPending(key);
    if (current?.token !== change.token) {
      localTokens.delete(change.token);
      return;
    }
    try {
      const result = await post("set", key, current.value, current.revision);
      if (result.applied) advanceLocalPending(key, current, result.entry.revision);
      entries[key] = result.entry;
      forget(key, current);
      if (version !== versions[key]) return;
      mirror(key, result.entry.value);
      window.dispatchEvent(new Event("ace:preferences-changed"));
    } catch (_) {
      if (currentPending(key)?.token !== change.token) {
        localTokens.delete(change.token);
      }
      // Keep the local choice and retry when the window next gains focus.
    }
  }

  function set(key, value) {
    if (!KEYS.includes(key)) return;
    mirror(key, value);
    if (initialised && !enabled) return;
    versions[key] = (versions[key] || 0) + 1;
    const change = {
      token: token(), value: value,
      revision: entries[key]?.revision || 0,
    };
    localTokens.add(change.token);
    savePending(key, change);
    const send = function () {
      if (enabled) void queue(function () {
        return applyPending(key, change, versions[key]);
      });
    };
    if (enabled) send();
    else void init().then(send);
  }

  async function sync() {
    try {
      const response = await fetch("/api/runtime/preferences", {
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const data = await response.json();
      initialised = true;
      if (data.enabled !== true) {
        // Ordinary browser mode only uses localStorage. A ?note=1 write can
        // happen before this response; it must not linger as a pending retry.
        KEYS.forEach(function (key) { savePending(key, null); });
        return;
      }
      enabled = true;
      Object.assign(entries, data.preferences);

      for (const key of KEYS) {
        const change = currentPending(key);
        if (!change) continue;
        await applyPending(key, change, versions[key]);
      }
      for (const key of KEYS) {
        if (Object.prototype.hasOwnProperty.call(entries, key) ||
            currentPending(key) || legacy[key] == null) continue;
        try {
          const result = await post("migrate", key, legacy[key]);
          entries[key] = result.entry;
          const newer = currentPending(key);
          if (result.applied && newer && localTokens.has(newer.token) &&
              newer.revision === 0) {
            newer.revision = result.entry.revision;
            savePending(key, newer);
          }
        } catch (_) {
          // An invalid legacy value stays local until the user changes it.
        }
      }
      for (const key of KEYS) {
        if (currentPending(key) || !Object.prototype.hasOwnProperty.call(entries, key)) continue;
        mirror(key, entries[key].value);
      }
      window.dispatchEvent(new Event("ace:preferences-changed"));
    } catch (_) {
      // Browser storage remains usable while the shared store is unavailable.
    }
  }

  function init() {
    if (initPromise) return initPromise;
    initPromise = queue(sync).finally(function () { initPromise = null; });
    return initPromise;
  }

  window.addEventListener("focus", function () { void init(); });
  window.addEventListener("storage", function (event) {
    if (event.key?.startsWith(PENDING_PREFIX)) void init();
  });
  window.ACE_PREFS = { get: get, set: set, remove: function (key) { set(key, null); } };
  window.ACE_PREFS.ready = init();
  if (window.__acePreferenceForcedOpenNote) set("ace-note-open", "1");
}());
