/* Shared codebook sidebar resize behaviour for coding and audit pages. */
(function () {
  "use strict";

  const DEFAULT_PX = 360;
  const MIN_PX = 150;
  const KEY_STEP_PX = 24;
  const STORAGE_KEY = "ace-sidebar-width";

  function initSidebar(handle, container) {
    if (!handle || !container || handle.dataset.aceResizeWired) return;
    handle.dataset.aceResizeWired = "1";

    const root = document.documentElement;
    let dragging = false;

    function maxPx() {
      const viewport = root.clientWidth;
      const available = container.getBoundingClientRect().width;
      const base = Math.min(viewport || available, available || viewport);
      return Math.max(MIN_PX, Math.floor((base || DEFAULT_PX) * 0.4));
    }

    function currentPx() {
      return parseInt(getComputedStyle(root).getPropertyValue("--ace-sidebar-width"), 10)
        || DEFAULT_PX;
    }

    function savedPx() {
      try { return parseInt(window.ACE_PREFS.get(STORAGE_KEY), 10) || DEFAULT_PX; }
      catch (_) { return DEFAULT_PX; }
    }

    function setWidth(px, persist) {
      const maximum = maxPx();
      const width = Math.max(MIN_PX, Math.min(maximum, px));
      root.style.setProperty("--ace-sidebar-width", width + "px");
      handle.setAttribute("aria-valuemin", String(MIN_PX));
      handle.setAttribute("aria-valuemax", String(maximum));
      handle.setAttribute("aria-valuenow", String(Math.round(width)));
      handle.setAttribute("aria-valuetext", Math.round(width) + " pixels");
      if (persist) {
        try { window.ACE_PREFS.set(STORAGE_KEY, String(Math.round(width))); }
        catch (_) {}
      }
    }

    function endDrag(event) {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      if (handle.hasPointerCapture(event.pointerId)) {
        handle.releasePointerCapture(event.pointerId);
      }
      setWidth(currentPx(), true);
    }

    handle.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      dragging = true;
      handle.setPointerCapture(event.pointerId);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      event.preventDefault();
    });
    handle.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      const left = container.getBoundingClientRect().left;
      setWidth(event.clientX - left, false);
    });
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
    handle.addEventListener("lostpointercapture", endDrag);

    function reset() {
      try { window.ACE_PREFS.remove(STORAGE_KEY); } catch (_) {}
      setWidth(DEFAULT_PX, false);
    }
    handle.addEventListener("dblclick", reset);
    document.addEventListener("click", function (event) {
      if (event.target.closest?.("#ace-layout-reset-btn")) reset();
    });
    handle.addEventListener("keydown", function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        setWidth(currentPx() + (event.key === "ArrowRight" ? KEY_STEP_PX : -KEY_STEP_PX), true);
      } else if (event.key === "Home") {
        setWidth(MIN_PX, true);
      } else if (event.key === "End") {
        setWidth(maxPx(), true);
      } else {
        return;
      }
      event.preventDefault();
    });

    function clampToViewport() {
      if (!dragging) setWidth(savedPx(), false);
    }
    window.addEventListener("resize", clampToViewport);
    clampToViewport();
  }

  window.ACE_RESIZE = { initSidebar };
})();
