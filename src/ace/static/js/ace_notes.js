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

let _noteStatusClearTimer = null;
let _previouslyFocused = null;
// #13: a dirty note edit captured before an inspector OOB swap so it can be
// restored after — see the beforeSwap/afterSettle pair below. Keyed by the
// source it was captured from so a cross-source swap can't transplant it.
let _pendingNoteRestore = null;
const LONG_NOTE_WARNING = "Long note (over 5,000 characters). Shorter notes are easier to scan.";
const NOTE_RETRY_HINT = "Note not saved — kept as draft; edit or navigate to retry";
// Global statusbar errors owned by the note autosave (this module's message
// plus bridge.js's navigation-gate variants). Only these exact texts — and
// only for the source they were set on — are cleared when a save recovers;
// an unrelated global error is never touched.
const NOTE_STATUSBAR_ERRORS = [
  "Note autosave failed — draft kept; edit or navigate to retry",
  "Note save failed — draft kept; edit or navigate again to retry",
  "Note save failed — draft kept; press V again to retry",
];
let _noteGlobalErrSource = null;

// Per-source draft state (issue #126), independent of the DOM: a delayed or
// in-flight save always uses the text captured for its own source id, never
// whatever source happens to be rendered. `dirty` stays true until a
// successful PUT acknowledges that exact text. `authored` marks text the
// user actually typed here. After an acknowledgement it only overrides
// responses from requests that began before that acknowledgement; newer
// server renders may contain another tab's changes.
const _noteDrafts = new Map();  // sourceId -> { text, dirty, authored, ackVersion }
const _notePumps = new Map();   // sourceId -> promise of the running save chain
const _noteTimers = new Map();  // sourceId -> debounce timer id
let _noteSaveVersion = 0;
const _noteRequestVersions = new WeakMap();
let _noteActiveSwapVersion;

document.addEventListener("htmx:beforeRequest", function (event) {
  const xhr = event.detail && event.detail.xhr;
  if (xhr) _noteRequestVersions.set(xhr, _noteSaveVersion);
});

function _noteResponsePredatesAck(event, draft) {
  const xhr = event && event.detail && event.detail.xhr;
  // htmx:oobAfterSwap omits xhr. Its enclosing beforeSwap runs first, so
  // carry that response's version through the synchronous OOB swap.
  const startedAt = xhr ? _noteRequestVersions.get(xhr)
    : event && event.type === "htmx:oobAfterSwap" ? _noteActiveSwapVersion
    : undefined;
  return startedAt !== undefined && startedAt < draft.ackVersion;
}

// Departure lock (issue #126): held only across the final note drain →
// history POST → unload during navigation. While held the textarea is
// readonly so no new edit can appear after the last flush.
let _noteEditLocked = false;
function _applyNoteLock(ta) { if (ta) ta.readOnly = _noteEditLocked; }
function aceLockNoteEditing() { _noteEditLocked = true; _applyNoteLock(_noteEls().textarea); }
function aceUnlockNoteEditing() { _noteEditLocked = false; _applyNoteLock(_noteEls().textarea); }
window.aceLockNoteEditing = aceLockNoteEditing;
window.aceUnlockNoteEditing = aceUnlockNoteEditing;

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
  const sourceId = _noteCurrentSourceId();
  if (sourceId) {
    _noteCancelTimer(sourceId);
    // Fire-and-drain (the pump never rejects). A failure surfaces via the
    // sticky status hint and is retried on the next edit or navigation.
    void _pumpNoteSource(sourceId);
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
  window.ACE_PREFS.set("ace-note-open", "1");
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
  window.ACE_PREFS.remove("ace-note-open");
  _restoreDrawerFocus();
  _previouslyFocused = null;
}
window.aceCloseNote = aceCloseNote;

function _noteCurrentSourceId() {
  const { textarea } = _noteEls();
  if (!textarea) return null;
  return textarea.getAttribute("data-source-id") || null;
}

function _noteSetDraft(sourceId, text) {
  if (!sourceId) return;
  const previous = _noteDrafts.get(sourceId);
  _noteDrafts.set(sourceId, {
    text: text, dirty: true, authored: true,
    ackVersion: previous ? previous.ackVersion : 0,
  });
}

function _noteInitDraft(sourceId, text) {
  if (!sourceId) return;
  if (!_noteDrafts.has(sourceId)) {
    _noteDrafts.set(sourceId, { text: text, dirty: false, authored: false, ackVersion: 0 });
  }
}

