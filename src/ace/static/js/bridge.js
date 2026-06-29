/**
 * ACE Bridge — client-side utilities for the coding page.
 *
 * Sections:
 *  2. Sentence navigation (↑/↓ focus)
 *  3. Group collapse / expand
 *  4. Keymap (dynamic keycap assignment)
 *  5. Apply code (sentence-based + custom selection)
 *  6. Keyboard shortcuts
 *  7. Navigation (prev/next source)
 *  8. Cheat sheet overlay
 *  9. Resize handle
 * 10. Source grid overlay
 * 11. Dialog close cleanup
 * 12. HTMX integration (configRequest, afterSwap, afterRequest)
 * 13. Code management helpers
 * 14. Code menu dropdown (with shortcut hints)
 * 15. Code search / filter / create / group
 * 16. SVG overlay — annotation rendering
 * 17. Sidebar keyboard navigation (ARIA treeview)
 * 18. Codebook menu
 * 19. Import form column-role assignment (delegated)
 * 20. DOMContentLoaded init
 * 21. Source note drawer (READ / EDIT / closed)
 * 22. Source-grid collapse toggle
 */

(function () {
  "use strict";

  function _escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* ================================================================
   * 1b. Active-zone tracking — flips body[data-active-zone] between
   *     "source" (text panel + scroll wrapper) and "codebook" (sidebar).
   *     Used by CSS (e.g. dim highlights when codebook is active) and by
   *     the Esc-to-source handler. Installed early so it runs on /code,
   *     /code/{id}/view, and any other page sharing bridge.js.
   * ================================================================ */

  function _setActiveZone(zone) {
    if (document.body.dataset.activeZone === zone) return;
    document.body.dataset.activeZone = zone;
  }

  function _codebookEditingDisabled() {
    return document.querySelector("#ace-headless-tree-mount[data-codebook-readonly='1']") !== null;
  }

  function _codeApplicationDisabled() {
    return !!document.getElementById("code-view") || !document.getElementById("text-panel");
  }

  function _codebookMutationSwapOptions() {
    if (document.getElementById("text-panel")) {
      return { target: "#text-panel", swap: "outerHTML" };
    }
    return { target: "#code-sidebar", swap: "none" };
  }

  function _codebookMutationContext() {
    const mount = document.getElementById("ace-headless-tree-mount");
    const codeView = document.getElementById("code-view");
    return {
      mode: mount?.dataset?.codebookMode || "coding",
      currentCodeId: codeView?.dataset?.codeId || "",
    };
  }

  function _codebookMutationValues(values) {
    const next = { ...(values || {}) };
    const ctx = _codebookMutationContext();
    if (ctx.mode !== "coding") next.codebook_mode = ctx.mode;
    if (ctx.currentCodeId && !next.current_code_id) {
      next.current_code_id = ctx.currentCodeId;
    }
    return next;
  }

  function _codebookMutationQueryString(values) {
    const params = new URLSearchParams();
    Object.entries(_codebookMutationValues(values)).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      params.set(key, value);
    });
    return params.toString();
  }

  function _denyCodebookEditing() {
    if (!_codebookEditingDisabled()) return false;
    if (typeof window._setStatus === "function") {
      window._setStatus("Back to source to edit the codebook", "ok");
    }
    return true;
  }

  document.addEventListener("focusin", function (e) {
    const t = e.target;
    if (!t || !t.closest) return;
    if (t.closest("#code-sidebar")) {
      _setActiveZone("codebook");
      // First Tab from the source panel into the codebook — show the hint
      // once per browser. Gated on relatedTarget being inside #text-panel
      // so a mouse click into the sidebar (or a focus arriving from a
      // dialog/statusbar) doesn't burn the one-shot. Persists in
      // localStorage so power users don't see it again. Skipped on
      // /code/{id}/view (audit page) where the hint is moot.
      const fromTextPanel = e.relatedTarget && e.relatedTarget.closest
        && e.relatedTarget.closest("#text-panel");
      if (fromTextPanel
          && !localStorage.getItem("ace-tab-hint-seen")
          && document.getElementById("text-panel")
          && typeof window._setStatus === "function") {
        window._setStatus(
          "Tab moves between panels · ⌥→ to move into a folder",
          "ok",
        );
        localStorage.setItem("ace-tab-hint-seen", "1");
      }
    } else if (t.closest("#ace-right-inspector")) {
      _setActiveZone("applied");
    } else if (t.closest("#text-panel, #text-scroll, #content-scroll")) {
      _setActiveZone("source");
    }
    // Other targets (body, dialogs, statusbar) — leave the current zone.
  });

  // Default zone on first paint. bridge.js loads at end of <body>, so the
  // DOM is parsed and we can read body. The focusin listener will flip it
  // as soon as the user clicks/Tabs into a zone.
  _setActiveZone("source");

  // Mark platform so CSS can swap modifier-key glyphs (⌘ on macOS, Ctrl
  // elsewhere). Used by .ace-hint-meta in the search-input hint line.
  // Detection via navigator.userAgentData.platform (modern) with a
  // navigator.platform fallback for browsers that don't expose the new API.
  (function () {
    const p =
      (navigator.userAgentData && navigator.userAgentData.platform) ||
      navigator.platform || "";
    document.body.dataset.platform = /mac/i.test(p) ? "mac" : "other";
  })();

  /* ================================================================
   * 2. Sentence navigation
   * ================================================================ */

  function _getSentences() {
    return document.querySelectorAll(".ace-sentence");
  }

  function _focusSentence(idx) {
    const sentences = _getSentences();
    if (idx < 0 || idx >= sentences.length) return;

    // Remove old focus
    const old = document.querySelector(".ace-sentence--focused");
    if (old) old.classList.remove("ace-sentence--focused");

    // Set new focus
    window.__aceFocusIndex = idx;
    let el = sentences[idx];
    el.classList.add("ace-sentence--focused");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    _scheduleCodeCues();
  }

  function _restoreFocus() {
    // Delay until after HTMX settling completes (outerHTML swap replaces DOM)
    requestAnimationFrame(function () {
      // Don't steal focus from the note drawer textarea during autosave —
      // the save response swaps #text-panel but the textarea lives outside it.
      if (document.activeElement && document.activeElement.id === "note-textarea") return;
      const idx = window.__aceFocusIndex;
      if (idx >= 0) _focusSentence(idx);
      _focusTextPanel();
    });
  }

  window.aceGetSentences = _getSentences;
  window.aceFocusSentence = _focusSentence;

  /* ================================================================
   * 3. Folder collapse / expand
   * ================================================================ */

  function _getSidebarTreeController() {
    const headlessMount = document.getElementById("ace-headless-tree-mount");
    if (!headlessMount) return null;
    const headless = window.AceHeadlessTreePreview &&
      typeof window.AceHeadlessTreePreview.getController === "function"
        ? window.AceHeadlessTreePreview.getController()
        : window.__aceHeadlessTreeController;
    if (headless && typeof headless.refresh === "function") {
      return headless.refresh();
    }
    return null;
  }

  function _refreshSidebarTreeController() {
    const controller = _getSidebarTreeController();
    if (controller && typeof controller.restoreCollapseState === "function") {
      controller.restoreCollapseState();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    _refreshSidebarTreeController();
    _syncAppliedCollapseA11y();
  });

  const APPLIED_COLLAPSED_KEY = "ace-applied-codes-collapsed";

  function _isNoteDrawerOpenDom() {
    return document.documentElement.dataset.aceNoteOpen === "1";
  }

  function _isAppliedCollapsed() {
    return document.documentElement.dataset.aceAppliedCodesCollapsed === "1";
  }

  function _syncAppliedCollapseA11y() {
    const collapsed = _isAppliedCollapsed();
    const noteOpen = _isNoteDrawerOpenDom();
    const panel = document.getElementById("ace-applied-codes-panel");
    const rail = document.getElementById("ace-applied-codes-rail");
    const expandedToggle = document.querySelector(".ace-applied-codes-toggle");
    const railToggle = document.querySelector(".ace-applied-rail-toggle");

    if (panel) {
      panel.toggleAttribute("inert", collapsed || noteOpen);
      panel.setAttribute("aria-hidden", collapsed || noteOpen ? "true" : "false");
    }
    if (rail) {
      rail.toggleAttribute("inert", !collapsed || noteOpen);
      rail.setAttribute("aria-hidden", collapsed && !noteOpen ? "false" : "true");
    }
    if (expandedToggle) expandedToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (railToggle) railToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }

  function _focusAppliedEntry() {
    if (_isNoteDrawerOpenDom()) return false;
    _syncAppliedCollapseA11y();
    if (_isAppliedCollapsed()) {
      const railToggle = document.querySelector(".ace-applied-rail-toggle");
      if (railToggle) {
        railToggle.focus();
        return true;
      }
      return false;
    }
    const firstRow = document.querySelector(".ace-applied-code-row");
    if (firstRow) {
      firstRow.focus();
      return true;
    }
    const expandedToggle = document.querySelector(".ace-applied-codes-toggle");
    if (expandedToggle) {
      expandedToggle.focus();
      return true;
    }
    return false;
  }

  function _setAppliedCollapsed(collapsed, opts) {
    if (collapsed) {
      document.documentElement.dataset.aceAppliedCodesCollapsed = "1";
      try { localStorage.setItem(APPLIED_COLLAPSED_KEY, "1"); } catch (_) {}
    } else {
      delete document.documentElement.dataset.aceAppliedCodesCollapsed;
      try { localStorage.removeItem(APPLIED_COLLAPSED_KEY); } catch (_) {}
    }
    _syncAppliedCollapseA11y();
    if (opts && opts.focus) _focusAppliedEntry();
  }

  function _toggleAppliedCollapsedShortcut() {
    _setAppliedCollapsed(!_isAppliedCollapsed(), { focus: true });
  }

  window.aceIsAppliedCollapsed = _isAppliedCollapsed;
  window.aceSetAppliedCollapsed = _setAppliedCollapsed;
  window.aceFocusAppliedEntry = _focusAppliedEntry;
  window.aceToggleAppliedCollapsed = _toggleAppliedCollapsedShortcut;

  function _toggleFolderCollapse(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.toggleFolderCollapse(folderRow);
    }
  }

  function _restoreCollapseState() {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.restoreCollapseState();
    }
  }

  // Click handler for folder rows — toggle on the chevron, focus on label.
  document.addEventListener("click", function (e) {
    const toggle = e.target.closest(".ace-folder-toggle");
    if (toggle) {
      const row = toggle.closest(".ace-code-folder-row");
      if (row) {
        _focusTreeItem(row);
        _toggleFolderCollapse(row);
        const labelEl = row.querySelector(".ace-folder-label");
        const name = labelEl ? labelEl.textContent.trim() : "folder";
        const expanded = row.getAttribute("aria-expanded") === "true";
        _announce(`${name}${expanded ? " expanded" : " collapsed"}`);
      }
      return;
    }
    // Click on the label or row (not chevron) — just focus the row
    const row = e.target.closest(".ace-code-folder-row");
    if (row && !e.target.closest(".ace-code-menu")) {
      _focusTreeItem(row);
    }
  });

  // Folder rename: F2 or double-click on a folder label enters inline
  // edit on the .ace-folder-label. Folders share the PUT /api/codes/{id}
  // route with codes.

  // Nav: flag toggle button (delegated — survives OOB swaps)
  let _pendingFlagAnnounce = false;
  document.addEventListener("click", function (e) {
    if (e.target.closest("#nav-flag-btn")) {
      _updateCurrentIndex();
      _pendingFlagAnnounce = true;
      const triggerFlag = document.getElementById("trigger-flag");
      if (triggerFlag) htmx.trigger(triggerFlag, "click");
    }
  });

  /* ================================================================
   * 4. Keymap — dynamic keycap assignment per tab
   * ================================================================ */

  let _currentKeyMap = []; // array of code IDs in keycap order

  function _keymapRoot() {
    return document.getElementById("ace-headless-tree-mount");
  }

  function _updateKeycaps() {
    const tree = _keymapRoot();
    if (!tree) return;
    const rows = tree.querySelectorAll(".ace-ht-row--code[data-code-id]");
    _currentKeyMap = [];
    if (_codeApplicationDisabled()) {
      rows.forEach(function (row) {
        row.removeAttribute("aria-keyshortcuts");
        const keycap = row.querySelector(".ace-ht-chip");
        if (keycap) {
          keycap.textContent = "";
          keycap.removeAttribute("title");
        }
      });
      return;
    }
    let labelIdx = 0; // Counter that only increments for non-chord rows
    rows.forEach(function (row) {
      // Also skip rows hidden by search filter
      if (row.hidden || row.style.display === "none") return;

      if (row.dataset.chord) {
        // Chord row — has a chord cap rendered server-side. Don't include in
        // the single-key map (else hotkey index would target the wrong row if
        // a chord code is reordered into the first 31 positions).
        // aria-keyshortcuts is intentionally omitted — its spec uses spaces for ALTERNATIVES,
        // not key sequences, so "; xy" would announce as "either ; or xy". The chord cap's
        // title attribute ("Press ; then xy to apply") carries the accessible hint instead.
        return;
      }

      _currentKeyMap.push(row.getAttribute("data-code-id"));

      const label = _keylabel(labelIdx);
      const keycap = row.querySelector(".ace-ht-chip:not(.ace-ht-chip--chord)");
      if (keycap) keycap.textContent = label;
      row.setAttribute("aria-keyshortcuts", label);
      labelIdx++;
    });
  }

  // Reserved letters: q (repeat), x (delete), z (undo), n (open note panel),
  //                   v (open coded text view)
  const _KEYCAP_LABELS = [
    "1","2","3","4","5","6","7","8","9","0",
    "a","b","c","d","e","f","g","h","i","j","k","l","m","o","p",
    "r","s","t","u","w","y"
  ];

  function _keylabel(i) {
    return i < _KEYCAP_LABELS.length ? _KEYCAP_LABELS[i] : "";
  }

  const _KEYCAP_POSITIONS = {};
  _KEYCAP_LABELS.forEach(function (label, i) { _KEYCAP_POSITIONS[label] = i; });

  function _keyToPosition(key) {
    const k = key.toLowerCase();
    const pos = _KEYCAP_POSITIONS[k];
    return pos !== undefined ? pos : -1;
  }

  /* ================================================================
   * Chord-key state machine — `;` enters chord mode; two letters
   * resolve to a matching .ace-code-row[data-chord]; Esc cancels.
   * ================================================================ */

  let _chordMode = null;        // null | "awaiting"
  window.aceIsChordAwaiting = function () { return _chordMode === "awaiting"; };
  let _chordBuffer = "";

  function _setChordCodebookFilter(active) {
    const controller = window.__aceHeadlessTreeController ||
      window.AceHeadlessTreePreview?.getController?.();
    if (controller && typeof controller.setChordFilter === "function") {
      controller.setChordFilter(!!active);
    }
  }

  function _enterChordMode() {
    _chordMode = "awaiting";
    _chordBuffer = "";
    document.body.dataset.chordMode = "awaiting";
    _setChordCodebookFilter(true);
    _setStatus("Two-key shortcut: ;__ · type two letters", "ok-sticky");
  }

  function _exitChordMode() {
    _chordMode = null;
    _chordBuffer = "";
    _setChordCodebookFilter(false);
    delete document.body.dataset.chordMode;
    delete document.body.dataset.chordBuffer;
    document.querySelectorAll(".ace-chord-match").forEach(function (el) {
      el.classList.remove("ace-chord-match");
    });
  }

  function _onChordBufferChange() {
    if (_chordBuffer.length === 1) {
      document.body.dataset.chordBuffer = _chordBuffer;
      let matches = 0;
      const tree = _keymapRoot();
      if (tree) {
        tree.querySelectorAll(".ace-ht-chip--chord").forEach(function (cap) {
          const row = cap.closest(".ace-ht-row--code");
          const chord = row && row.dataset.chord;
          const isMatch = !!(chord && chord.startsWith(_chordBuffer));
          if (isMatch) matches++;
          cap.classList.toggle("ace-chord-match", isMatch);
        });
      }
      _setStatus(
        "Two-key shortcut: ;" + _chordBuffer + "_ · " +
          matches + " " + (matches === 1 ? "match" : "matches"),
        "ok-sticky"
      );
    }
  }

  function _resolveChord(chord) {
    const tree = _keymapRoot();
    if (tree) {
      const row = tree.querySelector(`.ace-ht-row--code[data-chord="${chord}"]`);
      if (row) {
        const codeId = row.getAttribute("data-code-id");
        if (codeId) {
          _applyCode(codeId);
          _exitChordMode();
          return;
        }
      }
    }
    _exitChordMode();
    _setStatus("No code for ;" + chord, "err");
  }

  document.addEventListener("keydown", function (evt) {
    if (!document.getElementById("text-panel")) return;
    if (evt.target.matches("input, textarea, [contenteditable='true']")) return;
    if (evt.metaKey || evt.ctrlKey || evt.altKey) return;

    if (_chordMode === "awaiting") {
      if (evt.key === "Escape") {
        evt.preventDefault();
        evt.stopImmediatePropagation();
        _exitChordMode();
        return;
      }
      if (evt.key === ";") {
        evt.preventDefault();
        evt.stopImmediatePropagation();
        _exitChordMode();
        return;
      }
      if (/^[a-z]$/.test(evt.key)) {
        evt.preventDefault();
        evt.stopImmediatePropagation();
        _chordBuffer += evt.key;
        _onChordBufferChange();
        if (_chordBuffer.length === 2) {
          _resolveChord(_chordBuffer);
        }
        return;
      }
      // Fallthrough: any other key cancels chord mode without applying.
      // Suppress so the canceling key doesn't ALSO fire its normal handler
      // (e.g. `;1` shouldn't both cancel chord and apply code 1).
      evt.preventDefault();
      evt.stopImmediatePropagation();
      _exitChordMode();
      return;
    }

    if (evt.key === ";") {
      evt.preventDefault();
      evt.stopImmediatePropagation();
      _enterChordMode();
      return;
    }
  }, true);  // capture phase — runs before the single-key handler below

  /* ================================================================
   * 5. Apply code — uses parameter queue to avoid hx-sync race condition
   *
   * IMPORTANT: Do NOT use setAttribute("hx-vals") + htmx.trigger() on
   * shared hidden buttons. With hx-sync="this:queue all", queued requests
   * read hx-vals at execution time (not queue time), so rapid keypresses
   * overwrite each other's params. Instead, push params into a queue and
   * inject them via htmx:configRequest at request time.
   * ================================================================ */

  // Apply/delete use htmx.ajax() directly instead of hidden trigger buttons
  // to avoid issues with hx-sync queuing and param injection timing.

  function _applyCodeToSentence(codeId, afterApply) {
    if (_codeApplicationDisabled()) return false;
    if (!Number.isFinite(window.__aceFocusIndex) || window.__aceFocusIndex < 0) return false;

    const request = htmx.ajax("POST", "/api/code/apply-sentence", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        sentence_index: window.__aceFocusIndex,
        current_index: window.__aceCurrentIndex,
      },
    }).then(function () {
      _restoreFocus();
      if (typeof afterApply === "function") afterApply();
    });

    window.__aceLastCodeId = codeId;
    _flashCodeRow(codeId);
    return request;
  }

  function _applyCodeToSelection(codeId, afterApply) {
    if (_codeApplicationDisabled()) return false;
    const sel = window.__aceLastSelection;
    if (!sel) return false;

    const request = htmx.ajax("POST", "/api/code/apply", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        start_offset: sel.start,
        end_offset: sel.end,
        selected_text: sel.text,
        current_index: window.__aceCurrentIndex,
      },
    }).then(function () {
      _restoreFocus();
      if (typeof afterApply === "function") afterApply();
    });

    window.__aceLastCodeId = codeId;
    window.__aceLastSelection = null;
    window.getSelection().removeAllRanges();
    _flashCodeRow(codeId);
    return request;
  }

  function _deleteSentenceAnnotation() {
    if (window.__aceFocusIndex < 0) return;

    htmx.ajax("POST", "/api/code/delete-sentence", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        sentence_index: window.__aceFocusIndex,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);
  }

  function _deleteAppliedAnnotation(annotationId) {
    if (!annotationId) return;

    htmx.ajax("POST", "/api/code/delete-annotation", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        annotation_id: annotationId,
        current_index: window.__aceCurrentIndex || 0,
      },
    }).then(_restoreFocus);
  }

  window.aceDeleteSentenceAnnotation = _deleteSentenceAnnotation;
  window.aceDeleteAppliedAnnotation = _deleteAppliedAnnotation;

  function _flashCodeRow(codeId) {
    document.querySelectorAll(
      `.ace-code-row[data-code-id="${codeId}"], .ace-ht-row[data-item-id="${codeId}"]`
    ).forEach(function (r) {
      r.classList.add("ace-code-row--flash");
      setTimeout(function () { r.classList.remove("ace-code-row--flash"); }, 300);
    });
  }

  /* ================================================================
   * 6. Keyboard shortcuts
   * ================================================================ */

  // Custom selection tracking (for click-drag)
  window.__aceLastSelection = null;

  function _isTyping() {
    let el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (e) {
    if (_chordMode === "awaiting") return;
    if (_isTyping()) return;
    if (_menuOpen) return;

    // Skip entirely on pages without the coding surface (e.g. /code/{id}/view
    // shares bridge.js but has no #text-panel; its shortcuts live in code_view.js).
    if (!document.getElementById("text-panel")) return;

    let zone = _activeZone();
    const key = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;

    if (zone === "tree") {
      if (!ctrl && !e.altKey && key === "/" && !shift) {
        e.preventDefault();
        _focusSearchBar();
        return;
      }
      if (!ctrl && !e.altKey && key === "ArrowLeft" && shift) {
        e.preventDefault();
        _navigateSourceFromKeyboard(window.__aceCurrentIndex - 1);
        return;
      }
      if (!ctrl && !e.altKey && key === "ArrowRight" && shift) {
        e.preventDefault();
        _navigateSourceFromKeyboard(window.__aceCurrentIndex + 1);
        return;
      }
      return;
    }
    if (zone === "search") return;

    // Z / Shift+Z / Cmd-Z / Cmd+Shift+Z — global undo / redo
    // Focus passthrough is handled above by _isTyping() so text inputs keep
    // the browser's native undo. Cmd / Ctrl modifier is optional; Shift picks
    // redo over undo.
    if (key === "z" || key === "Z") {
      e.preventDefault();
      if (shift) {
        htmx.ajax("POST", "/api/redo", {
          target: "#text-panel",
          swap: "outerHTML",
          values: { current_index: window.__aceCurrentIndex },
        });
      } else {
        htmx.ajax("POST", "/api/undo", {
          target: "#text-panel",
          swap: "outerHTML",
          values: { current_index: window.__aceCurrentIndex },
        });
      }
      return;
    }

    // Skip remaining if modifier keys held
    if (ctrl || e.altKey) return;

    // Shift+← / Shift+→ — Navigate between sources
    if (key === "ArrowLeft" && shift) {
      e.preventDefault();
      _navigateSourceFromKeyboard(window.__aceCurrentIndex - 1);
      return;
    }
    if (key === "ArrowRight" && shift) {
      e.preventDefault();
      _navigateSourceFromKeyboard(window.__aceCurrentIndex + 1);
      return;
    }

    // Q — Repeat last code
    if (key === "q" || key === "Q") {
      e.preventDefault();
      if (window.__aceLastCodeId && window.__aceFocusIndex >= 0) {
        if (window.__aceLastSelection) {
          _applyCodeToSelection(window.__aceLastCodeId);
        } else {
          _applyCodeToSentence(window.__aceLastCodeId);
        }
      }
      return;
    }

    // X — Delete annotation on focused sentence
    if (key === "x" || key === "X") {
      e.preventDefault();
      _deleteSentenceAnnotation();
      return;
    }

    // F — Flag (Shift+F)
    if (key === "F" && shift) {
      e.preventDefault();
      _updateCurrentIndex();
      const flagBtn = document.getElementById("trigger-flag");
      if (flagBtn) htmx.trigger(flagBtn, "click");
      return;
    }

    // N — open note drawer (read mode) or enter edit mode if already open
    if ((key === "n" || key === "N") && !shift) {
      e.preventDefault();
      if (!window.aceIsNoteDrawerOpen || !window.aceIsNoteDrawerOpen()) {
        if (typeof window.aceOpenNoteRead === "function") window.aceOpenNoteRead();
      } else if (typeof window.aceEnterEditMode === "function") {
        window.aceEnterEditMode();
      }
      return;
    }

    // ? — Toggle cheat sheet
    if (key === "?" || (shift && key === "/")) {
      e.preventDefault();
      _toggleCheatSheet();
      return;
    }

    // Escape cascade
    if (key === "Escape") {
      const cheatSheet = document.getElementById("ace-cheat-sheet");
      if (cheatSheet) { cheatSheet.remove(); return; }

      const dialog = document.querySelector("dialog[open]");
      if (dialog) { dialog.close(); return; }

      // Clear custom selection
      if (window.__aceLastSelection) {
        window.__aceLastSelection = null;
        window.getSelection().removeAllRanges();
      }
      return;
    }

    // / — Jump to sidebar search bar
    if (key === "/" && !shift) {
      e.preventDefault();
      _focusSearchBar();
      return;
    }

    // 1-9, 0, a-z — Apply code at keymap position
    // Guard: only single-character keys (skip ArrowLeft, ArrowRight, etc.)
    if (!shift && key.length === 1) {
      const pos = _keyToPosition(key);
      if (pos >= 0) _updateKeycaps();
      if (pos >= 0 && pos < _currentKeyMap.length) {
        e.preventDefault();
        const codeId = _currentKeyMap[pos];
        if (!window.__aceLastSelection && window.__aceFocusIndex < 0) {
          _focusSentence(0);
        }
        _applyCode(codeId);
      }
    }
  });

  function _updateCurrentIndex() {
    const input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
  }

  /* ================================================================
   * 7. Navigation
   * ================================================================ */

  async function _recordSourceNavigation(fromIndex, toIndex) {
    if (!Number.isFinite(fromIndex) || !Number.isFinite(toIndex) || fromIndex === toIndex) return;
    try {
      const body = new URLSearchParams();
      body.set("from_index", String(fromIndex));
      body.set("to_index", String(toIndex));
      await fetch("/api/navigation", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
    } catch (_) {}
  }

  function _navigateSourceFromKeyboard(index) {
    if (!Number.isFinite(index)) return;
    if (index < 0) {
      if (typeof window._setStatus === "function") window._setStatus("First source", "ok");
      return;
    }
    if (index >= window.__aceTotalSources) {
      if (typeof window._setStatus === "function") window._setStatus("Last source", "ok");
      return;
    }
    window.aceNavigate(index);
  }

  window.aceNavigate = async function (index) {
    if (!Number.isFinite(index) || index < 0 || index >= window.__aceTotalSources) return;
    const fromIndex = window.__aceCurrentIndex;
    // Flush any pending or in-flight note save before tearing down the page.
    // Without this, debounced saves get cancelled by the navigation.
    if (typeof window.aceFlushNoteIfDirty === "function") {
      try { await window.aceFlushNoteIfDirty(); } catch (_) {}
    }
    await _recordSourceNavigation(fromIndex, index);
    try {
      const url = new URL(window.location.href);
      if (!url.searchParams.has("index")) {
        url.searchParams.set("index", String(fromIndex));
        history.replaceState({}, "", url.pathname + url.search);
      }
    } catch (_) {}
    window.__aceCurrentIndex = index;
    window.__aceFocusIndex = -1;
    _setAmbient();
    window.location.href = `/code?index=${index}`;
  };

  window.aceNavigatePrev = function () {
    window.aceNavigate(window.__aceCurrentIndex - 1);
  };

  window.aceNavigateNext = function () {
    window.aceNavigate(window.__aceCurrentIndex + 1);
  };

  /* ================================================================
   * 8. Cheat sheet overlay
   * ================================================================ */

  function _toggleCheatSheet() {
    const existing = document.getElementById("ace-cheat-sheet");
    if (existing) { existing.remove(); return; }

    const overlay = document.createElement("div");
    overlay.id = "ace-cheat-sheet";
    overlay.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.45);";

    const card = document.createElement("div");
    card.style.cssText = "background:var(--ace-bg,#fff);border:1px solid var(--ace-border,#bdbdbd);padding:24px 32px;max-width:520px;width:90%;max-height:80vh;overflow-y:auto;font-size:13px;line-height:1.6;";

    card.innerHTML =
      '<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;">Keyboard shortcuts</h3>' +
      '<table style="width:100%;border-collapse:collapse;">' +
      _shortcutRow("←", "Move from source to codebook") +
      _shortcutRow("↑ / ↓", "Navigate sentences") +
      _shortcutRow("→", "Move from source to applied codes") +
      _shortcutRow("Shift + ← / →", "Previous / next source") +
      _shortcutRow("1 – 9, 0, a–y (not q v x z n)", "Apply code") +
      _shortcutRow("; then two letters", "Apply a two-key shortcut") +
      _shortcutRow("Q", "Repeat last code") +
      _shortcutRow("Delete / ⌫", "Delete focused sentence code or choose one") +
      _shortcutRow("X", "Remove code from sentence") +
      _shortcutRow("Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Shift + Z", "Redo") +
      _shortcutRow("Shift + F", "Flag/unflag source") +
      _shortcutRow("N", "Open / close note panel") +
      _shortcutRow("V", "View coded text") +
      _shortcutRow("Applied ↑ / ↓", "Move through applied codes") +
      _shortcutRow("Applied ← / Esc", "Return to source") +
      _shortcutRow("]", "Open / collapse applied codes") +
      _shortcutRow("Applied Delete", "Delete the focused annotation") +
      _shortcutRow("Tab", "Cycle source → search → tree → source") +
      _shortcutRow("⌥ + →", "Move item into the folder above") +
      _shortcutRow("⌥ + ⇧ + →", "Wrap two sibling codes into a new folder") +
      _shortcutRow("⌥ + ←", "Move item out one folder level") +
      _shortcutRow("⌘/Ctrl + X", "Cut focused item") +
      _shortcutRow("⌘/Ctrl + V", "Paste cut item into focused folder/row") +
      _shortcutRow("Shift + Enter (in filter)", "Create new folder at root") +
      _shortcutRow("F2", "Rename code or folder (in sidebar)") +
      _shortcutRow("Codebook Delete / ⌫", "Delete code or folder (Z to undo)") +
      _shortcutRow("?", "Toggle this cheat sheet") +
      _shortcutRow("Esc", "Codebook → source · cancel cut · clear filter") +
      "</table>";

    overlay.appendChild(card);
    document.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) overlay.remove();
    });
  }

  function _shortcutRow(key, desc) {
    return `<tr style="border-bottom:1px solid var(--ace-border-light,#e0e0e0);"><td style="padding:4px 12px 4px 0;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;white-space:nowrap;color:var(--ace-text-muted,#777);">${key}</td><td style="padding:4px 0;">${desc}</td></tr>`;
  }

  /* ================================================================
   * 9. Resize handle
   * ================================================================ */

  function _initResize() {
    const handle = document.getElementById("resize-handle");
    if (!handle) return;
    const split = handle.closest(".ace-three-col");
    if (!split) return;

    let dragging = false;
    const DEFAULT_PX = 360;
    const MIN_PX = 150;
    const KEY_STEP_PX = 24;

    function _maxPx() {
      const vw = document.documentElement.clientWidth;
      const splitW = split.getBoundingClientRect().width;
      const base = Math.min(vw || splitW, splitW || vw);
      return Math.max(MIN_PX, Math.floor((base || DEFAULT_PX) * 0.4));
    }

    function _clampPx(px) {
      return Math.max(MIN_PX, Math.min(_maxPx(), px));
    }

    function _currentPx() {
      return parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"),
        10,
      ) || DEFAULT_PX;
    }

    function _syncAria(px) {
      handle.setAttribute("aria-valuemin", String(MIN_PX));
      handle.setAttribute("aria-valuemax", String(_maxPx()));
      handle.setAttribute("aria-valuenow", String(Math.round(px)));
      handle.setAttribute("aria-valuetext", Math.round(px) + " pixels");
    }

    function _setWidth(px, persist) {
      const clamped = _clampPx(px);
      document.documentElement.style.setProperty("--ace-sidebar-width", clamped + "px");
      _syncAria(clamped);
      if (persist) localStorage.setItem("ace-sidebar-width", String(Math.round(clamped)));
      return clamped;
    }

    handle.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      dragging = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      const rect = split.getBoundingClientRect();
      _setWidth(e.clientX - rect.left, false);
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      _setWidth(_currentPx(), true);
    });

    handle.addEventListener("dblclick", function () {
      _setWidth(DEFAULT_PX, true);
    });

    handle.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const delta = e.key === "ArrowRight" ? KEY_STEP_PX : -KEY_STEP_PX;
      _setWidth(_currentPx() + delta, true);
      e.preventDefault();
    });

    // Re-clamp on viewport resize (mirrors the drag's 40% cap above) so
    // shrinking the window never re-crushes the text — a width saved on a
    // large monitor is clamped down here, and grows back if the window
    // widens. Re-derives from the saved value each time; skipped during a
    // drag. Runs once now to refine the pre-CSS restore (which used
    // innerWidth as an approximation).
    function clampToViewport() {
      if (dragging) return;
      const saved = parseInt(localStorage.getItem("ace-sidebar-width") || "360", 10) || 360;
      _setWidth(saved, false);
    }
    window.addEventListener("resize", clampToViewport);
    clampToViewport();
  }

  function _initGridResize() {
    const handle = document.querySelector(".ace-sidebar-vsplit");
    if (!handle || handle.dataset.aceResizeWired) return;
    handle.dataset.aceResizeWired = "1";

    const DEFAULT_VH = 18;
    const MIN_VH = 10;
    const MAX_VH = 70;
    const KEY_STEP_PX = 8;

    function _vhToPx(vh) { return (window.innerHeight * vh) / 100; }
    function _pxToVh(px) { return (px / window.innerHeight) * 100; }
    function _clampVh(v) { return Math.max(MIN_VH, Math.min(MAX_VH, v)); }

    function _setValue(vh) {
      const clamped = _clampVh(vh);
      document.documentElement.style.setProperty("--ace-grid-height", clamped.toFixed(2) + "vh");
      const rounded = Math.round(clamped);
      handle.setAttribute("aria-valuenow", rounded.toString());
      handle.setAttribute("aria-valuetext", rounded + " percent of viewport height");
      return clamped;
    }

    function _persist(vh) {
      try { localStorage.setItem("ace-grid-height", vh.toFixed(2) + "vh"); } catch (_) {}
    }

    function _currentVh() {
      const computed = getComputedStyle(document.documentElement)
        .getPropertyValue("--ace-grid-height").trim();
      return parseFloat(computed) || DEFAULT_VH;
    }

    // Sync ARIA state with the actual computed starting height — catches
    // values restored from localStorage before the first user interaction.
    _setValue(_currentVh());

    // Pointer drag — all listeners on the handle, with setPointerCapture,
    // so they die cleanly with the subtree when #code-sidebar is replaced
    // by an OOB swap (no document-level listener leak).
    let dragging = false;
    let startY = 0;
    let startVh = DEFAULT_VH;

    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      dragging = true;
      startY = e.clientY;
      startVh = _currentVh();
      handle.setPointerCapture(e.pointerId);
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    handle.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      const dy = startY - e.clientY; // dragging up grows the panel
      const newVh = _pxToVh(_vhToPx(startVh) + dy);
      _setValue(newVh);
    });

    function _endDrag(e) {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = "";
      if (e && typeof e.pointerId === "number" && handle.hasPointerCapture(e.pointerId)) {
        handle.releasePointerCapture(e.pointerId);
      }
      _persist(_clampVh(_currentVh()));
    }

    handle.addEventListener("pointerup", _endDrag);
    handle.addEventListener("pointercancel", _endDrag);

    // Double-click reset
    handle.addEventListener("dblclick", function () {
      document.documentElement.style.removeProperty("--ace-grid-height");
      handle.setAttribute("aria-valuenow", DEFAULT_VH.toString());
      handle.setAttribute("aria-valuetext", DEFAULT_VH + " percent of viewport height");
      try { localStorage.removeItem("ace-grid-height"); } catch (_) {}
    });

    // Keyboard resize
    handle.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      const deltaPx = (e.key === "ArrowUp" ? 1 : -1) * KEY_STEP_PX;
      const newVh = _pxToVh(_vhToPx(_currentVh()) + deltaPx);
      const clamped = _setValue(newVh);
      _persist(clamped);
      e.preventDefault();
    });
  }

  /* ================================================================
   * 10. Source grid overlay — sparkline minimap + tile viewport
   * ================================================================ */

  let _aceSourceGridState = {
    sources: [],
    windowStart: 0,
    visibleCount: 0,
    resizeObs: null,
    hoveredIndex: -1, // -1 means "no hover; show active"
    lastActive: -1,   // last rendered active index; used to decide whether to
                      // auto-centre the viewport (only on active-source change,
                      // so sparkline clicks to a distant range aren't snapped back)
  };

  function _aceInspectorLine(src) {
    if (!src) return "";
    const n = src.index + 1;
    const flags = [];
    if (src.flagged) flags.push("flagged");
    if (src.note)    flags.push("has note");
    const plural = src.count === 1 ? "" : "s";
    const parts = [
      "#" + n,
      src.display_id,
      src.count + " annotation" + plural,
    ];
    if (flags.length) parts.push(flags.join(" · "));
    return parts.join(" · ");
  }

  function _aceUpdateInspector() {
    const el = document.getElementById("ace-grid-inspector");
    if (!el) return;
    const st = _aceSourceGridState;
    let src = null;
    if (st.hoveredIndex >= 0 && st.hoveredIndex < st.sources.length) {
      src = st.sources[st.hoveredIndex];
    } else if (typeof window.__aceCurrentIndex === "number" &&
               window.__aceCurrentIndex >= 0 &&
               window.__aceCurrentIndex < st.sources.length) {
      src = st.sources[window.__aceCurrentIndex];
    }
    el.textContent = _aceInspectorLine(src);
  }

  function _aceRenderTiles() {
    const host = document.getElementById("ace-grid-tiles");
    const label = document.getElementById("ace-grid-range-label");
    if (!host) return;
    const st = _aceSourceGridState;
    const active = typeof window.__aceCurrentIndex === "number"
      ? window.__aceCurrentIndex : 0;

    // Compute visible count from the CONTENT box (exclude padding) so the
    // math matches CSS `repeat(auto-fill, 22px)` — otherwise we overcount
    // columns by ~1 and the extra tiles spill into a row that gets clipped
    // by `overflow: hidden`.
    const cs = getComputedStyle(host);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const padY = parseFloat(cs.paddingTop)  + parseFloat(cs.paddingBottom);
    const rect = host.getBoundingClientRect();
    const contentW = Math.max(0, rect.width  - padX);
    const contentH = Math.max(0, rect.height - padY);
    const TILE = 22, GAP = 2;
    const cols = Math.max(1, Math.floor((contentW + GAP) / (TILE + GAP)));
    const rows = Math.max(1, Math.floor((contentH + GAP) / (TILE + GAP)));
    st.visibleCount = Math.min(st.sources.length, cols * rows);
    st.windowStart = _aceClampGridWindowStart(
      st.windowStart, st.sources.length, st.visibleCount, cols);

    // Move the tile viewport only when the active source has changed.
    // Sequential source navigation should scroll by whole tile rows, not
    // recenter around the new tile, so the grid keeps its column rhythm.
    if (active !== st.lastActive) {
      _aceRevealGridIndex(active, st.lastActive, cols);
    }
    st.lastActive = active;

    const from = st.windowStart;
    const to   = Math.min(st.sources.length, from + st.visibleCount);

    if (label) {
      label.textContent = "Sources " + (from + 1) + "–" + to +
        " of " + st.sources.length;
    }

    const frag = document.createDocumentFragment();
    for (let i = from; i < to; i++) {
      const s = st.sources[i];
      const cls = ["ace-grid-tile"];
      if (s.count >= 6) cls.push("hot");
      else if (s.count >= 3) cls.push("warm");
      if (i === active)  cls.push("active");
      if (s.flagged)     cls.push("flagged");
      if (s.note)        cls.push("note");

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = cls.join(" ");
      btn.setAttribute("role", "gridcell");
      btn.dataset.sourceIndex = String(i);
      btn.dataset.count = String(s.count);
      btn.tabIndex = (i === active) ? 0 : -1;
      if (i === active) btn.setAttribute("aria-current", "location");
      btn.title = "#" + (i + 1) + " · " + s.display_id +
        " · " + s.count + " annotation" + (s.count === 1 ? "" : "s");

      const span = document.createElement("span");
      span.textContent = String(s.count);
      btn.appendChild(span);

      btn.addEventListener("click", function () {
        if (typeof window.aceNavigate === "function") {
          window.aceNavigate(i);
        }
      });
      btn.addEventListener("mouseenter", function () {
        _aceSourceGridState.hoveredIndex = i;
        _aceUpdateInspector();
      });
      btn.addEventListener("focus", function () {
        _aceSourceGridState.hoveredIndex = i;
        _aceUpdateInspector();
      });

      frag.appendChild(btn);
    }
    host.replaceChildren(frag);

    // Mouse leaving the tile grid clears hover → inspector falls back to active
    if (!host.dataset.aceMouseleaveWired) {
      host.addEventListener("mouseleave", function () {
        _aceSourceGridState.hoveredIndex = -1;
        _aceUpdateInspector();
      });
      host.dataset.aceMouseleaveWired = "1";
    }

    _aceUpdateInspector();
  }

  function _aceRenderSparkline() {
    const host = document.getElementById("ace-grid-spark");
    if (!host) return;
    const st = _aceSourceGridState;
    const total = st.sources.length;
    if (total === 0) { host.replaceChildren(); return; }

    const W = host.clientWidth || 240;
    const H = 38;
    const padX = 2;
    const innerW = Math.max(1, W - 2 * padX);

    const nPoints = Math.max(40, Math.min(160, Math.floor(innerW / 4)));
    let maxCount = 1;
    for (let k = 0; k < total; k++) {
      if (st.sources[k].count > maxCount) maxCount = st.sources[k].count;
    }

    // One vertex per source so peaks land exactly at playhead positions.
    // Downsample with interpolation only when total exceeds the render
    // budget, bounding path length for large datasets.
    const renderPoints = Math.min(total, nPoints);
    const density = new Array(renderPoints);
    if (renderPoints === total) {
      for (let i = 0; i < total; i++) density[i] = st.sources[i].count;
    } else {
      const span = total - 1;
      for (let i = 0; i < renderPoints; i++) {
        const pos = (i / (renderPoints - 1)) * span;
        const lo = Math.floor(pos);
        const hi = Math.min(total - 1, lo + 1);
        const frac = pos - lo;
        density[i] = st.sources[lo].count * (1 - frac) +
                     st.sources[hi].count * frac;
      }
    }

    const xDenom = Math.max(1, renderPoints - 1);
    const pts = density.map(function (d, i) {
      const x = padX + (i / xDenom) * innerW;
      const y = H - (d / maxCount) * (H - 4) - 2;
      return [x, y];
    });
    const line = "M" + pts.map(function (p) {
      return p[0].toFixed(1) + "," + p[1].toFixed(1);
    }).join(" L");
    const area = line + " L" + (W - padX).toFixed(1) + "," + H +
                        " L" + padX.toFixed(1) + "," + H + " Z";

    const denom = Math.max(1, total - 1);
    const vpX1 = padX + (st.windowStart / denom) * innerW;
    const vpEnd = Math.min(total, st.windowStart + st.visibleCount) - 1;
    const vpX2 = padX + (Math.max(vpEnd, 0) / denom) * innerW;
    const vpW  = Math.max(6, vpX2 - vpX1);
    const active = typeof window.__aceCurrentIndex === "number"
      ? window.__aceCurrentIndex : 0;
    const playX = padX + (active / denom) * innerW;

    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + (H + 4));
    svg.setAttribute("preserveAspectRatio", "none");

    function mk(tag, attrs) {
      const el = document.createElementNS(NS, tag);
      for (const k in attrs) el.setAttribute(k, attrs[k]);
      return el;
    }
    svg.appendChild(mk("path", { class: "spark-area", d: area }));
    svg.appendChild(mk("path", { class: "spark-line", d: line }));
    svg.appendChild(mk("rect", {
      class: "spark-viewport",
      x: vpX1.toFixed(1), y: 0,
      width: vpW.toFixed(1), height: H,
    }));
    svg.appendChild(mk("line", {
      class: "spark-playhead",
      x1: playX, x2: playX, y1: 0, y2: H,
    }));
    svg.appendChild(mk("circle", {
      class: "spark-playhead-cap",
      cx: playX, cy: H + 2, r: 2,
    }));

    svg.addEventListener("click", function (ev) {
      const r = svg.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const normalised = (x - padX) / innerW;
      const idx = Math.round(Math.max(0, Math.min(1, normalised)) * denom);
      _aceSourceGridState.windowStart = _aceWindowStartForGridTarget(
        idx,
        idx - Math.floor(_aceSourceGridState.visibleCount / 2),
        total,
        _aceSourceGridState.visibleCount,
        _aceTileCols(),
      );
      _aceRenderSparkline();
      _aceRenderTiles();
      if (typeof window.aceNavigate === "function") {
        window.aceNavigate(idx);
      }
    });

    host.replaceChildren(svg);
  }

  function _aceTileCols() {
    const host = document.getElementById("ace-grid-tiles");
    if (!host) return 1;
    const cs = getComputedStyle(host);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const rect = host.getBoundingClientRect();
    const contentW = Math.max(0, rect.width - padX);
    const TILE = 22, GAP = 2;
    return Math.max(1, Math.floor((contentW + GAP) / (TILE + GAP)));
  }

  function _aceMaxGridWindowStart(total, visibleCount, cols) {
    if (total <= visibleCount) return 0;
    const safeCols = Math.max(1, cols);
    return Math.ceil((total - visibleCount) / safeCols) * safeCols;
  }

  function _aceClampGridWindowStart(start, total, visibleCount, cols) {
    const safeCols = Math.max(1, cols);
    const maxStart = _aceMaxGridWindowStart(total, visibleCount, safeCols);
    const rowStart = Math.floor(Math.max(0, start) / safeCols) * safeCols;
    return Math.max(0, Math.min(maxStart, rowStart));
  }

  function _aceWindowStartForGridTarget(targetIndex, start, total, visibleCount, cols) {
    const safeCols = Math.max(1, cols);
    const maxStart = _aceMaxGridWindowStart(total, visibleCount, safeCols);
    let rowStart = _aceClampGridWindowStart(start, total, visibleCount, safeCols);
    while (targetIndex < rowStart) {
      rowStart = Math.max(0, rowStart - safeCols);
    }
    while (targetIndex >= rowStart + visibleCount) {
      rowStart = Math.min(maxStart, rowStart + safeCols);
    }
    return rowStart;
  }

  function _aceRevealGridIndex(targetIndex, previousIndex, cols) {
    const st = _aceSourceGridState;
    if (!st.visibleCount || st.sources.length === 0) return false;
    const safeCols = Math.max(1, cols);
    const total = st.sources.length;
    const maxStart = _aceMaxGridWindowStart(total, st.visibleCount, safeCols);

    st.windowStart = _aceClampGridWindowStart(
      st.windowStart, total, st.visibleCount, safeCols);
    const start = st.windowStart;
    const end = start + st.visibleCount;
    if (targetIndex >= start && targetIndex < end) return false;

    const previousWasVisible = previousIndex >= start && previousIndex < end;
    if (previousWasVisible && targetIndex === previousIndex + 1 && targetIndex >= end) {
      st.windowStart = Math.min(maxStart, start + safeCols);
    } else if (previousWasVisible && targetIndex === previousIndex - 1 && targetIndex < start) {
      st.windowStart = Math.max(0, start - safeCols);
    } else {
      st.windowStart = _aceWindowStartForGridTarget(
        targetIndex,
        targetIndex - Math.floor(st.visibleCount / 2),
        total,
        st.visibleCount,
        safeCols,
      );
    }
    return true;
  }

  function _aceNavigateFocus(targetIndex, previousIndex) {
    const st = _aceSourceGridState;
    const total = st.sources.length;
    if (total === 0) return;
    targetIndex = Math.max(0, Math.min(total - 1, targetIndex));

    if (_aceRevealGridIndex(targetIndex, previousIndex, _aceTileCols())) {
      _aceRenderTiles();
      _aceRenderSparkline();
    }

    // Focus the destination tile
    const host = document.getElementById("ace-grid-tiles");
    if (!host) return;
    const btn = host.querySelector(
      '[data-source-index="' + targetIndex + '"]');
    if (btn) {
      host.querySelectorAll('.ace-grid-tile').forEach(function (t) {
        t.tabIndex = -1;
      });
      btn.tabIndex = 0;
      btn.focus();
      _aceSourceGridState.hoveredIndex = targetIndex;
      _aceUpdateInspector();
    }
  }

  function _aceInitTileKeyboard() {
    const host = document.getElementById("ace-grid-tiles");
    if (!host || host.dataset.aceKbdWired) return;
    host.dataset.aceKbdWired = "1";

    host.addEventListener("keydown", function (e) {
      const target = e.target.closest(".ace-grid-tile");
      if (!target) return;
      const idx = parseInt(target.dataset.sourceIndex, 10);
      if (Number.isNaN(idx)) return;
      const st = _aceSourceGridState;
      const cols = _aceTileCols();
      const total = st.sources.length;

      let dest = null;
      switch (e.key) {
        case "ArrowLeft":  dest = idx - 1; break;
        case "ArrowRight": dest = idx + 1; break;
        case "ArrowUp":    dest = idx - cols; break;
        case "ArrowDown":  dest = idx + cols; break;
        case "Home":       dest = 0; break;
        case "End":        dest = total - 1; break;
        case "PageUp":     dest = idx - Math.max(cols, st.visibleCount); break;
        case "PageDown":   dest = idx + Math.max(cols, st.visibleCount); break;
        case "Enter":
        case " ": {
          if (typeof window.aceNavigate === "function") {
            window.aceNavigate(idx);
          }
          e.preventDefault();
          return;
        }
        case "Escape": {
          const panel = document.querySelector(".ace-text-panel");
          if (panel) panel.focus();
          e.preventDefault();
          return;
        }
        default:
          return;
      }

      // Clamp to valid range; _aceNavigateFocus also clamps but do it here too
      // so we can tell "key consumed" vs "already at target".
      const clamped = Math.max(0, Math.min(total - 1, dest));
      if (clamped !== idx) {
        _aceNavigateFocus(clamped, idx);
      }
      e.preventDefault();
    });
  }

  window._aceRenderSourceGrid = function () {
    const blob = document.getElementById("ace-sources-data");
    if (!blob) return;
    try {
      _aceSourceGridState.sources = JSON.parse(blob.textContent || "[]");
    } catch (e) {
      _aceSourceGridState.sources = [];
    }
    // HTMX sidebar swaps (e.g. after code CRUD) detach the old tile host,
    // so the existing observer would point at a dead node. Re-observe the
    // current host on every call to stay pointed at live DOM.
    const tiles = document.getElementById("ace-grid-tiles");
    if (_aceSourceGridState.resizeObs) {
      _aceSourceGridState.resizeObs.disconnect();
    }
    if (tiles) {
      _aceSourceGridState.resizeObs = new ResizeObserver(function () {
        _aceRenderTiles();
        _aceRenderSparkline();
      });
      _aceSourceGridState.resizeObs.observe(tiles);
    }
    _aceRenderTiles();
    _aceRenderSparkline();
    _aceInitTileKeyboard();
  };

  /* ================================================================
   * 11. Dialog close cleanup
   * ================================================================ */

  document.addEventListener("close", function (evt) {
    if (evt.target.tagName === "DIALOG") {
      const container = document.getElementById("modal-container");
      if (container) container.innerHTML = "";
    }
  }, true);

  /* ================================================================
   * 12. HTMX integration
   * ================================================================ */

  // Custom selection capture (for click-drag)
  // Uses data-start/data-end attributes on sentence spans to compute
  // source-text offsets (DOM offsets differ due to inter-span whitespace).
  document.addEventListener("mouseup", function () {
    const container = document.querySelector(".ace-text-panel");
    if (!container) return;

    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      window.__aceLastSelection = null;
      return;
    }

    const range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      return;
    }

    const text = sel.toString();
    if (!text) { window.__aceLastSelection = null; return; }

    // Find the sentence spans containing the selection endpoints
    const startSrc = _sourceOffset(range.startContainer, range.startOffset);
    const endSrc = _sourceOffset(range.endContainer, range.endOffset);

    if (startSrc < 0 || endSrc < 0 || startSrc === endSrc) {
      window.__aceLastSelection = null;
      return;
    }

    window.__aceLastSelection = { start: startSrc, end: endSrc, text: text };
  });

  function _sourceOffset(node, domOffset) {
    // Walk up to find the containing .ace-sentence span
    let el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    let sentence = el.closest(".ace-sentence");
    if (!sentence) return -1;

    const sentStart = parseInt(sentence.dataset.start, 10);
    if (isNaN(sentStart)) return -1;

    // Compute character offset within this sentence's text content
    const walker = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
    let charPos = 0;
    let current;
    while ((current = walker.nextNode())) {
      if (current === node) return sentStart + charPos + domOffset;
      charPos += current.textContent.length;
    }
    // Fallback: if node is the sentence element itself, use domOffset as child index
    return sentStart + domOffset;
  }

  // Click on sentence to focus it
  document.addEventListener("click", function (e) {
    let sentence = e.target.closest(".ace-sentence");
    if (sentence) {
      const idx = parseInt(sentence.dataset.idx, 10);
      if (!isNaN(idx)) {
        _focusSentence(idx);
        _focusTextPanel();
        // Clear custom selection if this was a simple click (not drag)
        if (!window.__aceLastSelection) {
          window.getSelection().removeAllRanges();
        }
      }
    }

    const appliedCollapseToggle = e.target.closest("[data-ace-applied-toggle]");
    if (appliedCollapseToggle) {
      e.preventDefault();
      e.stopPropagation();
      _setAppliedCollapsed(!_isAppliedCollapsed(), { focus: true });
      return;
    }

    const removeAppliedButton = e.target.closest(".ace-applied-annotation-remove");
    if (removeAppliedButton) {
      e.preventDefault();
      e.stopPropagation();
      _deleteAppliedAnnotation(removeAppliedButton.dataset.annotationId);
      return;
    }

    const appliedToggle = e.target.closest(".ace-applied-code-toggle");
    if (appliedToggle) {
      e.preventDefault();
      e.stopPropagation();
      const expanded = appliedToggle.getAttribute("aria-expanded") === "true";
      const targetId = appliedToggle.getAttribute("aria-controls");
      const target = targetId ? document.getElementById(targetId) : null;
      appliedToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (target) target.hidden = expanded;
      return;
    }

    // Click an applied-code row to flash every matching annotation in source.
    const appliedCodeRow = e.target.closest(".ace-applied-code-row");
    if (appliedCodeRow) {
      const codeId = appliedCodeRow.dataset.codeId;
      const dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      const matching = JSON.parse(dataEl.dataset.annotations || "[]")
        .filter(function (a) { return a.code_id === codeId; });
      _renderFlashRects(matching);
      return;
    }

    const appliedAnnotationRow = e.target.closest(".ace-applied-annotation-row");
    if (appliedAnnotationRow) {
      const annotationId = appliedAnnotationRow.dataset.annotationId;
      const dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      const matching = JSON.parse(dataEl.dataset.annotations || "[]")
        .filter(function (a) { return a.id === annotationId; });
      _renderFlashRects(matching);
      return;
    }
  });

  document.addEventListener("mouseover", function (e) {
    const removeButton = e.target.closest(".ace-applied-annotation-remove");
    if (removeButton && !removeButton.contains(e.relatedTarget)) {
      _setAppliedAnnotationPreview(removeButton.dataset.annotationId);
      return;
    }

    const annRow = e.target.closest(".ace-applied-annotation-row");
    if (annRow && !annRow.contains(e.relatedTarget)) {
      _setAppliedAnnotationPreview(annRow.dataset.annotationId);
      return;
    }

    const row = e.target.closest(".ace-applied-code-row");
    if (!row || row.contains(e.relatedTarget)) return;
    _setAppliedCodePreview(row.dataset.codeId);
  });

  document.addEventListener("mouseout", function (e) {
    const removeButton = e.target.closest(".ace-applied-annotation-remove");
    if (removeButton && !removeButton.contains(e.relatedTarget)) {
      _clearAppliedCodePreview();
      return;
    }

    const annRow = e.target.closest(".ace-applied-annotation-row");
    if (annRow && !annRow.contains(e.relatedTarget)) {
      _clearAppliedCodePreview();
      return;
    }

    const row = e.target.closest(".ace-applied-code-row");
    if (!row || row.contains(e.relatedTarget)) return;
    _clearAppliedCodePreview();
  });

  document.addEventListener("focusin", function (e) {
    const removeButton = e.target.closest(".ace-applied-annotation-remove");
    if (removeButton) {
      _setAppliedAnnotationPreview(removeButton.dataset.annotationId);
      return;
    }

    const annRow = e.target.closest(".ace-applied-annotation-row");
    if (annRow) {
      _setAppliedAnnotationPreview(annRow.dataset.annotationId);
      return;
    }

    const row = e.target.closest(".ace-applied-code-row");
    if (!row) return;
    _setAppliedCodePreview(row.dataset.codeId);
  });

  document.addEventListener("focusout", function (e) {
    const removeButton = e.target.closest(".ace-applied-annotation-remove");
    if (removeButton && !removeButton.contains(e.relatedTarget)) {
      _clearAppliedCodePreview();
      return;
    }

    const annRow = e.target.closest(".ace-applied-annotation-row");
    if (annRow && !annRow.contains(e.relatedTarget)) {
      _clearAppliedCodePreview();
      return;
    }

    const row = e.target.closest(".ace-applied-code-row");
    if (!row || row.contains(e.relatedTarget)) return;
    _clearAppliedCodePreview();
  });

  // Flash a single annotation by ID — used by the server-emitted
  // ace-undo-flash hint after /api/undo or /api/redo restores an
  // annotation.
  window._flashAnnotation = function (annotationId) {
    const annDataEl = document.getElementById("ace-ann-data");
    if (!annDataEl) return;
    let annotations;
    try {
      annotations = JSON.parse(annDataEl.dataset.annotations || "[]");
    } catch (err) {
      return;
    }
    const ann = annotations.find(function (a) { return a.id === annotationId; });
    if (ann) _renderFlashRects([ann]);
  };

  // --- Focus restoration across HTMX swaps ---

  const _sidebarFocusState = {
    codeId: null,
    folderId: null,
    searchText: "",
    scrollTop: 0,
    zone: null,
  };

  document.addEventListener("htmx:beforeSwap", function (e) {
    const target = e.detail.target;
    if (!target) return;
    if (target.id !== "code-sidebar" && target.id !== "coding-workspace" && target.id !== "text-panel") return;

    let zone = _activeZone();
    _sidebarFocusState.zone = zone;

    if (zone === "tree") {
      const active = _getActiveTreeItem();
      _sidebarFocusState.codeId = active ? active.getAttribute("data-code-id") : null;
      _sidebarFocusState.folderId = active ? active.getAttribute("data-folder-id") : null;
    }

    let search = document.getElementById("code-search-input");
    _sidebarFocusState.searchText = search ? search.value : "";

    const tree = document.getElementById("ace-headless-tree-mount");
    _sidebarFocusState.scrollTop = tree ? tree.scrollTop : 0;
  });

  /* ================================================================
   * 4xx error feedback — surface HTMX error bodies in the status bar
   * ================================================================ */

  // Surface 4xx response bodies as a sticky status-bar error instead of
  // letting HTMX silently drop them. Coding routes raise HTTPException(400),
  // which FastAPI serialises to {"detail": "..."} — prefer that, fall back to
  // raw text, then a generic message. 5xx is left untouched so a server
  // traceback isn't dumped into the status bar.
  document.addEventListener("htmx:beforeSwap", function (e) {
    const xhr = e.detail && e.detail.xhr;
    if (!xhr || xhr.status < 400 || xhr.status >= 500) return;
    let msg = "";
    try {
      const body = JSON.parse(xhr.responseText);
      if (body && typeof body.detail === "string") msg = body.detail;
    } catch (_) {
      if (xhr.responseText) msg = xhr.responseText.slice(0, 200);
    }
    if (!msg) msg = "That action couldn't complete — try again.";
    if (typeof window._setStatus === "function") window._setStatus(msg, "err");
    if (typeof e.detail.shouldSwap === "boolean") e.detail.shouldSwap = false;
  });

  // Track whether the sidebar element survived the most recent swap.
  // Annotation-only routes (apply, delete-annotation, navigate, flag,
  // apply-sentence, delete-sentence) deliberately omit the sidebar OOB so
  // the aside doesn't get torn down on every code application; codebook
  // mutation routes still emit it. Element identity is the cheapest
  // detection — a fresh outerHTML swap creates a new node.
  let _lastSidebarEl =
    typeof document !== "undefined"
      ? document.getElementById("code-sidebar")
      : null;

  // Patch per-row code-count chips from #ace-ann-data so annotation-only
  // updates don't need to re-render the full sidebar.
  let _lastCodeCountPayload = "";
  function _syncCodeCounts() {
    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    const annPayload = dataEl.dataset.annotations || "[]";
    const countPayload = dataEl.dataset.codeCounts || "";
    const payloadKey = `${annPayload}\n${countPayload}`;
    if (payloadKey === _lastCodeCountPayload) return;
    _lastCodeCountPayload = payloadKey;
    const counts = new Map();
    let usedGlobalCounts = false;
    if (countPayload) {
      try {
        const parsedCounts = JSON.parse(countPayload);
        if (
          parsedCounts &&
          typeof parsedCounts === "object" &&
          !Array.isArray(parsedCounts)
        ) {
          Object.entries(parsedCounts).forEach(function ([codeId, value]) {
            const n = Number(value);
            counts.set(String(codeId), Number.isFinite(n) ? n : 0);
          });
          usedGlobalCounts = true;
        }
      } catch (_) {
        usedGlobalCounts = false;
      }
    }
    if (!usedGlobalCounts) {
      let annotations;
      try {
        annotations = JSON.parse(annPayload);
      } catch (_) {
        return;
      }
      for (const a of annotations) {
        counts.set(a.code_id, (counts.get(a.code_id) || 0) + 1);
      }
    }
    document
      .querySelectorAll("#ace-headless-tree-mount .ace-ht-row--code[data-code-id]")
      .forEach(function (row) {
        const cnt = row.querySelector(".ace-ht-count");
        if (!cnt) return;
        const n = counts.get(row.dataset.codeId) || 0;
        cnt.textContent = n > 0 ? String(n) : "";
      });
  }

  // Re-bind sidebar event wiring after an HTMX swap replaces sidebar DOM.
  // opts: { sortable: bool, gridResize: bool } — both default false.
  // Sortable re-init is skipped while a drag is in progress.
  // Always restores tree scrollTop (saved in htmx:beforeSwap) so applying a
  // code via hotkey/click doesn't bounce the sidebar back to the top.
  function _syncSidebarAfterSwap(opts) {
    opts = opts || {};
    if (opts.sortable && !_isDragging) _initSortable();
    _restoreCollapseState();
    _updateKeycaps();
    if (opts.gridResize) _initGridResize();
    const tree = document.getElementById("ace-headless-tree-mount");
    if (tree && _sidebarFocusState.scrollTop) {
      tree.scrollTop = _sidebarFocusState.scrollTop;
    }
    if (_codeCuesEnabled()) {
      _scheduleCodeCues();
    } else {
      _clearCodeCues();
    }
  }

  // Re-render the source grid if its data blob is present in the swapped
  // DOM. Primary HTMX swaps don't fire htmx:oobAfterSwap for OOB targets,
  // so call this explicitly from afterSettle to keep the tile grid in
  // sync with the server-rendered `ace-sources-data` JSON.
  function _rerenderSourceGridIfPresent() {
    if (document.getElementById("ace-sources-data") &&
        typeof window._aceRenderSourceGrid === "function") {
      window._aceRenderSourceGrid();
    }
  }

  // After HTMX swap: restore focus, rebuild tabs, update keycaps,
  // and refresh the ambient status-bar segment. Use afterSettle (not
  // afterSwap) — fires after HTMX finishes all DOM changes.
  document.addEventListener("htmx:afterSettle", function (evt) {
    // Keep the ambient left segment of the statusbar in sync on every
    // afterSettle, including target-less events — preserves the
    // behaviour of the previously-standalone listener this replaced.
    _setAmbient();

    // If a soft-delete swapped in an undo affordance, wire its click +
    // hover-pause + 7 s auto-clear timer. Idempotent.
    _initUndoAffordance();
    _syncReceiptFromStatusbar();
    _syncAppliedCollapseA11y();

    // Server-emitted "ok" pills (e.g. /api/undo's "Nothing to undo")
    // arrive as plain OOB swaps and don't run the client-side fade
    // timer that _setStatus sets up. Mirror the same 2 s fade so they
    // don't sit forever waiting for the next user action.
    _maybeFadeOkStatus();

    const target = (evt.detail || {}).target;
    if (!target) return;

    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _syncCodingTextControls();
      _restoreFocus();
      _paintSvg();

      // Annotation-only responses leave the sidebar's DOM intact — patch
      // the per-row counts in place. Codebook-mutation responses replace
      // the aside via OOB, so element identity changes and we need the
      // full re-bind (Sortable, collapse state, keycaps, ghost class);
      // the new sidebar already carries fresh server-rendered counts.
      const sidebarEl = document.getElementById("code-sidebar");
      if (sidebarEl && sidebarEl !== _lastSidebarEl) {
        _lastSidebarEl = sidebarEl;
        _syncSidebarAfterSwap({ sortable: true, gridResize: true });
        if (_cutCode) {
          const r = _findCodebookItemRow(_cutCode);
          if (r) {
            r.classList.add("ace-code-row--ghost");
          } else {
            _setCut(null);
            window._setStatus("Cut cleared (item removed)", "ok");
          }
        }
      } else {
        _syncCodeCounts();
      }
      _rerenderSourceGridIfPresent();

      // Announce flag state and restore focus after flag toggle
      if (_pendingFlagAnnounce) {
        _pendingFlagAnnounce = false;
        const flagBtn = document.getElementById("nav-flag-btn");
        if (flagBtn) {
          const pressed = flagBtn.getAttribute("aria-pressed") === "true";
          _announce(pressed ? "Source flagged" : "Source unflagged");
          flagBtn.focus();
        }
      }
    }

    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      _lastSidebarEl = document.getElementById("code-sidebar");
      _syncSidebarAfterSwap({ sortable: true, gridResize: true });
      _initCodingTextControls();
      // Re-apply ghost class if a cut is staged and the row still exists.
      // If the row vanished (deleted by another action), clear the cut state.
      if (_cutCode) {
        const r = _findCodebookItemRow(_cutCode);
        if (r) {
          r.classList.add("ace-code-row--ghost");
        } else {
          _setCut(null);
          window._setStatus("Cut cleared (item removed)", "ok");
        }
      }
      _rerenderSourceGridIfPresent();

      // Restore focus state
      let search = document.getElementById("code-search-input");
      if (_sidebarFocusState.searchText && search) {
        search.value = _sidebarFocusState.searchText;
        search.dispatchEvent(new Event("input", { bubbles: true }));
      }

      // Scroll already restored in _syncSidebarAfterSwap.

      if (_sidebarFocusState.zone === "tree") {
        let item = null;
        if (_sidebarFocusState.codeId) {
          item = _findCodebookItemRow(_sidebarFocusState.codeId);
        } else if (_sidebarFocusState.folderId) {
          item = _findCodebookItemRow(_sidebarFocusState.folderId);
        }
        if (item) {
          _focusTreeItem(item, { activate: false });
        } else {
          const items = _getTreeItems();
          if (items.length > 0) _focusTreeItem(items[0], { activate: false });
        }
      } else if (_sidebarFocusState.zone === "search" && search) {
        search.focus();
      }

      // Reset sidebar state
      _sidebarFocusState.codeId = null;
      _sidebarFocusState.folderId = null;
      _sidebarFocusState.searchText = "";
      _sidebarFocusState.zone = null;
    }

    // Auto-open dialogs
    if (target.id === "modal-container") {
      const dialog = target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
      if (dialog && typeof window._aceInitCodebookImportDialog === "function") {
        window._aceInitCodebookImportDialog(dialog);
      }
    }
  });

  // Inject current_index into flag hidden trigger requests
  document.addEventListener("htmx:configRequest", function (e) {
    const elt = e.detail.elt;
    if (!elt || !elt.id) return;

    if (elt.id === "trigger-flag") {
      e.detail.parameters.current_index = window.__aceCurrentIndex;
      e.detail.parameters.source_index = window.__aceCurrentIndex;
    }
  });

  // ace-navigate event from HX-Trigger header
  document.addEventListener("ace-navigate", function (e) {
    // Spec §3.5.3 — cut state is per-source. When the user navigates
    // between sources (Shift+←/→ etc.) the pending cut is dropped so
    // a stale ⌘V on a different source can't move the wrong code.
    if (typeof _setCut === "function") {
      _setCut(null);
    }
    _clearCodeCues();
    const detail = e.detail || {};
    if (detail.index !== undefined) {
      window.__aceCurrentIndex = parseInt(detail.index, 10);
    }
    if (detail.total !== undefined) {
      window.__aceTotalSources = parseInt(detail.total, 10);
    }
    window.__aceFocusIndex = -1;
    const input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
    // Reset scroll position for new source
    const cs = document.getElementById("text-scroll") || document.getElementById("content-scroll");
    if (cs) cs.scrollTop = 0;
    // Sync URL so a refresh lands on the same source as the visible panel.
    // Used by cross-source undo/redo, where the server swaps the body but
    // the page never reloads.
    try {
      history.replaceState({}, "", "/code?index=" + window.__aceCurrentIndex);
    } catch (_) {}
  });

  /* ================================================================
   * 13. Code management helpers
   * ================================================================ */

  let _menuOpen = false;
  let _lastSelectedCodeId = null;

  // Cut/paste state for the codebook sidebar (⌘X / ⌘V).
  // `_cutCode` holds the id of the codebook item currently flagged for paste;
  // the matching row carries `.ace-code-row--ghost` so the user sees what's cut.
  // Cleared on paste, on Esc, or when a sibling write swaps the sidebar.
  let _cutCode = null;

  function _findCodebookItemRow(itemId) {
    if (!itemId) return null;
    const controller = _getSidebarTreeController();
    const root = controller && typeof controller.rootElement === "function"
      ? controller.rootElement()
      : null;
    if (root) {
      const row = root.querySelector(
        `.ace-code-row[data-code-id="${itemId}"], .ace-code-folder-row[data-folder-id="${itemId}"], .ace-ht-row[data-item-id="${itemId}"]`
      );
      if (row) return row;
    }
    return document.querySelector(
      `.ace-code-row[data-code-id="${itemId}"], .ace-code-folder-row[data-folder-id="${itemId}"], .ace-ht-row[data-item-id="${itemId}"]`
    );
  }

  function _codebookRowLabel(row) {
    const label = row?.querySelector?.(".ace-code-name, .ace-folder-label, .ace-ht-label");
    return label ? label.textContent.trim() : "";
  }

  function _codebookFolderRows() {
    return Array.from(
      document.querySelectorAll(".ace-code-folder-row, .ace-ht-row[data-kind='folder']")
    );
  }

  function _startCodebookRename(row) {
    if (_denyCodebookEditing()) return;
    if (!row) return;
    const itemId = _itemIdFromTreeElement(row);
    const controller = _getSidebarTreeController();
    if (
      itemId &&
      row.classList.contains("ace-ht-row") &&
      controller &&
      typeof controller.startRenaming === "function"
    ) {
      controller.startRenaming(itemId);
      return;
    }
    _startInlineRename(row, { isFolder: _isFolderRow(row) });
  }

  function _setCut(codeId) {
    if (_cutCode) {
      const old = _findCodebookItemRow(_cutCode);
      if (old) old.classList.remove("ace-code-row--ghost");
    }
    _cutCode = codeId;
    if (codeId) {
      const row = _findCodebookItemRow(codeId);
      if (row) row.classList.add("ace-code-row--ghost");
    }
  }

  let _activeColourPopover = null;

  function _closeColourPopover() {
    if (_activeColourPopover) {
      _activeColourPopover.remove();
      _activeColourPopover = null;
    }
    document.removeEventListener("click", _onColourOutsideClick);
    document.removeEventListener("keydown", _onColourEscape);
  }

  function _openColourPopover(codeId) {
    if (_denyCodebookEditing()) return;
    _closeAllPopovers();
    let row = _findCodebookItemRow(codeId);
    if (!row) return;
    const rect = row.getBoundingClientRect();

    const popover = document.createElement("div");
    popover.className = "ace-colour-popover";

    const palette = Array.isArray(window.__aceColourPalette) ? window.__aceColourPalette : [];
    palette.forEach(function (hex) {
      if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) return;
      const swatch = document.createElement("button");
      swatch.className = "ace-colour-swatch";
      swatch.style.background = hex;
      swatch.addEventListener("click", function () {
        _closeAllPopovers();
        htmx.ajax("PUT", `/api/codes/${codeId}`, {
          ..._codebookMutationSwapOptions(),
          values: {
            colour: hex,
            current_index: window.__aceCurrentIndex || 0,
          },
        });
      });
      popover.appendChild(swatch);
    });

    document.body.appendChild(popover);
    _activeColourPopover = popover;

    popover.style.top = `${rect.bottom + 4}px`;
    popover.style.left = rect.left + "px";

    setTimeout(function () {
      document.addEventListener("click", _onColourOutsideClick);
      document.addEventListener("keydown", _onColourEscape);
    }, 0);
  }

  function _onColourOutsideClick(e) {
    if (_activeColourPopover && !_activeColourPopover.contains(e.target)) _closeColourPopover();
  }

  function _onColourEscape(e) {
    if (e.key === "Escape") _closeColourPopover();
  }

  // Right-click contextmenu wiring lives in section 14 below
  // (`_renderContextMenu` dispatcher). The colour popover is reachable from
  // the new menu via "Change colour…".

  function _closeAllPopovers() {
    _closeCodeMenu();
    _closeColourPopover();
  }

  function _refreshSidebar() {
    htmx.ajax("POST", "/api/codes/reorder", {
      target: "#code-sidebar",
      swap: "outerHTML",
      values: _codebookMutationValues({
        code_ids: "[]",
        current_index: window.__aceCurrentIndex,
      }),
    }).then(function () {
      _syncSidebarAfterSwap({ sortable: true });
    });
  }

  function _codeAction(method, url, body) {
    if (_denyCodebookEditing()) return Promise.resolve();
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body,
    }).then(function (r) {
      if (!r.ok) { window._setStatus("Action failed", "err"); return Promise.reject(); }
      _refreshSidebar();
    });
  }

  function _startInlineRename(elementOrId, opts) {
    if (_denyCodebookEditing()) return;
    opts = opts || {};
    const isFolder = !!opts.isFolder;
    let row;
    if (typeof elementOrId === "string") {
      // String → code id. Folder rename always passes the row element.
      row = document.querySelector(`.ace-code-row[data-code-id="${elementOrId}"]`);
    } else {
      row = elementOrId;
    }
    if (!row) return;
    const nameEl = isFolder
      ? row.querySelector(".ace-folder-label")
      : row.querySelector(".ace-code-name");
    if (!nameEl) return;
    const targetId = isFolder
      ? row.getAttribute("data-folder-id")
      : row.getAttribute("data-code-id");
    if (!targetId) return;

    const original = nameEl.textContent;
    nameEl.contentEditable = "true";
    nameEl.focus();

    const range = document.createRange();
    range.selectNodeContents(nameEl);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    let done = false;
    function clearRenameState() {
      nameEl.removeAttribute("contenteditable");
      const selection = window.getSelection && window.getSelection();
      if (selection && selection.rangeCount) {
        const range = selection.getRangeAt(0);
        if (nameEl.contains(range.commonAncestorContainer)) selection.removeAllRanges();
      }
    }

    function cancel(restoreFocus) {
      if (done) return;
      done = true;
      nameEl.textContent = original;
      clearRenameState();
      if (restoreFocus) {
        _focusTreeItem(row);
      } else {
        clearInactiveSelection();
      }
    }

    function clearInactiveSelection() {
      row.setAttribute("tabindex", "-1");
      if (document.activeElement === row) row.blur();
      _setActiveZone("source");
    }

    function save(restoreFocus) {
      if (done) return;
      done = true;
      const newName = nameEl.textContent.trim();
      clearRenameState();
      if (!newName || newName === original) {
        nameEl.textContent = original;
        if (restoreFocus) _focusTreeItem(row);
        else clearInactiveSelection();
        return;
      }
      _codeAction("PUT", `/api/codes/${targetId}`,
        `name=${encodeURIComponent(newName)}&current_index=${window.__aceCurrentIndex}`
      ).catch(function () { nameEl.textContent = original; });
      if (restoreFocus) _focusTreeItem(row);
      else clearInactiveSelection();
    }

    nameEl.addEventListener("keydown", function handler(e) {
      if (e.key === "Enter") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); save(true); }
      if (e.key === "Escape") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); cancel(true); }
    });

    nameEl.addEventListener("blur", function blurHandler() {
      nameEl.removeEventListener("blur", blurHandler);
      setTimeout(function () { save(false); }, 50);
    });

    nameEl.addEventListener("paste", function pasteHandler(e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text.replace(/\n/g, " "));
    });
  }

  // _startGroupRename was removed: folders share the PUT /api/codes/{id}
  // route with codes, preserving `kind='folder'`.

  document.addEventListener("dblclick", function (e) {
    const nameEl = e.target.closest(".ace-code-name, .ace-folder-label");
    if (!nameEl) return;
    if (_denyCodebookEditing()) return;
    const row = nameEl.closest(".ace-code-row, .ace-code-folder-row");
    if (!row) return;
    if (row.classList.contains("ace-code-folder-row")) {
      _startInlineRename(row, { isFolder: true });
      return;
    }
    const codeId = row.getAttribute("data-code-id");
    if (codeId) _startInlineRename(codeId);
  });

  function _executeDelete(codeId) {
    if (_denyCodebookEditing()) return;
    _lastSelectedCodeId = null;
    // Route the response through HTMX (not _codeAction's plain fetch) so the
    // OOB statusbar/pill fragments carrying the [Z] undo affordance get
    // applied to the page. current_index goes in the URL — htmx.ajax's
    // `values` ride in the request body for DELETE, but the route reads
    // current_index via Query, so a body-borne value would be ignored.
    const query = _codebookMutationQueryString({
      current_index: window.__aceCurrentIndex || 0,
    });
    htmx.ajax("DELETE", `/api/codes/${codeId}?${query}`, {
      ..._codebookMutationSwapOptions(),
    });
  }

  function _moveCode(codeId, direction) {
    if (_denyCodebookEditing()) return;
    const controller = _getSidebarTreeController();
    if (controller && typeof controller.moveItemInDirection === "function") {
      const row = _findCodebookItemRow(codeId);
      if (row && controller.rootElement && controller.rootElement()?.contains(row)) {
        controller.moveItemInDirection(codeId, direction);
        return;
      }
    }
    const row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    const container = row ? row.parentElement : null;
    if (!row || !container) return;

    function isSiblingItem(el) {
      return el && el.classList && el.classList.contains("ace-code-row");
    }

    if (direction === -1) {
      let prev = row.previousElementSibling;
      while (prev && !isSiblingItem(prev)) prev = prev.previousElementSibling;
      if (!prev) return;
      container.insertBefore(row, prev);
    } else {
      let next = row.nextElementSibling;
      while (next && !isSiblingItem(next)) next = next.nextElementSibling;
      if (!next) return;
      container.insertBefore(row, next.nextElementSibling);
    }
    _persistScopeOrder(container);
  }

  // _moveToGroup was removed: PUT /api/codes/{id} no longer accepts
  // `group_name` (v7 dropped that column in favour of parent_id). Code/folder
  // re-parenting will be wired in Task 9 against PUT /api/codes/{id}/parent.

  let _isDragging = false;

  function _initSortable() {
    if (_codebookEditingDisabled()) return;
    const controller = _getSidebarTreeController();
    if (controller && typeof controller.initSortable === "function") {
      controller.initSortable({
        Sortable: typeof Sortable === "undefined" ? undefined : Sortable,
        onDragStateChange: function (dragging) {
          _isDragging = dragging;
        },
        onInvalidDrop: function () {
          _refreshSidebar();
          window._setStatus("A folder cannot move inside itself", "err");
        },
        onMoveParent: function (itemId, newParentId, targetOrderIds) {
          htmx.ajax("PUT", "/api/codes/" + itemId + "/parent", {
            ..._codebookMutationSwapOptions(),
            values: _codebookMutationValues({
              parent_id: newParentId,
              target_order_ids: JSON.stringify(targetOrderIds || []),
              current_index: window.__aceCurrentIndex,
            }),
          });
        },
        onPersistScopeOrder: _persistScopeOrder,
      });
      return;
    }
  }

  /* ================================================================
   * 14. Right-click context menu (Task 12)
   * ----------------------------------------------------------------
   * Mouse-discovery surface for the keyboard codebook gestures. Three
   * menu shapes:
   *   - code row: Move to folder \u25b8, Move to root, Convert to folder,
   *     Cut, Paste here, Rename, Change colour\u2026, View coded text, Delete
   *   - folder row: Rename, Cut, Paste here, Delete folder
   *   - empty area of the tree: New folder, Paste here
   *
   * Submenus (Move to folder \u25b8) render in-place: clicking the parent
   * item REPLACES the menu's contents with the submenu items, prefixed
   * by a "\u2190 Back" item that returns to the parent menu. No hover-open,
   * no nested floating panel \u2014 keeps positioning logic trivial.
   *
   * Each menu item delegates to existing helpers (`_startInlineRename`,
   * `_setCut`, `_openColourPopover`, `_executeDelete`, etc.) so behaviour
   * matches the keyboard gestures exactly: same API endpoints, same
   * undo entries.
   * ================================================================ */

  let _activeCodeMenu = null;

  function _closeCodeMenu() {
    if (_activeCodeMenu) {
      _activeCodeMenu.remove();
      _activeCodeMenu = null;
      _menuOpen = false;
    }
    document.removeEventListener("click", _onMenuOutsideClick);
    // Capture flag MUST match the addEventListener call below (line ~2230)
    // — without it, removeEventListener silently does nothing and we leak one
    // listener per menu open.
    document.removeEventListener("keydown", _onMenuEscape, true);
  }

  function _onMenuOutsideClick(e) {
    if (_activeCodeMenu && !_activeCodeMenu.contains(e.target)) _closeCodeMenu();
  }

  function _onMenuEscape(e) {
    if (e.key === "Escape") {
      e.stopPropagation();
      e.preventDefault();
      _closeCodeMenu();
    }
  }

  // --- Helpers for menu actions (Task 12) ---

  /** Move a code into the named folder via PUT /api/codes/{id}/parent. */
  function _moveCodeToFolder(codeId, folderId) {
    if (_denyCodebookEditing()) return;
    if (!codeId || !folderId) return;
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        parent_id: folderId,
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  }

  /** Move an item back to root (empty parent_id). */
  function _moveCodeToRoot(codeId) {
    if (_denyCodebookEditing()) return;
    if (!codeId) return;
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        parent_id: "",
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  }

  /** Paste the cut item onto a code row (target_id is a code id). */
  function _pasteCodeInto(targetId) {
    if (_denyCodebookEditing()) return;
    if (!_cutCode || !targetId || targetId === _cutCode) return;
    const cutId = _cutCode;
    htmx.ajax("POST", "/api/codes/cut-paste", {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        code_id: cutId,
        target_id: targetId,
        current_index: window.__aceCurrentIndex || 0,
      }),
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  }

  /** Paste the cut item into a folder (target_id is a folder id; "" = root). */
  function _pasteCodeIntoFolder(folderId) {
    if (_denyCodebookEditing()) return;
    if (!_cutCode) return;
    const cutId = _cutCode;
    htmx.ajax("POST", "/api/codes/cut-paste", {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        code_id: cutId,
        target_id: folderId || "",
        current_index: window.__aceCurrentIndex || 0,
      }),
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  }

  function _convertCodeToFolder(codeId) {
    if (_denyCodebookEditing()) return;
    if (!codeId) return;
    htmx.ajax("POST", `/api/codes/${codeId}/convert-to-folder`, {
      ..._codebookMutationSwapOptions(),
      values: { current_index: window.__aceCurrentIndex || 0 },
    });
  }

  /** Focus the filter input and prompt the user to create a folder.
   *  Simpler than chaining "create + auto-move" \u2014 user types the name and
   *  hits Shift+Enter (existing handler in section 15). If `forCodeId` is
   *  set we just hint that the next step (cut/paste) is on them. */
  function _promptNewFolder(forCodeId) {
    if (_denyCodebookEditing()) return;
    const input = document.getElementById("code-search-input");
    if (!input) return;
    input.focus();
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    if (forCodeId) {
      _announce("Type folder name + Shift+Enter, then \u2318X / \u2318V to move the code in.");
      window._setStatus("Type name + Shift+Enter to create folder", "ok");
    } else {
      _announce("Type folder name + Shift+Enter to create.");
      window._setStatus("Type name + Shift+Enter to create folder", "ok");
    }
  }

  // --- Menu builders ---

  function _buildCodeRowMenu(row) {
    const codeId = _itemIdFromTreeElement(row);
    if (_codebookEditingDisabled()) {
      return [{
        label: "View coded text",
        shortcut: "V",
        handler: function () {
          try { sessionStorage.setItem("cv-restore-codebook-focus", "1"); } catch (_) {}
          window.location.href = `/code/${codeId}/view`;
        },
      }];
    }
    const inFolder = !!_parentFolderRow(row);
    const folders = _codebookFolderRows()
      .map(function (f) {
        return {
          id: _itemIdFromTreeElement(f),
          name: _codebookRowLabel(f) || "(folder)",
        };
      })
      .filter(function (f) { return f.id; });

    const items = [];

    if (folders.length > 0) {
      items.push({
        label: "Move to folder",
        submenu: folders.map(function (f) {
          return {
            label: f.name,
            handler: function () { _moveCodeToFolder(codeId, f.id); },
          };
        }).concat([
          { sep: true },
          { label: "New folder\u2026", handler: function () { _promptNewFolder(codeId); } },
        ]),
      });
    } else {
      items.push({
        label: "Move to new folder\u2026",
        handler: function () { _promptNewFolder(codeId); },
      });
    }

    if (inFolder) {
      items.push({
        label: "Move to root",
        shortcut: "\u2325\u2190",
        handler: function () { _moveCodeToRoot(codeId); },
      });
    }
    items.push({ sep: true });
    items.push({
      label: "Convert to folder",
      handler: function () { _convertCodeToFolder(codeId); },
    });
    items.push({
      label: "Cut",
      shortcut: "\u2318X",
      handler: function () {
        _setCut(codeId);
        const name = _codebookRowLabel(row) || "code";
        _announce(`Cut ${name}.`);
        window._setStatus(`Cut: ${name} \u00b7 \u2318V to paste \u00b7 Esc to cancel`, "ok-sticky");
      },
    });
    items.push({
      label: "Paste here",
      shortcut: "\u2318V",
      disabled: !_cutCode || _cutCode === codeId,
      handler: function () { _pasteCodeInto(codeId); },
    });
    items.push({ sep: true });
    items.push({
      label: "Rename",
      shortcut: "F2",
      handler: function () { _startCodebookRename(row); },
    });
    items.push({
      label: "Change colour\u2026",
      handler: function () { _openColourPopover(codeId); },
    });
    items.push({
      label: "View coded text",
      shortcut: "V",
      handler: function () {
        try { sessionStorage.setItem("cv-restore-codebook-focus", "1"); } catch (_) {}
        window.location.href = `/code/${codeId}/view`;
      },
    });
    items.push({
      label: "Delete",
      shortcut: "\u232b",
      handler: function () { _executeDelete(codeId); },
    });
    return items;
  }

  function _buildFolderRowMenu(folderRow) {
    if (_codebookEditingDisabled()) return [];
    const folderId = _itemIdFromTreeElement(folderRow);
    const name = _codebookRowLabel(folderRow) || "folder";
    return [
      {
        label: "Rename folder",
        shortcut: "F2",
        handler: function () { _startCodebookRename(folderRow); },
      },
      {
        label: "Cut",
        shortcut: "\u2318X",
        handler: function () {
          _setCut(folderId);
          _announce(`Cut ${name}.`);
          window._setStatus(`Cut: ${name} · \u2318V to paste · Esc to cancel`, "ok-sticky");
        },
      },
      {
        label: "Paste here",
        shortcut: "\u2318V",
        disabled: !_cutCode || _cutCode === folderId,
        handler: function () { _pasteCodeIntoFolder(folderId); },
      },
      { sep: true },
      {
        label: "Delete folder",
        shortcut: "\u232b",
        handler: function () { _executeDelete(folderId); },
      },
    ];
  }

  function _buildEmptyAreaMenu() {
    if (_codebookEditingDisabled()) return [];
    return [
      {
        label: "New folder",
        shortcut: "\u21e7Enter",
        handler: function () { _promptNewFolder(null); },
      },
      {
        label: "Paste here",
        shortcut: "\u2318V",
        disabled: !_cutCode,
        handler: function () { _pasteCodeIntoFolder(""); },
      },
    ];
  }

  /** Replace the active context menu's items in-place. Used by submenu
   *  navigation so the menu position stays put and there's no nested
   *  floating panel to track. */
  function _populateContextMenu(menu, items) {
    while (menu.firstChild) menu.removeChild(menu.firstChild);
    items.forEach(function (it) {
      if (it.sep) {
        const sep = document.createElement("div");
        sep.className = "ace-context-menu-sep";
        menu.appendChild(sep);
        return;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ace-context-menu-item";
      if (it.submenu) btn.classList.add("ace-context-menu-submenu");
      btn.textContent = it.label;
      if (it.shortcut) {
        const k = document.createElement("span");
        k.className = "ace-context-menu-shortcut";
        k.textContent = it.shortcut;
        btn.appendChild(k);
      }
      if (it.disabled) btn.disabled = true;
      btn.addEventListener("click", function (ev) {
        if (it.disabled) return;
        if (it.submenu) {
          ev.preventDefault();
          ev.stopPropagation();
          // In-place submenu: replace items, prefix with a Back row that
          // restores the parent menu. Back has keepOpen so it doesn't fall
          // through to _closeCodeMenu after running its handler.
          const backed = [{
            label: "\u2190 Back",
            keepOpen: true,
            handler: function () { _populateContextMenu(menu, items); },
          }, { sep: true }].concat(it.submenu);
          _populateContextMenu(menu, backed);
          return;
        }
        if (it.handler) it.handler();
        if (it.keepOpen) return;
        _closeCodeMenu();
      });
      menu.appendChild(btn);
    });
  }

  function _renderContextMenu(items, x, y) {
    _closeAllPopovers();
    _menuOpen = true;
    const menu = document.createElement("div");
    menu.className = "ace-context-menu";
    menu.setAttribute("role", "menu");
    document.body.appendChild(menu);
    _activeCodeMenu = menu;

    _populateContextMenu(menu, items);

    // Position: prefer requested x/y, but flip if it would overflow the
    // viewport. offsetWidth/Height require the element be in the DOM,
    // so we appended first.
    const mw = menu.offsetWidth, mh = menu.offsetHeight;
    const left = x + mw > window.innerWidth ? Math.max(0, x - mw) : x;
    const top = y + mh > window.innerHeight ? Math.max(0, y - mh) : y;
    menu.style.left = left + "px";
    menu.style.top = top + "px";

    setTimeout(function () {
      document.addEventListener("click", _onMenuOutsideClick);
      document.addEventListener("keydown", _onMenuEscape, true);
    }, 0);
  }

  // Single contextmenu dispatcher for the codebook sidebar. Replaces the
  // previous two listeners (colour popover + old code menu).
  document.addEventListener("contextmenu", function (e) {
    if (!e.target.closest || !e.target.closest("#code-sidebar")) return;
    let items;
    const codeRow = e.target.closest(".ace-code-row, .ace-ht-row[data-kind='code']");
    const folderRow = e.target.closest(".ace-code-folder-row, .ace-ht-row[data-kind='folder']");
    if (codeRow) {
      items = _buildCodeRowMenu(codeRow);
    } else if (folderRow) {
      items = _buildFolderRowMenu(folderRow);
    } else if (e.target.closest("#ace-headless-tree-mount")) {
      items = _buildEmptyAreaMenu();
    } else {
      return;
    }
    if (!items.length) return;
    e.preventDefault();
    e.stopPropagation();
    _renderContextMenu(items, e.clientX, e.clientY);
  });

  /** Unified apply helper used by keycap click, search Enter, and tree Enter. */
  function _applyCode(codeId) {
    if (_codeApplicationDisabled()) return false;
    // The server emits a branch-specific OOB status on /api/code/apply-sentence, which swaps into
    // #ace-statusbar-event. No client-side status message here.
    const isSelection = !!window.__aceLastSelection;
    if (isSelection) {
      return _applyCodeToSelection(codeId, null);
    } else if (window.__aceFocusIndex >= 0) {
      return _applyCodeToSentence(codeId, null);
    } else {
      return false;
    }
  }

  document.addEventListener("ace:apply-code", function (event) {
    const codeId = event.detail && event.detail.codeId;
    if (!codeId) return;
    if (_codeApplicationDisabled()) return;
    _clearSearchFilter();
    _applyCode(codeId);
  });

  document.addEventListener("ace:rename-codebook-item", function (event) {
    if (_denyCodebookEditing()) return;
    const detail = event.detail || {};
    const itemId = detail.itemId;
    const name = (detail.name || "").trim();
    if (!itemId || !name) return;
    htmx.ajax("PUT", `/api/codes/${itemId}`, {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        name: name,
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  });

  document.addEventListener("ace:delete-codebook-item", function (event) {
    if (_denyCodebookEditing()) return;
    const detail = event.detail || {};
    if (!detail.itemId) return;
    _executeDelete(detail.itemId);
  });

  // Code-chip click: apply code to focused sentence/selection
  document.addEventListener("click", function (e) {
    const chip = e.target.closest(".ace-code-chip");
    if (!chip) return;
    e.stopPropagation();
    let row = chip.closest(".ace-code-row");
    if (!row) return;
    if (row.querySelector('[contenteditable="true"]')) return;
    let codeId = row.getAttribute("data-code-id");
    if (!codeId) return;
    _clearSearchFilter();
    _applyCode(codeId);
  });

  // Click on code row (not chip): focus/select for management
  document.addEventListener("click", function (e) {
    let row = e.target.closest(".ace-code-row");
    if (!row) return;
    if (e.target.closest(".ace-code-chip")) return;
    if (e.target.closest(".ace-code-menu") || _isDragging) return;
    if (e.target.isContentEditable) return;
    _focusTreeItem(row);
  });

  /** Clear the search filter input and trigger the input handler to restore all rows. */
  function _clearSearchFilter() {
    let el = document.getElementById("code-search-input");
    if (!el) return;
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  /* ================================================================
   * 15. Code search / filter / create
   * ================================================================ */

  // Codebook search and create-on-search are owned by codebook_headless_tree_source.js.


  // Esc-to-source: when focus is anywhere inside the codebook sidebar that is
  // NOT already handled by the search input / tree keydown handlers (e.g. on
  // the help button, codebook dropdown trigger, or a sidebar-hosted button),
  // Esc returns focus to #text-panel. Bound at capture phase so it runs
  // before the (bubbling-phase) generic Esc cascade in the global keydown
  // handler — but explicitly defers to:
  //   * `#code-search-input` — its own Esc handler clears the filter first
  //   * treeitems — the tree keydown handler at the bottom of this IIFE
  //   * any contentEditable / input / textarea element — inline rename
  //     and chord-edit need Esc to revert their local state.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    const t = e.target;
    if (!t || !t.closest) return;
    if (!t.closest("#code-sidebar")) return;
    // Cut state takes priority over the focus-shift: if a code is flagged
    // for paste (⌘X), Esc clears it without moving focus. Runs before the
    // treeitem / input / contentEditable bail-outs so the cancellation works
    // from any sidebar element.
    if (_cutCode) {
      _setCut(null);
      _announce("Cut cleared.");
      window._setStatus("", "ok");
      e.stopPropagation();
      e.preventDefault();
      return;
    }
    if (t.id === "code-search-input") return;
    if (t.getAttribute && t.getAttribute("role") === "treeitem") return;
    if (t.isContentEditable) return;
    const tag = (t.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    // stopPropagation so this Esc doesn't ALSO fire the bubble-phase
    // Esc cascade (which would close any open dialog / clear text
    // selection / step out of note-drawer edit mode after focus lands
    // on text-panel).
    e.stopPropagation();
    e.preventDefault();
    const tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  }, true);

  // ⌘X / Ctrl+X — cut a focused code row; ⌘V / Ctrl+V — paste it onto the
  // focused folder/code row. Bound at document level so it fires regardless
  // of which sidebar element holds focus, but early-returns if focus is
  // inside an input / textarea / contenteditable so native cut/paste keeps
  // working in the filter input and inline-rename caret.
  document.addEventListener("keydown", function (e) {
    if (!(e.metaKey || e.ctrlKey)) return;
    const key = e.key.toLowerCase();
    if (key !== "x" && key !== "v") return;

    // Skip if focus is in any editable text — covers inline rename
    // (contenteditable), the filter <input>, and any textarea.
    const ae = document.activeElement;
    if (ae && (ae.isContentEditable || ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) {
      return;
    }

    if (key === "x") {
      // Skip if the user has a text selection (default cut behaviour wins).
      const sel = window.getSelection();
      if (sel && sel.toString().length > 0) return;
      if (!(e.target.closest && e.target.closest("#code-sidebar"))) return;
      if (_denyCodebookEditing()) {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      const row = e.target.closest(".ace-code-row, .ace-code-folder-row, .ace-ht-row");
      if (!row) {
        return;
      }
      const codeId = _itemIdFromTreeElement(row);
      const nameEl = row.querySelector(".ace-code-name, .ace-folder-label, .ace-ht-label");
      const name = nameEl ? nameEl.textContent : "item";
      _setCut(codeId);
      _announce(`Cut ${name}.`);
      // Sticky status bar mirror so sighted users see the cut state even
      // when they scroll away from the ghosted row. "ok-sticky" is a kind
      // _setStatus does NOT auto-clear (only "ok" fades).
      window._setStatus(`Cut: ${name} · ⌘V to paste · Esc to cancel`, "ok-sticky");
      return;
    }

    // key === "v"
    if (!_cutCode) return;
    if (!(e.target.closest && e.target.closest("#code-sidebar"))) return;
    if (_denyCodebookEditing()) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    // Paste while focus is in the filter input is already filtered above by
    // the INPUT guard, but if some other non-row sidebar element has focus
    // we still want a useful announcement.
    if (e.target.id === "code-search-input") {
      _announce("Focus a code or folder row first.");
      window._setStatus("Focus a code or folder row first", "err");
      return;
    }
    const targetRow = e.target.closest(".ace-code-row, .ace-code-folder-row, .ace-ht-row");
    let targetId = null;
    if (targetRow) {
      targetId = _itemIdFromTreeElement(targetRow);
    }
    if (!targetId) {
      _announce("Focus a code or folder row first.");
      window._setStatus("Focus a code or folder row first", "err");
      return;
    }
    if (targetId === _cutCode) {
      _announce("Already there — press Esc to clear cut.");
      return;
    }
    const cutId = _cutCode;
    htmx.ajax("POST", "/api/codes/cut-paste", {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        code_id: cutId,
        target_id: targetId,
        current_index: window.__aceCurrentIndex,
      }),
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  });

  function _persistScopeOrder(container, orderedIds) {
    if (_denyCodebookEditing()) return;
    if (!container) return;
    const ids = Array.isArray(orderedIds) ? orderedIds : _directChildItemIds(container);
    const parentId = container.getAttribute("data-folder-children") || "";
    htmx.ajax("POST", "/api/codes/reorder-in-scope", {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        code_ids: JSON.stringify(ids),
        parent_id: parentId,
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  }

  // _makeGroupElements was removed: only consumers were the deleted
  // _createGroupFromSearch and _promptNewGroupForCode helpers.

  /* ================================================================
   * 16. SVG overlay — annotation rendering
   * ================================================================ */

  /**
   * Build a flat list of {node, sourceStart, sourceEnd} entries
   * for all text nodes inside sentence spans in the text panel.
   */
  function _buildTextIndex(container) {
    let index = [];
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      let sentence = node.parentElement.closest(".ace-sentence");
      if (!sentence) continue;
      const sentStart = parseInt(sentence.dataset.start, 10);
      if (isNaN(sentStart)) continue;

      let charsBefore = 0;
      const tw = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
      let t;
      while ((t = tw.nextNode())) {
        if (t === node) break;
        charsBefore += t.textContent.length;
      }

      const nodeSourceStart = sentStart + charsBefore;
      index.push({
        node: node,
        sourceStart: nodeSourceStart,
        sourceEnd: nodeSourceStart + node.textContent.length,
      });
    }
    return index;
  }

  /**
   * Find the DOM position (node + offset) for a source character offset.
   */
  function _findDOMPosition(textIndex, sourceOffset) {
    for (let i = 0; i < textIndex.length; i++) {
      const entry = textIndex[i];
      if (sourceOffset >= entry.sourceStart && sourceOffset <= entry.sourceEnd) {
        return { node: entry.node, offset: sourceOffset - entry.sourceStart };
      }
    }
    return null;
  }

  // Rect-merge tuning.
  // CONTAIN_SLOP is in pixels — the tolerance for "rect A strictly contains rect B"
  // when deduplicating block-element and inline-text rects that overlap.
  // LINE_OVERLAP_RATIO is a proportion — two rects are considered to be on the
  // same visual line when their vertical extents overlap by at least this much
  // of the smaller rect's height.
  const CONTAIN_SLOP = 0.5;
  const LINE_OVERLAP_RATIO = 0.5;

  function _paraBreakRects(body) {
    return Array.from(body.querySelectorAll(".ace-para-break")).map(function (el) {
      return el.getBoundingClientRect();
    });
  }

  /**
   * Merge DOMRectList entries from a Range into per-visual-line rects.
   * Steps:
   *   1. Drop rects whose vertical extent is fully contained within any
   *      .ace-para-break element — WebKit's getClientRects() emits a rect
   *      for block-level elements the range crosses, producing a phantom
   *      highlight in the inter-paragraph gap for cross-paragraph ranges.
   *   2. Drop any rect that strictly contains another rect — kills duplicate
   *      `display: block` element rects when a Range fully contains a list item.
   *   3. Per-line union — sort by top, group rects whose vertical extents
   *      overlap by at least LINE_OVERLAP_RATIO of the smaller height, union
   *      left/right/top/bottom per group. This collapses sub-pixel gaps at
   *      sentence boundaries.
   */
  function _mergeRectsByLine(rects, paraBreakRects) {
    const PARA_SLOP = 1;
    const validInitial = Array.from(rects).filter(function (r) {
      return r.width >= 1 && r.height >= 1;
    });
    const valid = (paraBreakRects && paraBreakRects.length)
      ? validInitial.filter(function (r) {
          return !paraBreakRects.some(function (br) {
            return r.top >= br.top - PARA_SLOP && r.bottom <= br.bottom + PARA_SLOP;
          });
        })
      : validInitial;

    // Step 1: drop any rect that strictly contains another
    const nonContaining = valid.filter(function (r, i) {
      return !valid.some(function (other, j) {
        if (i === j) return false;
        const contains =
          r.left <= other.left + CONTAIN_SLOP &&
          r.top <= other.top + CONTAIN_SLOP &&
          r.right >= other.right - CONTAIN_SLOP &&
          r.bottom >= other.bottom - CONTAIN_SLOP;
        const sameRect =
          Math.abs(r.left - other.left) <= CONTAIN_SLOP &&
          Math.abs(r.top - other.top) <= CONTAIN_SLOP &&
          Math.abs(r.right - other.right) <= CONTAIN_SLOP &&
          Math.abs(r.bottom - other.bottom) <= CONTAIN_SLOP;
        return contains && !sameRect;
      });
    });

    // Step 2: per-line union via Y-overlap
    const sorted = nonContaining.sort(function (a, b) {
      return a.top - b.top || a.left - b.left;
    });
    const lines = [];
    for (const r of sorted) {
      let line = null;
      for (const ln of lines) {
        const overlap = Math.min(ln.bottom, r.bottom) - Math.max(ln.top, r.top);
        const minH = Math.min(ln.bottom - ln.top, r.bottom - r.top);
        if (overlap >= minH * LINE_OVERLAP_RATIO) {
          line = ln;
          break;
        }
      }
      if (line) {
        line.left = Math.min(line.left, r.left);
        line.right = Math.max(line.right, r.right);
        line.top = Math.min(line.top, r.top);
        line.bottom = Math.max(line.bottom, r.bottom);
      } else {
        lines.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right });
      }
    }
    return lines;
  }

  // ResizeObserver state — single observer re-attached after each paint.
  let _resizeObserver = null;
  let _paintRaf = null;
  let _observedBody = null;

  // Flash cleanup timeout — module-level so rapid flashes (chip click,
  // undo/redo restore) can cancel any pending cleanup before scheduling
  // the next one.
  let _flashTimeout = null;
  const FLASH_CLEANUP_MS = 1500;

  // Paint SVG flash rects for the given annotations into #ace-hl-overlay,
  // scroll the first into view, and schedule a cleanup. Used by both the
  // chip-click "flash all annotations of this code" path and the per-id
  // restore-after-undo path. Annotations are objects with {start, end,
  // code_id} (and optionally id; not used for rendering).
  function _renderFlashRects(annotations) {
    if (!annotations || !annotations.length) return;
    const body = document.querySelector(".ace-text-body");
    const svg = document.getElementById("ace-hl-overlay");
    if (!body || !svg) return;

    if (_flashTimeout) {
      clearTimeout(_flashTimeout);
      _flashTimeout = null;
    }
    svg.querySelectorAll("rect.ace-flash").forEach(function (el) { el.remove(); });

    const textIndex = _buildTextIndex(body);
    if (!textIndex.length) return;
    const paraBreakRects = _paraBreakRects(body);
    const overlayRect = svg.getBoundingClientRect();

    let firstRange = null;
    for (const ann of annotations) {
      const startPos = _findDOMPosition(textIndex, ann.start);
      const endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;
      let range;
      try {
        range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);
      } catch (err) {
        continue;
      }
      if (!firstRange) firstRange = range;
      for (const line of _mergeRectsByLine(range.getClientRects(), paraBreakRects)) {
        const x = Math.floor(line.left - overlayRect.left);
        const y = Math.floor(line.top - overlayRect.top);
        const right = Math.ceil(line.right - overlayRect.left);
        const bottom = Math.ceil(line.bottom - overlayRect.top);
        const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        el.setAttribute("class", "ace-flash ace-flash-" + ann.code_id);
        el.setAttribute("fill", "transparent");
        el.setAttribute("x", x);
        el.setAttribute("y", y);
        el.setAttribute("width", right - x);
        el.setAttribute("height", bottom - y);
        svg.appendChild(el);
      }
    }

    if (firstRange) {
      const startEl = firstRange.startContainer.parentElement;
      if (startEl) startEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    _flashTimeout = setTimeout(function () {
      svg.querySelectorAll("rect.ace-flash").forEach(function (el) { el.remove(); });
      _flashTimeout = null;
    }, FLASH_CLEANUP_MS);
  }

  function _clearAppliedCodePreview() {
    const svg = document.getElementById("ace-hl-overlay");
    if (svg) {
      svg.querySelectorAll("rect.ace-code-preview").forEach(function (el) { el.remove(); });
    }
    document.querySelectorAll(".ace-applied-code-row.is-code-preview").forEach(function (row) {
      row.classList.remove("is-code-preview");
    });
    document.querySelectorAll(".ace-applied-annotation-row.is-code-preview").forEach(function (row) {
      row.classList.remove("is-code-preview");
    });
    document.querySelectorAll(".ace-applied-timeline-marker.is-code-preview").forEach(function (marker) {
      marker.classList.remove("is-code-preview");
    });
  }

  function _renderAppliedCodePreviewRects(annotations) {
    if (!annotations || !annotations.length) return;
    const body = document.querySelector(".ace-text-body");
    const svg = document.getElementById("ace-hl-overlay");
    if (!body || !svg) return;

    const textIndex = _buildTextIndex(body);
    if (!textIndex.length) return;
    const paraBreakRects = _paraBreakRects(body);
    const overlayRect = svg.getBoundingClientRect();

    for (const ann of annotations) {
      const startPos = _findDOMPosition(textIndex, ann.start);
      const endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;
      let range;
      try {
        range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);
      } catch (err) {
        continue;
      }
      for (const line of _mergeRectsByLine(range.getClientRects(), paraBreakRects)) {
        const x = Math.floor(line.left - overlayRect.left);
        const y = Math.floor(line.top - overlayRect.top);
        const right = Math.ceil(line.right - overlayRect.left);
        const bottom = Math.ceil(line.bottom - overlayRect.top);
        const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        el.setAttribute("class", "ace-code-preview ace-flash-" + ann.code_id);
        el.setAttribute("fill", "transparent");
        el.setAttribute("x", x);
        el.setAttribute("y", y);
        el.setAttribute("width", right - x);
        el.setAttribute("height", bottom - y);
        svg.appendChild(el);
      }
    }
  }

  function _setAppliedCodePreview(codeId) {
    _clearAppliedCodePreview();
    if (!codeId) return;
    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    let matching;
    try {
      matching = JSON.parse(dataEl.dataset.annotations || "[]")
        .filter(function (a) { return a.code_id === codeId; });
    } catch (err) {
      return;
    }
    document.querySelectorAll('.ace-applied-code-row[data-code-id="' + codeId + '"]').forEach(function (row) {
      row.classList.add("is-code-preview");
    });
    document.querySelectorAll('.ace-applied-timeline-marker[data-code-id="' + codeId + '"]').forEach(function (marker) {
      marker.classList.add("is-code-preview");
    });
    _renderAppliedCodePreviewRects(matching);
  }

  function _setAppliedAnnotationPreview(annotationId) {
    _clearAppliedCodePreview();
    if (!annotationId) return;
    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    let matching;
    try {
      matching = JSON.parse(dataEl.dataset.annotations || "[]")
        .filter(function (a) { return a.id === annotationId; });
    } catch (err) {
      return;
    }
    document.querySelectorAll('.ace-applied-annotation-row[data-annotation-id="' + annotationId + '"]').forEach(function (row) {
      row.classList.add("is-code-preview");
    });
    document.querySelectorAll('.ace-applied-timeline-marker[data-annotation-id="' + annotationId + '"]').forEach(function (marker) {
      marker.classList.add("is-code-preview");
    });
    _renderAppliedCodePreviewRects(matching);
  }

  window.aceSetAppliedCodePreview = _setAppliedCodePreview;
  window.aceSetAppliedAnnotationPreview = _setAppliedAnnotationPreview;
  window.aceClearAppliedCodePreview = _clearAppliedCodePreview;

  /**
   * Attach the (lazy) ResizeObserver to the current .ace-text-body element.
   * After OOB swaps replace #text-panel, this is called with the new body;
   * the reference comparison detects the swap, unobserves the detached old
   * body, and observes the new one. Paints are debounced to one per
   * animation frame via requestAnimationFrame.
   */
  function _attachResizeObserver(body) {
    if (_observedBody === body) return;
    if (!_resizeObserver) {
      _resizeObserver = new ResizeObserver(function () {
        if (_paintRaf) cancelAnimationFrame(_paintRaf);
        _paintRaf = requestAnimationFrame(function () {
          _paintSvg();
          _paintRaf = null;
        });
      });
    } else if (_observedBody) {
      _resizeObserver.unobserve(_observedBody);
    }
    _resizeObserver.observe(body);
    _observedBody = body;
  }

  /**
   * Detach the ResizeObserver from any previously-observed body and clear
   * all paint state. Called on the early-return paths in _paintSvg when the
   * text body is gone (e.g., after a swap to the excerpt-list view) so we
   * don't retain a reference to a detached DOM node.
   */
  function _detachResizeObserver() {
    if (_resizeObserver && _observedBody) {
      _resizeObserver.unobserve(_observedBody);
    }
    _observedBody = null;
    if (_paintRaf) {
      cancelAnimationFrame(_paintRaf);
      _paintRaf = null;
    }
  }

  /**
   * Paint all annotation highlights as SVG <rect> elements inside
   * #ace-hl-overlay. Reads annotation data from #ace-ann-data, builds a
   * Range per annotation, normalises getClientRects() into per-line rects,
   * and emits one <rect class="ace-hl-{cid}"> element per visual line.
   */
  function _paintSvg() {
    const body = document.querySelector(".ace-text-body");
    if (!body) { _detachResizeObserver(); return; }
    const svg = document.getElementById("ace-hl-overlay");
    if (!svg) { _detachResizeObserver(); return; }

    // Clear existing highlight rects (preserve any in-flight flash rects)
    svg.querySelectorAll('rect[data-ace-hl="1"]').forEach(function (el) { el.remove(); });
    svg.querySelectorAll("rect.ace-code-preview").forEach(function (el) { el.remove(); });

    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    const annotations = JSON.parse(dataEl.dataset.annotations || "[]");
    if (!annotations.length) {
      _attachResizeObserver(body);
      return;
    }

    // Size the SVG to match its containing block so coordinates are correct.
    const bodyBox = body.getBoundingClientRect();
    svg.setAttribute("width", bodyBox.width);
    svg.setAttribute("height", bodyBox.height);

    const overlayRect = svg.getBoundingClientRect();

    // Build the text index ONCE for all annotations — O(N+M) instead of O(N*M).
    // ResizeObserver re-fires this on every layout change, so per-annotation
    // tree walks compound quickly on large sources.
    const textIndex = _buildTextIndex(body);
    if (!textIndex.length) {
      _attachResizeObserver(body);
      return;
    }

    const paraBreakRects = _paraBreakRects(body);

    for (const ann of annotations) {
      const startPos = _findDOMPosition(textIndex, ann.start);
      const endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;
      let range;
      try {
        range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);
      } catch (e) {
        continue;
      }
      const lines = _mergeRectsByLine(range.getClientRects(), paraBreakRects);
      for (const line of lines) {
        const x = Math.floor(line.left - overlayRect.left);
        const y = Math.floor(line.top - overlayRect.top);
        const right = Math.ceil(line.right - overlayRect.left);
        const bottom = Math.ceil(line.bottom - overlayRect.top);
        const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        el.setAttribute("fill", "transparent");
        el.setAttribute("class", "ace-hl-" + ann.code_id);
        el.dataset.aceHl = "1";
        el.setAttribute("x", x);
        el.setAttribute("y", y);
        el.setAttribute("width", right - x);
        el.setAttribute("height", bottom - y);
        svg.appendChild(el);
      }
    }

    _attachResizeObserver(body);
  }

  /* ================================================================
   * 17. Sidebar keyboard navigation (ARIA treeview)
   * ================================================================ */

  /** Push a message to a live region. Polite by default; assertive=true for errors. */
  function _announce(message, assertive) {
    const id = assertive ? "ace-live-region-assertive" : "ace-live-region";
    const region = document.getElementById(id);
    if (!region) return;
    region.textContent = message;
    setTimeout(function () { region.textContent = ""; }, 3000);
  }

  // ---- Status bar helpers ----
  let _statusEventClearTimer = null;

  /** Update the ambient left segment from current DOM state. */
  function _setAmbient() {
    const el = document.querySelector(".ace-statusbar-ambient");
    if (!el) return;
    const parts = [];
    const projName = document.documentElement.dataset.aceProjectName;
    if (projName) parts.push(projName);
    const idx = window.__aceCurrentIndex;
    const total = window.__aceTotalSources;
    if (Number.isFinite(idx) && Number.isFinite(total) && total > 0) {
      parts.push("Source " + (idx + 1) + " / " + total);
    }
    const appliedRows = document.querySelectorAll(".ace-applied-code-row");
    if (appliedRows.length) {
      parts.push(appliedRows.length + (appliedRows.length === 1 ? " code" : " codes"));
    }
    const flagBtn = document.getElementById("nav-flag-btn");
    if (flagBtn && flagBtn.classList.contains("ace-flag-btn--active")) {
      parts.push("flagged");
    }
    el.textContent = parts.join(" · ");
  }

  /**
   * Soft-delete affordance: a server-emitted statusbar fragment with an
   * inline [Z] undo keycap, mirrored client-side into the text-panel pill
   * (because the pill lives inside #text-panel and gets clobbered on every
   * primary swap — so we re-mirror after each swap from the persistent
   * statusbar source of truth).
   *
   * The countdown hairline drains via the --undo-progress CSS variable and
   * supports true pause/resume: on hover, JS reads elapsed time, freezes
   * the progress at its current value, and clears the timer. On mouseleave
   * it restarts with the remaining duration — not a fresh 7 s.
   */
  const UNDO_DURATION_MS = 7000;
  let _undoTimer = null;
  let _undoStartTime = null;     // null when paused or not running
  let _undoRemainingMs = 0;      // remaining ms until auto-clear fires
  let _undoFrozenProgress = 1;   // last computed progress (1 → 0); seeds new pill buttons

  function _undoButtons() {
    return document.querySelectorAll(".ace-statusbar-undo[data-ace-undo-affordance]");
  }

  function _undoSetProgress(progress, durationMs) {
    _undoButtons().forEach(function (b) {
      if (durationMs !== undefined) {
        b.style.setProperty("--undo-duration", (durationMs / 1000) + "s");
      }
      b.style.setProperty("--undo-progress", String(progress));
    });
    document.querySelectorAll(".ace-notification-receipt--undo").forEach(function (el) {
      if (durationMs !== undefined) {
        el.style.setProperty("--undo-duration", (durationMs / 1000) + "s");
      }
      el.style.setProperty("--undo-progress", String(progress));
    });
  }

  function _undoStart(remainingMs) {
    // Set initial progress without transition (two RAFs let the browser
    // commit it before flipping to 0, so the transition actually runs).
    _undoSetProgress(_undoFrozenProgress);
    _undoStartTime = Date.now();
    _undoRemainingMs = remainingMs;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { _undoSetProgress(0, remainingMs); });
    });
    if (_undoTimer) clearTimeout(_undoTimer);
    _undoTimer = setTimeout(_clearUndoAffordance, remainingMs);
  }

  function _undoPause() {
    if (_undoStartTime === null) return;
    const elapsed = Date.now() - _undoStartTime;
    _undoFrozenProgress = Math.max(0, 1 - elapsed / _undoRemainingMs);
    _undoRemainingMs = Math.max(0, _undoRemainingMs - elapsed);
    _undoStartTime = null;
    if (_undoTimer) { clearTimeout(_undoTimer); _undoTimer = null; }
    // Visually freeze. The :hover rule sets transition:none, so this assignment
    // sticks; when :hover ends, the scaleX(...) value is already in place and
    // the transition resumes from there once _undoStart sets a new target.
    _undoSetProgress(_undoFrozenProgress);
  }

  function _undoResume() {
    if (_undoStartTime !== null) return; // already running
    if (_undoRemainingMs <= 0) { _clearUndoAffordance(); return; }
    _undoStart(_undoRemainingMs);
  }

  function _receiptEl() {
    return document.getElementById("ace-notification-receipt");
  }

  function _clearReceiptClasses(el) {
    if (!el) return;
    el.classList.remove(
      "ace-notification-receipt--ok",
      "ace-notification-receipt--ok-sticky",
      "ace-notification-receipt--err",
      "ace-notification-receipt--undo",
    );
  }

  function _setReceiptLiveSemantics(el, enabled) {
    if (!el) return;
    if (enabled) {
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
    } else {
      el.removeAttribute("role");
      el.removeAttribute("aria-live");
    }
  }

  function _syncReceiptFromStatusbar() {
    const sb = document.querySelector(".ace-statusbar-event");
    const receipt = _receiptEl();
    if (!sb || !receipt) return;
    if (sb.classList.contains("ace-statusbar-event--undo")) return;

    const text = sb.textContent.trim();
    if (!text) return;

    let kind = null;
    if (sb.classList.contains("ace-statusbar-event--err")) {
      kind = "err";
    } else if (sb.classList.contains("ace-statusbar-event--ok-sticky")) {
      kind = "ok-sticky";
    } else if (sb.classList.contains("ace-statusbar-event--ok")) {
      kind = "ok";
    }
    if (!kind) return;

    const receiptClass = "ace-notification-receipt--" + kind;
    if (receipt.textContent.trim() === text && receipt.classList.contains(receiptClass)) return;

    _setReceiptLiveSemantics(receipt, true);
    receipt.textContent = text;
    receipt.removeAttribute("style");
    _clearReceiptClasses(receipt);
    receipt.classList.add(receiptClass);
  }

  function _clearUndoAffordance() {
    if (_undoTimer) { clearTimeout(_undoTimer); _undoTimer = null; }
    _undoStartTime = null;
    _undoRemainingMs = 0;
    _undoFrozenProgress = 1;
    const sbEl = document.querySelector(".ace-statusbar-event--undo");
    if (sbEl) {
      sbEl.textContent = "";
      sbEl.classList.remove("ace-statusbar-event--undo");
    }
    const receiptEl = document.querySelector(".ace-notification-receipt--undo");
    if (receiptEl) {
      receiptEl.textContent = "";
      receiptEl.removeAttribute("style");
      receiptEl.classList.remove("ace-notification-receipt--undo");
      _setReceiptLiveSemantics(receiptEl, true);
    }
  }

  function _initUndoAffordance() {
    const sbEvent = document.querySelector(".ace-statusbar-event--undo");
    if (!sbEvent) return;

    // Always re-mirror — the receipt is inside #text-panel and gets clobbered
    // by any primary swap that lands during the affordance window. Listener-
    // binding is gated separately, per-button.
    const receipt = _receiptEl();
    if (receipt) {
      _clearReceiptClasses(receipt);
      receipt.classList.add("ace-notification-receipt--undo");
      _setReceiptLiveSemantics(receipt, false);
      if (receipt.innerHTML !== sbEvent.innerHTML) {
        receipt.innerHTML = sbEvent.innerHTML;
      }
    }

    // Bind per-button so the freshly-mirrored receipt button gets its handlers
    // even when the persistent statusbar button is already wired.
    _undoButtons().forEach(function (btn) {
      if (btn.dataset.aceUndoBound === "1") return;
      btn.dataset.aceUndoBound = "1";
      btn.addEventListener("mouseenter", _undoPause);
      btn.addEventListener("mouseleave", _undoResume);
      btn.addEventListener("focusin", _undoPause);
      btn.addEventListener("focusout", _undoResume);
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        document.querySelectorAll(".ace-statusbar-undo-keycap").forEach(function (k) {
          k.classList.add("ace-statusbar-undo-keycap--pressed");
        });
        setTimeout(function () {
          document.querySelectorAll(".ace-statusbar-undo-keycap").forEach(function (k) {
            k.classList.remove("ace-statusbar-undo-keycap--pressed");
          });
        }, 200);
        if (_undoTimer) { clearTimeout(_undoTimer); _undoTimer = null; }
        htmx.ajax("POST", "/api/undo", {
          target: "#text-panel",
          swap: "outerHTML",
          values: { current_index: window.__aceCurrentIndex },
        });
      });
    });

    // First time we've seen this affordance? Kick off the countdown.
    // Otherwise re-apply current state to all buttons (covers freshly-
    // mirrored receipt button mid-countdown or while paused).
    if (_undoStartTime === null && _undoRemainingMs === 0) {
      _undoFrozenProgress = 1;
      _undoStart(UNDO_DURATION_MS);
    } else if (_undoStartTime !== null) {
      // Running — recompute current visual progress and restart the
      // transition so the new receipt picks up the animation.
      const elapsed = Date.now() - _undoStartTime;
      const currentProgress = Math.max(0, 1 - elapsed / _undoRemainingMs);
      const newRemaining = Math.max(0, _undoRemainingMs - elapsed);
      _undoFrozenProgress = currentProgress;
      _undoRemainingMs = newRemaining;
      _undoStart(newRemaining);
    } else {
      // Paused — show the frozen progress on all buttons.
      _undoSetProgress(_undoFrozenProgress);
    }
  }

  /**
   * Show an ephemeral or sticky message in the status bar / coding receipt.
   *   kind="ok": text for ~2 s then fades (via empty-state CSS + timer clears text).
   *   kind="err": sticky until the next _setStatus() call.
   * Mirrors to the ARIA live region (assertive when kind="err").
   */
  function _setStatus(text, kind) {
    kind = kind || "ok";
    const sbEl = document.querySelector(".ace-statusbar-event");
    const receiptEl = _receiptEl();
    if (!sbEl && !receiptEl) return;

    if (_statusEventClearTimer) {
      clearTimeout(_statusEventClearTimer);
      _statusEventClearTimer = null;
    }

    if (sbEl) {
      sbEl.textContent = text || "";
      sbEl.classList.remove("ace-statusbar-event--ok", "ace-statusbar-event--ok-sticky", "ace-statusbar-event--err");
      if (text) sbEl.classList.add("ace-statusbar-event--" + kind);
    }
    if (receiptEl) {
      _setReceiptLiveSemantics(receiptEl, true);
      receiptEl.textContent = text || "";
      receiptEl.removeAttribute("style");
      _clearReceiptClasses(receiptEl);
      if (text) receiptEl.classList.add("ace-notification-receipt--" + kind);
    }

    if (text) _announce(text, kind === "err");

    if (kind === "ok" && text) {
      _statusEventClearTimer = setTimeout(function () {
        if (sbEl) {
          sbEl.textContent = "";
          sbEl.classList.remove("ace-statusbar-event--ok");
        }
        if (receiptEl) {
          receiptEl.textContent = "";
          receiptEl.classList.remove("ace-notification-receipt--ok");
        }
      }, 2000);
    }
  }

  window._setStatus = _setStatus;
  window._setAmbient = _setAmbient;

  /**
   * Schedule the same 2 s fade for "ok" status content delivered by a
   * server OOB swap (e.g. /api/undo's "Nothing to undo"). Plain HTMX
   * swaps replace the receipt element directly, bypassing _setStatus()'s
   * timer — without this helper, server-emitted "ok" receipts sit forever
   * until the next user action. "err" / "ok-sticky" / "undo" variants
   * are intentionally sticky and skipped.
   */
  function _maybeFadeOkStatus() {
    const sb = document.querySelector(".ace-statusbar-event");
    const receipt = _receiptEl();
    const sbOk = sb && sb.classList.contains("ace-statusbar-event--ok") && sb.textContent.trim();
    const receiptOk = receipt && receipt.classList.contains("ace-notification-receipt--ok") && receipt.textContent.trim();
    if (!sbOk && !receiptOk) return;
    if (_statusEventClearTimer) clearTimeout(_statusEventClearTimer);
    _statusEventClearTimer = setTimeout(function () {
      if (sb && sb.classList.contains("ace-statusbar-event--ok")) {
        sb.textContent = "";
        sb.classList.remove("ace-statusbar-event--ok");
      }
      if (receipt && receipt.classList.contains("ace-notification-receipt--ok")) {
        receipt.textContent = "";
        receipt.classList.remove("ace-notification-receipt--ok");
      }
    }, 2000);
  }

  /**
   * Briefly swap a control's label to a confirmation, then revert.
   * Used for import/export success feedback — no toast, no status-bar entry.
   * Safe to call repeatedly on the same element; the prior revert timer is
   * cancelled so the label always returns to the cached original.
   */
  function _flashOriginConfirmation(elementId, text, revertMs) {
    const el = document.getElementById(elementId);
    if (!el) return;
    revertMs = revertMs || 1500;
    if (!el.dataset.aceOriginalLabel) {
      el.dataset.aceOriginalLabel = el.textContent;
    }
    el.textContent = text;
    el.classList.add("ace-origin-flash");
    if (el._aceFlashTimer) clearTimeout(el._aceFlashTimer);
    el._aceFlashTimer = setTimeout(function () {
      el.textContent = el.dataset.aceOriginalLabel;
      delete el.dataset.aceOriginalLabel;
      el.classList.remove("ace-origin-flash");
      el._aceFlashTimer = null;
    }, revertMs);
  }
  window._flashOriginConfirmation = _flashOriginConfirmation;

  // --- Zone cycling (Tab / Shift+Tab / Escape / /) ---

  /** Move focus to text panel. */
  function _focusTextPanel() {
    const tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  }

  /** Move focus to search bar. */
  function _focusSearchBar() {
    const sb = document.getElementById("code-search-input");
    if (sb) sb.focus();
  }

  /** Move focus into the code tree (last-focused item or first visible item). */
  function _focusCodeTree() {
    const headlessTree = document.getElementById("ace-headless-tree-mount");
    if (headlessTree) {
      const activeHeadless = headlessTree.querySelector('[role="treeitem"][tabindex="0"]');
      const firstHeadless = headlessTree.querySelector('[role="treeitem"]');
      if (activeHeadless) activeHeadless.focus();
      else if (firstHeadless) firstHeadless.focus();
      return;
    }
    const active = _getActiveTreeItem();
    if (active && active.style.display !== "none") {
      active.focus();
    } else {
      const items = _getTreeItems();
      if (items.length > 0) _focusTreeItem(items[0]);
    }
  }

  function _visibleCreateActions() {
    return Array.from(document.querySelectorAll("#ace-code-create-actions .ace-code-create-action"))
      .filter(function (button) {
        return !button.disabled && button.offsetParent !== null;
      });
  }

  function _focusCreateAction(index) {
    const actions = _visibleCreateActions();
    if (!actions.length) return false;
    const clamped = Math.max(0, Math.min(index, actions.length - 1));
    actions[clamped].focus();
    return true;
  }

  /** Determine which zone currently has focus: "text", "search", "tree", or null. */
  function _activeZone() {
    let el = document.activeElement;
    if (!el) return null;
    if (el.id === "text-panel" || el.closest("#text-panel")) return "text";
    if (el.closest("#ace-right-inspector")) return "applied";
    if (el.id === "code-search-input") return "search";
    if (el.closest("#ace-code-create-actions")) return "create";
    const headlessTree = document.getElementById("ace-headless-tree-mount");
    if (headlessTree && headlessTree.contains(el)) return "tree";
    return null;
  }

  // Zone-level Tab cycling — captures Tab before browser default
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;
    if (!document.getElementById("text-panel")) return;

    let zone = _activeZone();
    if (!zone) return;

    if (!e.shiftKey) {
      if (zone === "text") { e.preventDefault(); _focusSearchBar(); return; }
      if (zone === "search") {
        e.preventDefault();
        if (!_focusCreateAction(0)) _focusCodeTree();
        return;
      }
      if (zone === "create") {
        const actions = _visibleCreateActions();
        const idx = actions.indexOf(document.activeElement);
        e.preventDefault();
        if (idx >= 0 && idx < actions.length - 1) actions[idx + 1].focus();
        else _focusTextPanel();
        return;
      }
      if (zone === "tree") { e.preventDefault(); _focusTextPanel(); return; }
    } else {
      if (zone === "text") {
        e.preventDefault();
        if (!_focusCreateAction(_visibleCreateActions().length - 1)) _focusCodeTree();
        return;
      }
      if (zone === "search") { e.preventDefault(); _focusTextPanel(); return; }
      if (zone === "create") {
        const actions = _visibleCreateActions();
        const idx = actions.indexOf(document.activeElement);
        e.preventDefault();
        if (idx > 0) actions[idx - 1].focus();
        else _focusSearchBar();
        return;
      }
      if (zone === "tree") { e.preventDefault(); _focusSearchBar(); return; }
    }
  }, true);  // capture phase to intercept before default Tab behaviour

  // --- Roving tabindex ---

  /** Return all visible treeitems (group headers + code rows) in DOM order. */
  function _getTreeItems() {
    const controller = _getSidebarTreeController();
    return controller ? controller.getTreeItems() : [];
  }

  /** Move roving tabindex to the given treeitem. */
  function _focusTreeItem(item, options) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.focusTreeItem(item, options);
    }
  }

  /** Get the currently focused treeitem (tabindex="0"). */
  function _getActiveTreeItem() {
    const controller = _getSidebarTreeController();
    return controller ? controller.getActiveTreeItem() : null;
  }

  /** Check if a treeitem is a folder row. */
  function _isFolderRow(item) {
    const controller = _getSidebarTreeController();
    return controller ? controller.isFolderRow(item) : false;
  }

  function _parentFolderRow(item) {
    const controller = _getSidebarTreeController();
    return controller ? controller.parentFolderRow(item) : null;
  }

  function _itemIdFromTreeElement(el) {
    const controller = _getSidebarTreeController();
    return controller ? controller.itemIdFromTreeElement(el) : null;
  }

  function _directChildItemIds(container) {
    const controller = _getSidebarTreeController();
    return controller ? controller.directChildItemIds(container) : [];
  }

  /** Move a folder block (the wrapper carrying header + children group) up
   *  or down by one position relative to its sibling folder blocks. */
  function _moveFolderInDirection(folderRow, direction) {
    if (_denyCodebookEditing()) return;
    const controller = _getSidebarTreeController();
    const controlledId = controller && typeof controller.itemIdFromTreeElement === "function"
      ? controller.itemIdFromTreeElement(folderRow)
      : null;
    if (controlledId && typeof controller.moveItemInDirection === "function") {
      controller.moveItemInDirection(controlledId, direction);
      return;
    }
    const block = folderRow.closest(".ace-folder-block");
    const container = block ? block.parentElement : null;
    if (!block || !container) return;

    function isFolderBlock(el) {
      return el && el.classList && el.classList.contains("ace-folder-block");
    }

    if (direction === -1) {
      let prev = block.previousElementSibling;
      while (prev && !isFolderBlock(prev)) prev = prev.previousElementSibling;
      if (!prev) return;
      container.insertBefore(block, prev);
    } else {
      let next = block.nextElementSibling;
      while (next && !isFolderBlock(next)) next = next.nextElementSibling;
      if (!next) return;
      container.insertBefore(block, next.nextElementSibling); // null ref → append
    }

    _persistScopeOrder(container);

    _updateKeycaps();
    _initSortable();
  }

  // --- Indent/outdent helpers (Alt-arrow gestures) ---

  /** Move a codebook item into the scope of `folderRow` via PUT /api/codes/{id}/parent. */
  function _doMoveToFolderAbove(row, folderRow) {
    if (_denyCodebookEditing()) return;
    const codeId = _itemIdFromTreeElement(row);
    const parentId = _itemIdFromTreeElement(folderRow);
    if (!codeId || !parentId) return;
    if (_parentFolderRow(row) === folderRow) {
      _announce("Already in that folder.");
      return;
    }
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        parent_id: parentId,
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  }

  /** Move a codebook item out one level, or to root if it is already one level deep. */
  function _doMoveOutOfFolder(row) {
    if (_denyCodebookEditing()) return;
    const codeId = _itemIdFromTreeElement(row);
    if (!codeId) return;
    const parentRow = _parentFolderRow(row);
    const grandparentRow = parentRow ? _parentFolderRow(parentRow) : null;
    const newParentId = grandparentRow ? _itemIdFromTreeElement(grandparentRow) : "";
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      ..._codebookMutationSwapOptions(),
      values: _codebookMutationValues({
        parent_id: newParentId || "",
        current_index: window.__aceCurrentIndex || 0,
      }),
    });
  }

  function _folderRowAbove(item) {
    const items = _getTreeItems();
    const idx = items.indexOf(item);
    if (idx <= 0) return null;
    const above = items[idx - 1];
    if (_isFolderRow(above)) return above;
    return _parentFolderRow(above);
  }

  // --- Tree keydown handler ---

  document.addEventListener("keydown", function (e) {
    if (_chordMode === "awaiting") return;
    const controller = _getSidebarTreeController();
    const activeRoot = controller && typeof controller.rootElement === "function"
      ? controller.rootElement()
      : null;
    if (!activeRoot || !activeRoot.contains(document.activeElement)) return;
    const active = document.activeElement;
    if (!active || active.getAttribute("role") !== "treeitem") return;
    if (active.querySelector('[contenteditable="true"]')) return;

    const key = e.key;
    const alt = e.altKey;
    const shift = e.shiftKey;

    // Alt+Shift+↑ — Move code up (or folder up if focused on a folder row)
    if (key === "ArrowUp" && alt && shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      if (!_isFolderRow(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(_itemIdFromTreeElement(active), -1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      } else {
        const labelEl = active.querySelector(".ace-folder-label");
        const name = labelEl ? labelEl.textContent.trim() : "folder";
        _moveFolderInDirection(active, -1);
        _announce(`${name} moved up`);
      }
      return;
    }

    // Alt+Shift+↓ — Move code down (or folder down if focused on a folder row)
    if (key === "ArrowDown" && alt && shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      if (!_isFolderRow(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(_itemIdFromTreeElement(active), 1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      } else {
        const labelEl = active.querySelector(".ace-folder-label");
        const name = labelEl ? labelEl.textContent.trim() : "folder";
        _moveFolderInDirection(active, 1);
        _announce(`${name} moved down`);
      }
      return;
    }

    // ⌥⇧→ — Wrap focused code + the sibling code above into a NEW folder.
    // Composite: creates folder + moves both codes in one transaction. After
    // the swap settles, focus moves to the new folder header and inline
    // rename starts immediately.
    if (key === "ArrowRight" && alt && shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      if (_isFolderRow(active)) {
        const folderAbove = _folderRowAbove(active);
        if (folderAbove) _doMoveToFolderAbove(active, folderAbove);
        else _announce("No folder above to move into.");
        return;
      }
      const codeId = _itemIdFromTreeElement(active);
      const allRows = _getTreeItems();
      const idx = allRows.indexOf(active);
      if (idx <= 0) {
        _announce("No row above. Need two sibling codes to make a folder.");
        window._setStatus("Need a row above to wrap into a folder", "err");
        return;
      }
      const above = allRows[idx - 1];
      if (_isFolderRow(above)) {
        _doMoveToFolderAbove(active, above);
        return;
      }
      if (_parentFolderRow(above) !== _parentFolderRow(active)) {
        _announce("Need two sibling codes to make a folder.");
        window._setStatus("Need two sibling codes to wrap into a folder", "err");
        return;
      }
      const aboveCodeId = _itemIdFromTreeElement(above);
      htmx.ajax("POST", `/api/codes/${codeId}/indent-promote`, {
        ..._codebookMutationSwapOptions(),
        values: _codebookMutationValues({
          above_code_id: aboveCodeId,
          folder_name: "New folder",
          current_index: window.__aceCurrentIndex || 0,
        }),
      }).then(function () {
        // After OOB swap, the moved code lives inside a new folder. Locate
        // the folder header (sibling above the [role="group"] container that
        // wraps the code) and start inline rename on it. Defer past
        // htmx:afterSettle (which can re-bind focus via _syncSidebarAfterSwap)
        // by using a slightly longer timeout — the focus call inside
        // `_startInlineRename` would otherwise race with sidebar re-init.
        setTimeout(function () {
          const moved = document.querySelector(
            `.ace-code-row[data-code-id="${codeId}"], .ace-ht-row[data-item-id="${codeId}"]`
          );
          if (!moved) return;
          const folderRow = _parentFolderRow(moved);
          if (folderRow && _isFolderRow(folderRow)) {
            _focusTreeItem(folderRow);
            _startInlineRename(folderRow, { isFolder: true });
          }
        }, 100);
      });
      return;
    }

    // ⌥→ (no shift) — Move focused item into the folder above. Never
    // creates a folder on its own; ⌥⇧→ is the explicit wrap gesture.
    if (key === "ArrowRight" && alt && !shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      const above = _folderRowAbove(active);
      if (!above) {
        if (_isFolderRow(active)) {
          _announce("No folder above to move into.");
        } else {
          _announce("Press Alt-Shift-Right to create a folder around sibling codes.");
          window._setStatus("⌥⇧→ to wrap into a new folder", "ok");
        }
        return;
      }
      if (_isFolderRow(above)) {
        _doMoveToFolderAbove(active, above);
        return;
      }
      return;
    }

    // ⌥← — Move focused item out one folder level.
    if (key === "ArrowLeft" && alt && !shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      if (!_parentFolderRow(active)) {
        _announce("Already at root.");
        return;
      }
      _doMoveOutOfFolder(active);
      return;
    }

    // Enter — Apply focused code to current sentence, return focus to text panel
    if (key === "Enter" && !alt && !shift) {
      e.preventDefault();
      if (!_isFolderRow(active)) {
        const codeId3 = _itemIdFromTreeElement(active);
        if (codeId3) {
          _clearSearchFilter();
          const applied = _applyCode(codeId3);
          if (applied && typeof applied.then === "function") {
            applied.then(function () {
              window.aceCodingKeyboard?.returnToSource?.();
            });
          } else if (applied) {
            window.aceCodingKeyboard?.returnToSource?.();
          }
        }
      } else {
        // On a folder row: toggle expand/collapse
        _toggleFolderCollapse(active);
      }
      return;
    }

    // F2 — Inline rename. Works on both code rows and folder headers.
    // Folders share the PUT /api/codes/{id} endpoint with codes (the row's
    // `kind='folder'` is preserved by the model layer).
    if (key === "F2" && !alt && !shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      const itemId = _itemIdFromTreeElement(active);
      if (controller && typeof controller.startRenaming === "function" && itemId) {
        controller.startRenaming(itemId);
        return;
      }
      if (_isFolderRow(active)) {
        _startInlineRename(active, { isFolder: true });
      } else {
        const codeId4 = itemId;
        if (codeId4) _startInlineRename(codeId4);
      }
      return;
    }

    // Delete / Backspace — Soft-delete (acts immediately; status bar shows
    // an inline [Z] undo keycap that's clickable for ~7 s). On a folder row
    // this cascades to descendants in one transaction (children lifted to
    // root by the undo handler). No confirm dialog per spec §8 — undo is
    // the safety net.
    if ((key === "Delete" || key === "Backspace") && !alt && !shift) {
      e.preventDefault();
      if (_denyCodebookEditing()) return;
      const itemId = _itemIdFromTreeElement(active);
      if (itemId) _executeDelete(itemId);
      return;
    }

    const items = _getTreeItems();
    const idx = items.indexOf(active);
    if (key === "ArrowRight" && !alt && !shift && !_isFolderRow(active)) {
      e.preventDefault();
      if (typeof window.aceCodingKeyboard?.returnToSource === "function") {
        window.aceCodingKeyboard.returnToSource();
      }
      return;
    }

    const plainNavigationKey = !alt && !shift && !e.ctrlKey && !e.metaKey
      && (key === "ArrowDown"
          || key === "ArrowUp"
          || key === "ArrowLeft"
          || key === "ArrowRight"
          || key === "Home"
          || key === "End");
    if (plainNavigationKey && active.classList.contains("ace-ht-row")) {
      return;
    }

    // ↓ — Next visible treeitem
    if (key === "ArrowDown" && !alt && !shift) {
      e.preventDefault();
      if (idx < items.length - 1) _focusTreeItem(items[idx + 1]);
      return;
    }

    // ↑ — Previous visible treeitem
    if (key === "ArrowUp" && !alt && !shift) {
      e.preventDefault();
      if (idx > 0) _focusTreeItem(items[idx - 1]);
      return;
    }

    // → — Expand folder or move to first child
    if (key === "ArrowRight" && !alt && !shift) {
      e.preventDefault();
      if (_isFolderRow(active)) {
        if (active.getAttribute("aria-expanded") === "false") {
          _expandFolder(active);
        } else {
          const firstChild = controller && typeof controller.firstChildOfFolderRow === "function"
            ? controller.firstChildOfFolderRow(active)
            : active.nextElementSibling?.querySelector?.('[role="treeitem"]');
          if (firstChild) _focusTreeItem(firstChild);
        }
      }
      return;
    }

    // ← — Collapse folder or move to parent folder
    if (key === "ArrowLeft" && !alt && !shift) {
      e.preventDefault();
      if (_isFolderRow(active)) {
        if (active.getAttribute("aria-expanded") === "true") {
          _collapseFolder(active);
        } else {
          const parent = _parentFolderRow(active);
          if (parent) _focusTreeItem(parent);
        }
      } else {
        const folderRow = _parentFolderRow(active);
        if (folderRow) _focusTreeItem(folderRow);
      }
      return;
    }

    // Home — First treeitem
    if (key === "Home") {
      e.preventDefault();
      if (items.length > 0) _focusTreeItem(items[0]);
      return;
    }

    // End — Last treeitem
    if (key === "End") {
      e.preventDefault();
      if (items.length > 0) _focusTreeItem(items[items.length - 1]);
      return;
    }

    // Escape — Cancel pending cut state first; otherwise return to text panel.
    if (key === "Escape" && !alt && !shift) {
      e.preventDefault();
      if (_cutCode) {
        _setCut(null);
        _announce("Cut cleared.");
        window._setStatus("", "ok");
        return;
      }
      _clearSearchFilter();
      _focusTextPanel();
      return;
    }
  });

  // V — open the coded-text view. Uses the focused sidebar code when one is
  // focused, otherwise falls back to the top code in the sidebar. The fallback
  // keeps keyboard-first nav working without having to land on a row first.
  // Same precedent as n/q/x/z: reserved letter for a global action.
  document.addEventListener("keydown", function (evt) {
    if (_chordMode === "awaiting") return;
    if (evt.key !== "v" && evt.key !== "V") return;
    if (evt.metaKey || evt.ctrlKey || evt.altKey || evt.shiftKey) return;
    const tag = (evt.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || evt.target.isContentEditable) return;
    const controller = _getSidebarTreeController();
    let treeItem = controller && typeof controller.activeCodeItem === "function"
      ? controller.activeCodeItem()
      : null;
    if (!treeItem && controller && typeof controller.firstCodeItem === "function") {
      treeItem = controller.firstCodeItem();
    }
    let codeId = treeItem ? _itemIdFromTreeElement(treeItem) : "";
    if (!codeId) {
      treeItem = controller && typeof controller.firstCodeItem === "function"
        ? controller.firstCodeItem()
        : null;
      codeId = treeItem ? treeItem.getAttribute("data-code-id") : "";
    }
    if (!codeId) return;
    evt.preventDefault();
    try { sessionStorage.setItem("cv-restore-codebook-focus", "1"); } catch (_) {}
    window.location.href = `/code/${codeId}/view`;
  });

  // --- Folder expand / collapse ---
  //
  // Folder rows are <div class="ace-code-folder-row" aria-expanded="\u2026"
  function _expandFolder(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.expandFolder(folderRow);
    }
  }

  function _collapseFolder(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.collapseFolder(folderRow);
    }
  }

  /* ================================================================
   * 17b. Coding text size
   * ================================================================ */

  const CODING_TEXT_SIZE_KEY = "ace-coding-text-size";
  const CODING_TEXT_WIDTH_KEY = "ace-coding-text-width";
  const CODING_TEXT_DEFAULT_SIZE = 17;
  const CODING_TEXT_DEFAULT_WIDTH = "72ch";
  const CODING_TEXT_FALLBACK_SIZES = [15, 17, 19, 20, 21, 24];
  const CODING_TEXT_FALLBACK_WIDTHS = ["64ch", "72ch", "88ch", "112ch"];
  let _codingTextGlobalBound = false;

  function _codingTextSizes() {
    const sizes = Array.from(document.querySelectorAll(".ace-coding-text-option[data-coding-text-size]"))
      .map(function (option) { return parseInt(option.dataset.codingTextSize, 10); })
      .filter(function (size) { return Number.isFinite(size) && size >= 13 && size <= 32; });
    return sizes.length ? sizes : CODING_TEXT_FALLBACK_SIZES;
  }

  function _normaliseCodingTextSize(value) {
    const n = parseInt(value, 10);
    return _codingTextSizes().indexOf(n) >= 0 ? n : CODING_TEXT_DEFAULT_SIZE;
  }

  function _currentCodingTextSize() {
    try {
      return _normaliseCodingTextSize(localStorage.getItem(CODING_TEXT_SIZE_KEY));
    } catch (_) {
      return CODING_TEXT_DEFAULT_SIZE;
    }
  }

  function _codingTextWidths() {
    const widths = Array.from(document.querySelectorAll(".ace-coding-width-option[data-coding-text-width]"))
      .map(function (option) { return option.dataset.codingTextWidth; })
      .filter(function (width) { return CODING_TEXT_FALLBACK_WIDTHS.indexOf(width) >= 0; });
    return widths.length ? widths : CODING_TEXT_FALLBACK_WIDTHS;
  }

  function _normaliseCodingTextWidth(value) {
    const widths = _codingTextWidths();
    return widths.indexOf(value) >= 0 ? value : CODING_TEXT_DEFAULT_WIDTH;
  }

  function _currentCodingTextWidth() {
    try {
      return _normaliseCodingTextWidth(localStorage.getItem(CODING_TEXT_WIDTH_KEY));
    } catch (_) {
      return CODING_TEXT_DEFAULT_WIDTH;
    }
  }

  function _codingTextIndex(size) {
    const sizes = _codingTextSizes();
    const index = sizes.indexOf(_normaliseCodingTextSize(size));
    return index >= 0 ? index : sizes.indexOf(CODING_TEXT_DEFAULT_SIZE);
  }

  function _setCodingTextMenuOpen(open) {
    const btn = document.getElementById("coding-text-menu-btn");
    const dropdown = document.getElementById("coding-text-dropdown");
    if (!btn || !dropdown) return;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    dropdown.hidden = !open;
  }

  function _syncCodingTextControls() {
    const size = _currentCodingTextSize();
    const width = _currentCodingTextWidth();
    const sizes = _codingTextSizes();
    const index = _codingTextIndex(size);
    document.documentElement.style.setProperty("--ace-coding-text-size", size + "px");
    document.documentElement.style.setProperty("--ace-coding-text-width", width);
    document.querySelectorAll(".ace-coding-text-option").forEach(function (btn) {
      const active = _normaliseCodingTextSize(btn.dataset.codingTextSize) === size;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    document.querySelectorAll(".ace-coding-width-option").forEach(function (btn) {
      const active = _normaliseCodingTextWidth(btn.dataset.codingTextWidth) === width;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const slider = document.getElementById("coding-text-slider");
    if (slider) {
      slider.min = "0";
      slider.max = String(Math.max(0, sizes.length - 1));
      slider.step = "1";
      slider.value = String(Math.max(0, index));
      slider.setAttribute("aria-valuetext", size + " px");
    }
    const value = document.getElementById("coding-text-value");
    if (value) value.textContent = size + " px";
  }

  function _setCodingTextSize(size) {
    const normalised = _normaliseCodingTextSize(size);
    try {
      localStorage.setItem(CODING_TEXT_SIZE_KEY, String(normalised));
    } catch (_) {}
    _syncCodingTextControls();
    requestAnimationFrame(function () {
      _paintSvg();
    });
  }

  function _setCodingTextWidth(width) {
    const normalised = _normaliseCodingTextWidth(width);
    try {
      localStorage.setItem(CODING_TEXT_WIDTH_KEY, normalised);
    } catch (_) {}
    _syncCodingTextControls();
    requestAnimationFrame(function () {
      _paintSvg();
    });
  }

  function _setCodingTextIndex(index) {
    const sizes = _codingTextSizes();
    const next = sizes[parseInt(index, 10)];
    if (next) _setCodingTextSize(next);
  }

  function _initCodingTextControls() {
    const wrapper = document.getElementById("coding-text-menu-wrapper");
    const btn = document.getElementById("coding-text-menu-btn");
    if (!wrapper || !btn) return;

    _syncCodingTextControls();

    if (btn.dataset.aceCodingTextBound !== "1") {
      btn.dataset.aceCodingTextBound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        _setCodebookMenuOpen(false);
        const open = btn.getAttribute("aria-expanded") !== "true";
        _setCodingTextMenuOpen(open);
      });
    }

    document.querySelectorAll(".ace-coding-text-option").forEach(function (option) {
      if (option.dataset.aceCodingTextBound === "1") return;
      option.dataset.aceCodingTextBound = "1";
      option.addEventListener("click", function (e) {
        e.preventDefault();
        _setCodingTextSize(option.dataset.codingTextSize);
      });
    });

    document.querySelectorAll(".ace-coding-width-option").forEach(function (option) {
      if (option.dataset.aceCodingTextWidthBound === "1") return;
      option.dataset.aceCodingTextWidthBound = "1";
      option.addEventListener("click", function (e) {
        e.preventDefault();
        _setCodingTextWidth(option.dataset.codingTextWidth);
      });
    });

    const slider = document.getElementById("coding-text-slider");
    if (slider && slider.dataset.aceCodingTextBound !== "1") {
      slider.dataset.aceCodingTextBound = "1";
      slider.addEventListener("input", function () {
        _setCodingTextIndex(slider.value);
      });
    }

    if (!_codingTextGlobalBound) {
      _codingTextGlobalBound = true;
      document.addEventListener("click", function (e) {
        const currentWrapper = document.getElementById("coding-text-menu-wrapper");
        if (!currentWrapper) return;
        if (e.target && e.target.closest && e.target.closest("#coding-text-menu-wrapper")) return;
        _setCodingTextMenuOpen(false);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        const btn = document.getElementById("coding-text-menu-btn");
        if (btn && btn.getAttribute("aria-expanded") === "true") {
          _setCodingTextMenuOpen(false);
          e.stopPropagation();
        }
      }, true);
    }
  }

  /* ================================================================
   * 18. Codebook menu
   * ================================================================ */

  const CODE_CUES_ENABLED_KEY = "ace-codebook-cues-enabled";
  const CODE_CUES_DELAY_MS = 150;
  const CODE_CUES_MAX = 3;
  let _codeCueTimer = null;
  let _codeCueController = null;
  let _codeCueRequestId = 0;

  function _codeCuesEnabled() {
    return window.localStorage.getItem(CODE_CUES_ENABLED_KEY) === "1";
  }

  function _syncCodeCuesMenuItem() {
    const btn = document.getElementById("codebook-cues-toggle-btn");
    if (!btn) return;
    btn.setAttribute("aria-checked", _codeCuesEnabled() ? "true" : "false");
  }

  function _codeCueSelector(codeId) {
    const raw = String(codeId);
    const escaped = window.CSS && typeof window.CSS.escape === "function"
      ? window.CSS.escape(raw)
      : raw.replace(/["\\]/g, "\\$&");
    return `.ace-code-row[data-code-id="${escaped}"], .ace-ht-row--code[data-code-id="${escaped}"]`;
  }

  function _clearCodeCueRows() {
    document.querySelectorAll(".ace-code-row--cue, .ace-ht-row--cue").forEach(function (row) {
      row.classList.remove("ace-code-row--cue");
      row.classList.remove("ace-ht-row--cue");
    });
  }

  function _clearCodeCues() {
    _codeCueRequestId += 1;
    if (_codeCueTimer !== null) {
      clearTimeout(_codeCueTimer);
      _codeCueTimer = null;
    }
    if (_codeCueController) {
      _codeCueController.abort();
      _codeCueController = null;
    }
    _clearCodeCueRows();
  }

  function _codebookFilterActive() {
    const input = document.getElementById("code-search-input");
    return !!(input && input.value.trim());
  }

  function _focusedSentenceCuePayload(requestId) {
    const sentence = document.querySelector(".ace-sentence--focused");
    if (!sentence) return null;
    const sentences = Array.from(_getSentences());
    const sentenceIndex = sentences.indexOf(sentence);
    if (sentenceIndex < 0) return null;
    const start = Number.parseInt(sentence.dataset.start || "-1", 10);
    const end = Number.parseInt(sentence.dataset.end || "-1", 10);
    return {
      request_id: requestId,
      current_index: Number.isFinite(window.__aceCurrentIndex) ? window.__aceCurrentIndex : 0,
      sentence_index: sentenceIndex,
      start: Number.isFinite(start) ? start : -1,
      end: Number.isFinite(end) ? end : -1,
      text: sentence.textContent || "",
    };
  }

  function _rowIsCueVisible(row) {
    if (!row || row.hidden) return false;
    const style = window.getComputedStyle(row);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  function _applyCodeCues(cues) {
    _clearCodeCueRows();
    if (!_codeCuesEnabled() || _codebookFilterActive()) return;
    (cues || []).slice(0, CODE_CUES_MAX).forEach(function (cue) {
      document.querySelectorAll(_codeCueSelector(cue.code_id)).forEach(function (row) {
        if (!_rowIsCueVisible(row)) return;
        row.classList.add("ace-code-row--cue");
        row.classList.add("ace-ht-row--cue");
      });
    });
  }

  function _scheduleCodeCues() {
    const requestId = _codeCueRequestId + 1;
    _codeCueRequestId = requestId;
    if (_codeCueTimer !== null) {
      clearTimeout(_codeCueTimer);
      _codeCueTimer = null;
    }
    if (_codeCueController) {
      _codeCueController.abort();
      _codeCueController = null;
    }
    if (!_codeCuesEnabled() || _codebookFilterActive()) {
      _clearCodeCues();
      return;
    }
    _codeCueTimer = setTimeout(function () {
      _codeCueTimer = null;
      if (!_codeCuesEnabled() || _codebookFilterActive()) {
        _clearCodeCues();
        return;
      }
      const payload = _focusedSentenceCuePayload(requestId);
      if (!payload) {
        _clearCodeCues();
        return;
      }
      const controller = new AbortController();
      _codeCueController = controller;
      fetch("/api/code-cues", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
        .then(function (response) {
          if (!response.ok) {
            _clearCodeCueRows();
            return null;
          }
          return response.json();
        })
        .then(function (data) {
          if (!data) return;
          if (data.request_id !== payload.request_id) return;
          if (data.current_index !== payload.current_index) return;
          if (data.sentence_index !== payload.sentence_index) return;
          if (data.start !== payload.start || data.end !== payload.end) return;
          if (payload.request_id !== _codeCueRequestId) return;
          _applyCodeCues(data.cues || []);
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") return;
          _clearCodeCueRows();
        })
        .finally(function () {
          if (_codeCueController === controller) {
            _codeCueController = null;
          }
        });
    }, CODE_CUES_DELAY_MS);
  }

  function _setCodeCuesEnabled(enabled) {
    window.localStorage.setItem(CODE_CUES_ENABLED_KEY, enabled ? "1" : "0");
    _syncCodeCuesMenuItem();
    if (enabled) {
      _scheduleCodeCues();
    } else {
      _clearCodeCues();
    }
  }

  document.addEventListener("input", function (e) {
    if (!e.target || e.target.id !== "code-search-input") return;
    if (_codebookFilterActive()) {
      _clearCodeCues();
    } else if (_codeCuesEnabled()) {
      _scheduleCodeCues();
    }
  }, true);

  function _setCodebookMenuOpen(open, opts) {
    const btn = document.getElementById("codebook-menu-btn");
    const dropdown = document.getElementById("codebook-dropdown");
    if (!btn || !dropdown) return;
    const options = opts || {};
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    dropdown.hidden = !open;
    if (open) {
      _syncCodeCuesMenuItem();
      const firstItem = dropdown.querySelector("button:not([disabled])");
      if (firstItem) firstItem.focus();
    } else if (options.restoreFocus) {
      btn.focus();
    }
  }

  function _codebookMenuItems() {
    const dropdown = document.getElementById("codebook-dropdown");
    if (!dropdown) return [];
    return Array.from(dropdown.querySelectorAll('[role="menuitem"]:not([disabled]), [role="menuitemcheckbox"]:not([disabled])'));
  }

  function _focusCodebookMenuItem(delta) {
    const items = _codebookMenuItems();
    if (!items.length) return;
    const index = items.indexOf(document.activeElement);
    const nextIndex = index < 0 ? 0 : (index + delta + items.length) % items.length;
    items[nextIndex].focus();
  }

  // Codebook menu: toggle, import, export, shortcuts
  document.addEventListener("click", function (e) {
    const dropdown = document.getElementById("codebook-dropdown");

    // Keyboard shortcuts (absorbed from the old `?` button)
    if (e.target.closest("#codebook-menu-shortcuts-btn")) {
      _setCodebookMenuOpen(false);
      _toggleCheatSheet();
      return;
    }

    if (e.target.closest("#codebook-cues-toggle-btn")) {
      _setCodeCuesEnabled(!_codeCuesEnabled());
      return;
    }

    if (e.target.closest("#create-first-code-btn")) {
      _setCodebookMenuOpen(false);
      const input = document.getElementById("code-search-input");
      if (input) {
        _clearSearchFilter();
        input.focus();
      }
      window._setStatus("Type a code name, then press Enter", "ok");
      return;
    }

    if (e.target.closest("#empty-import-codebook-btn")) {
      const importBtn = document.getElementById("codebook-menu-import-btn");
      if (importBtn) importBtn.click();
      return;
    }

    // Import button
    if (e.target.closest("#codebook-menu-import-btn")) {
      window._aceCodebookImportReturnFocus = document.getElementById("codebook-menu-btn");
      _setCodebookMenuOpen(false);
      fetch("/api/native/pick-file", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "accept=.csv"
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.path) return;
          htmx.ajax("POST", "/api/codes/import/preview-path", {
            values: _codebookMutationValues({
              path: data.path,
              current_index: window.__aceCurrentIndex,
            }),
            target: "#modal-container",
            swap: "innerHTML",
          });
        });
      return;
    }

    // Export codebook button
    if (e.target.closest("#codebook-export-btn")) {
      _setCodebookMenuOpen(false);
      window.location.href = "/api/codes/export";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export all annotations button
    if (e.target.closest("#export-annotations-btn")) {
      _setCodebookMenuOpen(false);
      window.location.href = "/api/export/annotations";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export source notes button
    if (e.target.closest("#export-notes-btn")) {
      _setCodebookMenuOpen(false);
      window.location.href = "/api/export/notes";
      window._setStatus("Exported", "ok");
      return;
    }

    // Fullscreen toggle button
    if (e.target.closest("#fullscreen-btn")) {
      _setCodebookMenuOpen(false);
      _toggleFullscreen();
      return;
    }

    // Toggle button
    if (e.target.closest("#codebook-menu-btn")) {
      _setCodingTextMenuOpen(false);
      const btn = document.getElementById("codebook-menu-btn");
      const open = btn && btn.getAttribute("aria-expanded") !== "true";
      _setCodebookMenuOpen(open);
      e.stopPropagation();
      return;
    }

    // Click outside — close if open
    if (dropdown && !dropdown.hidden) {
      _setCodebookMenuOpen(false);
    }
  });

  // Codebook menu: Escape closes dropdown
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      const dropdown = document.getElementById("codebook-dropdown");
      if (dropdown && !dropdown.hidden) {
        _setCodebookMenuOpen(false, { restoreFocus: true });
        e.preventDefault();
        e.stopPropagation();
      }
      return;
    }
    const dropdown = document.getElementById("codebook-dropdown");
    if (!dropdown || dropdown.hidden) return;
    if (!e.target.closest("#codebook-menu-wrapper")) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      e.stopPropagation();
      _focusCodebookMenuItem(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      _focusCodebookMenuItem(-1);
    } else if (e.key === "Home") {
      const first = _codebookMenuItems()[0];
      if (first) {
        e.preventDefault();
        e.stopPropagation();
        first.focus();
      }
    } else if (e.key === "End") {
      const items = _codebookMenuItems();
      const last = items[items.length - 1];
      if (last) {
        e.preventDefault();
        e.stopPropagation();
        last.focus();
      }
    }
  }, true);

  // Fullscreen toggle
  function _toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(function (err) {
        window._setStatus(`Fullscreen failed: ${err.message}`, "err");
      });
    }
  }

  // Update menu item label when fullscreen state changes
  document.addEventListener("fullscreenchange", function () {
    const btn = document.getElementById("fullscreen-btn");
    if (btn) btn.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
  });

  // Cmd/Ctrl+Shift+F — toggle fullscreen
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "F" || e.key === "f")) {
      e.preventDefault();
      _toggleFullscreen();
    }
  });

  // Import codes from preview dialog
  window._aceInitCodebookImportDialog = function (dialog) {
    if (!dialog || dialog.dataset.codebookImportReady === "1") return;
    if (!dialog.classList.contains("ace-codebook-import-dialog")) return;
    dialog.dataset.codebookImportReady = "1";

    const selects = Array.from(dialog.querySelectorAll("[data-codebook-import-map]"));
    const preview = dialog.querySelector("#codebook-import-preview");
    const review = dialog.querySelector("#codebook-import-review");
    const skipped = dialog.querySelector("#codebook-import-skipped");
    const commit = dialog.querySelector("#codebook-import-commit");
    const subtitle = dialog.querySelector(".ace-import-dialog-sub");
    const tabs = Array.from(dialog.querySelectorAll("[data-codebook-import-view]"));
    const panels = Array.from(dialog.querySelectorAll("[data-codebook-import-panel]"));
    const counts = dialog.querySelector("[data-codebook-import-counts]");
    let requestSeq = 0;

    function showView(view) {
      tabs.forEach(function (tab) {
        const selected = tab.dataset.codebookImportView === view;
        tab.setAttribute("aria-selected", selected ? "true" : "false");
        tab.tabIndex = selected ? 0 : -1;
      });
      panels.forEach(function (panel) {
        const selected = panel.dataset.codebookImportPanel === view;
        panel.classList.toggle("is-active", selected);
        panel.hidden = !selected;
      });
    }

    function refreshPreview() {
      const seq = ++requestSeq;
      const body = new URLSearchParams();
      body.set("path", dialog.dataset.csvPath || "");
      body.set("name_column", dialog.querySelector("#codebook-map-name")?.value || "");
      body.set("group_column", dialog.querySelector("#codebook-map-group")?.value || "");
      body.set("definition_column", dialog.querySelector("#codebook-map-definition")?.value || "");

      const activePanel = dialog.querySelector(".ace-codebook-import-panel.is-active .ace-codebook-import-preview-list");
      if (activePanel) activePanel.setAttribute("aria-busy", "true");
      if (counts) counts.textContent = "Updating preview";

      fetch("/api/codes/import/preview-map", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      }).then(function (response) {
        return response.json();
      }).then(function (data) {
        if (seq !== requestSeq) return;
        if (preview) {
          preview.innerHTML = data.preview_html || "";
          preview.removeAttribute("aria-busy");
        }
        if (review) {
          review.innerHTML = data.review_html || "";
          review.removeAttribute("aria-busy");
        }
        if (skipped) {
          skipped.innerHTML = data.skipped_html || "";
          skipped.removeAttribute("aria-busy");
        }
        if (commit) {
          commit.dataset.codes = data.codes_json || "[]";
          commit.textContent = data.import_label || "Import";
          commit.disabled = !!data.disabled;
        }
        if (counts) {
          const parts = [];
          if (typeof data.row_count === "number") parts.push(data.row_count + " rows");
          if (typeof data.new_count === "number") parts.push(data.new_count + " new");
          if (typeof data.exists_count === "number" && data.exists_count > 0) parts.push(data.exists_count + " existing");
          if (typeof data.skipped_count === "number" && data.skipped_count > 0) parts.push(data.skipped_count + " skipped");
          counts.textContent = parts.join(" · ");
        }
        if (subtitle) {
          const filename = (dialog.dataset.csvPath || "").split(/[\\/]/).pop();
          subtitle.textContent = filename
            ? filename + " · " + (data.summary || "")
            : (data.summary || "");
        }
      }).catch(function () {
        if (seq !== requestSeq) return;
        [preview, review, skipped].forEach(function (region) {
          if (!region) return;
          region.removeAttribute("aria-busy");
          region.innerHTML = '<div class="ace-codebook-import-empty">Could not update preview.</div>';
        });
        if (counts) counts.textContent = "Preview failed";
        if (commit) commit.disabled = true;
      });
    }

    selects.forEach(function (select) {
      select.addEventListener("change", refreshPreview);
    });
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        showView(tab.dataset.codebookImportView || "match");
      });
      tab.addEventListener("keydown", function (evt) {
        const current = tabs.indexOf(tab);
        let next = current;
        if (evt.key === "ArrowRight") next = (current + 1) % tabs.length;
        else if (evt.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
        else if (evt.key === "Home") next = 0;
        else if (evt.key === "End") next = tabs.length - 1;
        else return;
        evt.preventDefault();
        tabs[next].focus();
        showView(tabs[next].dataset.codebookImportView || "match");
      });
    });
    dialog.addEventListener("close", function () {
      const returnTarget = window._aceCodebookImportReturnFocus;
      if (returnTarget && document.contains(returnTarget)) returnTarget.focus();
      window._aceCodebookImportReturnFocus = null;
    }, { once: true });
    const title = dialog.querySelector("#codebook-import-title");
    if (title && typeof title.focus === "function") title.focus({ preventScroll: true });
  };

  window.aceImportFromPreview = function (btn) {
    const codesJson = btn.getAttribute("data-codes");
    const currentIndex = btn.getAttribute("data-current-index") || window.__aceCurrentIndex;
    const mode = btn.dataset.codebookMode || _codebookMutationContext().mode;
    const currentCodeId = btn.dataset.currentCodeId || _codebookMutationContext().currentCodeId;
    if (
      mode === "audit"
      && !window.confirm("Import codebook? This can change the audit view. You can undo imported codes.")
    ) {
      return;
    }
    const dialog = btn.closest("dialog");
    if (dialog) dialog.close();

    let importCount = 0;
    try {
      const parsed = JSON.parse(codesJson);
      if (Array.isArray(parsed)) importCount = parsed.length;
    } catch (_) { /* ignore — fall back to no count */ }
    const successLabel = importCount > 0
      ? "Imported " + importCount + " code" + (importCount === 1 ? "" : "s")
      : "Imported";

    // One-time afterRequest listener — fires the success message only when the
    // import request actually succeeded. _oob_status returns HTTP 200 with an
    // OOB error fragment that overwrites the status bar, so we additionally
    // skip when the response body contains the err-status marker.
    const onAfter = function (evt) {
      if (!evt.detail) return;
      const xhr = evt.detail.xhr;
      if (!xhr || !xhr.responseURL || !xhr.responseURL.endsWith("/api/codes/import")) return;
      document.removeEventListener("htmx:afterRequest", onAfter);
      if (!evt.detail.successful) return;
      const body = xhr.responseText || "";
      if (body.indexOf("ace-statusbar-event--err") !== -1) return;
      window._setStatus(successLabel, "ok");
    };
    document.addEventListener("htmx:afterRequest", onAfter);

    htmx.ajax("POST", "/api/codes/import", {
      values: _codebookMutationValues({
        codes_json: codesJson,
        current_index: currentIndex,
        codebook_mode: mode,
        current_code_id: currentCodeId,
      }),
      target: "#code-sidebar",
      swap: mode === "audit" ? "none" : "outerHTML",
    });
  };

  /* ================================================================
   * 19. Import mapping controls (delegated)
   * ================================================================ */

  function _getImportForm(el) {
    return (el && el.closest && el.closest("#import-form")) || document.getElementById("import-form");
  }

  function _getImportPreviewRows(form) {
    const data = form && form.querySelector("#import-preview-data");
    if (!data) return [];
    try {
      const parsed = JSON.parse(data.dataset.previewRows || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function _getSelectedImportTextColumns(form) {
    return Array.from(form.querySelectorAll("[data-import-text-col]:checked"))
      .map(function (input) { return input.value; })
      .filter(Boolean);
  }

  function _updateImportExamples(form, rows, idCol) {
    const examples = form.querySelector(".ace-import-examples");
    if (!examples) return;
    Array.from(examples.querySelectorAll("code")).forEach(function (code) {
      code.remove();
    });
    const seen = new Set();
    rows.some(function (row, i) {
      const values = row.values || {};
      const label = values[idCol] || row.label || ("Row " + (i + 1));
      if (!label || seen.has(label)) return false;
      seen.add(label);
      const code = document.createElement("code");
      code.textContent = label;
      examples.appendChild(code);
      return seen.size >= 3;
    });
    if (seen.size === 0) {
      const code = document.createElement("code");
      code.textContent = "No labels yet";
      examples.appendChild(code);
    }
  }

  function _renderImportPreview(form, rows, idCol, textCols) {
    const previewLabel = form.querySelector("[data-import-preview-label]");
    const previewMeta = form.querySelector("[data-import-preview-meta]");
    const previewScroll = form.querySelector(".ace-import-preview-scroll");
    if (!previewScroll) return;

    let idx = Number.parseInt(form.dataset.previewIndex || "0", 10);
    if (!Number.isFinite(idx) || idx < 0) idx = 0;
    if (rows.length > 0 && idx >= rows.length) idx = idx % rows.length;
    form.dataset.previewIndex = String(idx);

    const row = rows[idx] || { label: "No rows", values: {} };
    const values = row.values || {};
    const label = values[idCol] || row.label || ("Row " + (idx + 1));
    if (previewLabel) previewLabel.textContent = label;
    if (previewMeta) {
      previewMeta.textContent = "row " + (idx + 1) + " · " + textCols.length + " column" + (textCols.length === 1 ? "" : "s");
    }

    previewScroll.replaceChildren();
    if (textCols.length === 0) {
      const empty = document.createElement("article");
      empty.className = "ace-import-sample-field";
      const p = document.createElement("p");
      p.textContent = "Select at least one text column to preview source text.";
      empty.appendChild(p);
      previewScroll.appendChild(empty);
      return;
    }

    textCols.forEach(function (col) {
      const article = document.createElement("article");
      article.className = "ace-import-sample-field";
      const header = document.createElement("header");
      const title = document.createElement("b");
      title.textContent = col;
      const body = document.createElement("p");
      body.textContent = values[col] || "";
      header.appendChild(title);
      article.appendChild(header);
      article.appendChild(body);
      previewScroll.appendChild(article);
    });
    previewScroll.scrollTop = 0;
  }

  function _syncImportMapping(form) {
    if (!form) return;
    const rows = _getImportPreviewRows(form);
    const idSelect = form.querySelector("#import-id-choice");
    const idCol = idSelect ? idSelect.value : "";
    const textCols = _getSelectedImportTextColumns(form);

    const idHidden = form.querySelector("#import-id-col");
    const textHidden = form.querySelector("#import-text-cols");
    if (idHidden) idHidden.value = idCol;
    if (textHidden) textHidden.value = textCols.join(",");

    form.querySelectorAll(".ace-import-column-row").forEach(function (row) {
      const input = row.querySelector("[data-import-text-col]");
      row.classList.toggle("is-selected", !!(input && input.checked));
    });

    const count = form.querySelector("[data-import-selected-count]");
    if (count) count.textContent = String(textCols.length);

    const submit = form.querySelector("#import-submit");
    if (submit) submit.disabled = !(idCol && textCols.length);

    _updateImportExamples(form, rows, idCol);
    _renderImportPreview(form, rows, idCol, textCols);
  }

  function _filterImportColumns(input) {
    const form = _getImportForm(input);
    if (!form) return;
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    let total = 0;
    form.querySelectorAll(".ace-import-column-row").forEach(function (row) {
      total += 1;
      const matched = !query || row.textContent.toLowerCase().indexOf(query) !== -1;
      row.hidden = !matched;
      if (matched) visible += 1;
    });
    const summary = form.querySelector(".ace-import-summary");
    if (summary) summary.textContent = query ? (visible + " of " + total + " shown") : (total + " columns");
  }

  document.addEventListener("change", function (e) {
    if (!e.target.matches("#import-id-choice, [data-import-text-col]")) return;
    const form = _getImportForm(e.target);
    _syncImportMapping(form);
  });

  document.addEventListener("input", function (e) {
    if (!e.target.matches(".ace-import-search")) return;
    _filterImportColumns(e.target);
  });

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-import-preview-refresh]");
    if (!btn) return;
    const form = _getImportForm(btn);
    if (!form) return;
    const rows = _getImportPreviewRows(form);
    if (rows.length > 1) {
      const current = Number.parseInt(form.dataset.previewIndex || "0", 10) || 0;
      let next = Math.floor(Math.random() * rows.length);
      if (next === current) next = (current + 1) % rows.length;
      form.dataset.previewIndex = String(next);
    }
    _syncImportMapping(form);
  });

  document.addEventListener("htmx:afterSettle", function () {
    const form = document.getElementById("import-form");
    if (!form) return;
    _syncImportMapping(form);
    const search = form.querySelector(".ace-import-search");
    if (search) _filterImportColumns(search);
  });

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("import-form");
    if (!form) return;
    _syncImportMapping(form);
    const search = form.querySelector(".ace-import-search");
    if (search) _filterImportColumns(search);
  });

  /* ================================================================
   * 19b. Codebook hover peek — side popover for truncated names and
   *      imported code definitions in the codebook sidebar. Portal-style: the peek
   *      element lives at body level so the sidebar's overflow:hidden
   *      can't clip it. Event delegation means it survives every OOB
   *      sidebar swap without re-binding.
   * ================================================================ */

  const _peek = {
    el: null,
    showTimer: null,
    hideTimer: null,
    currentRow: null,
  };
  const _PEEK_SHOW_MS = 220;
  const _PEEK_HIDE_GRACE_MS = 80;

  function _peekEl() {
    if (_peek.el) return _peek.el;
    const div = document.createElement("div");
    div.className = "ace-code-peek";
    div.setAttribute("role", "tooltip");
    div.setAttribute("aria-hidden", "true");
    document.body.appendChild(div);
    _peek.el = div;
    return div;
  }

  function _peekSuppressed() {
    if (document.querySelector(".ace-context-menu")) return true;
    if (document.querySelector(".ace-code-row--reordering")) return true;
    if (document.querySelector("#ace-headless-tree-mount .ace-ht-rename")) return true;
    return false;
  }

  function _peekContent(row) {
    const isFolder = _isFolderRow(row);
    const labelEl = row.querySelector(".ace-folder-label, .ace-code-name, .ace-ht-label");
    if (!labelEl) return null;
    const definition = !isFolder ? (row.dataset.definition || "").trim() : "";
    const isTruncated = labelEl.scrollWidth > labelEl.clientWidth;
    if (!isTruncated && !definition) return null;

    const fullName = labelEl.textContent.trim();
    const parts = [];
    let stripe = "";

    if (!isFolder) {
      stripe = row.style.getPropertyValue("--row-colour").trim() || "";
      const cnt = row.querySelector(".ace-code-count, .ace-ht-count");
      if (cnt && cnt.textContent.trim()) {
        parts.push(`<span><strong>${_escapeHtml(cnt.textContent.trim())}</strong>&times;</span>`);
      }
      const chip = row.querySelector(".ace-code-chip, .ace-ht-chip");
      if (chip) {
        const txt = chip.textContent.trim();
        if (txt) {
          const isChord = chip.classList.contains("ace-code-chip--chord") ||
            chip.classList.contains("ace-ht-chip--chord");
          parts.push(`<span>${isChord ? "chord" : "key"} <strong>${_escapeHtml(txt)}</strong></span>`);
        }
      }
    }
    return { fullName, stripe, metaHtml: parts.join(""), definition };
  }

  function _peekShow(row) {
    if (_peekSuppressed()) return;
    const content = _peekContent(row);
    if (!content) return;

    const el = _peekEl();
    el.style.setProperty("--ace-code-peek-stripe", content.stripe || "var(--ace-border)");
    el.innerHTML =
      `<p class="ace-code-peek-name">${_escapeHtml(content.fullName)}</p>` +
      (content.definition
        ? `<div class="ace-code-peek-definition">${_escapeHtml(content.definition)}</div>`
        : "") +
      (content.metaHtml ? `<div class="ace-code-peek-meta">${content.metaHtml}</div>` : "");

    el.classList.add("ace-code-peek--visible");
    el.setAttribute("aria-hidden", "false");

    const rect = row.getBoundingClientRect();
    const peekW = el.offsetWidth;
    const peekH = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = rect.right + 6;
    if (left + peekW > vw - 8) left = Math.max(8, rect.left - peekW - 6);

    let top = rect.top + rect.height / 2 - peekH / 2;
    if (top < 8) top = 8;
    if (top + peekH > vh - 8) top = vh - peekH - 8;

    el.style.left = left + "px";
    el.style.top = top + "px";
    _peek.currentRow = row;
  }

  function _peekHide() {
    if (_peek.showTimer) { clearTimeout(_peek.showTimer); _peek.showTimer = null; }
    if (_peek.hideTimer) { clearTimeout(_peek.hideTimer); _peek.hideTimer = null; }
    if (!_peek.el) return;
    _peek.el.classList.remove("ace-code-peek--visible");
    _peek.el.setAttribute("aria-hidden", "true");
    _peek.currentRow = null;
  }

  function _peekScheduleShow(row) {
    if (_peek.hideTimer) { clearTimeout(_peek.hideTimer); _peek.hideTimer = null; }
    if (_peek.showTimer) clearTimeout(_peek.showTimer);
    if (_peek.currentRow && _peek.currentRow !== row) _peekHide();
    _peek.showTimer = setTimeout(function () { _peekShow(row); }, _PEEK_SHOW_MS);
  }

  function _initCodePeek() {
    const ROW_SEL = "#ace-headless-tree-mount .ace-ht-row";

    document.addEventListener("mouseover", function (e) {
      if (!e.target.closest) return;
      const row = e.target.closest(ROW_SEL);
      if (!row || row === _peek.currentRow) return;
      _peekScheduleShow(row);
    });

    document.addEventListener("mouseout", function (e) {
      if (!e.target.closest) return;
      const row = e.target.closest(ROW_SEL);
      if (!row) return;
      const to = e.relatedTarget;
      if (to && row.contains(to)) return;
      if (_peek.showTimer) { clearTimeout(_peek.showTimer); _peek.showTimer = null; }
      _peek.hideTimer = setTimeout(_peekHide, _PEEK_HIDE_GRACE_MS);
    });

    document.addEventListener("focusin", function (e) {
      if (!e.target.closest) return;
      const row = e.target.closest(ROW_SEL);
      if (!row) return;
      _peekScheduleShow(row);
    });

    document.addEventListener("focusout", function (e) {
      if (!e.target.closest) return;
      if (!e.target.closest("#ace-headless-tree-mount")) return;
      const to = e.relatedTarget;
      if (!to || !to.closest || !to.closest("#ace-headless-tree-mount")) _peekHide();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") _peekHide();
    }, true);

    document.addEventListener("contextmenu", _peekHide);
    document.addEventListener("ace-navigate", _peekHide);
    window.addEventListener("resize", _peekHide);

    document.addEventListener("scroll", function (e) {
      if (e.target && e.target.id === "ace-headless-tree-mount") _peekHide();
    }, true);

    document.body.addEventListener("htmx:beforeSwap", function (e) {
      const t = e.detail && e.detail.target;
      if (!t) return;
      if (t.id === "code-sidebar" || t.id === "text-panel" || t.id === "coding-workspace") {
        _peekHide();
      }
    });
  }

  /* ================================================================
   * 20. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _syncSidebarAfterSwap({ sortable: true, gridResize: true });
    _paintSvg();
    _setAmbient();
    _initCodePeek();
    _initCodingTextControls();
    _syncAppliedCollapseA11y();

    // Set initial roving tabindex — first treeitem gets tabindex="0"
    const items = _getTreeItems();
    if (items.length > 0) {
      items[0].setAttribute("tabindex", "0");
    }

    // Auto-focus first sentence so keyboard works immediately
    const sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    _focusTextPanel();
  });

  /* ================================================================
   * 22. Source-grid collapse toggle
   * ================================================================ */

  /** Toggle the sidebar source-grid panel between expanded and collapsed. */
  function _aceToggleGridCollapse() {
    const wasCollapsed = document.documentElement.dataset.aceGridCollapsed === "1";
    const btn = document.getElementById("ace-grid-collapse-btn");
    if (wasCollapsed) {
      delete document.documentElement.dataset.aceGridCollapsed;
      try { localStorage.removeItem("ace-grid-collapsed"); } catch (_) {}
      if (btn) btn.setAttribute("aria-expanded", "true");
      // Re-render so the ResizeObserver picks up the restored height.
      if (typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }
    } else {
      document.documentElement.dataset.aceGridCollapsed = "1";
      try { localStorage.setItem("ace-grid-collapsed", "1"); } catch (_) {}
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
  }

  // Event delegation on document — survives HTMX OOB swaps that re-create
  // the button element.
  document.addEventListener("click", function (evt) {
    const btn = evt.target.closest("#ace-grid-collapse-btn");
    if (btn) {
      evt.preventDefault();
      _aceToggleGridCollapse();
    }
  });
})();
