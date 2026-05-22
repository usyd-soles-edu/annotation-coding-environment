(function () {
  "use strict";

  const TAB_ID_KEY = "ace-runtime-tab-id";
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
  void init();
}());