// Synchronous restore for a freshly swapped-in note textarea — the ONE
// shared hook body for every lifecycle that can deliver one
// (htmx:oobAfterSwap on the inspector, htmx:afterSwap / htmx:afterSettle
// on the primary swap targets, aceInitNotes). htmx restores focus during
// the swap itself, ~20 ms before afterSettle, so keystrokes can land on
// stale server HTML first (#126). Restore dirty drafts and clean drafts
// whose response predates their save before the browser can accept input;
// accept fresh server text so other tabs' edits remain visible. Apply the
// departure lock before the replacement field becomes editable.
let _noteLastTextarea = null;  // identity baseline: did this swap deliver a new field?
function _noteSyncReplacementTextarea(ta, restore, event) {
  if (!ta) return;
  _applyNoteLock(ta);
  const replaced = ta !== _noteLastTextarea;
  _noteLastTextarea = ta;
  const sourceId = ta.getAttribute("data-source-id");
  if (!sourceId) return;
  _noteInitDraft(sourceId, ta.value);
  const d = _noteDrafts.get(sourceId);
  const stale = d && (_noteResponsePredatesAck(event, d) ||
    (restore && restore.sourceId === sourceId && restore.stale));
  if (d && (d.dirty || (replaced && d.authored && stale)) && ta.value !== d.text) {
    ta.value = d.text;
  } else if (d && replaced && !d.dirty && !stale) {
    // A request made after our last save can carry a newer note from another
    // tab. Adopt it instead of retaining a clean local draft indefinitely.
    d.text = ta.value;
    d.authored = false;
  }
  // #126 caret: writing the authored text back resets the caret, so
  // restore focus/selection here — synchronously with the swap, before a
  // caret-only move in the settle gap can be rewound at afterSettle — and
  // only onto a genuinely replaced field, never a live one. Consumed once;
  // the snapshot's sourceId is still needed by the afterSettle pump below.
  if (replaced && restore && !restore.caretDone && restore.sourceId === sourceId &&
      restore.value === ta.value) {
    restore.caretDone = true;
    try { ta.setSelectionRange(restore.selStart, restore.selEnd); } catch (_) {}
    if (restore.focused) ta.focus();
  }
}

function _noteCancelTimer(sourceId) {
  const t = _noteTimers.get(sourceId);
  if (t) {
    clearTimeout(t);
    _noteTimers.delete(sourceId);
  }
}

function _scheduleNoteSave(sourceId) {
  _noteCancelTimer(sourceId);
  _noteTimers.set(sourceId, setTimeout(function () {
    _noteTimers.delete(sourceId);
    _pumpNoteSource(sourceId);
  }, 500));
}

// A completed save may refresh the pill/status — but only for the source it
// belongs to, and only once the newest draft for that source is clean.
function _noteApplyAck(sourceId, data) {
  const d = _noteDrafts.get(sourceId);
  if (!d || d.dirty) return;
  // Clear this module's OWNED global error even when the save belonged to
  // a source we've already left — a background retry that recovers must
  // not leave a stale failure on the statusbar with everything saved
  // (#126). Unrelated texts and other sources' errors stay put (the
  // ownership check inside handles that).
  _noteClearStatusbarErrorIfOwned(sourceId);
  if (typeof window._aceSetSourceNote === "function") {
    window._aceSetSourceNote(sourceId, data.has_note);
  }
  if (_noteCurrentSourceId() !== sourceId) return;
  const { pill } = _noteEls();
  // HTMX can replace the text panel (and pill) before its OOB inspector
  // textarea. In that gap, the textarea still names the old source.
  if (!pill || pill.getAttribute("data-source-id") !== sourceId) return;
  if (data.has_note) {
    pill.classList.add("ace-note-pill--has-note");
  } else {
    pill.classList.remove("ace-note-pill--has-note");
  }
  _syncHasNoteAttribute();
  if (data.deleted) {
    _setNoteStatus("", false);
    if (typeof window._setStatus === "function") window._setStatus("Note deleted", "ok");
  } else if (document.getElementById("note-status")?.textContent !== LONG_NOTE_WARNING) {
    _setNoteStatus("Saved", false);
  }
}

function _noteClearStatusbarErrorIfOwned(sourceId) {
  if (_noteGlobalErrSource !== null && _noteGlobalErrSource !== sourceId) return;
  const sb = document.querySelector(".ace-statusbar-event");
  if (!sb || NOTE_STATUSBAR_ERRORS.indexOf(sb.textContent) === -1) return;
  _noteGlobalErrSource = null;
  if (typeof window._setStatus === "function") window._setStatus("", "ok");
}

