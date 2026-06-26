(function () {
  "use strict";

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
// #13: a dirty note edit captured before an inspector OOB swap so it can be
// restored after — see the beforeSwap/afterSettle pair below.
let _pendingNoteRestore = null;
const LONG_NOTE_WARNING = "Long note (over 5,000 characters)";

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
window.aceIsNoteDrawerOpen = _isDrawerOpen;

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

function _syncNoteDrawerA11y() {
  const { drawer, textarea } = _noteEls();
  const open = _isDrawerOpen();
  if (drawer) drawer.setAttribute("aria-hidden", open ? "false" : "true");
  if (!textarea) return;
  textarea.disabled = !open;
  if (!open) {
    textarea.setAttribute("tabindex", "-1");
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

function _focusTextPanel() {
    const tp = document.getElementById("text-panel");
    if (tp) tp.focus();
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
  _syncNoteDrawerA11y();
  _syncAppliedPanelForNoteState();
  try { localStorage.setItem("ace-note-open", "1"); } catch (_) {}
  // No focus change — READ mode leaves focus where it was so shortcuts stay live.
}

window.aceOpenNoteRead = aceOpenNoteRead;

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

window.aceEnterEditMode = aceEnterEditMode;

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
  _syncNoteDrawerA11y();
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
    if (document.getElementById("note-status")?.textContent !== LONG_NOTE_WARNING) {
      _setNoteStatus("Saved", false);
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
      _setNoteStatus(LONG_NOTE_WARNING, true);
    } else if (document.getElementById("note-status")?.textContent === LONG_NOTE_WARNING) {
      _setNoteStatus("", false);
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
  if (typeof window.aceIsChordAwaiting === "function" && window.aceIsChordAwaiting()) return;
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

// #13: the inspector (which contains the note textarea) is OOB-swapped on
// mutations like flag/apply. If a debounced note save is still pending when
// that swap fires, the textarea is torn down mid-edit — the visible text
// reverts to the stored value and the next keystroke would overwrite the
// in-flight save. Capture the dirty edit before the swap and restore it
// after settle. Gated on the pending-save timer (which aceNavigate has
// already flushed), so a genuine source change is never clobbered.
document.addEventListener("htmx:beforeSwap", function (e) {
  const target = e.detail && e.detail.target;
  if (!target) return;
  if (target.id !== "text-panel" && target.id !== "coding-workspace") return;
  // A cancelled swap (e.g. the 4xx handler sets shouldSwap=false) won't reach
  // afterSettle, so don't capture — the textarea is untouched and the normal
  // debounce still saves it.
  if (e.detail.shouldSwap === false) return;
  if (!_noteSaveTimer) return;
  const ta = document.getElementById("note-textarea");
  if (!ta) return;
  _pendingNoteRestore = {
    value: ta.value,
    selStart: ta.selectionStart,
    selEnd: ta.selectionEnd,
    focused: _isEditing(),
  };
  // Stop the debounce here so it can't fire after the swap (saving the
  // reverted server value) and race the restore-save in afterSettle.
  clearTimeout(_noteSaveTimer);
  _noteSaveTimer = null;
});

document.body.addEventListener("htmx:afterSettle", function (evt) {
  const target = evt.detail && evt.detail.target;
  if (!target) return;
  if (target.id === "text-panel" || target.id === "coding-workspace") {
    if (_noteSaveTimer) { clearTimeout(_noteSaveTimer); _noteSaveTimer = null; }
    _noteInFlight = null;
    _syncHasNoteAttribute();
    _syncAppliedPanelForNoteState();
    // Restore a dirty edit captured before this swap, then persist it
    // straight away (not debounced — there's no typing stream to coalesce
    // here, and a timer would race the next swap).
    if (_pendingNoteRestore) {
      const ta = document.getElementById("note-textarea");
      if (ta) {
        ta.value = _pendingNoteRestore.value;
        try { ta.setSelectionRange(_pendingNoteRestore.selStart, _pendingNoteRestore.selEnd); } catch (_) {}
        if (_pendingNoteRestore.focused) ta.focus();
      }
      _pendingNoteRestore = null;
      _doSaveNote();
    }
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
    _syncNoteDrawerA11y();
    _syncAppliedPanelForNoteState();
  }
});

function aceInitNotes(root) {
  void root;
  _syncHasNoteAttribute();
  if (_isDrawerOpen()) {
    const { drawer, pill } = _noteEls();
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    if (pill) pill.setAttribute("aria-expanded", "true");
  }
  _syncNoteDrawerA11y();
  _syncAppliedPanelForNoteState();
}
window.aceInitNotes = aceInitNotes;

document.addEventListener("DOMContentLoaded", function () {
  aceInitNotes(document);
});

document.addEventListener("htmx:load", function (evt) {
  aceInitNotes(evt.detail && evt.detail.elt ? evt.detail.elt : document);
});

})();
