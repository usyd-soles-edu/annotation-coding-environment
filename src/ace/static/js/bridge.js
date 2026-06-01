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

  /* ================================================================
   * 3. Folder collapse / expand
   *
   * Folders are <div class="ace-code-folder-row" aria-expanded="…"
   * data-folder-id="…"> rows. The sibling <div role="group"
   * data-folder-children="…"> child container is hidden by CSS when
   * aria-expanded="false" (see coding.css). Toggling collapse is just
   * flipping the attribute on the folder row.
   *
   * Collapse state is per-tab in-memory (folder id → bool). We default
   * to expanded on first paint; explicit collapse persists across
   * sidebar OOB swaps within the session.
   * ================================================================ */

  const _collapsedFolders = {};
  let _sidebarTreeController = null;

  function _getSidebarTreeController() {
    const headlessMount = document.getElementById("ace-headless-tree-mount");
    if (headlessMount) {
      const headless = window.AceHeadlessTreePreview &&
        typeof window.AceHeadlessTreePreview.getController === "function"
          ? window.AceHeadlessTreePreview.getController()
          : window.__aceHeadlessTreeController;
      if (headless && typeof headless.refresh === "function") {
        return headless.refresh();
      }
    }
    if (typeof window.AceCodebookTree === "undefined") return null;
    if (!_sidebarTreeController) {
      _sidebarTreeController = window.AceCodebookTree.createController({
        collapsedFolders: _collapsedFolders,
      });
      window.__aceSidebarTree = _sidebarTreeController;
    } else if (typeof _sidebarTreeController.refresh === "function") {
      _sidebarTreeController.refresh();
    }
    return _sidebarTreeController;
  }

  function _refreshSidebarTreeController() {
    const controller = _getSidebarTreeController();
    if (controller && typeof controller.restoreCollapseState === "function") {
      controller.restoreCollapseState();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    _refreshSidebarTreeController();
  });

  function _toggleFolderCollapse(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.toggleFolderCollapse(folderRow);
      return;
    }
    if (!folderRow) return;
    const expanded = folderRow.getAttribute("aria-expanded") === "true";
    if (expanded) {
      _collapseFolder(folderRow);
    } else {
      _expandFolder(folderRow);
    }
  }

  function _restoreCollapseState() {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.restoreCollapseState();
      return;
    }
    const rows = document.querySelectorAll(".ace-code-folder-row");
    rows.forEach(function (row) {
      const folderId = row.getAttribute("data-folder-id");
      if (folderId && _collapsedFolders[folderId]) {
        _collapseFolder(row);
      }
    });
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

  // Folder rename: F2 on a focused folder row enters inline edit on the
  // .ace-folder-label (handled in the tree keydown listener). Legacy
  // double-click-to-rename was deleted with the /api/codes/rename-group
  // endpoint; folders share the PUT /api/codes/{id} route with codes.

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
    return document.getElementById("ace-headless-tree-mount") ||
      document.getElementById("code-tree");
  }

  function _updateKeycaps() {
    const tree = _keymapRoot();
    if (!tree) return;
    const isHeadless = tree.id === "ace-headless-tree-mount";
    const rows = tree.querySelectorAll(
      isHeadless ? ".ace-ht-row--code[data-code-id]" : ".ace-code-row"
    );
    _currentKeyMap = [];
    let labelIdx = 0; // Counter that only increments for non-chord rows
    rows.forEach(function (row) {
      if (!isHeadless && _isHiddenByCollapsedAncestor(row)) return;
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
      const keycap = row.querySelector(
        isHeadless ? ".ace-ht-chip:not(.ace-ht-chip--chord)" : ".ace-code-chip--key"
      );
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
  let _chordBuffer = "";

  function _enterChordMode() {
    _chordMode = "awaiting";
    _chordBuffer = "";
    document.body.dataset.chordMode = "awaiting";
  }

  function _exitChordMode() {
    _chordMode = null;
    _chordBuffer = "";
    delete document.body.dataset.chordMode;
    delete document.body.dataset.chordBuffer;
    document.querySelectorAll(".ace-chord-match").forEach(function (el) {
      el.classList.remove("ace-chord-match");
    });
  }

  function _onChordBufferChange() {
    if (_chordBuffer.length === 1) {
      document.body.dataset.chordBuffer = _chordBuffer;
      const tree = _keymapRoot();
      if (tree) {
        tree.querySelectorAll(".ace-code-chip--chord, .ace-ht-chip--chord").forEach(function (cap) {
          const row = cap.closest(".ace-code-row, .ace-ht-row--code");
          const chord = row && row.dataset.chord;
          cap.classList.toggle(
            "ace-chord-match",
            !!(chord && chord.startsWith(_chordBuffer))
          );
        });
      }
    }
  }

  function _resolveChord(chord) {
    const tree = _keymapRoot();
    if (tree) {
      const row = tree.querySelector(
        `.ace-code-row[data-chord="${chord}"], .ace-ht-row--code[data-chord="${chord}"]`
      );
      if (row) {
        const codeId = row.getAttribute("data-code-id");
        if (codeId) _applyCode(codeId);
      }
    }
    _exitChordMode();
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

  function _applyCodeToSentence(codeId) {
    if (!Number.isFinite(window.__aceFocusIndex) || window.__aceFocusIndex < 0) return;

    htmx.ajax("POST", "/api/code/apply-sentence", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        sentence_index: window.__aceFocusIndex,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);

    window.__aceLastCodeId = codeId;
    _flashCodeRow(codeId);
  }

  function _applyCodeToSelection(codeId) {
    const sel = window.__aceLastSelection;
    if (!sel) return;

    htmx.ajax("POST", "/api/code/apply", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        start_offset: sel.start,
        end_offset: sel.end,
        selected_text: sel.text,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);

    window.__aceLastCodeId = codeId;
    window.__aceLastSelection = null;
    window.getSelection().removeAllRanges();
    _flashCodeRow(codeId);
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

    // Only handle keys when text panel (or nothing specific) is focused
    let zone = _activeZone();
    if (zone === "search" || zone === "tree") return;
    // Skip entirely on pages without the coding surface (e.g. /code/{id}/view
    // shares bridge.js but has no #text-panel; its shortcuts live in code_view.js).
    if (!document.getElementById("text-panel")) return;

    const key = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;

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

    // ↓ — Navigate to next sentence (or focus first if none focused)
    if (key === "ArrowDown") {
      e.preventDefault();
      const sentences = _getSentences();
      if (sentences.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(0);
      } else if (window.__aceFocusIndex < sentences.length - 1) {
        _focusSentence(window.__aceFocusIndex + 1);
      }
      return;
    }

    // ↑ — Navigate to previous sentence (or focus last if none focused)
    if (key === "ArrowUp") {
      e.preventDefault();
      const sentencesUp = _getSentences();
      if (sentencesUp.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(sentencesUp.length - 1);
      } else if (window.__aceFocusIndex > 0) {
        _focusSentence(window.__aceFocusIndex - 1);
      }
      return;
    }

    // Shift+← / Shift+→ — Navigate between sources
    if (key === "ArrowLeft" && shift) {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex - 1);
      return;
    }
    if (key === "ArrowRight" && shift) {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex + 1);
      return;
    }

    // ← / → (unmodified) — Aliases for ↑ / ↓ when reading. Text panel has no
    // character cursor, so the horizontal arrows are free. "Forward / back"
    // reads more naturally than strict "up / down" for sequential content.
    if (key === "ArrowRight" && !shift) {
      e.preventDefault();
      const sentencesR = _getSentences();
      if (sentencesR.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(0);
      } else if (window.__aceFocusIndex < sentencesR.length - 1) {
        _focusSentence(window.__aceFocusIndex + 1);
      }
      return;
    }
    if (key === "ArrowLeft" && !shift) {
      e.preventDefault();
      const sentencesL = _getSentences();
      if (sentencesL.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(sentencesL.length - 1);
      } else if (window.__aceFocusIndex > 0) {
        _focusSentence(window.__aceFocusIndex - 1);
      }
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
      if (!_isDrawerOpen()) {
        aceOpenNoteRead();
      } else {
        aceEnterEditMode();
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
        let codeId = _currentKeyMap[pos];
        if (window.__aceLastSelection) {
          _applyCodeToSelection(codeId);
        } else if (window.__aceFocusIndex >= 0) {
          _applyCodeToSentence(codeId);
        } else {
          // Auto-focus first sentence if none focused
          _focusSentence(0);
          _applyCodeToSentence(codeId);
        }
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

  window.aceNavigate = async function (index) {
    if (!Number.isFinite(index) || index < 0 || index >= window.__aceTotalSources) return;
    // Flush any pending or in-flight note save before tearing down the page.
    // Without this, debounced saves get cancelled by the navigation.
    if (typeof aceFlushNoteIfDirty === "function") {
      try { await aceFlushNoteIfDirty(); } catch (_) {}
    }
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
      _shortcutRow("↑ / ↓", "Navigate sentences") +
      _shortcutRow("Shift + ← / →", "Previous / next source") +
      _shortcutRow("1 – 9, 0, a–y (not q x z n)", "Apply code") +
      _shortcutRow("Q", "Repeat last code") +
      _shortcutRow("X", "Remove code from sentence") +
      _shortcutRow("Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Shift + Z", "Redo") +
      _shortcutRow("Shift + F", "Flag/unflag source") +
      _shortcutRow("N", "Open / close note panel") +
      _shortcutRow("Tab", "Cycle source → search → tree → source") +
      _shortcutRow("⌥ + →", "Move item into the folder above") +
      _shortcutRow("⌥ + ⇧ + →", "Wrap two sibling codes into a new folder") +
      _shortcutRow("⌥ + ←", "Move item out one folder level") +
      _shortcutRow("⌘/Ctrl + X", "Cut focused item") +
      _shortcutRow("⌘/Ctrl + V", "Paste cut item into focused folder/row") +
      _shortcutRow("Shift + Enter (in filter)", "Create new folder at root") +
      _shortcutRow("F2", "Rename code or folder (in sidebar)") +
      _shortcutRow("Delete / ⌫", "Delete code or folder (in sidebar; Z to undo)") +
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
      let x = e.clientX - rect.left;
      const min = 150;
      const max = rect.width * 0.4;
      x = Math.max(min, Math.min(max, x));
      document.documentElement.style.setProperty("--ace-sidebar-width", `${x}px`);
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      const width = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"), 10);
      if (width) localStorage.setItem("ace-sidebar-width", width);
    });

    handle.addEventListener("dblclick", function () {
      document.documentElement.style.setProperty("--ace-sidebar-width", "360px");
      localStorage.setItem("ace-sidebar-width", 360);
    });
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
        // Clear custom selection if this was a simple click (not drag)
        if (!window.__aceLastSelection) {
          window.getSelection().removeAllRanges();
        }
      }
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
  });

  document.addEventListener("mouseover", function (e) {
    const row = e.target.closest(".ace-applied-code-row");
    if (!row || row.contains(e.relatedTarget)) return;
    _setAppliedCodePreview(row.dataset.codeId);
  });

  document.addEventListener("mouseout", function (e) {
    const row = e.target.closest(".ace-applied-code-row");
    if (!row || row.contains(e.relatedTarget)) return;
    _clearAppliedCodePreview();
  });

  document.addEventListener("focusin", function (e) {
    const row = e.target.closest(".ace-applied-code-row");
    if (!row) return;
    _setAppliedCodePreview(row.dataset.codeId);
  });

  document.addEventListener("focusout", function (e) {
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

    const tree = document.getElementById("code-tree");
    _sidebarFocusState.scrollTop = tree ? tree.scrollTop : 0;
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

  // Patch per-row code-count chips from #ace-ann-data so the sidebar's
  // visible state matches the swapped-in annotation list without needing
  // the server to re-render the aside. Short-circuits when the raw
  // annotations payload is byte-for-byte identical to the last call.
  let _lastAnnDataPayload = "";
  function _syncCodeCounts() {
    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    const payload = dataEl.dataset.annotations || "[]";
    if (payload === _lastAnnDataPayload) return;
    _lastAnnDataPayload = payload;
    let annotations;
    try {
      annotations = JSON.parse(payload);
    } catch (_) {
      return;
    }
    const counts = new Map();
    for (const a of annotations) {
      counts.set(a.code_id, (counts.get(a.code_id) || 0) + 1);
    }
    document
      .querySelectorAll("#code-tree .ace-code-row[data-code-id]")
      .forEach(function (row) {
        const cnt = row.querySelector(".ace-code-count");
        if (!cnt) return;
        const n = counts.get(row.dataset.codeId) || 0;
        if (n > 0) {
          cnt.textContent = String(n);
          cnt.title =
            n + " annotation" + (n !== 1 ? "s" : "") + " in this source";
          cnt.removeAttribute("aria-hidden");
        } else {
          cnt.textContent = "";
          cnt.setAttribute("aria-hidden", "true");
          cnt.removeAttribute("title");
        }
      });
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
    const tree = document.getElementById("code-tree");
    if (tree && _sidebarFocusState.scrollTop) {
      tree.scrollTop = _sidebarFocusState.scrollTop;
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
          _focusTreeItem(item);
        } else {
          const items = _getTreeItems();
          if (items.length > 0) _focusTreeItem(items[0]);
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

  const _COLOUR_PALETTE = ["#A91818","#557FE6","#6DA918","#E655D4","#18A991","#E6A455","#3C18A9","#5BE655","#A91848","#55B0E6","#9DA918","#C855E6","#18A960","#E67355","#1824A9","#8CE655","#A91879","#55E1E6","#A98418","#9755E6","#18A930","#E65567","#1855A9","#BCE655","#A918A9","#55E6BB","#A95418","#6755E6","#30A918","#E65598","#1885A9","#E6E055","#7818A9","#55E68B","#A92318","#5574E6"];

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
    _closeAllPopovers();
    let row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    if (!row) return;
    const rect = row.getBoundingClientRect();

    const popover = document.createElement("div");
    popover.className = "ace-colour-popover";

    _COLOUR_PALETTE.forEach(function (hex) {
      const swatch = document.createElement("button");
      swatch.className = "ace-colour-swatch";
      swatch.style.background = hex;
      swatch.addEventListener("click", function () {
        _closeAllPopovers();
        _codeAction("PUT", `/api/codes/${codeId}`,
          `colour=${encodeURIComponent(hex)}&current_index=${window.__aceCurrentIndex}`);
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
      values: { code_ids: "[]", current_index: window.__aceCurrentIndex },
    }).then(function () {
      _syncSidebarAfterSwap({ sortable: true });
    });
  }

  function _codeAction(method, url, body) {
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
    function save() {
      if (done) return;
      done = true;
      const newName = nameEl.textContent.trim();
      nameEl.contentEditable = "false";
      if (!newName || newName === original) {
        nameEl.textContent = original;
        _focusTreeItem(row);
        return;
      }
      _codeAction("PUT", `/api/codes/${targetId}`,
        `name=${encodeURIComponent(newName)}&current_index=${window.__aceCurrentIndex}`
      ).catch(function () { nameEl.textContent = original; });
      _focusTreeItem(row);
    }

    nameEl.addEventListener("keydown", function handler(e) {
      if (e.key === "Enter") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); save(); }
      if (e.key === "Escape") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); done = true; nameEl.textContent = original; nameEl.contentEditable = "false"; _focusTreeItem(row); }
    });

    nameEl.addEventListener("blur", function blurHandler() {
      nameEl.removeEventListener("blur", blurHandler);
      setTimeout(function () { save(); }, 50);
    });

    nameEl.addEventListener("paste", function pasteHandler(e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text.replace(/\n/g, " "));
    });
  }

  // _startGroupRename was removed: the underlying PUT /api/codes/rename-group
  // route was deleted with the v7 migration (commit 769e51d). Folder rename
  // will be re-introduced in Task 9 against PUT /api/codes/{id} (folders share
  // the same `name` column as codes; `kind='folder'` is preserved).

  document.addEventListener("dblclick", function (e) {
    const nameEl = e.target.closest(".ace-code-name");
    if (!nameEl) return;
    let row = nameEl.closest(".ace-code-row");
    if (!row) return;
    let codeId = row.getAttribute("data-code-id");
    if (codeId) _startInlineRename(codeId);
  });

  function _executeDelete(codeId) {
    _lastSelectedCodeId = null;
    // Route the response through HTMX (not _codeAction's plain fetch) so the
    // OOB statusbar/pill fragments carrying the [Z] undo affordance get
    // applied to the page. current_index goes in the URL — htmx.ajax's
    // `values` ride in the request body for DELETE, but the route reads
    // current_index via Query, so a body-borne value would be ignored.
    const idx = encodeURIComponent(window.__aceCurrentIndex);
    htmx.ajax("DELETE", `/api/codes/${codeId}?current_index=${idx}`, {
      target: "#text-panel",
      swap: "outerHTML",
    });
  }

  function _moveCode(codeId, direction) {
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

  let _sortableInstances = [];
  let _isDragging = false;
  // Original DOM positions of code rows, captured on entry to search mode so
  // we can restore the codebook to its grouped layout when the query clears.
  // null = not in search mode; Map<rowEl, {parent, nextSibling}> otherwise.
  let _origRowPositions = null;

  function _initSortable() {
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
            target: "#text-panel",
            swap: "outerHTML",
            values: {
              parent_id: newParentId,
              target_order_ids: JSON.stringify(targetOrderIds || []),
              current_index: window.__aceCurrentIndex,
            },
          });
        },
        onPersistScopeOrder: _persistScopeOrder,
      });
      return;
    }

    // Sortable.min.js only loads on /code (coding.html). On /code/{id}/view the
    // sidebar partial is shared but drag-to-reorder isn't wired — bail quietly.
    if (typeof Sortable === "undefined") return;

    // Destroy any prior instances bound to detached DOM. Without this, OOB
    // swaps accumulate Sortable bindings and onEnd fires multiple times per
    // drop — every swap that re-renders the sidebar would otherwise leave
    // stale instances pointing at orphaned nodes.
    _sortableInstances.forEach(function (s) {
      try { s.destroy(); } catch (_) {}
    });
    _sortableInstances = [];

    // Root and every folder group accept code rows and folder blocks. Codes
    // stay leaves because only `.ace-folder-block` owns a child group.
    const root = document.getElementById("code-tree");
    if (!root) return;

    function tauriRuntime() {
      return !!(window.__TAURI__ || window.__TAURI_INTERNALS__);
    }

    if (tauriRuntime() && root.dataset.aceDragSelectionBound !== "1") {
      root.dataset.aceDragSelectionBound = "1";
      root.addEventListener("mousedown", function (evt) {
        if (evt.target.closest("input, textarea, button, a, [contenteditable='true']")) return;
        if (!evt.target.closest(".ace-code-row, .ace-code-folder-row")) return;
        if (evt.cancelable) evt.preventDefault();
        const selection = window.getSelection && window.getSelection();
        if (selection && selection.removeAllRanges) selection.removeAllRanges();
      }, true);
    }

    function commonOpts() {
      const useFallbackDrag = tauriRuntime();
      return {
        group: "codes",
        animation: 0,
        delay: 200,
        delayOnTouchOnly: true,
        forceFallback: useFallbackDrag,
        fallbackOnBody: useFallbackDrag,
        fallbackTolerance: useFallbackDrag ? 4 : 0,
        ghostClass: "ace-codebook-sort-placeholder",
        onStart: function () { _isDragging = true; },
      };
    }

    function isInvalidFolderDrop(container, dragEl) {
      if (!dragEl.classList.contains("ace-folder-block")) return false;
      return dragEl.contains(container);
    }

    function handleItemEnd(evt) {
      const itemId = _itemIdFromTreeElement(evt.item);
      if (!itemId) return;
      const newContainer = evt.to;
      const newParentId = newContainer.getAttribute("data-folder-children") || "";
      const oldContainer = evt.from;
      const oldParentId = oldContainer.getAttribute("data-folder-children") || "";
      if (isInvalidFolderDrop(newContainer, evt.item)) {
        _refreshSidebar();
        window._setStatus("A folder cannot move inside itself", "err");
        return;
      }

      if (newParentId === oldParentId) {
        _persistScopeOrder(newContainer);
      } else {
        htmx.ajax("PUT", "/api/codes/" + itemId + "/parent", {
          target: "#text-panel",
          swap: "outerHTML",
          values: {
            parent_id: newParentId,
            current_index: window.__aceCurrentIndex,
          },
        });
      }
    }

    const rootInstance = new Sortable(root, Object.assign(commonOpts(), {
      handle: ".ace-code-row, .ace-code-folder-row",
      draggable: ".ace-code-row, .ace-folder-block",
      onEnd: function (evt) {
        _isDragging = false;
        handleItemEnd(evt);
      },
    }));
    _sortableInstances.push(rootInstance);

    document.querySelectorAll('#code-tree [role="group"]').forEach(function (container) {
      const instance = new Sortable(container, Object.assign(commonOpts(), {
        group: {
          name: "codes",
          put: function (to, _from, dragEl) {
            return !isInvalidFolderDrop(to.el, dragEl);
          },
        },
        handle: ".ace-code-row, .ace-code-folder-row",
        draggable: ".ace-code-row, .ace-folder-block",
        onEnd: function (evt) {
          _isDragging = false;
          handleItemEnd(evt);
        },
      }));
      _sortableInstances.push(instance);
    });
  }

  /* ================================================================
   * 14. Right-click context menu (Task 12)
   * ----------------------------------------------------------------
   * Mouse-discovery surface for the keyboard codebook gestures. Three
   * menu shapes:
   *   - code row: Move to folder \u25b8, Move to root, Convert to folder,
   *     Cut, Paste here, Rename, Change colour\u2026, View coded text, Delete
   *   - folder row: Rename, Cut, Paste here, Delete folder
   *   - empty area of #code-tree: New folder, Paste here
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
    if (!codeId || !folderId) return;
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: { parent_id: folderId, current_index: window.__aceCurrentIndex || 0 },
    });
  }

  /** Move an item back to root (empty parent_id). */
  function _moveCodeToRoot(codeId) {
    if (!codeId) return;
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: { parent_id: "", current_index: window.__aceCurrentIndex || 0 },
    });
  }

  /** Paste the cut item onto a code row (target_id is a code id). */
  function _pasteCodeInto(targetId) {
    if (!_cutCode || !targetId || targetId === _cutCode) return;
    const cutId = _cutCode;
    htmx.ajax("POST", "/api/codes/cut-paste", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: cutId,
        target_id: targetId,
        current_index: window.__aceCurrentIndex || 0,
      },
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  }

  /** Paste the cut item into a folder (target_id is a folder id; "" = root). */
  function _pasteCodeIntoFolder(folderId) {
    if (!_cutCode) return;
    const cutId = _cutCode;
    htmx.ajax("POST", "/api/codes/cut-paste", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: cutId,
        target_id: folderId || "",
        current_index: window.__aceCurrentIndex || 0,
      },
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  }

  function _convertCodeToFolder(codeId) {
    if (!codeId) return;
    htmx.ajax("POST", `/api/codes/${codeId}/convert-to-folder`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: { current_index: window.__aceCurrentIndex || 0 },
    });
  }

  /** Focus the filter input and prompt the user to create a folder.
   *  Simpler than chaining "create + auto-move" \u2014 user types the name and
   *  hits Shift+Enter (existing handler in section 15). If `forCodeId` is
   *  set we just hint that the next step (cut/paste) is on them. */
  function _promptNewFolder(forCodeId) {
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
    } else if (e.target.closest("#code-tree, #ace-headless-tree-mount")) {
      items = _buildEmptyAreaMenu();
    } else {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    _renderContextMenu(items, e.clientX, e.clientY);
  });

  /** Unified apply helper used by keycap click, search Enter, and tree Enter. */
  function _applyCode(codeId, opts) {
    opts = opts || {};
    let codeName = opts.codeName || "";
    let row = _findCodebookItemRow(codeId);
    if (row) {
      codeName = _codebookRowLabel(row) || codeName;
    }
    const isSelection = !!window.__aceLastSelection;
    if (isSelection) {
      _applyCodeToSelection(codeId);
    } else if (window.__aceFocusIndex >= 0) {
      _applyCodeToSentence(codeId);
    } else {
      return;
    }
    if (codeName) {
      const target = isSelection ? "selection" : "sentence " + (window.__aceFocusIndex + 1);
      _announce(`'${codeName}' applied to ${target}`);
    }
  }

  document.addEventListener("ace:apply-code", function (event) {
    const detail = event.detail || {};
    if (!detail.codeId) return;
    _clearSearchFilter();
    _applyCode(detail.codeId, { codeName: detail.codeName || "" });
  });

  document.addEventListener("ace:rename-codebook-item", function (event) {
    const detail = event.detail || {};
    const itemId = detail.itemId;
    const name = (detail.name || "").trim();
    if (!itemId || !name) return;
    htmx.ajax("PUT", `/api/codes/${itemId}`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        name: name,
        current_index: window.__aceCurrentIndex || 0,
      },
    });
  });

  document.addEventListener("ace:delete-codebook-item", function (event) {
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
    _exitSlashMode();
    _resetSearchFilterState();
    if (!el) return;
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  /* ================================================================
   * 15. Code search / filter / create
   * ================================================================ */

  document.addEventListener("input", function (e) {
    if (e.target.id !== "code-search-input") return;
    const rawValue = e.target.value;
    const query = rawValue.toLowerCase();
    const tree = document.getElementById("code-tree");
    if (!tree) return;

    // Slash command mode dispatch — when input starts with "/" we replace
    // the tree with a command palette and short-circuit normal filter logic.
    if (rawValue.startsWith("/")) {
      _enterSlashMode();
      _renderSlashSuggestions(rawValue);
      return;
    } else if (_slashState.active) {
      // Leaving slash mode — restore class state and the saved tree HTML.
      // Then fall through so the filter logic below repaints the tree with
      // the (non-slash) query.
      _slashState.active = false;
      const inputEl = document.getElementById("code-search-input");
      if (inputEl) inputEl.classList.remove("slash-active");
      if (_slashState.savedTreeHTML !== null) {
        tree.innerHTML = _slashState.savedTreeHTML;
        _slashState.savedTreeHTML = null;
      }
    }

    // Remove any existing "create" prompt
    const oldPrompt = tree.querySelector(".ace-create-prompt");
    if (oldPrompt) oldPrompt.remove();
    // Remove any existing zero-match create row (will be re-added if needed)
    const oldCreateRow = tree.querySelector(".ace-create-row");
    if (oldCreateRow) oldCreateRow.remove();

    if (query && !query.startsWith("/")) {
      // Filter + score-rank via fuzzysort. Matched rows are flattened to
      // tree-level in descending score order; group headers + groups hide.
      _sortableInstances.forEach(function (s) { s.option("disabled", true); });
      const allRows = Array.from(tree.querySelectorAll(".ace-code-row"));

      // Snapshot original positions on first entry to search mode so we can
      // put rows back in their original groups when the query clears.
      if (!_origRowPositions) {
        _origRowPositions = new Map();
        allRows.forEach(function (row) {
          _origRowPositions.set(row, {
            parent: row.parentNode,
            nextSibling: row.nextSibling,
          });
        });
      }

      // Pair each row with its name for fuzzysort. Use the cached original
      // text, not nameEl.textContent — a previous keystroke may have left
      // <mark> tags which would distort scoring.
      const candidates = allRows.map(function (row) {
        const nameEl = row.querySelector(".ace-code-name");
        // Strip any prior <mark>: textContent already does that.
        return { row: row, name: nameEl ? nameEl.textContent : "" };
      });

      const results = fuzzysort.go(query, candidates, { key: "name" });

      // Hide everything first; matches will be re-shown below.
      allRows.forEach(function (row) {
        row.style.display = "none";
        row.setAttribute("aria-hidden", "true");
        const nameEl = row.querySelector(".ace-code-name");
        if (nameEl && nameEl.querySelector("mark")) {
          nameEl.textContent = nameEl.textContent; // strip prior highlight
        }
      });
      // Hide folder rows + their children containers + the root divider so
      // matching code rows render flat at the top of the visible flow.
      tree.querySelectorAll(".ace-code-folder-row, [role='group'], .ace-root-divider").forEach(function (el) {
        el.style.display = "none";
        el.setAttribute("aria-hidden", "true");
      });

      // Reattach matched rows at tree level in descending-score order. Since
      // group containers are now display:none, the rows render flat at the
      // top of the visible tree flow.
      results.forEach(function (result) {
        const row = result.obj.row;
        const text = result.obj.name;
        row.style.display = "";
        row.removeAttribute("aria-hidden");
        const nameEl = row.querySelector(".ace-code-name");
        if (nameEl) {
          // Coalesce adjacent matched indexes into one <mark> span.
          const matchSet = new Set(result.indexes);
          let html = "";
          let inMark = false;
          for (let i = 0; i < text.length; i++) {
            const isMatch = matchSet.has(i);
            if (isMatch && !inMark) { html += "<mark>"; inMark = true; }
            else if (!isMatch && inMark) { html += "</mark>"; inMark = false; }
            html += _escapeHtml(text[i]);
          }
          if (inMark) html += "</mark>";
          nameEl.innerHTML = html;
        }
        tree.appendChild(row);
      });

      // No matches: zero-match create affordance is rendered by
      // _renderZeroMatchCreateRow() at the tail of this handler — kept in
      // one place so the chip-style ↵ row replaces the legacy plain prompt.

      // Mark the top-scoring row as the Enter target.
      const prevTarget = tree.querySelector(".ace-code-row--search-target");
      if (prevTarget) {
        prevTarget.classList.remove("ace-code-row--search-target");
        prevTarget.removeAttribute("aria-current");
      }
      if (results.total > 0) {
        const target = results[0].obj.row;
        target.classList.add("ace-code-row--search-target");
        target.setAttribute("aria-current", "true");
      }
    } else {
      // Empty: restore all rows + folders, undo any score-order moves.
      // (The legacy "/foo" group-creation mode was removed \u2014 folders are
      // now created via Task 9 wrap-into-folder shortcut, not via search.)
      _sortableInstances.forEach(function (s) { s.option("disabled", false); });

      // Put rows back where they were before search mode. Skip any row whose
      // cached parent was detached (e.g. tree was re-rendered via OOB swap
      // mid-search) — the new tree already has them in the right place.
      if (_origRowPositions) {
        _origRowPositions.forEach(function (pos, row) {
          if (row.isConnected && pos.parent.isConnected) {
            pos.parent.insertBefore(row, pos.nextSibling);
          }
        });
        _origRowPositions = null;
      }

      tree.querySelectorAll(".ace-code-row").forEach(function (row) {
        row.style.display = "";
        row.removeAttribute("aria-hidden");
        const nameEl = row.querySelector(".ace-code-name");
        if (nameEl && nameEl.querySelector("mark")) {
          nameEl.textContent = nameEl.textContent; // Strip HTML
        }
      });
      tree.querySelectorAll(".ace-code-folder-row, .ace-root-divider").forEach(function (el) { el.style.display = ""; el.removeAttribute("aria-hidden"); });
      tree.querySelectorAll('[role="group"]').forEach(function (g) { g.style.display = ""; g.removeAttribute("aria-hidden"); });
      _restoreCollapseState();
      const prevTarget = tree.querySelector(".ace-code-row--search-target");
      if (prevTarget) {
        prevTarget.classList.remove("ace-code-row--search-target");
        prevTarget.removeAttribute("aria-current");
      }
    }

    _updateKeycaps();
    _renderZeroMatchCreateRow(rawValue);
  });

  function _createCodeFromSearchOrSlash(rawValue) {
    const input = document.getElementById("code-search-input");
    if (!input) return;
    let val = (rawValue !== undefined ? rawValue : input.value).trim();
    if (!val) return;

    // Slash command path
    if (val.startsWith("/")) {
      _commitSlashCommand(val);
      return;
    }

    // Plain code creation
    htmx.ajax("POST", "/api/codes", {
      values: { name: val, current_index: window.__aceCurrentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    }).then(function () { _scrollNewRowIntoView(val, false); });
    input.value = "";
    _exitSlashMode();
    _announce(`Code '${val}' created`);
  }

  /** Find a code or folder row by its label text. opts.isFolder picks the
   *  selector; opts.caseInsensitive folds case for NOCASE dedupe. */
  function _findRowByName(name, opts) {
    opts = opts || {};
    const ci = !!opts.caseInsensitive;
    const target = ci ? name.trim().toLowerCase() : name.trim();
    const rowSel = opts.isFolder ? ".ace-code-folder-row" : ".ace-code-row";
    const labelSel = opts.isFolder ? ".ace-folder-label" : ".ace-code-name";
    for (const r of document.querySelectorAll(rowSel)) {
      const label = r.querySelector(labelSel);
      if (!label) continue;
      const text = label.textContent.trim();
      if ((ci ? text.toLowerCase() : text) === target) return r;
    }
    return null;
  }

  /** Scroll a freshly-created codebook row into view if it isn't already.
   *  `block: "nearest"` is a no-op when the row is already on screen, so
   *  short codebooks don't get jolted around. */
  function _scrollNewRowIntoView(name, isFolder) {
    const row = _findRowByName(name, { isFolder });
    if (row) row.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ============================================================
  // Slash command palette
  // ============================================================
  //
  // Two commands at v1: /code <name>, /folder <name>.
  // Bare `/` shows both. Typing `/co` narrows to /code (prefix match).
  // Command name is case-insensitive; argument is trimmed.
  // Empty arg → noop with hint, Enter does NOT commit.
  // Unknown command → "No matching command" in suggestion area.
  // ============================================================

  const _SLASH_COMMANDS = [
    {
      name: "code",
      desc: "create code",
      placeholder: "Name",
      commit: function (arg) {
        htmx.ajax("POST", "/api/codes", {
          values: { name: arg, current_index: window.__aceCurrentIndex },
          target: "#code-sidebar",
          swap: "outerHTML",
        }).then(function () { _scrollNewRowIntoView(arg, false); });
        _announce(`Code '${arg}' created`);
      },
    },
    {
      name: "folder",
      desc: "create folder",
      placeholder: "Name",
      commit: function (arg) {
        // Route via the shared safe-create helper so the client-side
        // NOCASE dedupe runs FIRST. The server's duplicate response is
        // OOB-only with no `HX-Reswap: none`, so a raw htmx.ajax with
        // target #text-panel + swap outerHTML would wipe the coding view
        // on collision (see CLAUDE.md gotcha for the Shift+Enter path).
        _createFolderSafe(arg);
      },
    },
  ];

  let _slashState = { active: false, selectedIndex: 0, savedTreeHTML: null };

  /** Create a folder with a client-side NOCASE dedupe guard.
   *  Server enforces uniqueness too, but its duplicate response is OOB-only
   *  with no `HX-Reswap: none` header — pairing that with our outerHTML swap
   *  on #text-panel would wipe the coding view (CLAUDE.md gotcha).
   *
   *  opts.focusAndRename — if true, after the create succeeds, focus the new
   *  folder row and open inline rename (the Shift+Enter behaviour). The
   *  slash-command path leaves it false; the folder is just created. */
  function _createFolderSafe(name, opts) {
    opts = opts || {};
    if (!name) return;
    const dupRow = _findRowByName(name, { isFolder: true, caseInsensitive: true });
    if (dupRow) {
      _clearSearchFilter();
      window._setStatus(`Folder '${name}' already exists — focused`, "ok");
      _focusTreeItem(dupRow);
      return;
    }
    const input = document.getElementById("code-search-input");
    htmx.ajax("POST", "/api/codes/folder", {
      target: "#text-panel",
      swap: "outerHTML",
      values: { name: name, current_index: window.__aceCurrentIndex },
    }).then(function () {
      // Clear filter input + state so the just-rendered new folder isn't
      // hidden by a stale filter the user typed.
      if (input) input.value = "";
      _clearSearchFilter();
      _announce(`Folder '${name}' created`);
      _scrollNewRowIntoView(name, true);
      if (opts.focusAndRename) {
        setTimeout(function () {
          const f = _findRowByName(name, { isFolder: true });
          if (f) {
            _focusTreeItem(f);
            _startInlineRename(f, { isFolder: true });
          }
          window._setStatus(`Folder ${name} created`, "ok");
        }, 30);
      } else {
        window._setStatus(`Folder ${name} created`, "ok");
      }
    });
  }

  function _parseSlash(value) {
    // Returns { matches: [...], arg: string, fragment: string }
    // fragment is what the user has typed after the / (used to filter commands).
    const v = value.replace(/^\//, "");
    const sp = v.indexOf(" ");
    let cmdFragment, arg;
    if (sp === -1) {
      cmdFragment = v;
      arg = "";
    } else {
      cmdFragment = v.slice(0, sp);
      arg = v.slice(sp + 1).trim();
    }
    // Case-insensitive prefix match
    const lower = cmdFragment.toLowerCase();
    const matches = _SLASH_COMMANDS.filter(function (c) {
      return c.name.startsWith(lower);
    });
    return {
      matches: matches,
      arg: arg,
      fragment: cmdFragment,
    };
  }

  function _enterSlashMode() {
    if (_slashState.active) {
      // Already active; just keep selection in range
      return;
    }
    // If a search filter is active, restore the tree to its pre-filter
    // state BEFORE snapshotting. Otherwise the snapshot would freeze the
    // filter's flattened layout and `_origRowPositions` would still hold
    // references to DOM nodes that the snapshot-restore is about to
    // replace, leaving rows stuck out-of-place after slash mode exits.
    _resetSearchFilterState();
    _slashState.active = true;
    _slashState.selectedIndex = 0;
    // Snapshot the current tree HTML so we can restore it if the user exits
    // slash mode without committing (slash-mode renders REPLACE the tree's
    // innerHTML, so without this snapshot the original rows are lost).
    const tree = document.getElementById("code-tree");
    if (tree) _slashState.savedTreeHTML = tree.innerHTML;
    const input = document.getElementById("code-search-input");
    if (input) input.classList.add("slash-active");
  }

  /** Reset filter state without touching the input value or refiring events.
   *  Mirrors the empty-query branch of the input handler — moves rows back
   *  to their original parents, clears _origRowPositions, restores display
   *  on hidden rows, drops the search-target marker. Safe to call when no
   *  filter is active (it's a no-op in that case). */
  function _resetSearchFilterState() {
    const tree = document.getElementById("code-tree");
    if (!tree) return;
    if (_origRowPositions) {
      _origRowPositions.forEach(function (pos, row) {
        if (row.isConnected && pos.parent.isConnected) {
          pos.parent.insertBefore(row, pos.nextSibling);
        }
      });
      _origRowPositions = null;
    }
    tree.querySelectorAll(".ace-code-row").forEach(function (row) {
      row.style.display = "";
      row.removeAttribute("aria-hidden");
      const nameEl = row.querySelector(".ace-code-name");
      if (nameEl && nameEl.querySelector("mark")) {
        nameEl.textContent = nameEl.textContent;  // strip mark HTML
      }
    });
    tree.querySelectorAll(".ace-code-folder-row, .ace-root-divider").forEach(function (el) {
      el.style.display = "";
      el.removeAttribute("aria-hidden");
    });
    tree.querySelectorAll('[role="group"]').forEach(function (g) {
      g.style.display = "";
      g.removeAttribute("aria-hidden");
    });
    const prevTarget = tree.querySelector(".ace-code-row--search-target");
    if (prevTarget) {
      prevTarget.classList.remove("ace-code-row--search-target");
      prevTarget.removeAttribute("aria-current");
    }
    if (typeof _restoreCollapseState === "function") _restoreCollapseState();
  }

  function _exitSlashMode() {
    if (!_slashState.active) return;
    _slashState.active = false;
    const input = document.getElementById("code-search-input");
    if (input) input.classList.remove("slash-active");
    // Restore the saved tree HTML so the original rows come back.
    const tree = document.getElementById("code-tree");
    if (tree && _slashState.savedTreeHTML !== null) {
      tree.innerHTML = _slashState.savedTreeHTML;
    }
    _slashState.savedTreeHTML = null;
    _renderTreeAfterSlashExit();
  }

  function _renderSlashSuggestions(value) {
    const tree = document.getElementById("code-tree");
    if (!tree) return;
    const parsed = _parseSlash(value);
    // Clamp selection to valid range
    if (_slashState.selectedIndex >= parsed.matches.length) {
      _slashState.selectedIndex = Math.max(0, parsed.matches.length - 1);
    }
    let html = '<div class="ace-slash-mode">Commands</div>';
    if (parsed.matches.length === 0) {
      html += '<div class="ace-empty-zero">No matching command</div>';
    } else {
      parsed.matches.forEach(function (cmd, i) {
        const selected = i === _slashState.selectedIndex;
        const argDisplay = parsed.arg
          ? '<span class="arg">' + _escapeHtml(parsed.arg) + '</span>'
          : '<span class="arg">' + cmd.placeholder + '</span>';
        const desc = parsed.arg
          ? cmd.desc
          : 'Type a name after /' + cmd.name;
        const commitHint = parsed.arg
          ? '<span class="commit-hint">↵</span>'
          : '<span class="desc">' + _escapeHtml(desc) + '</span>';
        html += '<div class="ace-slash-item" data-selected="' + selected + '" data-cmd-name="' + cmd.name + '">'
              + '<span class="cmd">/' + cmd.name + ' ' + argDisplay + '</span>'
              + commitHint
              + '</div>';
      });
    }
    tree.innerHTML = html;
  }

  function _commitSlashCommand(value) {
    const parsed = _parseSlash(value);
    if (parsed.matches.length === 0) return;
    // Find the selected one (or first if state out of range)
    const cmd = parsed.matches[Math.min(_slashState.selectedIndex, parsed.matches.length - 1)];
    if (!cmd) return;
    // Empty arg → noop (the suggestion description tells the user)
    if (!parsed.arg) return;
    // Exit slash mode FIRST so the tree is restored to its real codebook
    // rows before the commit runs. Some commits (e.g. _createFolderSafe)
    // need to query the live tree for dedupe — the slash suggestion list
    // is what's currently in the DOM until _exitSlashMode restores it.
    const input = document.getElementById("code-search-input");
    if (input) input.value = "";
    _exitSlashMode();
    cmd.commit(parsed.arg);
  }

  function _renderTreeAfterSlashExit() {
    // The tree is owned by the server-rendered template. Exiting slash mode
    // just lets the next OOB swap re-populate it. If the user exits slash
    // mode without committing, refire the input event so the filter loop
    // re-evaluates and repopulates the tree from the existing DOM rows.
    const input = document.getElementById("code-search-input");
    if (input) input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function _renderZeroMatchCreateRow(query) {
    const tree = document.getElementById("code-tree");
    if (!tree) return;
    if (!query.trim()) return;
    // Don't add if there are visible matches OR we're in slash mode
    if (_slashState.active) return;
    let visibleCount = 0;
    tree.querySelectorAll(".ace-code-row").forEach(function (r) {
      if (r.style.display !== "none") visibleCount++;
    });
    if (visibleCount > 0) return;
    // Render the inline create row at the top of the tree
    const existing = tree.querySelector(".ace-create-row");
    if (existing) existing.remove();
    const escaped = _escapeHtml(query.trim());
    const row = document.createElement("div");
    row.className = "ace-create-row";
    row.tabIndex = 0;
    row.innerHTML = '<span class="plus">+</span>'
                  + '<span class="label">Create code <em>\'' + escaped + '\'</em></span>'
                  + '<span class="commit-hint">↵</span>';
    row.addEventListener("click", function () {
      _createCodeFromSearchOrSlash(query.trim());
    });
    tree.insertBefore(row, tree.firstChild);
  }

  // _createGroupFromSearch and _makeGroupElements were removed: client-side
  // folder creation has no server endpoint to back it (folders are created
  // via Task 9 wrap-into-folder shortcut against POST /api/codes/folder).

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
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: cutId,
        target_id: targetId,
        current_index: window.__aceCurrentIndex,
      },
    }).then(function () {
      _setCut(null);
      window._setStatus("", "ok");
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.target.id !== "code-search-input") return;
    const input = e.target;

    // ⌘+Enter (or Ctrl+Enter on non-mac) creates a code from the input text,
    // regardless of filter state. Distinct from plain Enter, which still
    // applies the first match (existing behaviour preserved).
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      _createCodeFromSearchOrSlash(input.value);
      return;
    }

    // Slash command navigation — when the palette is active, ↑/↓ move the
    // selection, Enter commits the highlighted suggestion, Esc exits.
    if (_slashState.active) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const tree = document.getElementById("code-tree");
        const items = tree ? tree.querySelectorAll(".ace-slash-item") : [];
        if (items.length > 0) {
          _slashState.selectedIndex = Math.min(_slashState.selectedIndex + 1, items.length - 1);
          _renderSlashSuggestions(input.value);
        }
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        _slashState.selectedIndex = Math.max(_slashState.selectedIndex - 1, 0);
        _renderSlashSuggestions(input.value);
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        _commitSlashCommand(input.value);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        input.value = "";
        _exitSlashMode();
        return;
      }
    }

    // Shift+Enter — create a new folder named after the current filter text.
    // Server enforces NOCASE uniqueness via add_folder, but the duplicate
    // path returns an OOB-only status fragment with no `HX-Reswap: none`
    // header — pairing that with `swap: outerHTML` would wipe #text-panel.
    // So we do a client-side NOCASE check FIRST against the rendered tree
    // and short-circuit duplicates without hitting the server.
    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      const name = input.value.trim();
      if (!name) return;
      _createFolderSafe(name, { focusAndRename: true });
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (e.target.value) {
        e.target.value = "";
        e.target.dispatchEvent(new Event("input", { bubbles: true }));
      }
      _focusTextPanel();
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      _focusCodeTree();
      return;
    }

    if (e.key !== "Enter") return;
    const val = e.target.value.trim();
    if (!val) return;
    e.preventDefault();

    // Only create if no visible code rows; otherwise apply the first match.
    const tree = document.getElementById("code-tree");
    let count = 0;
    if (tree) {
      tree.querySelectorAll(".ace-code-row").forEach(function (r) {
        if (r.style.display !== "none") count++;
      });
    }
    if (count === 0) {
      _createCodeFromSearchOrSlash();
    } else {
      // Has matches — find first visible match, clear search, apply
      const firstMatch = tree
        ? Array.from(tree.querySelectorAll(".ace-code-row")).find(function (r) { return r.style.display !== "none"; })
        : null;
      _clearSearchFilter();
      if (firstMatch) {
        let codeId = firstMatch.getAttribute("data-code-id");
        if (codeId) _applyCode(codeId);
      }
    }
  });

  /** Collect all code row IDs from the tree and persist the order via API. */
  function _persistCodeOrder() {
    const allRows = document.querySelectorAll("#code-tree .ace-code-row");
    const ids = [];
    allRows.forEach(function (row) {
      let id = row.getAttribute("data-code-id");
      if (id) ids.push(id);
    });
    _codeAction("POST", "/api/codes/reorder",
      `code_ids=${encodeURIComponent(JSON.stringify(ids))}&current_index=${window.__aceCurrentIndex}`);
  }

  function _persistScopeOrder(container, orderedIds) {
    if (!container) return;
    const ids = Array.isArray(orderedIds) ? orderedIds : _directChildItemIds(container);
    const parentId = container.getAttribute("data-folder-children") || "";
    htmx.ajax("POST", "/api/codes/reorder-in-scope", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_ids: JSON.stringify(ids),
        parent_id: parentId,
        current_index: window.__aceCurrentIndex || 0,
      },
    });
  }

  /** Walk the tree top-to-bottom and persist a unified flat order of folder + code ids.
   *  Used by the keyboard folder-reorder gesture. The /codes/reorder endpoint only
   *  rewrites kind='code' rows; folder reorders need this tree-aware sibling. */
  function _persistTreeOrder() {
    const tree = document.getElementById("code-tree");
    if (!tree) return;
    const ids = [];
    Array.from(tree.children).forEach(function (node) {
      if (!node.classList) return;
      // Folder block wraps the folder header + its [role="group"] children.
      if (node.classList.contains("ace-folder-block")) {
        const fid = node.getAttribute("data-folder-id");
        if (fid) ids.push(fid);
        node.querySelectorAll(".ace-folder-block, .ace-code-row").forEach(function (child) {
          const id = _itemIdFromTreeElement(child);
          if (id) ids.push(id);
        });
        return;
      }
      // Root-level code row.
      const cid = node.getAttribute && node.getAttribute("data-code-id");
      if (cid) ids.push(cid);
    });
    htmx.ajax("POST", "/api/codes/reorder-tree", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        tree_ids: JSON.stringify(ids),
        current_index: window.__aceCurrentIndex || 0,
      },
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
    const pillEl = document.querySelector(".ace-text-event-pill--undo");
    if (pillEl) {
      pillEl.textContent = "";
      pillEl.classList.remove("ace-text-event-pill--undo");
    }
  }

  function _initUndoAffordance() {
    const sbEvent = document.querySelector(".ace-statusbar-event--undo");
    if (!sbEvent) return;

    // Always re-mirror — the pill is inside #text-panel and gets clobbered
    // by any primary swap that lands during the affordance window. Listener-
    // binding is gated separately, per-button.
    const pill = document.getElementById("ace-text-event-pill");
    if (pill && pill.innerHTML !== sbEvent.innerHTML) {
      pill.classList.add("ace-text-event-pill--undo");
      pill.innerHTML = sbEvent.innerHTML;
    }

    // Bind per-button so the freshly-mirrored pill button gets its handlers
    // even when the persistent statusbar button is already wired.
    _undoButtons().forEach(function (btn) {
      if (btn.dataset.aceUndoBound === "1") return;
      btn.dataset.aceUndoBound = "1";
      btn.addEventListener("mouseenter", _undoPause);
      btn.addEventListener("mouseleave", _undoResume);
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
    // mirrored pill button mid-countdown or while paused).
    if (_undoStartTime === null && _undoRemainingMs === 0) {
      _undoFrozenProgress = 1;
      _undoStart(UNDO_DURATION_MS);
    } else if (_undoStartTime !== null) {
      // Running — recompute current visual progress and restart the
      // transition so the new pill button picks up the animation.
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
   * Show an ephemeral or sticky message in the status bar event segment.
   *   kind="ok": text for ~2 s then fades (via empty-state CSS + timer clears text).
   *   kind="err": sticky until the next _setStatus() call.
   * Mirrors to the ARIA live region (assertive when kind="err").
   */
  function _setStatus(text, kind) {
    kind = kind || "ok";
    const sbEl = document.querySelector(".ace-statusbar-event");
    const pillEl = document.getElementById("ace-text-event-pill");
    if (!sbEl && !pillEl) return;

    if (_statusEventClearTimer) {
      clearTimeout(_statusEventClearTimer);
      _statusEventClearTimer = null;
    }

    if (sbEl) {
      sbEl.textContent = text || "";
      sbEl.classList.remove("ace-statusbar-event--ok", "ace-statusbar-event--ok-sticky", "ace-statusbar-event--err");
      if (text) sbEl.classList.add("ace-statusbar-event--" + kind);
    }
    if (pillEl) {
      pillEl.textContent = text || "";
      pillEl.classList.remove(
        "ace-text-event-pill--ok",
        "ace-text-event-pill--ok-sticky",
        "ace-text-event-pill--err",
      );
      if (text) pillEl.classList.add("ace-text-event-pill--" + kind);
    }

    if (text) _announce(text, kind === "err");

    if (kind === "ok" && text) {
      _statusEventClearTimer = setTimeout(function () {
        if (sbEl) {
          sbEl.textContent = "";
          sbEl.classList.remove("ace-statusbar-event--ok");
        }
        if (pillEl) {
          pillEl.textContent = "";
          pillEl.classList.remove("ace-text-event-pill--ok");
        }
      }, 2000);
    }
  }

  window._setStatus = _setStatus;
  window._setAmbient = _setAmbient;

  /**
   * Schedule the same 2 s fade for "ok" status content delivered by a
   * server OOB swap (e.g. /api/undo's "Nothing to undo"). Plain HTMX
   * swaps replace the pill element directly, bypassing _setStatus()'s
   * timer — without this helper, server-emitted "ok" pills sit forever
   * until the next user action. "err" / "ok-sticky" / "undo" variants
   * are intentionally sticky and skipped.
   */
  function _maybeFadeOkStatus() {
    const sb = document.querySelector(".ace-statusbar-event");
    const pill = document.getElementById("ace-text-event-pill");
    const sbOk = sb && sb.classList.contains("ace-statusbar-event--ok") && sb.textContent.trim();
    const pillOk = pill && pill.classList.contains("ace-text-event-pill--ok") && pill.textContent.trim();
    if (!sbOk && !pillOk) return;
    if (_statusEventClearTimer) clearTimeout(_statusEventClearTimer);
    _statusEventClearTimer = setTimeout(function () {
      if (sb && sb.classList.contains("ace-statusbar-event--ok")) {
        sb.textContent = "";
        sb.classList.remove("ace-statusbar-event--ok");
      }
      if (pill && pill.classList.contains("ace-text-event-pill--ok")) {
        pill.textContent = "";
        pill.classList.remove("ace-text-event-pill--ok");
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

  /** Determine which zone currently has focus: "text", "search", "tree", or null. */
  function _activeZone() {
    let el = document.activeElement;
    if (!el) return null;
    if (el.id === "text-panel" || el.closest("#text-panel")) return "text";
    if (el.id === "code-search-input") return "search";
    const tree = document.getElementById("code-tree");
    if (tree && tree.contains(el)) return "tree";
    const headlessTree = document.getElementById("ace-headless-tree-mount");
    if (headlessTree && headlessTree.contains(el)) return "tree";
    return null;
  }

  // Zone-level Tab cycling — captures Tab before browser default
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;

    let zone = _activeZone();
    if (!zone) return;

    if (!e.shiftKey) {
      if (zone === "text") { e.preventDefault(); _focusSearchBar(); return; }
      if (zone === "search") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "tree") { e.preventDefault(); _focusTextPanel(); return; }
    } else {
      if (zone === "text") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "search") { e.preventDefault(); _focusTextPanel(); return; }
      if (zone === "tree") { e.preventDefault(); _focusSearchBar(); return; }
    }
  }, true);  // capture phase to intercept before default Tab behaviour

  // --- Roving tabindex ---

  /** Return all visible treeitems (group headers + code rows) in DOM order. */
  function _getTreeItems() {
    const controller = _getSidebarTreeController();
    if (controller) return controller.getTreeItems();
    const tree = document.getElementById("code-tree");
    if (!tree) return [];
    const items = tree.querySelectorAll('[role="treeitem"]');
    const result = [];
    items.forEach(function (item) {
      // Skip items hidden by search filter
      if (item.style.display === "none") return;
      if (item.getAttribute("aria-hidden") === "true") return;
      if (_isHiddenByCollapsedAncestor(item)) return;
      result.push(item);
    });
    return result;
  }

  /** Move roving tabindex to the given treeitem. */
  function _focusTreeItem(item) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.focusTreeItem(item);
      return;
    }
    if (!item) return;
    const prev = _getActiveTreeItem();
    if (prev) prev.setAttribute("tabindex", "-1");
    item.setAttribute("tabindex", "0");
    item.focus();
  }

  /** Get the currently focused treeitem (tabindex="0"). */
  function _getActiveTreeItem() {
    const controller = _getSidebarTreeController();
    if (controller) return controller.getActiveTreeItem();
    const tree = document.getElementById("code-tree");
    return tree ? tree.querySelector('[role="treeitem"][tabindex="0"]') : null;
  }

  /** Check if a treeitem is a folder row. */
  function _isFolderRow(item) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.isFolderRow(item);
    return item && item.classList.contains("ace-code-folder-row");
  }

  function _containingGroupForItem(item) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.containingGroupForItem(item);
    if (!item) return null;
    if (item.parentElement && item.parentElement.getAttribute("role") === "group") {
      return item.parentElement;
    }
    const block = item.closest(".ace-folder-block");
    if (block && block.parentElement && block.parentElement.getAttribute("role") === "group") {
      return block.parentElement;
    }
    return null;
  }

  function _parentFolderRow(item) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.parentFolderRow(item);
    const group = _containingGroupForItem(item);
    const row = group ? group.previousElementSibling : null;
    return _isFolderRow(row) ? row : null;
  }

  function _isHiddenByCollapsedAncestor(item) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.isHiddenByCollapsedAncestor(item);
    let group = _containingGroupForItem(item);
    while (group) {
      const folderRow = group.previousElementSibling;
      if (folderRow && folderRow.getAttribute("aria-expanded") === "false") return true;
      const block = group.parentElement;
      group = block && block.parentElement && block.parentElement.getAttribute("role") === "group"
        ? block.parentElement
        : null;
    }
    return false;
  }

  function _itemIdFromTreeElement(el) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.itemIdFromTreeElement(el);
    if (!el || !el.getAttribute) return null;
    if (el.classList.contains("ace-folder-block")) return el.getAttribute("data-folder-id");
    return el.getAttribute("data-code-id") || el.getAttribute("data-folder-id");
  }

  function _directChildItemIds(container) {
    const controller = _getSidebarTreeController();
    if (controller) return controller.directChildItemIds(container);
    return Array.from(container.children)
      .map(function (el) { return _itemIdFromTreeElement(el); })
      .filter(Boolean);
  }

  /** Move a folder block (the wrapper carrying header + children group) up
   *  or down by one position relative to its sibling folder blocks. */
  function _moveFolderInDirection(folderRow, direction) {
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
    const codeId = _itemIdFromTreeElement(row);
    const parentId = _itemIdFromTreeElement(folderRow);
    if (!codeId || !parentId) return;
    if (_parentFolderRow(row) === folderRow) {
      _announce("Already in that folder.");
      return;
    }
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: { parent_id: parentId, current_index: window.__aceCurrentIndex || 0 },
    });
  }

  /** Move a codebook item out one level, or to root if it is already one level deep. */
  function _doMoveOutOfFolder(row) {
    const codeId = _itemIdFromTreeElement(row);
    if (!codeId) return;
    const parentRow = _parentFolderRow(row);
    const grandparentRow = parentRow ? _parentFolderRow(parentRow) : null;
    const newParentId = grandparentRow ? _itemIdFromTreeElement(grandparentRow) : "";
    htmx.ajax("PUT", `/api/codes/${codeId}/parent`, {
      target: "#text-panel",
      swap: "outerHTML",
      values: { parent_id: newParentId || "", current_index: window.__aceCurrentIndex || 0 },
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
      : document.getElementById("code-tree");
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
        target: "#text-panel",
        swap: "outerHTML",
        values: {
          above_code_id: aboveCodeId,
          folder_name: "New folder",
          current_index: window.__aceCurrentIndex || 0,
        },
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
          _applyCode(codeId3);
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
      const itemId = _itemIdFromTreeElement(active);
      if (itemId) _executeDelete(itemId);
      return;
    }

    const items = _getTreeItems();
    const idx = items.indexOf(active);

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
      const active = document.activeElement;
      treeItem = active && active.closest
        ? active.closest("#code-tree [role='treeitem'][data-code-id]")
        : null;
      if (!treeItem) {
        treeItem = document.querySelector("#code-tree [role='treeitem'][data-code-id]");
      }
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
  // data-folder-id="\u2026">. CSS rotates the chevron and hides the sibling
  // [role="group"] children container based on aria-expanded, so JS only
  // needs to flip the attribute. _collapsedFolders mirrors the state in
  // memory so it survives sidebar OOB swaps within a session.

  function _expandFolder(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.expandFolder(folderRow);
      return;
    }
    folderRow.setAttribute("aria-expanded", "true");
    const id = folderRow.getAttribute("data-folder-id");
    if (id) _collapsedFolders[id] = false;
  }

  function _collapseFolder(folderRow) {
    const controller = _getSidebarTreeController();
    if (controller) {
      controller.collapseFolder(folderRow);
      return;
    }
    folderRow.setAttribute("aria-expanded", "false");
    const id = folderRow.getAttribute("data-folder-id");
    if (id) _collapsedFolders[id] = true;
  }

  /* ================================================================
   * 17b. Coding text size
   * ================================================================ */

  const CODING_TEXT_SIZE_KEY = "ace-coding-text-size";
  const CODING_TEXT_DEFAULT_SIZE = 17;
  const CODING_TEXT_FALLBACK_SIZES = [15, 17, 19, 20, 21, 24];
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
    const sizes = _codingTextSizes();
    const index = _codingTextIndex(size);
    document.documentElement.style.setProperty("--ace-coding-text-size", size + "px");
    document.querySelectorAll(".ace-coding-text-option").forEach(function (btn) {
      const active = _normaliseCodingTextSize(btn.dataset.codingTextSize) === size;
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
        const codebookDropdown = document.getElementById("codebook-dropdown");
        if (codebookDropdown) codebookDropdown.style.display = "none";
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

  // Codebook menu: toggle, import, export, shortcuts
  document.addEventListener("click", function (e) {
    const dropdown = document.getElementById("codebook-dropdown");

    // Keyboard shortcuts (absorbed from the old `?` button)
    if (e.target.closest("#codebook-menu-shortcuts-btn")) {
      if (dropdown) dropdown.style.display = "none";
      _toggleCheatSheet();
      return;
    }

    if (e.target.closest("#create-first-code-btn")) {
      if (dropdown) dropdown.style.display = "none";
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
      if (dropdown) dropdown.style.display = "none";
      fetch("/api/native/pick-file", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "accept=.csv"
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.path) return;
          htmx.ajax("POST", "/api/codes/import/preview-path", {
            values: { path: data.path, current_index: window.__aceCurrentIndex },
            target: "#modal-container",
            swap: "innerHTML",
          });
        });
      return;
    }

    // Export codebook button
    if (e.target.closest("#codebook-export-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/codes/export";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export all annotations button
    if (e.target.closest("#export-annotations-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/export/annotations";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export source notes button
    if (e.target.closest("#export-notes-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/export/notes";
      window._setStatus("Exported", "ok");
      return;
    }

    // Fullscreen toggle button
    if (e.target.closest("#fullscreen-btn")) {
      if (dropdown) dropdown.style.display = "none";
      _toggleFullscreen();
      return;
    }

    // Toggle button
    if (e.target.closest("#codebook-menu-btn")) {
      _setCodingTextMenuOpen(false);
      if (dropdown) dropdown.style.display = dropdown.style.display === "none" ? "" : "none";
      e.stopPropagation();
      return;
    }

    // Click outside — close if open
    if (dropdown && dropdown.style.display !== "none") {
      dropdown.style.display = "none";
    }
  });

  // Codebook menu: Escape closes dropdown
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      const dropdown = document.getElementById("codebook-dropdown");
      if (dropdown && dropdown.style.display !== "none") {
        dropdown.style.display = "none";
        e.stopPropagation();
      }
    }
  });

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
  window.aceImportFromPreview = function (btn) {
    const codesJson = btn.getAttribute("data-codes");
    const currentIndex = btn.getAttribute("data-current-index") || window.__aceCurrentIndex;
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
      values: { codes_json: codesJson, current_index: currentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
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
   * 19b. Long-name hover peek — side popover for truncated code /
   *      folder names in the codebook sidebar. Portal-style: the peek
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
    if (document.querySelector("#code-tree [contenteditable=\"true\"], #ace-headless-tree-mount .ace-ht-rename")) return true;
    return false;
  }

  function _peekContent(row) {
    const isFolder = _isFolderRow(row);
    const labelEl = row.querySelector(".ace-folder-label, .ace-code-name, .ace-ht-label");
    if (!labelEl) return null;
    if (labelEl.scrollWidth <= labelEl.clientWidth) return null;

    const fullName = labelEl.textContent;
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
    return { fullName, stripe, metaHtml: parts.join("") };
  }

  function _peekShow(row) {
    if (_peekSuppressed()) return;
    const content = _peekContent(row);
    if (!content) return;

    const el = _peekEl();
    el.style.setProperty("--ace-code-peek-stripe", content.stripe || "var(--ace-border)");
    el.innerHTML =
      `<p class="ace-code-peek-name">${_escapeHtml(content.fullName)}</p>` +
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
    const ROW_SEL = "#code-tree .ace-code-row, #code-tree .ace-code-folder-row, #ace-headless-tree-mount .ace-ht-row";

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
      if (!e.target.closest("#code-tree, #ace-headless-tree-mount")) return;
      const to = e.relatedTarget;
      if (!to || !to.closest || !to.closest("#code-tree, #ace-headless-tree-mount")) _peekHide();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") _peekHide();
    }, true);

    document.addEventListener("contextmenu", _peekHide);
    document.addEventListener("ace-navigate", _peekHide);
    window.addEventListener("resize", _peekHide);

    document.addEventListener("scroll", function (e) {
      if (e.target && (e.target.id === "code-tree" || e.target.id === "ace-headless-tree-mount")) _peekHide();
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
   * 21. Source note drawer (READ / EDIT / closed)
   * ================================================================ */

  // Three implicit states derived from the DOM:
  //   closed — drawer hidden
  //   READ   — drawer open, textarea unfocused, shortcuts live
  //   EDIT   — drawer open, textarea focused, _isTyping() suppresses shortcuts
  //
  // html[data-ace-note-open="1"] — drawer open (persisted to localStorage so
  //   an inline <head> script can restore it before CSS loads — no flash)
  // html[data-ace-has-note="1"]  — rail dot amber (current source has a note)
  //
  // The EDIT mode visuals (amber ring, dimmed text) come from CSS
  // `:has(#note-textarea:focus)` — no JS mode flag. Focus IS the state.

  let _noteSaveTimer = null;
  let _noteInFlight = null;
  let _noteStatusClearTimer = null;
  let _previouslyFocused = null;

  function _noteEls() {
    return {
      drawer: document.getElementById("note-drawer"),
      textarea: document.getElementById("note-textarea"),
      status: document.getElementById("note-status"),
      pill: document.getElementById("note-pill"),
      appliedPanel: document.getElementById("ace-applied-codes-panel"),
    };
  }

  function _isDrawerOpen() {
    return document.documentElement.dataset.aceNoteOpen === "1";
  }

  function _isEditing() {
    return document.activeElement?.id === "note-textarea";
  }

  function _setNoteStatus(text, sticky) {
    const { status } = _noteEls();
    if (!status) return;
    status.textContent = text;
    if (_noteStatusClearTimer) {
      clearTimeout(_noteStatusClearTimer);
      _noteStatusClearTimer = null;
    }
    if (!sticky && text) {
      _noteStatusClearTimer = setTimeout(function () {
        status.textContent = "";
      }, 1500);
    }
  }

  function _syncHasNoteAttribute() {
    const { pill } = _noteEls();
    if (pill && pill.classList.contains("ace-note-pill--has-note")) {
      document.documentElement.dataset.aceHasNote = "1";
    } else {
      delete document.documentElement.dataset.aceHasNote;
    }
  }

  function _syncAppliedPanelForNoteState() {
    const { appliedPanel } = _noteEls();
    if (!appliedPanel) return;
    if (_isDrawerOpen()) {
      appliedPanel.setAttribute("aria-hidden", "true");
      appliedPanel.setAttribute("inert", "");
    } else {
      appliedPanel.removeAttribute("aria-hidden");
      appliedPanel.removeAttribute("inert");
    }
  }

  function _flushAndBlurTextarea() {
    if (_noteSaveTimer) {
      clearTimeout(_noteSaveTimer);
      _noteSaveTimer = null;
      _doSaveNote();
    }
    const { textarea } = _noteEls();
    if (!textarea) return;
    if (document.activeElement === textarea) textarea.blur();
    textarea.setAttribute("tabindex", "-1");
  }

  function _restoreDrawerFocus() {
    if (_previouslyFocused && document.contains(_previouslyFocused) &&
        typeof _previouslyFocused.focus === "function") {
      _previouslyFocused.focus();
    } else {
      _focusTextPanel();
    }
  }

  function aceOpenNoteRead() {
    const { drawer, pill } = _noteEls();
    if (!drawer) return;
    if (!_previouslyFocused) _previouslyFocused = document.activeElement;
    document.documentElement.dataset.aceNoteOpen = "1";
    drawer.setAttribute("aria-hidden", "false");
    if (pill) pill.setAttribute("aria-expanded", "true");
    _syncAppliedPanelForNoteState();
    try { localStorage.setItem("ace-note-open", "1"); } catch (_) {}
    // No focus change — READ mode leaves focus where it was so shortcuts stay live.
  }

  function aceEnterEditMode() {
    const { drawer, textarea } = _noteEls();
    if (!drawer || !textarea) return;
    if (!_isDrawerOpen()) aceOpenNoteRead();
    textarea.setAttribute("tabindex", "0");
    // Deferred so competing afterSettle/navigation handlers don't steal focus back.
    setTimeout(function () {
      textarea.focus();
      const n = textarea.value.length;
      textarea.setSelectionRange(n, n);
    }, 0);
  }

  function aceExitEditMode() {
    _flushAndBlurTextarea();
    _restoreDrawerFocus();
  }
  window.aceExitEditMode = aceExitEditMode;

  function aceCloseNote() {
    const { drawer, pill } = _noteEls();
    if (!drawer) return;
    _flushAndBlurTextarea();
    delete document.documentElement.dataset.aceNoteOpen;
    drawer.setAttribute("aria-hidden", "true");
    if (pill) pill.setAttribute("aria-expanded", "false");
    _syncAppliedPanelForNoteState();
    try { localStorage.removeItem("ace-note-open"); } catch (_) {}
    _restoreDrawerFocus();
    _previouslyFocused = null;
  }
  window.aceCloseNote = aceCloseNote;

  function _scheduleNoteSave() {
    if (_noteSaveTimer) clearTimeout(_noteSaveTimer);
    _noteSaveTimer = setTimeout(_doSaveNote, 500);
  }

  function _doSaveNote() {
    _noteSaveTimer = null;
    const { textarea } = _noteEls();
    if (!textarea) return Promise.resolve();
    const sourceId = textarea.getAttribute("data-source-id");
    if (!sourceId) return Promise.resolve();
    const text = textarea.value;
    // Returns the same OOB payload as flag_route — pill, grid strip, and
    // status badge all refresh together.
    const promise = fetch("/api/source-note/" + encodeURIComponent(sourceId), {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "note_text=" + encodeURIComponent(text),
    }).then(function (resp) {
      if (!resp.ok) throw new Error(resp.status);
      var ct = resp.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) return resp.json();
      return { has_note: !!text.trim() };
    }).then(function (data) {
      var pill = document.getElementById("note-pill");
      if (pill) {
        if (data.has_note) {
          pill.classList.add("ace-note-pill--has-note");
        } else {
          pill.classList.remove("ace-note-pill--has-note");
        }
      }
    }).catch(function (err) {
      if (err.name === "AbortError") return;
    });
    _noteInFlight = promise;
    return promise;
  }

  // Resolves once any pending or in-flight save is finished. Awaited by
  // aceNavigate so a full-page reload can't cancel a debounced save.
  function aceFlushNoteIfDirty() {
    if (_noteSaveTimer) {
      clearTimeout(_noteSaveTimer);
      _noteSaveTimer = null;
      return _doSaveNote();
    }
    if (_noteInFlight) return _noteInFlight;
    return Promise.resolve();
  }
  window.aceFlushNoteIfDirty = aceFlushNoteIfDirty;

  document.addEventListener("click", function (e) {
    if (e.target.closest("#note-pill")) {
      e.preventDefault();
      if (!_isDrawerOpen()) {
        aceOpenNoteRead();
      } else if (!_isEditing()) {
        aceEnterEditMode();
      }
      return;
    }
  });

  document.addEventListener("input", function (e) {
    if (e.target.id === "note-textarea") {
      _scheduleNoteSave();
      if (e.target.value.length > 5000) {
        _setNoteStatus("Long note (over 5,000 characters)", true);
      }
    }
  });

  // Double-Esc pattern: first Esc exits EDIT back to READ, second closes
  // the drawer. Separate listener so it runs even when the textarea has
  // focus (the main keydown handler returns early via _isTyping()).
  // Defers to higher-priority Escape targets (cheat sheet, open dialog,
  // source grid overlay) so closing those doesn't also close the drawer.
  document.addEventListener("mousedown", function (e) {
    if (!_isDrawerOpen()) return;
    if (e.target.closest("#note-drawer") || e.target.closest("#note-pill")) return;
    aceCloseNote();
  });

  document.addEventListener("keydown", function (e) {
    if (_chordMode === "awaiting") return;
    if (e.key !== "Escape") return;
    if (!_isDrawerOpen()) return;
    if (document.getElementById("ace-cheat-sheet")) return;
    if (document.querySelector("dialog[open]")) return;
    e.preventDefault();
    if (_isEditing()) {
      aceExitEditMode();
    } else {
      aceCloseNote();
    }
  });

  document.body.addEventListener("htmx:afterSettle", function (evt) {
    const target = evt.detail && evt.detail.target;
    if (!target) return;
    if (target.id === "text-panel" || target.id === "coding-workspace") {
      if (_noteSaveTimer) { clearTimeout(_noteSaveTimer); _noteSaveTimer = null; }
      _noteInFlight = null;
      _syncHasNoteAttribute();
      _syncAppliedPanelForNoteState();
    }
  });

  // When the server OOB-swaps a fresh sources payload, re-render the
  // sparkline + tiles from the new data.
  document.body.addEventListener("htmx:oobAfterSwap", function (evt) {
    if (!evt.detail || !evt.detail.target) return;
    if (evt.detail.target.id === "ace-sources-data") {
      if (typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }
    }
    if (evt.detail.target.id === "ace-applied-codes-panel") {
      _syncAppliedPanelForNoteState();
    }
    if (evt.detail.target.id === "ace-right-inspector") {
      const { drawer, pill } = _noteEls();
      const open = _isDrawerOpen();
      if (drawer) drawer.setAttribute("aria-hidden", open ? "false" : "true");
      if (pill) pill.setAttribute("aria-expanded", open ? "true" : "false");
      _syncAppliedPanelForNoteState();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    _syncHasNoteAttribute();
    if (_isDrawerOpen()) {
      const { drawer, pill } = _noteEls();
      if (drawer) drawer.setAttribute("aria-hidden", "false");
      if (pill) pill.setAttribute("aria-expanded", "true");
    }
    _syncAppliedPanelForNoteState();
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