function _noteShowSaveError(sourceId) {
  // A failure for a source that is no longer rendered stays silent here; the
  // sticky hint reappears when that source is revisited (afterSettle below).
  if (_noteCurrentSourceId() !== sourceId) return;
  _setNoteStatus(NOTE_RETRY_HINT, true);
  _noteGlobalErrSource = sourceId;
  if (typeof window._setStatus === "function") {
    window._setStatus("Note autosave failed — draft kept; edit or navigate to retry", "err");
  }
}

// Send one PUT. Never throws; resolves true once the server acknowledged.
async function _notePut(sourceId, text) {
  try {
    const resp = await fetch("/api/source-note/" + encodeURIComponent(sourceId), {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "note_text=" + encodeURIComponent(text),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    var ct = resp.headers.get("content-type") || "";
    const data = ct.indexOf("application/json") !== -1
      ? await resp.json()
      : { has_note: !!text.trim() };
    const d = _noteDrafts.get(sourceId);
    if (d && d.text === text) {
      d.dirty = false;  // clean only on ack of the latest text
      d.ackVersion = ++_noteSaveVersion;
    }
    _noteApplyAck(sourceId, data);
    return true;
  } catch (err) {
    if (err && err.name === "AbortError") return false;
    _noteShowSaveError(sourceId);
    return false;
  }
}

// Serial save chain per source: at most one PUT in flight, newer edits
// coalesced into the next round-trip (newest text is always sent last). The
// returned promise never rejects — background debounces must not create
// unhandled rejections. Resolves true once the source is clean, false if the
// last attempt failed (draft stays dirty for retry).
function _pumpNoteSource(sourceId) {
  const running = _notePumps.get(sourceId);
  if (running) return running;
  const p = (async function () {
    for (;;) {
      const d = _noteDrafts.get(sourceId);
      if (!d || !d.dirty) return true;
      const ok = await _notePut(sourceId, d.text);
      if (!ok) return false;
    }
  })().catch(function () {
    return false;  // belt-and-braces: the pump contract is "never rejects"
  }).finally(function () {
    _notePumps.delete(sourceId);
  });
  _notePumps.set(sourceId, p);
  return p;
}

// Drains every dirty draft — including edits that arrive while we await —
// so a full-page navigation can't strand an old-source draft. Rejects if any
// draft could not be saved (each distinct text is attempted once per flush).
async function aceFlushNoteIfDirty() {
  const attempted = new Map();
  let lastErr = null;
  for (;;) {
    for (const id of Array.from(_noteTimers.keys())) _noteCancelTimer(id);
    const todo = [];
    for (const entry of Array.from(_noteDrafts)) {
      const id = entry[0];
      const d = entry[1];
      if (_notePumps.has(id) || (d.dirty && attempted.get(id) !== d.text)) {
        todo.push(id);
        attempted.set(id, d.text);
      }
    }
    if (!todo.length) break;
    const results = await Promise.all(todo.map(function (id) {
      return _pumpNoteSource(id);
    }));
    for (let i = 0; i < results.length; i++) {
      if (!results[i]) lastErr = new Error("note save failed for source " + todo[i]);
    }
  }
  for (const entry of Array.from(_noteDrafts)) {
    if (entry[1].dirty) throw lastErr || new Error("note save failed");
  }
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
    // Browsers can't fire input on a readonly field; this also stops any
    // synthetic/programmatic edit from stranding during a departure.
    if (_noteEditLocked) return;
    const sourceId = e.target.getAttribute("data-source-id");
    if (sourceId) {
      _noteSetDraft(sourceId, e.target.value);
      _scheduleNoteSave(sourceId);
    }
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
  if (e.target.closest("#note-drawer, #note-pill, #ace-narrow-pan")) return;
  // A source switch rebinds the open drawer to the destination source.
  if (e.target.closest("#btn-prev, #btn-next, #ace-grid-tiles, #ace-grid-spark")) return;
  aceCloseNote();
});

document.addEventListener("keydown", function (e) {
  if (typeof window.aceIsChordAwaiting === "function" && window.aceIsChordAwaiting()) return;
  if (e.key !== "Escape") return;
  if (!_isDrawerOpen()) return;
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
// after settle. Captured whenever the source has authored text (dirty or
// not); never for a source the user hasn't edited, so a genuine fresh
// server render is left alone.
document.addEventListener("htmx:beforeSwap", function (e) {
  const xhr = e.detail && e.detail.xhr;
  _noteActiveSwapVersion = xhr ? _noteRequestVersions.get(xhr) : undefined;
  const target = e.detail && e.detail.target;
  if (!target) return;
  if (target.id !== "text-panel" && target.id !== "coding-workspace") return;
  // A cancelled swap (e.g. the 4xx handler sets shouldSwap=false) won't reach
  // afterSettle, so don't capture — the textarea is untouched and the normal
  // debounce still saves it.
  if (e.detail.shouldSwap === false) return;
  const ta = document.getElementById("note-textarea");
  if (!ta) return;
  const sourceId = ta.getAttribute("data-source-id");
  const d = sourceId && _noteDrafts.get(sourceId);
  if (!d || !(d.dirty || d.authored)) return;
  _pendingNoteRestore = {
    sourceId: sourceId,
    value: ta.value,
    selStart: ta.selectionStart,
    selEnd: ta.selectionEnd,
    focused: _isEditing(),
    stale: _noteResponsePredatesAck(e, d),
  };
  // Stop the debounce here so it can't fire after the swap (saving the
  // reverted server value) and race the restore-save in afterSettle.
  _noteCancelTimer(sourceId);
});

// A full-workspace replacement delivers the textarea with the PRIMARY
// swap: htmx has already restored focus onto the new field by the time
// afterSwap fires, and input can follow in the 20 ms settle gap (#126).
document.body.addEventListener("htmx:afterSwap", function (evt) {
  const target = evt.detail && evt.detail.target;
  if (!target) return;
  if (target.id !== "text-panel" && target.id !== "coding-workspace") return;
  _noteSyncReplacementTextarea(document.getElementById("note-textarea"), _pendingNoteRestore, evt);
});

document.body.addEventListener("htmx:afterSettle", function (evt) {
  const target = evt.detail && evt.detail.target;
  if (!target) return;
  if (target.id === "text-panel" || target.id === "coding-workspace") {
    // Drafts and in-flight saves survive swaps — never reset them here.
    _syncHasNoteAttribute();
    _syncAppliedPanelForNoteState();
    const ta = document.getElementById("note-textarea");
    if (!ta) return;
    const sourceId = ta.getAttribute("data-source-id");
    if (!sourceId) return;
    _noteSyncReplacementTextarea(ta, null, evt);
    const restore = _pendingNoteRestore;
    _pendingNoteRestore = null;
    if (restore && restore.sourceId !== sourceId) {
      // Cross-source swap (e.g. undo/redo crossing sources): the captured
      // edit belongs to the old source. Drain it under its own key in the
      // background — never transplant it into the new textarea.
      void _pumpNoteSource(restore.sourceId);
    }
    const d = _noteDrafts.get(sourceId);
    if (d && (d.dirty || d.authored)) {
      // The newest authored text for THIS source is authoritative,
      // snapshot or not — _noteSyncReplacementTextarea already wrote it
      // and the caret/focus back synchronously at the swap-phase hook;
      // restoring selection here would rewind a caret-only move made in
      // the settle gap.
      if (d.dirty) {
        // Still unsaved: persist straight away (not debounced — there's no
        // typing stream to coalesce and a timer would race the next swap).
        // With no save running, the previous attempt failed — say so.
        _noteCancelTimer(sourceId);
        if (!_notePumps.has(sourceId)) _setNoteStatus(NOTE_RETRY_HINT, true);
        void _pumpNoteSource(sourceId);
      }
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
    // Earliest hook where a replacement note textarea exists: lock it and
    // restore the authored text — and the snapshot's caret/focus —
    // synchronously (#126), well before settle.
    _noteSyncReplacementTextarea(document.getElementById("note-textarea"), _pendingNoteRestore, evt);
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
  const ta = document.getElementById("note-textarea");
  if (ta) _noteSyncReplacementTextarea(ta);
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

// Last-resort guard for exits the flush gates can't cover (reload, tab
// close, untracked links): any dirty draft means unsaved work on the page.
window.addEventListener("beforeunload", function (e) {
  for (const d of _noteDrafts.values()) {
    if (d.dirty) {
      e.preventDefault();
      e.returnValue = "";
      return;
    }
  }
});

document.addEventListener("DOMContentLoaded", function () {
  aceInitNotes(document);
});

document.addEventListener("htmx:load", function (evt) {
  aceInitNotes(evt.detail && evt.detail.elt ? evt.detail.elt : document);
});

})();
