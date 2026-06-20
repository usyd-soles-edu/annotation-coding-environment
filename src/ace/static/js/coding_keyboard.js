/**
 * Coding keyboard workflow controller.
 *
 * Owns cross-zone navigation for the coding page:
 *   Codebook <- Source sentence -> Applied codes
 *
 * Component-private editing keys stay in bridge.js / local widgets.
 */
(function () {
  "use strict";

  let sourceAnchorIndex = -1;
  let appliedFocusIndex = 0;
  let deletePickMode = false;
  let deleteCandidateIds = new Set();
  let appliedFocusToken = 0;

  function codingPage() {
    return !!document.getElementById("text-panel");
  }

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  function localWidgetOwnsFocus() {
    const el = document.activeElement;
    if (!el || !el.closest) return false;
    return !!el.closest(
      "dialog, [role='menu'], .ace-context-menu, .ace-colour-popover, " +
      "#note-drawer, .ace-ht-rename, [contenteditable='true']"
    );
  }

  function activeZone() {
    const el = document.activeElement;
    if (el && el.closest) {
      if (el.closest(".ace-applied-codes-panel")) return "applied";
      if (el.closest("#code-sidebar")) return "codebook";
      if (el.closest("#text-panel, #text-scroll, #content-scroll")) return "source";
    }
    return document.body.dataset.activeZone || "source";
  }

  function setZone(zone) {
    document.body.dataset.activeZone = zone;
  }

  function rememberSourceAnchor() {
    const idx = Number(window.__aceFocusIndex);
    if (Number.isFinite(idx) && idx >= 0) sourceAnchorIndex = idx;
    else if (sourceAnchorIndex < 0) sourceAnchorIndex = 0;
  }

  function getSentences() {
    if (typeof window.aceGetSentences === "function") {
      return Array.from(window.aceGetSentences());
    }
    return Array.from(document.querySelectorAll(".ace-sentence"));
  }

  function focusSentence(idx) {
    const sentences = getSentences();
    if (!sentences.length) return;
    const clamped = Math.max(0, Math.min(idx, sentences.length - 1));
    sourceAnchorIndex = clamped;
    if (typeof window.aceFocusSentence === "function") {
      window.aceFocusSentence(clamped);
    }
    const textPanel = document.getElementById("text-panel");
    if (textPanel) {
      if (!textPanel.hasAttribute("tabindex")) textPanel.setAttribute("tabindex", "-1");
      textPanel.focus({ preventScroll: true });
    }
    setZone("source");
  }

  function returnToSource() {
    const idx = sourceAnchorIndex >= 0 ? sourceAnchorIndex : Number(window.__aceFocusIndex || 0);
    appliedFocusToken += 1;
    clearDeletePickMode();
    focusSentence(idx);
    syncAppliedFocusables();
  }

  function moveSentence(delta) {
    const sentences = getSentences();
    if (!sentences.length) return;
    let idx = Number(window.__aceFocusIndex);
    if (!Number.isFinite(idx) || idx < 0) idx = delta > 0 ? -1 : sentences.length;
    focusSentence(idx + delta);
  }

  function firstCodebookItem() {
    return document.querySelector(
      "#ace-headless-tree-mount .ace-ht-row--code[role='treeitem'], " +
      "#ace-headless-tree-mount [role='treeitem'], " +
      "#code-sidebar [role='treeitem']"
    );
  }

  function focusCodebook() {
    rememberSourceAnchor();
    const item = firstCodebookItem();
    if (!item) {
      if (typeof window._setStatus === "function") window._setStatus("No codebook item to focus", "err");
      return;
    }
    item.setAttribute("tabindex", "0");
    item.focus({ preventScroll: true });
    setZone("codebook");
  }

  function annotationData() {
    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return [];
    try {
      return JSON.parse(dataEl.dataset.annotations || "[]");
    } catch (_) {
      return [];
    }
  }

  function currentSentenceRange() {
    const sentences = getSentences();
    const idx = Number(window.__aceFocusIndex);
    const sentence = Number.isFinite(idx) && idx >= 0 ? sentences[idx] : null;
    if (!sentence) return null;
    const start = Number(sentence.dataset.start);
    const end = Number(sentence.dataset.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
    return { start, end };
  }

  function annotationsForCurrentSentence() {
    const range = currentSentenceRange();
    if (!range) return [];
    return annotationData().filter(function (ann) {
      return Number(ann.start) < range.end && Number(ann.end) > range.start;
    });
  }

  function rowAnnotationId(row, annotations) {
    if (!row) return "";
    if (row.dataset.annotationId) return row.dataset.annotationId;
    const codeId = row.dataset.codeId;
    if (!codeId) return "";
    const source = annotations || annotationData();
    const matches = source.filter(function (ann) {
      return String(ann.code_id) === String(codeId);
    });
    return matches.length === 1 ? String(matches[0].id) : "";
  }

  function appliedRows() {
    return Array.from(document.querySelectorAll(
      ".ace-applied-code-row, " +
      ".ace-applied-annotation-list:not([hidden]) .ace-applied-annotation-row"
    ));
  }

  function syncAppliedFocusables() {
    const rows = appliedRows();
    const appliedActive = document.body.dataset.activeZone === "applied";
    rows.forEach(function (row, idx) {
      row.tabIndex = idx === appliedFocusIndex ? 0 : -1;
      row.classList.toggle("ace-applied-row--keyboard", idx === appliedFocusIndex && appliedActive);
    });
  }

  function expandGroupForRow(row) {
    const group = row && row.closest(".ace-applied-code-group");
    if (!group) return null;
    const toggle = group.querySelector(".ace-applied-code-toggle");
    const list = group.querySelector(".ace-applied-annotation-list");
    if (toggle && list) {
      toggle.setAttribute("aria-expanded", "true");
      list.hidden = false;
    }
    return group;
  }

  function focusAppliedRow(row) {
    if (!row) return false;
    expandGroupForRow(row);
    const rows = appliedRows();
    appliedFocusIndex = Math.max(0, rows.indexOf(row));
    setZone("applied");
    syncAppliedFocusables();
    const token = ++appliedFocusToken;
    row.focus({ preventScroll: true });
    requestAnimationFrame(function () {
      if (token === appliedFocusToken && row.isConnected) setZone("applied");
      if (token === appliedFocusToken && document.activeElement !== row && row.isConnected) {
        row.focus({ preventScroll: true });
      }
    });
    setTimeout(function () {
      if (token === appliedFocusToken && row.isConnected && document.activeElement === row) {
        setZone("applied");
      }
    }, 0);
    row.scrollIntoView({ block: "nearest" });
    if (row.classList.contains("ace-applied-annotation-row")) {
      window.aceSetAppliedAnnotationPreview?.(row.dataset.annotationId);
    } else {
      window.aceSetAppliedCodePreview?.(row.dataset.codeId);
    }
    return true;
  }

  function focusAppliedAt(index) {
    const rows = appliedRows();
    if (!rows.length) {
      if (typeof window._setStatus === "function") window._setStatus("No applied codes in this source", "ok");
      return false;
    }
    const clamped = Math.max(0, Math.min(index, rows.length - 1));
    return focusAppliedRow(rows[clamped]);
  }

  function focusAppliedPanel() {
    rememberSourceAnchor();
    clearDeletePickMode();
    return focusAppliedAt(0);
  }

  function focusFirstOccurrence(groupRow) {
    const group = expandGroupForRow(groupRow);
    const first = group ? group.querySelector(".ace-applied-annotation-row") : null;
    return first ? focusAppliedRow(first) : false;
  }

  function parentGroupRow(annotationRow) {
    const group = annotationRow && annotationRow.closest(".ace-applied-code-group");
    return group ? group.querySelector(".ace-applied-code-row") : null;
  }

  function clearDeletePickMode() {
    deletePickMode = false;
    deleteCandidateIds = new Set();
    document.querySelectorAll(".ace-applied-delete-candidate").forEach(function (row) {
      row.classList.remove("ace-applied-delete-candidate");
    });
  }

  function markDeleteCandidates(annotations) {
    clearDeletePickMode();
    deletePickMode = true;
    deleteCandidateIds = new Set(annotations.map(function (ann) { return String(ann.id); }));
    const allAnnotations = annotationData();
    document.querySelectorAll(".ace-applied-code-row, .ace-applied-annotation-row").forEach(function (row) {
      const id = rowAnnotationId(row, allAnnotations);
      if (id && deleteCandidateIds.has(String(id))) {
        row.classList.add("ace-applied-delete-candidate");
      }
    });
  }

  function enterDeletePickMode(annotations) {
    rememberSourceAnchor();
    markDeleteCandidates(annotations);
    const first = document.querySelector(".ace-applied-delete-candidate");
    if (first) focusAppliedRow(first);
    if (typeof window._setStatus === "function") window._setStatus("Choose a code to delete", "ok-sticky");
  }

  function deleteAnnotation(annotationId) {
    if (!annotationId) return false;
    clearDeletePickMode();
    window.aceDeleteAppliedAnnotation?.(annotationId);
    return true;
  }

  function handleSourceDelete() {
    const annotations = annotationsForCurrentSentence();
    if (!annotations.length) {
      if (typeof window._setStatus === "function") window._setStatus("No applied codes in this sentence", "ok");
      return;
    }
    if (annotations.length === 1) {
      deleteAnnotation(annotations[0].id);
      return;
    }
    enterDeletePickMode(annotations);
  }

  function handleAppliedDelete(row) {
    if (!row) return;
    if (row.classList.contains("ace-applied-code-row")) {
      const id = rowAnnotationId(row);
      if (id) {
        deleteAnnotation(id);
        return;
      }
      focusFirstOccurrence(row);
      return;
    }
    const id = row.dataset.annotationId;
    if (deletePickMode && !deleteCandidateIds.has(String(id))) return;
    deleteAnnotation(id);
  }

  function nextDeleteCandidate(delta) {
    const candidates = Array.from(document.querySelectorAll(".ace-applied-delete-candidate"));
    if (!candidates.length) return false;
    const current = document.activeElement;
    let idx = candidates.indexOf(current);
    if (idx < 0) idx = delta > 0 ? -1 : 0;
    const next = candidates[Math.max(0, Math.min(idx + delta, candidates.length - 1))];
    return focusAppliedRow(next);
  }

  function handleSourceKey(event) {
    const key = event.key;
    if (event.metaKey || event.ctrlKey || event.altKey) return false;
    if (event.shiftKey) return false;
    if (key === "ArrowDown") {
      event.preventDefault();
      event.stopImmediatePropagation();
      moveSentence(1);
      return true;
    }
    if (key === "ArrowUp") {
      event.preventDefault();
      event.stopImmediatePropagation();
      moveSentence(-1);
      return true;
    }
    if (key === "ArrowLeft") {
      event.preventDefault();
      event.stopImmediatePropagation();
      focusCodebook();
      return true;
    }
    if (key === "ArrowRight") {
      event.preventDefault();
      event.stopImmediatePropagation();
      focusAppliedPanel();
      return true;
    }
    if (key === "Delete" || key === "Backspace") {
      event.preventDefault();
      event.stopImmediatePropagation();
      handleSourceDelete();
      return true;
    }
    return false;
  }

  function handleAppliedKey(event) {
    const key = event.key;
    if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return false;
    const row = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest(".ace-applied-code-row, .ace-applied-annotation-row")
      : null;
    if (!row) return false;

    if (key === "ArrowDown" || key === "ArrowUp") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (deletePickMode) nextDeleteCandidate(key === "ArrowDown" ? 1 : -1);
      else focusAppliedAt(appliedRows().indexOf(row) + (key === "ArrowDown" ? 1 : -1));
      return true;
    }
    if (key === "ArrowRight" || key === "Enter") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (row.classList.contains("ace-applied-code-row")) focusFirstOccurrence(row);
      return true;
    }
    if (key === "ArrowLeft") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!deletePickMode && row.classList.contains("ace-applied-annotation-row")) {
        const parent = parentGroupRow(row);
        if (parent) {
          focusAppliedRow(parent);
          return true;
        }
      }
      returnToSource();
      return true;
    }
    if (key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      returnToSource();
      return true;
    }
    if (key === "Delete" || key === "Backspace") {
      event.preventDefault();
      event.stopImmediatePropagation();
      handleAppliedDelete(row);
      return true;
    }
    return false;
  }

  document.addEventListener("keydown", function (event) {
    if (!codingPage()) return;
    if (document.body.dataset.chordMode) return;
    if (isTypingTarget(event.target) || localWidgetOwnsFocus()) return;
    const zone = activeZone();
    if (zone === "applied") {
      handleAppliedKey(event);
      return;
    }
    if (zone === "source") {
      handleSourceKey(event);
    }
  }, true);

  document.addEventListener("focusin", function (event) {
    const target = event.target;
    if (!codingPage()) return;
    if (!target || !target.closest) return;
    if (target.closest(".ace-applied-codes-panel")) {
      const row = target.closest(".ace-applied-code-row, .ace-applied-annotation-row");
      if (row) {
        const rows = appliedRows();
        const idx = rows.indexOf(row);
        if (idx >= 0) appliedFocusIndex = idx;
      }
      setZone("applied");
    } else if (target.closest("#code-sidebar")) {
      setZone("codebook");
    } else if (target.closest("#text-panel, #text-scroll, #content-scroll")) {
      setZone("source");
    }
    syncAppliedFocusables();
  });

  document.addEventListener("htmx:afterSettle", function () {
    syncAppliedFocusables();
    if (deletePickMode) {
      const matches = annotationData().filter(function (ann) {
        return deleteCandidateIds.has(String(ann.id));
      });
      if (matches.length) markDeleteCandidates(matches);
      else clearDeletePickMode();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    syncAppliedFocusables();
  });

  window.aceCodingKeyboard = {
    returnToSource: returnToSource,
    refreshAppliedFocusables: syncAppliedFocusables,
  };
})();
