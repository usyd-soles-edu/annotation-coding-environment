// Coded text view — interactive tracks + excerpt table.
// Design spec: docs/superpowers/specs/2026-04-23-coded-text-view-design.md
// Mockup reference: docs/mockups/coded-text-view-options.html → Option 6C.

"use strict";

(function () {
  const dataEl = document.getElementById("ace-codeview-data");
  if (!dataEl) return;
  let data = JSON.parse(dataEl.textContent);
  let sources = data.sources;

  const tracksEl = document.getElementById("cv-tracks");
  const tableEl = document.getElementById("cv-table");
  const ctxEl = document.getElementById("cv-ctx");
  const clearBtn = document.getElementById("cv-clear");
  const modeHeadingEl = document.getElementById("cv-tracks-heading");
  const reviewPanelEl = document.querySelector("[data-cv-review-panel]");
  const editPanelEl = document.querySelector("[data-cv-edit-panel]");
  const reviewModeBtn = document.getElementById("cv-mode-review");
  const editModeBtn = document.getElementById("cv-mode-edit");
  const codeNameInput = document.getElementById("cv-code-name");
  const codeFolderSelect = document.getElementById("cv-code-folder");
  const codeDefinitionTextarea = document.getElementById("cv-code-definition");
  const CODEBOOK_CODE_ROW_SELECTOR = ".ace-ht-row--code[data-code-id]";
  let lastReviewFocus = null;
  let pendingMetadataSave = null;
  let codeViewMode = "review";

  function codebookTreeElement() {
    return document.getElementById("ace-headless-tree-mount");
  }

  function sidebarCodeRows(root) {
    const scope = root || document;
    return Array.from(scope.querySelectorAll(`#code-sidebar ${CODEBOOK_CODE_ROW_SELECTOR}`));
  }

  function codebookCodeRowFromTarget(target) {
    return target?.closest?.(`#code-sidebar ${CODEBOOK_CODE_ROW_SELECTOR}`) || null;
  }

  function codeIdFromCodebookRow(row) {
    return row?.dataset?.codeId || row?.getAttribute?.("data-code-id") || "";
  }

  function isCodebookCodeRow(row) {
    return !!(row?.matches?.(CODEBOOK_CODE_ROW_SELECTOR));
  }

  function setCurrentSidebarCode(codeId) {
    sidebarCodeRows().forEach((row) => {
      row.removeAttribute("aria-current");
      row.classList.remove("ace-ht-row--current");
    });
    const current = sidebarCodeRows().find((row) => codeIdFromCodebookRow(row) === codeId);
    if (current) {
      current.setAttribute("aria-current", "page");
      current.classList.add("ace-ht-row--current");
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Throttled live-region announcer. Rapid arrow-key extension should
  // announce once at the end of a stream of changes, not on every key.
  const liveEl = document.getElementById("cv-live");
  let liveTimer = null;
  function announce(msg) {
    if (!liveEl) return;
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => { liveEl.textContent = msg; }, 120);
  }

  function isEditableElement(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  // Mark an event as fully handled — preventDefault + stopImmediatePropagation
  // so bridge.js's document-level handlers (which share keys like F2, Enter,
  // V, Escape, Arrows on tree rows) never also fire. Used pervasively in this
  // file's keydown branches.
  function claim(evt) {
    evt.preventDefault();
    evt.stopImmediatePropagation();
  }

  // Apply roving-tabindex semantics: exactly one row in `rows` has tabindex="0",
  // all others "-1". Pass -1 (or a value out of range) to mark every row "-1".
  function setRovingTabindex(rows, activeIdx) {
    rows.forEach((r, i) => r.setAttribute("tabindex", i === activeIdx ? "0" : "-1"));
  }

  function trackRowEls() {
    return Array.from(tracksEl.querySelectorAll(".cv-track-row"));
  }

  // Selection state
  let selectedSources = new Set();          // Set<source idx>
  let selectedExcerpt = null;               // {srcIdx, excerptIdx} | null
  let anchorIdx = null;                     // most recent plain/Cmd click target

  // Tracks cursor: -1 on initial load (no cursor, overview shown).
  // Becomes an index into displayOrder once the user enters the zone.
  let tracksCursorIdx = -1;
  let sortBy = "source";                    // wired in Task 5
  let filterText = "";                      // wired in Task 5

  // Excerpts cursor — uses annotation id so the cursor survives sort / filter
  // re-renders. null means "no cursor yet" (initial load).
  let excerptsCursorId = null;

  // Remembered cursor per zone — stable identifiers so cursors survive DOM
  // rerenders (the stored idx/id is resolved back to an element at focus time).
  // Declared early because renderForData() resets these fields on initial
  // bootstrap (before the zone helpers later in the IIFE run).
  const rememberedCursor = {
    tracks: null,    // integer index into displayOrder, or null
    excerpts: null,  // annotation id string, or null
    codebook: null,  // code id string, or null
  };

  function renderFolderOptions() {
    if (!codeFolderSelect) return;
    const currentParent = data?.code?.parent_id || "";
    const options = [new Option("None", "")];
    (data.folders || []).forEach((folder) => {
      options.push(new Option(folder.name || "", folder.id || ""));
    });
    codeFolderSelect.replaceChildren(...options);
    codeFolderSelect.value = currentParent;
  }

  function editorHasDirtyValues() {
    if (!codeNameInput || !codeFolderSelect || !codeDefinitionTextarea || !data?.code) {
      return false;
    }
    function isDirtyField(key, currentValue, savedValue) {
      if (
        pendingMetadataSave
        && pendingMetadataSave.codeId === data.code.id
        && pendingMetadataSave.savedKeys.has(key)
        && currentValue === pendingMetadataSave.drafts[key]
      ) {
        return false;
      }
      return currentValue !== savedValue;
    }
    return (
      isDirtyField("name", codeNameInput.value, data.code.name || "")
      || isDirtyField("parentId", codeFolderSelect.value, data.code.parent_id || "")
      || isDirtyField("definition", codeDefinitionTextarea.value, data.code.definition || "")
    );
  }

  function confirmDiscardMetadataEdits() {
    return !editorHasDirtyValues() || window.confirm("Discard unsaved code edits?");
  }

  function confirmAndDiscardMetadataEdits() {
    if (!editorHasDirtyValues()) return true;
    if (!confirmDiscardMetadataEdits()) return false;
    populateCodeEditor();
    return true;
  }

  function preserveDirtyMetadataDraftForReload() {
    if (pendingMetadataSave && pendingMetadataSave.codeId === data?.code?.id) {
      if (!pendingMetadataSave.savedKeys.has("name")) {
        pendingMetadataSave.drafts.name = codeNameInput.value;
      }
      if (!pendingMetadataSave.savedKeys.has("parentId")) {
        pendingMetadataSave.drafts.parentId = codeFolderSelect.value;
      }
      if (!pendingMetadataSave.savedKeys.has("definition")) {
        pendingMetadataSave.drafts.definition = codeDefinitionTextarea.value;
      }
      pendingMetadataSave.restoreFocusId =
        document.activeElement?.id || pendingMetadataSave.restoreFocusId;
      return;
    }
    if (!editorHasDirtyValues()) return;
    const cleanKeys = [];
    const currentName = data.code.name || "";
    const currentParent = data.code.parent_id || "";
    const currentDefinition = data.code.definition || "";
    if (codeNameInput.value === currentName) cleanKeys.push("name");
    if (codeFolderSelect.value === currentParent) cleanKeys.push("parentId");
    if (codeDefinitionTextarea.value === currentDefinition) cleanKeys.push("definition");
    captureMetadataDraft(cleanKeys);
  }

  function captureMetadataDraft(savedKeys) {
    if (!codeNameInput || !codeFolderSelect || !codeDefinitionTextarea || !data?.code) {
      pendingMetadataSave = null;
      return null;
    }
    pendingMetadataSave = {
      codeId: data.code.id,
      savedKeys: new Set(savedKeys || []),
      restoreFocusId: document.activeElement?.id || null,
      drafts: {
        name: codeNameInput.value,
        parentId: codeFolderSelect.value,
        definition: codeDefinitionTextarea.value,
      },
    };
    return pendingMetadataSave;
  }

  function populateCodeEditor() {
    renderFolderOptions();
    if (!codeNameInput || !codeFolderSelect || !codeDefinitionTextarea || !data?.code) {
      pendingMetadataSave = null;
      return null;
    }

    codeNameInput.value = data.code.name || "";
    codeFolderSelect.value = data.code.parent_id || "";
    codeDefinitionTextarea.value = data.code.definition || "";

    const pending = pendingMetadataSave;
    let restoreFocusId = null;
    if (pending && pending.codeId === data.code.id) {
      if (!pending.savedKeys.has("name")) {
        codeNameInput.value = pending.drafts.name;
      }
      if (!pending.savedKeys.has("parentId")) {
        codeFolderSelect.value = pending.drafts.parentId;
      }
      if (!pending.savedKeys.has("definition")) {
        codeDefinitionTextarea.value = pending.drafts.definition;
      }
      restoreFocusId = pending.restoreFocusId;
    }
    pendingMetadataSave = null;
    return restoreFocusId;
  }

  function setCodeViewMode(mode, opts) {
    opts = opts || {};
    const nextMode = mode === "edit" ? "edit" : "review";
    const prevMode = codeViewMode;
    const leavingDirtyEdit =
      prevMode === "edit"
      && nextMode !== "edit"
      && opts.skipDirtyCheck !== true
      && editorHasDirtyValues();

    if (leavingDirtyEdit && !confirmAndDiscardMetadataEdits()) {
      return false;
    }

    if (nextMode === "edit" && prevMode !== "edit") {
      const active = document.activeElement;
      if (reviewPanelEl && active && reviewPanelEl.contains(active)) {
        lastReviewFocus = active;
      }
    }

    codeViewMode = nextMode;
    if (reviewPanelEl) reviewPanelEl.hidden = nextMode !== "review";
    if (editPanelEl) editPanelEl.hidden = nextMode !== "edit";
    if (modeHeadingEl) {
      modeHeadingEl.textContent = nextMode === "edit" ? "Edit selected code" : "Sources";
    }
    if (reviewModeBtn) reviewModeBtn.setAttribute("aria-pressed", nextMode === "review" ? "true" : "false");
    if (editModeBtn) editModeBtn.setAttribute("aria-pressed", nextMode === "edit" ? "true" : "false");

    if (opts.restoreFocusId) {
      const focusTarget = document.getElementById(opts.restoreFocusId);
      if (focusTarget && typeof focusTarget.focus === "function") {
        focusTarget.focus({ preventScroll: true });
        return true;
      }
    }

    if (nextMode === "edit") {
      if (prevMode !== "edit" && opts.focusName !== false && codeNameInput) {
        codeNameInput.focus({ preventScroll: true });
        codeNameInput.select();
      }
      return true;
    }

    if (
      prevMode === "edit"
      && lastReviewFocus
      && lastReviewFocus.isConnected
      && typeof lastReviewFocus.focus === "function"
    ) {
      lastReviewFocus.focus({ preventScroll: true });
    }
    return true;
  }

  function submitCodeUpdate(values, savedKeys) {
    if (!data?.code?.id) return;
    captureMetadataDraft(savedKeys);
    const requestValues = {
      codebook_mode: "audit",
      current_code_id: data.code.id,
      ...values,
    };
    if (window.htmx?.ajax) {
      window.htmx.ajax("PUT", `/api/codes/${data.code.id}`, {
        target: "#code-sidebar",
        swap: "none",
        values: requestValues,
      });
      return;
    }
    fetch(`/api/codes/${data.code.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(requestValues),
    }).catch(() => {});
  }

  function submitFolderUpdate(parentId) {
    if (!data?.code?.id) return;
    captureMetadataDraft(["parentId"]);
    const requestValues = {
      codebook_mode: "audit",
      current_code_id: data.code.id,
      parent_id: parentId,
    };
    if (window.htmx?.ajax) {
      window.htmx.ajax("PUT", `/api/codes/${data.code.id}/parent`, {
        target: "#code-sidebar",
        swap: "none",
        values: requestValues,
      });
      return;
    }
    fetch(`/api/codes/${data.code.id}/parent`, {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(requestValues),
    }).catch(() => {});
  }

  // --- Static render: tracks ---
  function renderTracksFresh() {
    tracksEl.innerHTML = sources.map((s) => {
      const ticks = s.excerpts.map((e, ei) => {
        return `<span class="tick" data-ex="${ei}"
                    style="left:${e.pos_pct.toFixed(2)}%;width:${e.width_pct.toFixed(2)}%"
                    title="excerpt ${ei + 1}"
                    aria-hidden="true"></span>`;
      }).join("");
      const pad = String(s.idx).padStart(2, "0");
      const label = `Source ${s.idx} — ${s.name}, ${s.count} excerpts`;
      return `<div class="cv-track-row" role="option" aria-selected="false"
                 tabindex="-1" data-src-idx="${s.idx}"
                 aria-label="${escapeHtml(label)}">
      <span class="idx" aria-hidden="true">${pad}</span>
      <span class="ct" aria-hidden="true">${s.count}</span>
      <span class="track" aria-hidden="true">${ticks}</span>
    </div>`;
    }).join("");
  }
  renderTracksFresh();

  // displayOrder drives both tracks order (left column) and table grouping.
  // Rebuilt whenever `sortBy` changes so the two columns read top-to-bottom
  // in the same order.
  let displayOrder = computeDisplayOrder();

  function bySrcIdx(idx) { return sources.find((s) => s.idx === idx); }

  function renderForData(newData) {
    data = newData;
    sources = data.sources;

    // Reset selection / cursor / filter state
    selectedSources.clear();
    selectedExcerpt = null;
    anchorIdx = null;
    tracksCursorIdx = -1;
    excerptsCursorId = null;
    filterText = "";
    if (searchEl) searchEl.value = "";
    rememberedCursor.tracks = null;
    rememberedCursor.excerpts = null;
    clearTimeout(liveTimer);

    // Reset sort chip — every code switch goes back to source-order sort
    sortBy = "source";
    if (toolbarEl) {
      toolbarEl.querySelectorAll("[data-sort]").forEach((c) =>
        c.setAttribute("aria-pressed", c.dataset.sort === "source" ? "true" : "false"));
    }

    // Rebuild tracks DOM and recompute display order
    renderTracksFresh();
    displayOrder = computeDisplayOrder();
    renderTracks();
    updateUI({ announce: false });

    // Header / title / colour
    const shell = document.getElementById("code-view");
    if (shell) shell.dataset.codeId = data.code.id;
    document.title = `${data.code.name} — Coded text — ACE`;
    const titleEl = document.querySelector(".cv-code-name");
    if (titleEl) titleEl.textContent = data.code.name;
    const summaryEl = document.querySelector(".cv-summary");
    if (summaryEl) {
      summaryEl.innerHTML =
        `<b>${data.stats.excerpts}</b> excerpts across `
        + `<b>${data.stats.sources_with_hits} of ${data.stats.total_sources}</b> sources`;
    }
    document.documentElement.style.setProperty("--code-colour", data.code.colour);
    document.documentElement.style.setProperty("--code-bg", data.code.colour + "22");
    if (tracksEl) {
      tracksEl.setAttribute("aria-label", `Sources with '${data.code.name}' excerpts`);
    }

    const restoreFocusId = populateCodeEditor();
    setCurrentSidebarCode(data.code.id);
    setCodeViewMode(codeViewMode, {
      focusName: false,
      restoreFocusId,
      skipDirtyCheck: true,
    });
  }

  // Returns the set of source idx values currently visible in the excerpts
  // column, per the pinned ∪ cursor rule. Does NOT account for selectedExcerpt
  // (which overrides everything) — callers that need to short-circuit on
  // selectedExcerpt should do so before calling this.
  function getVisibleSources() {
    const visible = new Set(selectedSources);
    if (tracksCursorIdx >= 0 && tracksCursorIdx < displayOrder.length) {
      visible.add(displayOrder[tracksCursorIdx]);
    }
    return visible;
  }

  function computeDisplayOrder() {
    const entries = sources.slice();
    if (sortBy === "length") {
      // Longest single excerpt per source, desc.
      entries.sort((a, b) => {
        const aMax = a.excerpts.reduce((m, e) => Math.max(m, e.text.length), 0);
        const bMax = b.excerpts.reduce((m, e) => Math.max(m, e.text.length), 0);
        return bMax - aMax;
      });
    } else if (sortBy === "position") {
      // Earliest excerpt start (pos_pct), asc.
      entries.sort((a, b) => {
        const aMin = a.excerpts.reduce((m, e) => Math.min(m, e.pos_pct), Infinity);
        const bMin = b.excerpts.reduce((m, e) => Math.min(m, e.pos_pct), Infinity);
        return aMin - bMin;
      });
    }
    return entries.map((s) => s.idx);
  }

  // Reorder track rows in-place to match displayOrder. appendChild on an
  // already-attached node moves it; listeners and per-row state survive.
  function renderTracks() {
    displayOrder.forEach((idx) => {
      const row = tracksEl.querySelector(`.cv-track-row[data-src-idx="${idx}"]`);
      if (row) tracksEl.appendChild(row);
    });
  }

  // --- Table rendering (respects selection + sort + filter) ---
  function renderTable() {
    let srcSet;
    if (selectedExcerpt) {
      srcSet = [selectedExcerpt.srcIdx];
    } else if (selectedSources.size === 0 && tracksCursorIdx < 0) {
      srcSet = displayOrder.slice(); // overview — no pins, no cursor
    } else {
      const visible = getVisibleSources();
      srcSet = displayOrder.filter((idx) => visible.has(idx));
    }

    // Flatten to {src, excerpt, localIdx}
    let items = [];
    srcSet.forEach((idx) => {
      const s = bySrcIdx(idx);
      if (!s) return;
      const excerpts = selectedExcerpt ? [s.excerpts[selectedExcerpt.excerptIdx]] : s.excerpts;
      excerpts.forEach((e, localEi) => {
        const ei = selectedExcerpt ? selectedExcerpt.excerptIdx : localEi;
        items.push({ srcIdx: idx, excerptIdx: ei, pos: e.pos_pct, len: e.text.length, text: e.text, annId: e.id });
      });
    });

    // Filter (wired in Task 5; code is here so the shape is ready)
    if (filterText) {
      const q = filterText.toLowerCase();
      items = items.filter((it) => it.text.toLowerCase().includes(q));
    }

    // Sort (wired in Task 5; code is here so the shape is ready)
    if (sortBy === "length") items.sort((a, b) => b.len - a.len);
    else if (sortBy === "position") items.sort((a, b) => a.pos - b.pos);
    // 'source' keeps source-then-offset order (already the case from srcSet iteration)

    // role="presentation" on non-option children — the parent #cv-table is a
    // listbox, so screen readers should only see .cv-row[role="option"] as
    // child items. The header and empty-state are decorative.
    let html = `<div class="cv-table-head" role="presentation"><span>#</span><span>Excerpt</span></div>`;
    if (items.length === 0) {
      const emptyText = data.stats && data.stats.excerpts === 0
        ? "No excerpts yet."
        : "No excerpts match the filter.";
      html += `<div class="cv-empty" role="presentation">${emptyText}</div>`;
    } else {
      items.forEach((it, i) => {
        const isSelected = (selectedExcerpt
                            && selectedExcerpt.srcIdx === it.srcIdx
                            && selectedExcerpt.excerptIdx === it.excerptIdx);
        const cls = isSelected ? " selected" : "";
        const isCursor = (it.annId != null && it.annId === excerptsCursorId);
        const ti = isCursor ? "0" : "-1";
        html += `<div class="cv-row${cls}"
                      role="option"
                      tabindex="${ti}"
                      aria-selected="${isSelected ? "true" : "false"}"
                      data-ann-id="${escapeHtml(it.annId)}"
                      data-src-idx="${it.srcIdx}" data-ex="${it.excerptIdx}">
          <span class="idx">${i + 1}</span>
          <span class="txt">${escapeHtml(it.text)}</span>
        </div>`;
      });
    }
    tableEl.innerHTML = html;
  }

  // After renderTable() rebuilds the DOM, make sure exactly one .cv-row has
  // tabindex="0". Uses annId so the cursor survives sort/filter re-renders.
  function reconcileExcerptsCursor() {
    const rows = Array.from(tableEl.querySelectorAll(".cv-row"));
    if (rows.length === 0) { excerptsCursorId = null; return; }
    // If we have a tracked cursor, make sure it's still present in the DOM
    if (excerptsCursorId != null) {
      const row = tableEl.querySelector(
        `.cv-row[data-ann-id="${CSS.escape(excerptsCursorId)}"]`,
      );
      if (row) {
        // cursor row still exists — the renderTable template already set tabindex
        return;
      }
      // Cursor no longer in DOM (filtered out / sorted away): reset
      excerptsCursorId = null;
    }
    // No cursor yet (initial load or after cursor loss): mark first row as the
    // tab stop but leave excerptsCursorId null so T2's "overview on load" rule
    // is preserved. A user Tab into this zone focuses row 0; first arrow press
    // promotes it to a real cursor.
    rows.forEach((r, i) => r.setAttribute("tabindex", i === 0 ? "0" : "-1"));
  }

  function highlightSource(idx) {
    tracksEl.querySelectorAll(".cv-track-row.hovered").forEach((r) => r.classList.remove("hovered"));
    const row = tracksEl.querySelector(`.cv-track-row[data-src-idx="${idx}"]`);
    if (row) row.classList.add("hovered");
  }
  function clearHighlight() {
    tracksEl.querySelectorAll(".cv-track-row.hovered").forEach((r) => r.classList.remove("hovered"));
  }

  // --- Update all UI to match state ---
  function updateUI(opts) {
    opts = opts || {};
    const shouldAnnounce = opts.announce !== false; // default true

    // Track row selection + aria-selected
    tracksEl.querySelectorAll(".cv-track-row").forEach((r) => {
      const idx = Number(r.getAttribute("data-src-idx"));
      const isSel = selectedSources.has(idx);
      r.classList.toggle("selected", isSel);
      r.setAttribute("aria-selected", isSel ? "true" : "false");
    });
    // Tick selection (single excerpt)
    tracksEl.querySelectorAll(".tick").forEach((t) => {
      t.classList.remove("selected");
    });
    if (selectedExcerpt) {
      const sel = tracksEl.querySelector(
        `.cv-track-row[data-src-idx="${selectedExcerpt.srcIdx}"] .tick[data-ex="${selectedExcerpt.excerptIdx}"]`,
      );
      if (sel) sel.classList.add("selected");
    }
    // Context bar + Clear
    if (selectedExcerpt) {
      const s = bySrcIdx(selectedExcerpt.srcIdx);
      ctxEl.innerHTML = `Showing excerpt <b>${selectedExcerpt.excerptIdx + 1}</b>
                         from <b>${escapeHtml(s.name)}</b>`;
    } else if (selectedSources.size === 0 && tracksCursorIdx < 0) {
      // Overview — no cursor, no pins (initial load)
      ctxEl.innerHTML = `Showing <b>all</b> sources ·
                         <b>${data.stats.excerpts}</b> excerpts`;
    } else {
      // Cursor and/or pins contributing (pinned ∪ cursor rule)
      const visible = getVisibleSources();
      const n = visible.size;
      let excerptCount = 0;
      visible.forEach((srcIdx) => {
        const src = bySrcIdx(srcIdx);
        if (src) excerptCount += src.excerpts.length;
      });
      ctxEl.innerHTML = `Showing <b>${excerptCount}</b> excerpt${excerptCount === 1 ? "" : "s"}
                         from <b>${n}</b> source${n === 1 ? "" : "s"}`;
    }
    clearBtn.disabled = !selectedExcerpt && selectedSources.size === 0 && tracksCursorIdx < 0;

    renderTable();
    reconcileExcerptsCursor();

    // Announce current scope to screen readers (throttled)
    if (shouldAnnounce) {
      announce(ctxEl.textContent.replace(/\s+/g, " ").trim());
    }
  }

  // --- Mouse handlers on tracks ---
  tracksEl.addEventListener("click", (evt) => {
    const tick = evt.target.closest(".tick");
    const row = evt.target.closest(".cv-track-row");
    if (tick) {
      const srcIdx = Number(row.getAttribute("data-src-idx"));
      const excerptIdx = Number(tick.getAttribute("data-ex"));
      selectedExcerpt = { srcIdx, excerptIdx };
      selectedSources = new Set([srcIdx]);
      anchorIdx = srcIdx;
      // Set cursor to the clicked row's position and give it tabindex="0"
      const clickedPos = displayOrder.indexOf(srcIdx);
      tracksCursorIdx = clickedPos >= 0 ? clickedPos : -1;
      setRovingTabindex(trackRowEls(), tracksCursorIdx);
      updateUI(); // announce — selectedExcerpt changed
      return;
    }
    if (!row) return;
    const idx = Number(row.getAttribute("data-src-idx"));

    // Set cursor to the clicked row's position in displayOrder
    const clickedPos = displayOrder.indexOf(idx);
    tracksCursorIdx = clickedPos >= 0 ? clickedPos : -1;
    setRovingTabindex(trackRowEls(), tracksCursorIdx);

    // Shift+click with no anchor, or shift+click on the anchor row itself,
    // falls through to the plain-click branch (matches Finder/File Explorer).
    if (evt.shiftKey && anchorIdx !== null && anchorIdx !== idx) {
      const aPos = displayOrder.indexOf(anchorIdx);
      const bPos = displayOrder.indexOf(idx);
      if (aPos >= 0 && bPos >= 0) {
        const [lo, hi] = [Math.min(aPos, bPos), Math.max(aPos, bPos)];
        selectedSources = new Set(displayOrder.slice(lo, hi + 1));
      }
      selectedExcerpt = null;
    } else if (evt.metaKey || evt.ctrlKey) {
      if (selectedSources.has(idx)) selectedSources.delete(idx);
      else selectedSources.add(idx);
      selectedExcerpt = null;
      anchorIdx = idx;
    } else {
      if (selectedSources.size === 1 && selectedSources.has(idx) && !selectedExcerpt) {
        selectedSources.clear();
        anchorIdx = null;
      } else {
        selectedSources = new Set([idx]);
        selectedExcerpt = null;
        anchorIdx = idx;
      }
    }
    updateUI(); // announce — selectedSources or selectedExcerpt changed
  });

  // Delegated hover linkage — set once; survives every table re-render.
  // mouseover/mouseout bubble, unlike mouseenter/mouseleave — use those
  // with a closest() guard so the linkage triggers once per row entry.
  tableEl.addEventListener("mouseover", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row || !tableEl.contains(row)) return;
    // Only fire when entering the row from outside it (mimic mouseenter)
    const related = evt.relatedTarget;
    if (related && row.contains(related)) return;
    highlightSource(Number(row.getAttribute("data-src-idx")));
  });
  tableEl.addEventListener("mouseout", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    // Only fire when leaving the row entirely (mimic mouseleave)
    const related = evt.relatedTarget;
    if (related && row.contains(related)) return;
    clearHighlight();
  });

  // Keyboard focus on an excerpt row has the same linkage to tracks as hover.
  // focus/blur don't bubble, so use capture phase.
  tableEl.addEventListener("focus", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    highlightSource(Number(row.getAttribute("data-src-idx")));
  }, true);
  tableEl.addEventListener("blur", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    clearHighlight();
  }, true);

  // --- Keyboard navigation on tracks (roving tabindex) ---
  function focusedRowIdx() {
    return trackRowEls().indexOf(document.activeElement);
  }
  function moveFocus(newPos, opts) {
    opts = opts || {};
    const silent = opts.announce === false;
    const rows = trackRowEls();
    if (rows.length === 0) return;
    const idx = Math.max(0, Math.min(newPos, rows.length - 1));
    setRovingTabindex(rows, idx);
    const target = rows[idx];
    target.focus();
    target.scrollIntoView({ block: "nearest" });
    tracksCursorIdx = idx;
    updateUI(silent ? { announce: false } : undefined);
  }
  function extendRange(toIdx) {
    if (anchorIdx === null) return;
    const aPos = displayOrder.indexOf(anchorIdx);
    const bPos = displayOrder.indexOf(toIdx);
    if (aPos < 0 || bPos < 0) return;
    const [lo, hi] = [Math.min(aPos, bPos), Math.max(aPos, bPos)];
    selectedSources = new Set(displayOrder.slice(lo, hi + 1));
    selectedExcerpt = null;
  }

  tracksEl.addEventListener("keydown", (evt) => {
    const rows = trackRowEls();
    if (rows.length === 0) return;
    const pos = focusedRowIdx();
    if (pos < 0) return;
    const focusedSrcIdx = Number(rows[pos].getAttribute("data-src-idx"));

    // Navigation — no selection change (silent cursor move)
    if (evt.key === "ArrowDown" && !evt.shiftKey) {
      evt.preventDefault(); moveFocus(pos + 1, { announce: false }); return;
    }
    if (evt.key === "ArrowUp" && !evt.shiftKey) {
      evt.preventDefault(); moveFocus(pos - 1, { announce: false }); return;
    }
    if (evt.key === "Home") { evt.preventDefault(); moveFocus(0, { announce: false }); return; }
    if (evt.key === "End")  { evt.preventDefault(); moveFocus(rows.length - 1, { announce: false }); return; }

    // Shift+Arrow — move focus AND extend range from anchor
    if (evt.shiftKey && (evt.key === "ArrowUp" || evt.key === "ArrowDown")) {
      evt.preventDefault();
      const next = Math.max(0, Math.min(rows.length - 1, pos + (evt.key === "ArrowDown" ? 1 : -1)));
      const targetIdx = Number(rows[next].getAttribute("data-src-idx"));
      if (anchorIdx === null) anchorIdx = focusedSrcIdx;
      extendRange(targetIdx);
      moveFocus(next); // announce — selectedSources range extended
      return;
    }

    // Space — toggle focused row like a plain click
    if ((evt.key === " " || evt.code === "Space") && !evt.shiftKey) {
      evt.preventDefault();
      tracksCursorIdx = pos; // keep cursor coherent with the row we just acted on
      if (selectedSources.size === 1 && selectedSources.has(focusedSrcIdx) && !selectedExcerpt) {
        selectedSources.clear();
        anchorIdx = null;
      } else {
        selectedSources = new Set([focusedSrcIdx]);
        selectedExcerpt = null;
        anchorIdx = focusedSrcIdx;
      }
      updateUI(); // announce — pin/unpin changed selectedSources
      return;
    }

    // Shift+Space — extend range from anchor to focused (no focus move)
    if ((evt.key === " " || evt.code === "Space") && evt.shiftKey) {
      evt.preventDefault();
      tracksCursorIdx = pos; // keep cursor coherent with the row we just acted on
      if (anchorIdx === null) anchorIdx = focusedSrcIdx;
      extendRange(focusedSrcIdx);
      updateUI(); // announce — selectedSources range extended
      return;
    }

    // Ctrl/Cmd+A — select all
    if ((evt.metaKey || evt.ctrlKey) && evt.key.toLowerCase() === "a") {
      evt.preventDefault();
      selectedSources = new Set(displayOrder);
      selectedExcerpt = null;
      // Cmd/Ctrl+A pins all tracks. tracksCursorIdx is deliberately NOT reset —
      // the cursor row stays where the user last was, and since every source is
      // now pinned, the cursor's contribution is already in the visible set.
      updateUI(); // announce — selectedSources changed to all
      return;
    }
  });

  clearBtn.addEventListener("click", () => {
    selectedSources.clear();
    selectedExcerpt = null;
    anchorIdx = null;
    tracksCursorIdx = -1;
    setRovingTabindex(trackRowEls(), -1); // no cursor
    updateUI(); // announce — all state cleared
  });

  // --- Keyboard navigation on excerpts (roving tabindex) ---
  function excerptRows() {
    return Array.from(tableEl.querySelectorAll(".cv-row"));
  }

  function moveExcerptsCursor(newIdx) {
    const rows = excerptRows();
    if (rows.length === 0) return;
    const idx = Math.max(0, Math.min(newIdx, rows.length - 1));
    rows.forEach((r, i) => r.setAttribute("tabindex", i === idx ? "0" : "-1"));
    const target = rows[idx];
    target.focus();
    target.scrollIntoView({ block: "nearest" });
    excerptsCursorId = target.dataset.annId || null;

    // Update context bar with "Excerpt N of M in <source>"
    const srcIdx = parseInt(target.dataset.srcIdx, 10);
    const src = (data.sources || []).find((s) => s.idx === srcIdx);
    const srcName = (src && (src.name || src.display_id)) || `Source ${srcIdx}`;
    if (ctxEl) {
      ctxEl.innerHTML = `Excerpt <b>${idx + 1}</b> of <b>${rows.length}</b> in <b>${escapeHtml(srcName)}</b>`;
    }
  }

  function currentExcerptsCursorPos() {
    const rows = excerptRows();
    return rows.findIndex((r) => r.getAttribute("tabindex") === "0");
  }

  tableEl.addEventListener("keydown", (evt) => {
    // Only handle when the focused element is a .cv-row inside this table.
    const target = evt.target;
    if (!target || !target.classList || !target.classList.contains("cv-row")) return;

    const rows = excerptRows();
    if (rows.length === 0) return;
    const pos = currentExcerptsCursorPos();

    if (evt.key === "ArrowDown") {
      evt.preventDefault();
      moveExcerptsCursor(pos >= 0 ? pos + 1 : 0);
      return;
    }
    if (evt.key === "ArrowUp") {
      evt.preventDefault();
      moveExcerptsCursor(pos >= 0 ? pos - 1 : 0);
      return;
    }
    if (evt.key === "Home") {
      evt.preventDefault();
      moveExcerptsCursor(0);
      return;
    }
    if (evt.key === "End") {
      evt.preventDefault();
      moveExcerptsCursor(rows.length - 1);
      return;
    }
  });

  // --- Global key handlers (Esc two-stage + N exits-and-opens-notes) ---
  // Registered on the capturing phase with stopImmediatePropagation so the
  // page's bridge.js (which also handles N and Esc on the coding page) never
  // sees these events when we're on /code/{id}/view.
  document.addEventListener("keydown", (evt) => {
    // If the cheat sheet dialog is open, let native dialog handling take over
    // (Esc closes it natively; our Esc handler must not also navigate away).
    const _dlg = document.getElementById("cv-cheatsheet-dialog");
    if (_dlg && _dlg.open) return;

    // Don't hijack keys while the user is typing in any form control (filter,
    // sidebar search, etc). Special case: Esc in #cv-search clears the field
    // and blurs — other controls handle their own Esc via their own wiring.
    const searchEl = document.getElementById("cv-search");
    const tag = (evt.target.tagName || "").toLowerCase();
    const inFormControl =
      tag === "input" || tag === "textarea" || tag === "select" || evt.target.isContentEditable;
    if (inFormControl) {
      if (evt.target === searchEl && evt.key === "Escape") {
        evt.target.value = "";
        filterText = "";
        evt.target.blur();
        updateUI(); // announce — filter cleared, visible excerpts changed
        claim(evt);
      }
      return;
    }

    if (evt.key === "Escape") {
      if (filterText || selectedSources.size > 0 || selectedExcerpt || tracksCursorIdx >= 0) {
        filterText = "";
        selectedSources.clear();
        selectedExcerpt = null;
        anchorIdx = null;
        tracksCursorIdx = -1;
        setRovingTabindex(trackRowEls(), -1); // no cursor = overview
        if (searchEl) searchEl.value = "";
        updateUI(); // announce — all state cleared, back to overview
      } else {
        if (!confirmDiscardMetadataEdits()) {
          claim(evt);
          return;
        }
        window.location.href = "/code";
      }
      claim(evt);
      return;
    }

    if (evt.key === "n" || evt.key === "N") {
      if (!confirmDiscardMetadataEdits()) {
        claim(evt);
        return;
      }
      window.location.href = "/code?note=1";
      claim(evt);
      return;
    }
  }, true); // capture phase — wins over bridge.js

  // --- Sort chips ---
  const toolbarEl = document.getElementById("cv-toolbar");
  if (toolbarEl) {
    toolbarEl.querySelectorAll("[data-sort]").forEach((chip) => {
      chip.addEventListener("click", () => {
        toolbarEl.querySelectorAll("[data-sort]").forEach((c) =>
          c.setAttribute("aria-pressed", "false"));
        chip.setAttribute("aria-pressed", "true");
        sortBy = chip.getAttribute("data-sort");
        displayOrder = computeDisplayOrder();
        renderTracks();
        updateUI(); // announce — display order changed, visible excerpt set updated
      });
    });
  }

  // --- Text filter ---
  const searchEl = document.getElementById("cv-search");
  if (searchEl) {
    searchEl.addEventListener("input", (evt) => {
      filterText = evt.target.value.trim();
      updateUI(); // announce — filter changed, visible excerpt set updated
    });
  }

  // --- Code metadata editor ---
  populateCodeEditor();
  setCodeViewMode("review", { focusName: false, skipDirtyCheck: true });

  if (reviewModeBtn) {
    reviewModeBtn.addEventListener("click", () => {
      setCodeViewMode("review");
    });
  }
  if (editModeBtn) {
    editModeBtn.addEventListener("click", () => {
      setCodeViewMode("edit");
    });
  }
  if (editPanelEl) {
    editPanelEl.addEventListener("submit", (evt) => {
      evt.preventDefault();
    });
  }
  if (codeNameInput) {
    codeNameInput.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      claim(evt);
      submitCodeUpdate({ name: codeNameInput.value }, ["name"]);
    });
  }
  if (codeFolderSelect) {
    codeFolderSelect.addEventListener("change", () => {
      submitFolderUpdate(codeFolderSelect.value);
    });
  }
  if (codeDefinitionTextarea) {
    codeDefinitionTextarea.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter" || (!evt.metaKey && !evt.ctrlKey)) return;
      claim(evt);
      submitCodeUpdate({ definition: codeDefinitionTextarea.value }, ["definition"]);
    });
  }

  document.addEventListener("click", (evt) => {
    const backLink = evt.target?.closest?.(".cv-back");
    if (!backLink) return;
    if (!confirmDiscardMetadataEdits()) {
      claim(evt);
    }
  }, true);

  // --- Codebook sidebar wiring ---
  // The shared codebook partial is rendered here as well. Mark the currently-
  // viewed code; activation loads excerpts while editing stays shared with /code.
  (function initSidebar() {
    const currentId = data.code.id;
    setCurrentSidebarCode(currentId);
    const root = codebookTreeElement();
    if (root) {
      const observer = new MutationObserver(() => setCurrentSidebarCode(data.code.id));
      observer.observe(root, { childList: true, subtree: true });
    }

    document.addEventListener("click", (evt) => {
      const row = codebookCodeRowFromTarget(evt.target);
      if (!row) return;
      if (evt.target.closest(
        ".ace-context-menu, .ace-codebook-dropdown, .ace-ht-rename, .ace-ht-toggle, .ace-ht-chip, input, textarea, select, button, a"
      )) return;
      const id = codeIdFromCodebookRow(row);
      if (!id) return;
      if (id !== data.code.id && !confirmAndDiscardMetadataEdits()) return;
      selectCodebookRowById(id);
      if (id === data.code.id) return;   // already here, no-op
      loadCode(id, { pushHistory: true });
    });

    document.addEventListener("ace:view-code", (evt) => {
      const codeId = evt.detail && evt.detail.codeId;
      if (!codeId) return;
      if (codeId !== data.code.id && !confirmAndDiscardMetadataEdits()) return;
      selectCodebookRowById(codeId);
      if (codeId !== data.code.id) {
        loadCode(codeId, {
          pushHistory: evt.detail?.pushHistory !== false,
          viewTransition: evt.detail?.viewTransition !== false,
        });
      }
    });
  })();

  // --- Sidebar resize — shared ace-sidebar-width localStorage with /code ---
  // Port of bridge.js::_initResize, tailored to this page's container.
  (function initResize() {
    const handle = document.getElementById("cv-resize-handle");
    const container = document.getElementById("code-view");
    if (!handle || !container) return;
    let dragging = false;
    handle.addEventListener("pointerdown", (e) => {
      dragging = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    document.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const rect = container.getBoundingClientRect();
      let x = e.clientX - rect.left;
      const min = 150;
      const max = rect.width * 0.4;
      x = Math.max(min, Math.min(max, x));
      document.documentElement.style.setProperty("--ace-sidebar-width", `${x}px`);
    });
    document.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      const width = parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"),
        10,
      );
      if (width) localStorage.setItem("ace-sidebar-width", width);
    });
    handle.addEventListener("dblclick", () => {
      document.documentElement.style.setProperty("--ace-sidebar-width", "360px");
      localStorage.setItem("ace-sidebar-width", 360);
      clampToViewport();
    });

    // Re-clamp on viewport resize (mirrors the drag's cap) so a width saved on
    // a large monitor doesn't crush the text here either. Re-derives from the
    // saved value; runs once to refine the pre-CSS restore.
    function clampToViewport() {
      if (dragging) return;
      const vw = document.documentElement.clientWidth;
      const splitW = container.getBoundingClientRect().width;
      if (!vw || !splitW) return;
      const saved = parseInt(localStorage.getItem("ace-sidebar-width") || "360", 10) || 360;
      const px = Math.max(150, Math.min(saved, Math.min(vw, splitW) * 0.4));
      document.documentElement.style.setProperty("--ace-sidebar-width", px + "px");
    }
    window.addEventListener("resize", clampToViewport);
    clampToViewport();
  })();

  renderForData(data);
  if (liveEl) {
    announce(ctxEl.textContent.replace(/\s+/g, " ").trim());
  }

  // Restore codebook focus after an auto-navigate reload so holding ↑/↓
  // continues the codebook scroll seamlessly across page loads.
  const CODEBOOK_FOCUS_RESTORE_KEY = "cv-restore-codebook-focus";
  try {
    if (sessionStorage.getItem(CODEBOOK_FOCUS_RESTORE_KEY) === "1") {
      sessionStorage.removeItem(CODEBOOK_FOCUS_RESTORE_KEY);
      const currentRow = sidebarCodeRows().find(
        (row) => row.getAttribute("aria-current") === "page",
      );
      if (currentRow) {
        sidebarCodeRows().forEach((r) => r.setAttribute("tabindex", "-1"));
        currentRow.setAttribute("tabindex", "0");
        currentRow.focus({ preventScroll: true });
        currentRow.scrollIntoView({ block: "nearest" });
      }
    }
  } catch (_) {}

  // --- Codebook keyboard navigation -------------------------------------
  // `/` focuses search; ↑/↓/Home/End on code rows move the roving tabindex;
  // Enter navigates; search handles ↓/↑/Esc.

  const treeEl = codebookTreeElement();
  const codeSearchInput = document.getElementById("code-search-input");
  let previousFocusBeforeSearch = null;

  function visibleCodeRows() {
    if (!treeEl) return [];
    const all = Array.from(treeEl.querySelectorAll(CODEBOOK_CODE_ROW_SELECTOR));
    return all.filter((row) => {
      if (row.hidden || row.style.display === "none" || row.getAttribute("aria-hidden") === "true") {
        return false;
      }
      return true;
    });
  }

  function moveCodebookCursor(targetRow) {
    const rows = visibleCodeRows();
    rows.forEach((r) => r.setAttribute("tabindex", "-1"));
    if (!targetRow) return;
    targetRow.setAttribute("tabindex", "0");
    targetRow.focus();
    targetRow.scrollIntoView({ block: "nearest" });
  }

  function selectCodebookRowById(codeId) {
    const row = sidebarCodeRows().find((candidate) => codeIdFromCodebookRow(candidate) === codeId);
    if (!row) return;
    moveCodebookCursor(row);
    rememberedCursor.codebook = codeId;
  }

  const navAbort = { ctl: null };

  async function loadCode(codeId, opts) {
    opts = opts || {};
    const pushHistory = opts.pushHistory !== false;
    const forceReload = opts.forceReload === true;
    if (!codeId || (!forceReload && codeId === data.code.id)) return { cancelled: false };
    if (!forceReload && !confirmAndDiscardMetadataEdits()) return { cancelled: true };
    if (navAbort.ctl) navAbort.ctl.abort();
    navAbort.ctl = new AbortController();
    let json;
    try {
      const cached = dataCache.get(codeId);
      if (cached) {
        json = await cached;
        if (json === null) {
          dataCache.delete(codeId);
        } else {
          _cacheTouch(codeId);
        }
      }
      if (!json) {
        const res = await fetch(`/api/code/${codeId}/view-data`,
                                { signal: navAbort.ctl.signal });
        if (!res.ok) throw new Error(`status ${res.status}`);
        json = await res.json();
        dataCache.set(codeId, Promise.resolve(json));
        _cacheEvictIfFull();
      }
    } catch (e) {
      if (e && e.name === "AbortError") return { cancelled: false };
      // Fallback: full navigate so something still works on fetch failure.
      window.location.href = `/code/${codeId}/view`;
      return { cancelled: false };
    }
    const useViewTransition = opts.viewTransition !== false;
    if (useViewTransition && typeof document.startViewTransition === "function") {
      document.startViewTransition(() => renderForData(json));
    } else {
      renderForData(json);
    }
    if (pushHistory) {
      history.pushState({ codeId }, "", `/code/${codeId}/view`);
    } else {
      history.replaceState({ codeId }, "", `/code/${codeId}/view`);
    }
    return { cancelled: false };
  }

  const dataCache = new Map(); // codeId -> Promise<data | null>
  const DATA_CACHE_MAX = 8;

  function _cacheTouch(codeId) {
    // Move to most-recent position by re-inserting. Map preserves insertion order
    // so the oldest entry is keys().next().value.
    if (dataCache.has(codeId)) {
      const v = dataCache.get(codeId);
      dataCache.delete(codeId);
      dataCache.set(codeId, v);
    }
  }

  function _cacheEvictIfFull() {
    while (dataCache.size > DATA_CACHE_MAX) {
      const oldest = dataCache.keys().next().value;
      dataCache.delete(oldest);
    }
  }

  function prefetch(codeId) {
    if (!codeId || codeId === data.code.id) return;
    if (dataCache.has(codeId)) { _cacheTouch(codeId); return; }
    const p = fetch(`/api/code/${codeId}/view-data`)
      .then((r) => r.ok ? r.json() : null)
      .catch(() => null)
      .then((j) => {
        if (j === null) dataCache.delete(codeId);
        return j;
      });
    dataCache.set(codeId, p);
    _cacheEvictIfFull();
  }

  function requestAuditUndo(redo) {
    const currentCodeId = data?.code?.id || "";
    window.htmx?.ajax?.("POST", redo ? "/api/redo" : "/api/undo", {
      target: "#code-sidebar",
      swap: "none",
      values: {
        codebook_mode: "audit",
        current_code_id: currentCodeId,
      },
    });
  }

  document.addEventListener("ace:codebook-mutated", (evt) => {
    const detail = evt.detail || {};
    if (detail.mode !== "audit") return;

    const affectedCodeIds = Array.isArray(detail.affectedCodeIds)
      ? detail.affectedCodeIds.filter(Boolean)
      : [];
    if (detail.folderListChanged === true) {
      dataCache.clear();
    } else if (affectedCodeIds.length > 0) {
      affectedCodeIds.forEach((codeId) => dataCache.delete(codeId));
    } else {
      dataCache.clear();
    }

    if (detail.fallbackCodeId) {
      loadCode(detail.fallbackCodeId, { pushHistory: false, viewTransition: false });
      return;
    }

    const currentCodeId = data && data.code ? data.code.id : null;
    const hasExplicitAuditReload = Object.prototype.hasOwnProperty.call(detail, "auditReload");
    const currentWasDeleted =
      !!currentCodeId
      && (
        detail.operation === "delete"
        || (
          detail.auditReload === false
          && detail.folderListChanged === true
          && !detail.fallbackCodeId
        )
      )
      && affectedCodeIds.includes(currentCodeId);
    if (currentWasDeleted) {
      setCurrentSidebarCode("");
      dataCache.delete(currentCodeId);
      window.location.href = "/code";
      return;
    }
    const shouldReloadCurrent =
      !!currentCodeId
      && (
        detail.auditReload === true
        || (
          !hasExplicitAuditReload
          && detail.operation !== "delete"
          && affectedCodeIds.includes(currentCodeId)
        )
      );
    if (shouldReloadCurrent) {
      preserveDirtyMetadataDraftForReload();
      dataCache.delete(currentCodeId);
      loadCode(currentCodeId, {
        pushHistory: false,
        viewTransition: false,
        forceReload: true,
      });
      return;
    }

    if (currentCodeId) {
      setCurrentSidebarCode(currentCodeId);
    }
  });

  document.addEventListener("click", (evt) => {
    const undoButton = evt.target?.closest?.(".ace-statusbar-undo[data-ace-undo-affordance]");
    if (!undoButton) return;
    claim(evt);
    requestAuditUndo(false);
  }, true);

  // Document-level `/` → focus codebook search.
  // Registered at capture phase, matching the existing code_view.js convention.
  document.addEventListener("keydown", (evt) => {
    if (evt.key === "/") {
      if (evt.ctrlKey || evt.metaKey || evt.altKey) return;
      if (isEditableElement(document.activeElement)) return;
      if (!codeSearchInput) return;
      evt.preventDefault();
      previousFocusBeforeSearch =
        document.activeElement && document.activeElement.isConnected
          ? document.activeElement
          : null;
      codeSearchInput.focus();
      codeSearchInput.select();
      return;
    }

    // ? → open cheat sheet
    if (evt.key === "?"
        && !evt.ctrlKey && !evt.metaKey && !evt.altKey) {
      // evt.shiftKey is TRUE for "?" on US layouts — don't reject it
      if (isEditableElement(document.activeElement)) return;
      const dlg = document.getElementById("cv-cheatsheet-dialog");
      if (!dlg || typeof dlg.showModal !== "function") return;
      claim(evt);
      // Guard against re-open: showModal() throws InvalidStateError if the
      // dialog is already open, which would break subsequent keyboard handling.
      if (dlg.open) return;
      dlg.__opener = document.activeElement;
      dlg.showModal();
      return;
    }

    // Shift+← / Shift+→ → move tracks cursor (works from any zone)
    if (evt.shiftKey && !evt.ctrlKey && !evt.metaKey && !evt.altKey
        && (evt.key === "ArrowLeft" || evt.key === "ArrowRight")) {
      if (isEditableElement(document.activeElement)) return;
      const rows = trackRowEls();
      if (rows.length === 0) return;
      const dir = (evt.key === "ArrowRight") ? 1 : -1;
      const base = tracksCursorIdx >= 0 ? tracksCursorIdx : 0;
      const target = Math.max(0, Math.min(rows.length - 1, base + dir));
      evt.preventDefault();
      moveFocus(target, { announce: false });
      return;
    }

    // ← / → → move between columns: codebook → tracks → excerpts (no wrap).
    // Skipped inside form controls so plain ←/→ remains text-cursor movement.
    // Entering excerpts triggers a full reset (clears pinned tracks, search
    // filter, selected excerpt, cursor returns to row 0).
    if (!evt.shiftKey && !evt.ctrlKey && !evt.metaKey && !evt.altKey
        && (evt.key === "ArrowLeft" || evt.key === "ArrowRight")) {
      if (isEditableElement(document.activeElement)) return;
      const zone = currentZone();
      const ZONES_LR = ["codebook", "tracks", "excerpts"];
      const idx = ZONES_LR.indexOf(zone);
      if (idx < 0) {
        // Fresh page entry — no zone has focus yet. Treat the arrow as the
        // entry direction: ← lands in the codebook (leftmost), → lands in
        // the tracks list (natural starting point for browsing sources).
        claim(evt);
        focusZone(evt.key === "ArrowLeft" ? "codebook" : "tracks");
        return;
      }
      const nextIdx = idx + (evt.key === "ArrowRight" ? 1 : -1);
      if (nextIdx < 0 || nextIdx >= ZONES_LR.length) return;
      claim(evt);
      if (ZONES_LR[nextIdx] === "excerpts") {
        // Full reset on entry: matches Clear-button behaviour plus clearing
        // the search filter. The tracksCursorIdx + tabindex reset is critical
        // — without it updateUI()'s context bar still filters by the cursor
        // (see the `selectedSources.size === 0 && tracksCursorIdx < 0` branch).
        selectedSources.clear();
        selectedExcerpt = null;
        anchorIdx = null;
        tracksCursorIdx = -1;
        setRovingTabindex(trackRowEls(), -1);
        filterText = "";
        const cvSearch = document.getElementById("cv-search");
        if (cvSearch) cvSearch.value = "";
        rememberedCursor.excerpts = null;
        updateUI({ announce: false });
      }
      focusZone(ZONES_LR[nextIdx]);
      return;
    }

    // V → exit back to coding. stopImmediatePropagation (via claim) is required
    // because bridge.js has its own V handler at document level
    // that navigates to /code/<id>/view; without claim it would re-enter this
    // page instead of exiting.
    if ((evt.key === "v" || evt.key === "V")
        && !evt.ctrlKey && !evt.metaKey && !evt.altKey && !evt.shiftKey) {
      if (isEditableElement(document.activeElement)) return;
      claim(evt);
      if (!confirmDiscardMetadataEdits()) return;
      window.location.href = "/code";
      return;
    }

    // Z / Shift+Z — audit-safe undo / redo. Editable fields keep native undo.
    if ((evt.key === "z" || evt.key === "Z")
        && !evt.ctrlKey && !evt.metaKey && !evt.altKey) {
      if (isEditableElement(document.activeElement)) return;
      claim(evt);
      requestAuditUndo(evt.shiftKey);
      return;
    }

    // q, x → reserved on this page (explicit no-op)
    if ((evt.key === "q" || evt.key === "Q"
         || evt.key === "x" || evt.key === "X")
        && !evt.ctrlKey && !evt.metaKey && !evt.altKey && !evt.shiftKey) {
      if (isEditableElement(document.activeElement)) return;
      evt.preventDefault();
      return;
    }

    // T6: ↓ from body focus → enter tracks. Zone handlers own ↓ when focus is
    // already inside a zone, so we only act when currentZone() is null.
    if (evt.key === "ArrowDown"
        && !evt.ctrlKey && !evt.metaKey && !evt.altKey && !evt.shiftKey) {
      if (isEditableElement(document.activeElement)) return;
      if (currentZone() !== null) return;
      evt.preventDefault();
      focusTracksZone();
      return;
    }
  }, true); // capture phase — matches existing code_view.js convention

  // Keydown on the code tree is owned by the shared codebook controller.
  if (treeEl) {
    treeEl.addEventListener("focusin", (evt) => {
      const row = evt.target.closest && evt.target.closest(CODEBOOK_CODE_ROW_SELECTOR);
      const codeId = codeIdFromCodebookRow(row);
      if (codeId) prefetch(codeId);
    }, true);
  }

  // Keydown on the codebook search input: ↓/↑/Esc.
  // Registered at capture phase so Esc (when search has content) fires before
  // the document-level Esc handler (which navigates to /code on second Esc).
  // stopImmediatePropagation is only called when we're actually clearing the
  // search — an empty-search Esc falls through to the existing doc handler.
  if (codeSearchInput) {
    codeSearchInput.addEventListener("keydown", (evt) => {
      if (evt.key === "Escape" && codeSearchInput.value.length > 0) {
        claim(evt);
        codeSearchInput.value = "";
        // Trigger existing filter logic (input listener in _sidebar_codebook.html)
        codeSearchInput.dispatchEvent(new Event("input", { bubbles: true }));
        if (previousFocusBeforeSearch && previousFocusBeforeSearch.isConnected) {
          previousFocusBeforeSearch.focus();
          previousFocusBeforeSearch = null;
        } else {
          codeSearchInput.blur();
        }
        return;
      }
    }, true); // capture phase — stopImmediatePropagation blocks bridge.js handlers
  }

  // --- Zone focus helpers (used by ←/→ zone-shift) ---------------------

  function currentZone() {
    const a = document.activeElement;
    if (!a || a === document.body || a === document.documentElement) return null;
    if (a.classList && a.classList.contains("cv-back")) return "back";
    if (a.id === "code-search-input") return "codebook"; // search is "in" codebook
    if (a.closest && a.closest("#cv-tracks")) return "tracks";
    if (a.closest && a.closest("#cv-table")) return "excerpts";
    if (a.closest && a.closest("#code-sidebar")) return "codebook";
    return null;
  }

  function focusTracksZone() {
    const rows = trackRowEls();
    if (rows.length === 0) return;
    let targetIdx = 0;
    if (rememberedCursor.tracks != null && rememberedCursor.tracks < rows.length) {
      targetIdx = rememberedCursor.tracks;
    } else if (tracksCursorIdx >= 0 && tracksCursorIdx < rows.length) {
      targetIdx = tracksCursorIdx;
    }
    // moveFocus sets tabindex, focuses, scrolls, updates tracksCursorIdx, and
    // calls updateUI. Use silent mode — Tab doesn't need to announce.
    moveFocus(targetIdx, { announce: false });
  }

  function focusExcerptsZone() {
    const rows = excerptRows();
    if (rows.length === 0) return;
    let target = null;
    if (rememberedCursor.excerpts != null) {
      target = tableEl.querySelector(
        `.cv-row[data-ann-id="${CSS.escape(rememberedCursor.excerpts)}"]`,
      );
    }
    if (!target) target = rows[0];
    moveExcerptsCursor(rows.indexOf(target));
  }

  function focusCodebookZone() {
    const rows = visibleCodeRows();
    if (rows.length === 0) return;
    let target = null;
    if (rememberedCursor.codebook != null) {
      target = rows.find((r) => codeIdFromCodebookRow(r) === rememberedCursor.codebook) || null;
    }
    if (!target) {
      // Fall back to the currently-viewed code (has aria-current="page")
      target = rows.find((r) => r.getAttribute("aria-current") === "page") || rows[0];
    }
    moveCodebookCursor(target);
    updateUI({ announce: false });
  }

  function focusBackLink() {
    const back = document.querySelector(".cv-back");
    if (back) {
      back.focus();
      back.scrollIntoView({ block: "nearest" });
    }
    updateUI({ announce: false });
  }

  function focusZone(name) {
    if (name === "tracks")   return focusTracksZone();
    if (name === "excerpts") return focusExcerptsZone();
    if (name === "codebook") return focusCodebookZone();
    if (name === "back")     return focusBackLink();
  }

  // focusout listener to save remembered cursors (capture phase)
  document.addEventListener("focusout", (evt) => {
    const a = evt.target;
    if (!a || !a.classList) return;
    if (a.classList.contains("cv-track-row")) {
      const idx = trackRowEls().indexOf(a);
      if (idx >= 0) rememberedCursor.tracks = idx;
    } else if (a.classList.contains("cv-row")) {
      if (a.dataset.annId) rememberedCursor.excerpts = a.dataset.annId;
    } else if (isCodebookCodeRow(a)) {
      const codeId = codeIdFromCodebookRow(a);
      if (codeId) rememberedCursor.codebook = codeId;
    }
    // back link has no remembered state — not a roving zone
  }, true); // capture phase

  // --- Back/forward navigation ---
  window.addEventListener("popstate", () => {
    const m = location.pathname.match(/^\/code\/([^/]+)\/view\/?$/);
    if (m && m[1] !== data.code.id) {
      loadCode(m[1], { pushHistory: false }).then((result) => {
        if (result?.cancelled) {
          history.replaceState({ codeId: data.code.id }, "", `/code/${data.code.id}/view`);
        }
      });
    }
  });

  // --- Cheat sheet dialog close + focus restoration ---

  const cheatDlg = document.getElementById("cv-cheatsheet-dialog");
  const cheatCloseBtn = document.getElementById("cv-cheatsheet-close-btn");
  if (cheatCloseBtn && cheatDlg) {
    cheatCloseBtn.addEventListener("click", () => cheatDlg.close());
  }
  if (cheatDlg) {
    cheatDlg.addEventListener("close", () => {
      const opener = cheatDlg.__opener;
      if (opener && opener.isConnected && typeof opener.focus === "function") {
        opener.focus();
      }
      cheatDlg.__opener = null;
    });
  }
})();
