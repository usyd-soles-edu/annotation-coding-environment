(function () {
  "use strict";

  const TAB_ID_KEY = "ace-runtime-tab-id";
  const RECENT_FILES_KEY = "ace-recent-files";
  const PENDING_RECENT_KEY = "ace-recent-pending";
  const HEARTBEAT_INTERVAL_MS = 15000;

  let enabled = false;
  let intervalId = null;
  let tabId = null;
  let launcherAuthenticated = false;
  let sharedRecentsEnabled = false;
  let sharedRecent = null;
  let recentVersion = 0;
  let recentNetworkQueue = Promise.resolve();
  let runtimeInitPromise = null;
  let pendingRecentChange = readPendingRecent();
  let pendingRecentStored = !!pendingRecentChange;

  function randomTabId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
    } catch (_err) {
      // Ignore and use the non-crypto fallback below.
    }
    return String(Date.now()) + "-" + String(Math.random()).slice(2);
  }

  function getTabId() {
    if (tabId) return tabId;

    try {
      tabId = window.sessionStorage.getItem(TAB_ID_KEY);
      if (!tabId) {
        tabId = randomTabId();
        window.sessionStorage.setItem(TAB_ID_KEY, tabId);
      }
    } catch (_err) {
      tabId = randomTabId();
    }

    return tabId;
  }

  function formBody(id) {
    return "tab_id=" + encodeURIComponent(id);
  }

  function migrateRecent(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(function (item) {
      if (typeof item === "string") return { path: item, openedAt: 0 };
      if (item && typeof item.path === "string") {
        return {
          path: item.path,
          openedAt: Number.isSafeInteger(item.openedAt) && item.openedAt >= 0
            ? item.openedAt : 0,
        };
      }
      return null;
    }).filter(Boolean);
  }

  function getLocalRecentFiles() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(RECENT_FILES_KEY)) || [];
      const list = migrateRecent(raw).slice(0, 1);
      if (Array.isArray(raw) && raw.length > list.length) {
        window.localStorage.setItem(RECENT_FILES_KEY, JSON.stringify(list));
      }
      return list;
    } catch (_err) {
      return [];
    }
  }

  function mirrorRecentToLocal(recent) {
    try {
      if (recent) {
        window.localStorage.setItem(RECENT_FILES_KEY, JSON.stringify([recent]));
      } else {
        window.localStorage.removeItem(RECENT_FILES_KEY);
      }
    } catch (_err) {
      // The shared record remains usable when browser storage is unavailable.
    }
  }

  function getRecentFiles() {
    return sharedRecentsEnabled
      ? (sharedRecent ? [sharedRecent] : [])
      : getLocalRecentFiles();
  }

  function notifyRecentChanged() {
    window.dispatchEvent(new Event("ace:recents-changed"));
  }

  async function postSharedRecent(action, recent) {
    const response = await window.fetch("/api/runtime/recent-project", {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: action,
        path: recent?.path || "",
        opened_at: recent?.openedAt || 0,
      }),
    });
    if (!response.ok) throw new Error("Shared recent project update failed");
    const result = await response.json();
    if (result.enabled !== true) throw new Error("Shared recent project is unavailable");
    return migrateRecent([result.recent])[0] || null;
  }

  function parsePendingRecent(raw) {
    try {
      const change = JSON.parse(raw);
      if (!change || typeof change.token !== "string" ||
          !["set", "remove", "clear"].includes(change.action)) return null;
      if (change.action !== "clear" &&
          (typeof change.recent?.path !== "string" || !change.recent.path ||
           change.recent.path.length > 32768)) return null;
      return change;
    } catch (_err) {
      return null;
    }
  }

  function readPendingRecent() {
    try {
      return parsePendingRecent(window.localStorage.getItem(PENDING_RECENT_KEY));
    } catch (_err) {
      return null;
    }
  }

  function currentPendingRecent() {
    if (!pendingRecentStored) return pendingRecentChange;
    try {
      pendingRecentChange = parsePendingRecent(
        window.localStorage.getItem(PENDING_RECENT_KEY)
      );
      pendingRecentStored = !!pendingRecentChange;
    } catch (_err) {
      // An in-flight local action can still retry in this page.
    }
    return pendingRecentChange;
  }

  function rememberPendingRecent(action, recent) {
    const change = { token: randomTabId(), action: action, recent: recent };
    pendingRecentChange = change;
    try {
      window.localStorage.setItem(PENDING_RECENT_KEY, JSON.stringify(change));
      pendingRecentStored = true;
    } catch (_err) {
      // Retry within this page even if browser storage is unavailable.
      pendingRecentStored = false;
    }
    return change;
  }

  function forgetPendingRecent(change) {
    if (currentPendingRecent()?.token !== change.token) return;
    pendingRecentChange = null;
    pendingRecentStored = false;
    try {
      if (readPendingRecent()?.token === change.token) {
        window.localStorage.removeItem(PENDING_RECENT_KEY);
      }
    } catch (_err) {}
  }

  function queueRecentNetwork(work) {
    recentNetworkQueue = recentNetworkQueue.catch(function () {}).then(work);
    return recentNetworkQueue;
  }

  function queueSharedRecent(change, version) {
    void queueRecentNetwork(async function () {
      if (currentPendingRecent()?.token !== change.token) return;
      try {
        const saved = await postSharedRecent(change.action, change.recent);
        forgetPendingRecent(change);
        if (version !== recentVersion) return;
        sharedRecent = saved;
        sharedRecentsEnabled = true;
        mirrorRecentToLocal(saved);
        notifyRecentChanged();
      } catch (_err) {
        if (version !== recentVersion) return;
        sharedRecentsEnabled = false;
        notifyRecentChanged();
      }
    });
  }

  function changeRecent(action, recent) {
    const version = ++recentVersion;
    sharedRecent = action === "set" ? recent : null;
    mirrorRecentToLocal(sharedRecent);
    notifyRecentChanged();
    if (launcherAuthenticated) {
      queueSharedRecent(rememberPendingRecent(action, recent), version);
    }
  }

  function addRecentFile(path) {
    changeRecent("set", { path: path, openedAt: Date.now() });
  }

  function clearRecentFiles() {
    changeRecent("clear", null);
  }

  function removeRecentFile(path) {
    const recent = getRecentFiles()[0];
    if (recent && recent.path === path) {
      changeRecent("remove", recent);
    }
  }

  function loadSharedRecent() {
    const version = recentVersion;
    return queueRecentNetwork(async function () {
      try {
        const pending = currentPendingRecent();
        if (pending) {
          await postSharedRecent(pending.action, pending.recent);
          forgetPendingRecent(pending);
          if (version !== recentVersion) return;
        }
        const legacy = getLocalRecentFiles()[0] || null;
        const response = await window.fetch("/api/runtime/recent-project", {
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Shared recent project read failed");
        const result = await response.json();
        if (result.enabled !== true) throw new Error("Shared recent project is unavailable");
        const saved = legacy
          ? await postSharedRecent("migrate", legacy)
          : migrateRecent([result.recent])[0] || null;
        // A focus refresh that began before Clear must not restore old data.
        if (version !== recentVersion) return;
        sharedRecent = saved;
        sharedRecentsEnabled = true;
        mirrorRecentToLocal(saved);
        notifyRecentChanged();
      } catch (_err) {
        if (version !== recentVersion) return;
        sharedRecentsEnabled = false;
        notifyRecentChanged();
      }
    });
  }

  async function postRuntimeEvent(path) {
    try {
      await window.fetch(path, {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
        body: formBody(getTabId()),
      });
    } catch (_err) {
      // Best effort only.
    }
  }

  function heartbeat() {
    void postRuntimeEvent("/api/runtime/heartbeat");
  }

  function startHeartbeat() {
    if (intervalId !== null) return;
    heartbeat();
    intervalId = window.setInterval(heartbeat, HEARTBEAT_INTERVAL_MS);
  }

  function disconnect() {
    if (!enabled) return;

    try {
      if (window.navigator && typeof window.navigator.sendBeacon === "function") {
        const body = formBody(getTabId());
        const payload = new Blob([body], {
          type: "application/x-www-form-urlencoded;charset=UTF-8",
        });
        if (window.navigator.sendBeacon("/api/runtime/disconnect", payload)) {
          return;
        }
      }
    } catch (_err) {
      // Fall through to fetch keepalive below.
    }

    void postRuntimeEvent("/api/runtime/disconnect");
  }

  function init() {
    if (runtimeInitPromise) return runtimeInitPromise;
    runtimeInitPromise = (async function () {
      try {
        if (!launcherAuthenticated) {
          const response = await window.fetch("/api/runtime/status", {
            credentials: "same-origin",
          });
          if (!response.ok) return;
          const status = await response.json();
          if (!status || status.enabled !== true || status.authenticated !== true) return;
          launcherAuthenticated = true;
          enabled = true;
          startHeartbeat();
        }
        await loadSharedRecent();
      } catch (_err) {
        // The next focus retries; local browser history remains available.
      }
    }()).finally(function () { runtimeInitPromise = null; });
    return runtimeInitPromise;
  }

  window.addEventListener("pagehide", disconnect);
  window.addEventListener("focus", function () { void init(); });
  window.addEventListener("storage", function (event) {
    if (event.key !== PENDING_RECENT_KEY || !pendingRecentStored) return;
    const previousToken = pendingRecentChange?.token;
    pendingRecentChange = parsePendingRecent(event.newValue);
    pendingRecentStored = !!pendingRecentChange;
    if (previousToken !== pendingRecentChange?.token) {
      recentVersion += 1;
      if (launcherAuthenticated) void init();
    }
  });
  window.ACE_RECENTS = {
    get: getRecentFiles,
    add: addRecentFile,
    remove: removeRecentFile,
    clear: clearRecentFiles,
  };
  window.ACE_RECENTS.ready = init();
}());
