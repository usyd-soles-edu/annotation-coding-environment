(function () {
  "use strict";

  const TAB_ID_KEY = "ace-runtime-tab-id";
  const RECENT_FILES_KEY = "ace-recent-files";
  const HEARTBEAT_INTERVAL_MS = 15000;

  let enabled = false;
  let intervalId = null;
  let tabId = null;

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
      if (item && typeof item.path === "string") return item;
      return null;
    }).filter(Boolean);
  }

  function getRecentFiles() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(RECENT_FILES_KEY)) || [];
      return migrateRecent(raw);
    } catch (_err) {
      return [];
    }
  }

  function addRecentFile(path) {
    let list = getRecentFiles().filter(function (item) { return item.path !== path; });
    list.unshift({ path: path, openedAt: Date.now() });
    if (list.length > 5) list = list.slice(0, 5);
    window.localStorage.setItem(RECENT_FILES_KEY, JSON.stringify(list));
  }

  function clearRecentFiles() {
    window.localStorage.removeItem(RECENT_FILES_KEY);
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

  async function init() {
    try {
      const response = await window.fetch("/api/runtime/status", {
        credentials: "same-origin",
      });
      if (!response.ok) return;

      const status = await response.json();
      if (!status || status.enabled !== true || status.authenticated !== true) return;

      enabled = true;
      startHeartbeat();
    } catch (_err) {
      // Runtime support is optional outside launcher mode.
    }
  }

  window.addEventListener("pagehide", disconnect);
  window.ACE_RECENTS = {
    get: getRecentFiles,
    add: addRecentFile,
    clear: clearRecentFiles,
  };
  void init();
}());
