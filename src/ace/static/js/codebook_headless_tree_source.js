import {
  createOnDropHandler,
  createTree,
  dragAndDropFeature,
  hotkeysCoreFeature,
  keyboardDragAndDropFeature,
  renamingFeature,
  syncDataLoaderFeature,
} from "@headless-tree/core";

(function () {
  "use strict";

  const ROOT_ID = "root";
  let tree = null;
  let items = {};
  let renderQueued = false;
  let dragRenderQueued = false;
  let dropLog = [];
  let mountedElement = null;
  let changedDropScopes = null;
  let dragImageElement = null;
  let lastAssistiveDragName = "";
  let suppressNextRefocus = false;
  let searchRaw = "";
  let searchText = "";
  let chordFilterActive = false;
  const TRANSPARENT_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
  const RESERVED_SINGLE_KEYS = new Set(["q", "x", "z", "n", "v"]);

  function clearCodebookActiveState() {
    const active = document.activeElement;
    if (active?.closest?.("#ace-headless-tree-mount .ace-ht-row")) active.blur();
    if (document.body?.dataset?.activeZone === "codebook") {
      document.body.dataset.activeZone = "source";
    }
  }

  function clearCodebookActiveStateAfterFrame() {
    clearCodebookActiveState();
    requestAnimationFrame(function () {
      clearCodebookActiveState();
      requestAnimationFrame(clearCodebookActiveState);
    });
    setTimeout(clearCodebookActiveState, 0);
    setTimeout(clearCodebookActiveState, 50);
  }

  function itemData(id) {
    return items[id];
  }

  function childrenOf(id) {
    return itemData(id)?.children ?? [];
  }

  function snapshotChildrenByParent() {
    const snapshot = {};
    Object.entries(items).forEach(function ([id, item]) {
      if (Array.isArray(item.children)) snapshot[id] = [...item.children];
    });
    return snapshot;
  }

  function restoreChildrenByParent(snapshot) {
    if (!snapshot) return;
    Object.entries(snapshot).forEach(function ([id, children]) {
      if (items[id]) items[id].children = [...children];
    });
    tree?.rebuildTree?.();
    scheduleRender();
  }

  function findParentId(itemId) {
    for (const [id, item] of Object.entries(items)) {
      if ((item.children || []).includes(itemId)) return id;
    }
    return null;
  }

  function folderIds() {
    return Object.values(items)
      .filter((item) => item.kind === "folder" && item.id !== ROOT_ID)
      .map((item) => item.id);
  }

  function keyLabel(index) {
    const labels = [];
    for (let n = 1; n <= 9; n += 1) labels.push(String(n));
    labels.push("0");
    for (let code = 97; code <= 121; code += 1) {
      const letter = String.fromCharCode(code);
      if (!RESERVED_SINGLE_KEYS.has(letter)) labels.push(letter);
    }
    return labels[index] || "";
  }

  function codeRank(itemId) {
    const codeIds = visibleCodeItems().map((item) => item.getId());
    return codeIds.indexOf(itemId);
  }

  function itemMatchesSearch(id) {
    if (!searchText) return true;
    const item = itemData(id);
    if (!item) return false;
    if ((item.name || "").toLowerCase().includes(searchText)) return true;
    return childrenOf(id).some(itemMatchesSearch);
  }

  function itemMatchesChordFilter(id) {
    if (!chordFilterActive) return true;
    const item = itemData(id);
    if (!item) return false;
    if (item.kind === "code") return !!item.chord;
    return childrenOf(id).some(itemMatchesChordFilter);
  }

  function visibleTreeItems() {
    const current = tree.getItems();
    if (!searchText && !chordFilterActive) return current;
    return current.filter(function (item) {
      const id = item.getId();
      if (chordFilterActive) return itemMatchesChordFilter(id);
      return itemMatchesSearch(id);
    });
  }

  function visibleCodeItems() {
    return visibleTreeItems().filter(function (item) {
      return item.getItemData().kind === "code";
    });
  }

  function firstVisibleCodeItem() {
    return visibleCodeItems()[0] || null;
  }

  function normalisedName(name) {
    return (name || "").trim().toLowerCase();
  }

  function findDuplicateName(kind, name) {
    const target = normalisedName(name);
    if (!target) return null;
    return Object.values(items).find(function (item) {
      return item.kind === kind && normalisedName(item.name) === target;
    }) || null;
  }

  function pathNamesFor(id) {
    const names = [];
    let current = id;
    const seen = new Set();
    while (current && current !== ROOT_ID && !seen.has(current)) {
      seen.add(current);
      const item = itemData(current);
      if (!item) break;
      names.push(item.name || "");
      current = findParentId(current);
    }
    return names.reverse().filter(Boolean);
  }

  function ancestorIdsFor(id) {
    const ancestors = [];
    let current = findParentId(id);
    const seen = new Set();
    while (current && current !== ROOT_ID && !seen.has(current)) {
      seen.add(current);
      ancestors.push(current);
      current = findParentId(current);
    }
    return new Set(ancestors);
  }

  function activeDragTarget() {
    return tree?.getDragTarget?.() || null;
  }

  function dropReceiverFolderId() {
    const target = activeDragTarget();
    const targetId = target?.item?.getId?.();
    if (!targetId || targetId === ROOT_ID) return "";
    return target.item.getItemData?.()?.kind === "folder" ? targetId : "";
  }

  function tinyDragImage() {
    if (!dragImageElement) {
      dragImageElement = document.createElement("img");
      dragImageElement.className = "ace-ht-drag-image";
      dragImageElement.alt = "";
      dragImageElement.src = TRANSPARENT_GIF;
      dragImageElement.width = 1;
      dragImageElement.height = 1;
      dragImageElement.draggable = false;
    }
    if (!dragImageElement.isConnected) document.body.append(dragImageElement);
    return { imgElement: dragImageElement, xOffset: 0, yOffset: 0 };
  }

  function nativeDragPayload(draggedItems) {
    return {
      format: "text/plain",
      data: draggedItems.map(function (item) {
        return item.getItemName?.() || "";
      }).filter(Boolean).join("\n"),
      dropEffect: "move",
      effectAllowed: "move",
    };
  }

  function dragTargetText(target) {
    if (!target) return "Choose a destination.";
    const targetName = target.item.getId() === ROOT_ID
      ? "the top level"
      : target.item.getItemName();
    if (!("insertionIndex" in target)) return `inside ${targetName}`;
    return `at position ${target.insertionIndex + 1} in ${targetName}`;
  }

  function updateDndAnnouncement() {
    const announcer = document.getElementById("ace-ht-dnd-announcer");
    if (!announcer || !tree) return;

    const state = tree.getState?.() || {};
    const assistiveState = state.assistiveDndState || 0;
    const dragged = state.dnd?.draggedItems?.[0] || null;
    if (dragged) lastAssistiveDragName = dragged.getItemName?.() || "item";
    const name = lastAssistiveDragName || "item";

    if (assistiveState === 1) {
      announcer.textContent = `Moving ${name}. Use arrow keys to choose a position, Enter to move, Escape to cancel.`;
    } else if (assistiveState === 2) {
      announcer.textContent = `Moving ${name} ${dragTargetText(activeDragTarget())}. Enter to move, Escape to cancel.`;
    } else if (assistiveState === 3) {
      announcer.textContent = `Moved ${name}.`;
    } else if (assistiveState === 4) {
      announcer.textContent = "Move cancelled.";
    } else {
      announcer.textContent = "";
    }
  }

  async function persistDrop(id, previousParent, nextParent, order, restoreSnapshot) {
    if (denyCodebookEditing()) {
      restoreChildrenByParent(restoreSnapshot);
      return;
    }
    setStatus("Saving");
    try {
      if (previousParent === nextParent) {
        await htmxSwap("POST", "/api/codes/reorder-in-scope", {
          code_ids: JSON.stringify(order),
          parent_id: formParentId(nextParent),
          current_index: currentIndex(),
        });
      } else {
        await htmxSwap("PUT", `/api/codes/${id}/parent`, {
          parent_id: formParentId(nextParent),
          target_order_ids: JSON.stringify(order),
          current_index: currentIndex(),
        });
      }
      setStatus("");
    } catch (error) {
      setStatus("Move failed");
      restoreChildrenByParent(restoreSnapshot);
      window.__aceHeadlessTreePreviewError = String(error && error.message || error);
      throw error;
    }
  }

  function scheduleRender() {
    if (renderQueued) return;
    renderQueued = true;
    queueMicrotask(function () {
      renderQueued = false;
      renderTree();
    });
  }

  function setStatus(text) {
    const el = document.querySelector("[data-headless-tree-status]");
    if (el) el.textContent = text;
  }

  function currentIndex() {
    return window.__aceCurrentIndex || 0;
  }

  function codebookEditingDisabled() {
    return document.querySelector("#ace-headless-tree-mount[data-codebook-readonly='1']") !== null;
  }

  function codeApplicationDisabled() {
    return !!document.getElementById("code-view") || !document.getElementById("text-panel");
  }

  function denyCodebookEditing() {
    if (!codebookEditingDisabled()) return false;
    setStatus("Back to source to edit the codebook");
    return true;
  }

  function formParentId(parentId) {
    return parentId && parentId !== ROOT_ID ? parentId : "";
  }

  async function htmxSwap(method, url, values) {
    if (!window.htmx || typeof window.htmx.ajax !== "function") {
      throw new Error("HTMX is unavailable");
    }
    return window.htmx.ajax(method, url, {
      target: document.getElementById("text-panel") ? "#text-panel" : "#code-sidebar",
      swap: document.getElementById("text-panel") ? "outerHTML" : "none",
      values,
    });
  }

  async function htmxSidebarSwap(method, url, values) {
    if (!window.htmx || typeof window.htmx.ajax !== "function") {
      throw new Error("HTMX is unavailable");
    }
    return window.htmx.ajax(method, url, {
      target: "#code-sidebar",
      swap: "outerHTML",
      values,
    });
  }

  function applyProps(element, props) {
    Object.entries(props).forEach(function ([key, value]) {
      if (value === undefined || value === null) return;
      if (key === "ref") {
        value(element);
        return;
      }
      if (key === "style" && typeof value === "object") {
        Object.assign(element.style, value);
        return;
      }
      if (key === "tabIndex") {
        element.tabIndex = value;
        return;
      }
      if (key === "draggable") {
        element.draggable = Boolean(value);
        return;
      }
      if (key === "value") {
        element.value = value;
        return;
      }
      if (key.startsWith("on") && typeof value === "function") {
        const raw = key.slice(2).toLowerCase();
        const eventName = raw === "change" ? "input" : raw;
        element.addEventListener(eventName, value);
        return;
      }
      if (key === "aria-selected") return;
      element.setAttribute(key, String(value));
    });
  }

  function updateChildren(item, newChildren) {
    const id = item.getId();
    if (!items[id]) return;
    items[id].children = [...newChildren];
    if (changedDropScopes) changedDropScopes.set(id, [...newChildren]);
  }

  const applyLibraryDrop = createOnDropHandler(updateChildren);

  async function handleDrop(draggedItems, target) {
    if (draggedItems.length !== 1) return;
    const item = draggedItems[0];
    const id = item.getId();
    const restoreSnapshot = snapshotChildrenByParent();
    const previousParent = findParentId(id) || ROOT_ID;
    changedDropScopes = new Map();
    let changedScopes;
    try {
      await applyLibraryDrop(draggedItems, target);
      changedScopes = changedDropScopes;
    } finally {
      changedDropScopes = null;
    }
    const nextParent = findParentId(id) || ROOT_ID;
    const order = changedScopes?.get(nextParent) || [...childrenOf(nextParent)];
    dropLog.push({
      id,
      from: previousParent,
      to: nextParent,
      order,
    });
    tree.rebuildTree();
    scheduleRender();

    await persistDrop(id, previousParent, nextParent, order, restoreSnapshot);
  }

  function canDrop(draggedItems, target) {
    if (draggedItems.length !== 1) return false;
    if (!target || !target.item) return false;
    const dragged = draggedItems[0];
    const targetId = target.item.getId();
    const targetData = target.item.getItemData?.() || {};
    if (dragged.getId() === ROOT_ID) return false;
    if (dragged.getId() === targetId) return false;
    if (target.item.isDescendentOf(dragged.getId())) return false;
    if (targetId === ROOT_ID) return true;
    if (!("insertionIndex" in target)) {
      return targetData.kind === "folder";
    }
    return targetData.kind === "folder";
  }

  function applyCode(item) {
    const data = item.getItemData();
    if (data.kind !== "code") return;
    if (codeApplicationDisabled()) {
      document.dispatchEvent(new CustomEvent("ace:view-code", {
        detail: {
          codeId: item.getId(),
          codeName: data.name || "",
        },
      }));
      return;
    }
    document.dispatchEvent(new CustomEvent("ace:apply-code", {
      detail: {
        codeId: item.getId(),
        codeName: data.name || "",
      },
    }));
  }

  function persistRename(item, name) {
    const next = name.trim();
    if (!next || next === item.getItemData().name) return;
    document.dispatchEvent(new CustomEvent("ace:rename-codebook-item", {
      detail: {
        itemId: item.getId(),
        name: next,
      },
    }));
  }

  function deleteItem(item) {
    if (item.getId() === ROOT_ID) return;
    document.dispatchEvent(new CustomEvent("ace:delete-codebook-item", {
      detail: { itemId: item.getId() },
    }));
  }

  function clearSearchInput() {
    const input = document.getElementById("code-search-input");
    searchRaw = "";
    searchText = "";
    if (input) input.value = "";
    scheduleRender();
  }

  function focusItemById(id) {
    if (!id || !tree) return;
    const item = tree.getItemInstance(id);
    if (!item) return;
    item.setFocused();
    scheduleRender();
  }

  function rowByItemId(id) {
    if (!mountedElement || !id) return null;
    return mountedElement.querySelector(`.ace-ht-row[data-item-id="${id}"]`);
  }

  function itemIdFromElement(element) {
    return element?.getAttribute?.("data-item-id") || null;
  }

  function createCode(name) {
    if (denyCodebookEditing()) return;
    const next = name.trim();
    if (!next) return;
    const duplicate = findDuplicateName("code", next);
    if (duplicate) {
      clearSearchInput();
      focusItemById(duplicate.id);
      setStatus("Already exists");
      return;
    }
    clearSearchInput();
    setStatus("Creating");
    htmxSidebarSwap("POST", "/api/codes", {
      name: next,
      current_index: currentIndex(),
    }).then(function () {
      setStatus("");
    }).catch(function (error) {
      setStatus("Create failed");
      window.__aceHeadlessTreePreviewError = String(error && error.message || error);
    });
  }

  function createFolder(name) {
    if (denyCodebookEditing()) return;
    const next = name.trim();
    if (!next) return;
    const duplicate = findDuplicateName("folder", next);
    if (duplicate) {
      clearSearchInput();
      focusItemById(duplicate.id);
      setStatus("Already exists");
      return;
    }
    clearSearchInput();
    setStatus("Creating");
    htmxSwap("POST", "/api/codes/folder", {
      name: next,
      current_index: currentIndex(),
    }).then(function () {
      setStatus("");
    }).catch(function (error) {
      setStatus("Create failed");
      window.__aceHeadlessTreePreviewError = String(error && error.message || error);
    });
  }

  function commitSlashCommand(value) {
    const parts = value.trim().match(/^\/(\S+)\s+(.+)$/);
    if (!parts) return false;
    const command = parts[1].toLowerCase();
    const name = parts[2].trim();
    if (!name) return false;
    if ("code".startsWith(command)) {
      createCode(name);
      return true;
    }
    if ("folder".startsWith(command)) {
      createFolder(name);
      return true;
    }
    setStatus("Unknown command");
    return true;
  }

  function createSearchRow() {
    const name = searchRaw.trim();
    if (chordFilterActive) return null;
    if (!name || name.startsWith("/") || firstVisibleCodeItem()) return null;
    const row = document.createElement("div");
    row.className = "ace-ht-create-row";
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    row.setAttribute("aria-label", `Create code ${name}`);

    const plus = document.createElement("span");
    plus.className = "ace-ht-create-plus";
    plus.textContent = "+";
    row.append(plus);

    const label = document.createElement("span");
    label.className = "ace-ht-create-label";
    label.textContent = `Create code '${name}'`;
    row.append(label);

    const hint = document.createElement("span");
    hint.className = "ace-ht-create-hint";
    hint.textContent = "Enter";
    row.append(hint);

    function commit(event) {
      event.preventDefault();
      event.stopPropagation();
      createCode(name);
    }
    row.addEventListener("click", commit);
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter") commit(event);
    });
    return row;
  }

  function rowForItem(item) {
    const data = item.getItemData();
    const row = document.createElement("div");
    const focusedId = tree.getFocusedItem?.()?.getId?.() || "";
    const focusedAncestors = focusedId ? ancestorIdsFor(focusedId) : new Set();
    const dropReceiverId = dropReceiverFolderId();
    const itemProps = { ...item.getProps() };
    const defaultKeyDown = itemProps.onKeyDown;
    const defaultClick = itemProps.onClick;
    let renamePointerQueued = false;
    function queueRenamingFromPointer(event) {
      if (denyCodebookEditing()) return true;
      if (event.target?.closest?.(".ace-ht-toggle, .ace-ht-chip, input, textarea, button, a")) return false;
      event.preventDefault();
      event.stopPropagation();
      if (renamePointerQueued) return true;
      renamePointerQueued = true;
      setTimeout(function () {
        item.setFocused();
        item.startRenaming?.();
        scheduleRender();
      }, 0);
      return true;
    }
    itemProps.onKeyDown = function (event) {
      if (event.key === "Enter" && data.kind === "code") {
        event.preventDefault();
        event.stopPropagation();
        applyCode(item);
        return;
      }
      if ((event.key === "Delete" || event.key === "Backspace") && item.getId() !== ROOT_ID) {
        event.preventDefault();
        event.stopPropagation();
        if (denyCodebookEditing()) return;
        deleteItem(item);
        return;
      }
      if (typeof defaultKeyDown === "function") defaultKeyDown(event);
    };
    itemProps.onClick = function (event) {
      if (event.target?.closest?.(".ace-ht-rename, input, textarea")) {
        event.stopPropagation();
        return;
      }
      if (event.detail >= 2 && queueRenamingFromPointer(event)) return;
      if (data.kind === "folder" && !event.target?.closest?.(".ace-ht-toggle")) {
        event.preventDefault();
        event.stopPropagation();
        item.setFocused();
        return;
      }
      if (typeof defaultClick === "function") defaultClick(event);
    };
    applyProps(row, itemProps);
    row.addEventListener("dblclick", function (event) {
      queueRenamingFromPointer(event);
    });
    row.classList.add("ace-ht-row");
    row.classList.add(data.kind === "folder" ? "ace-ht-row--folder" : "ace-ht-row--code");
    if (focusedAncestors.has(item.getId())) row.classList.add("ace-ht-row--path-parent");
    if (dropReceiverId === item.getId()) row.classList.add("ace-ht-row--drop-receiver");
    row.dataset.itemId = item.getId();
    row.dataset.kind = data.kind;
    if (data.kind === "folder") row.dataset.folderId = item.getId();
    if (data.kind === "code") row.dataset.codeId = item.getId();
    if (data.chord) row.dataset.chord = data.chord;
    const level = item.getItemMeta().level + 1;
    const path = pathNamesFor(item.getId());
    row.dataset.level = String(level);
    row.dataset.path = path.join(" / ");
    row.title = path.length > 1
      ? `${data.kind === "folder" ? "Folder" : "Code"} path: ${path.join(" / ")}`
      : `${data.kind === "folder" ? "Folder" : "Code"} level ${level}`;
    row.style.setProperty("--ht-indent", `${Math.max(0, level - 1) * 14}px`);
    if (data.colour) row.style.setProperty("--row-colour", data.colour);
    if (item.isDragTargetAbove?.()) row.dataset.dropTarget = "above";
    if (item.isDragTargetBelow?.()) row.dataset.dropTarget = "below";
    if (item.isUnorderedDragTarget?.()) row.dataset.dropTarget = "inside";

    const toggle = document.createElement("span");
    toggle.className = "ace-ht-toggle";
    toggle.setAttribute("aria-hidden", "true");
    toggle.textContent = item.isFolder() ? (item.isExpanded() ? "v" : ">") : "";
    if (item.isFolder()) {
      toggle.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        item.setFocused();
        if (item.isExpanded()) item.collapse();
        else item.expand();
        scheduleRender();
      });
    }
    row.append(toggle);

    if (item.isRenaming?.()) {
      const input = document.createElement("input");
      input.className = "ace-ht-rename";
      input.setAttribute("aria-label", `Rename ${data.name}`);
      input.dataset.itemId = item.getId();
      const renameProps = { ...item.getRenameInputProps() };
      delete renameProps.onKeyDown;
      delete renameProps.onBlur;
      applyProps(input, renameProps);
      let renameCommitted = false;
      let pointerAwayArmed = false;
      function removePointerAwayListener() {
        if (!pointerAwayArmed) return;
        pointerAwayArmed = false;
        document.removeEventListener("pointerdown", onRenamePointerAway, true);
      }
      function commitRename() {
        if (renameCommitted) return;
        renameCommitted = true;
        removePointerAwayListener();
        persistRename(item, input.value);
        tree.completeRenaming();
      }
      function commitRenameAway(focusTarget) {
        if (renameCommitted) return;
        renameCommitted = true;
        removePointerAwayListener();
        persistRename(item, input.value);
        tree.completeRenaming();
        suppressNextRefocus = true;
        clearCodebookActiveStateAfterFrame();
        queueMicrotask(function () {
          if (
            focusTarget &&
            typeof focusTarget.focus === "function" &&
            focusTarget.isConnected
          ) {
            focusTarget.focus({ preventScroll: true });
          }
        });
      }
      function cancelRename(focusTarget, allowSameRowFocus) {
        if (renameCommitted) return;
        renameCommitted = true;
        removePointerAwayListener();
        const rowElement = item.getElement?.();
        tree.abortRenaming();
        if (!allowSameRowFocus) {
          suppressNextRefocus = true;
          clearCodebookActiveStateAfterFrame();
        }
        queueMicrotask(function () {
          const targetIsSameRow = focusTarget && rowElement?.contains?.(focusTarget);
          if (
            focusTarget &&
            (!targetIsSameRow || allowSameRowFocus)
          ) {
            if (typeof focusTarget.focus === "function" && focusTarget.isConnected) {
              focusTarget.focus({ preventScroll: true });
              return;
            }
          }
          const active = document.activeElement;
          if (active?.closest?.("#ace-headless-tree-mount .ace-ht-row")) active.blur();
        });
      }
      function renameChanged() {
        const next = input.value.trim();
        return !!next && next !== item.getItemData().name;
      }
      function onRenamePointerAway(event) {
        if (row.contains(event.target)) return;
        if (renameChanged()) {
          commitRenameAway(event.target);
          return;
        }
        cancelRename(event.target, false);
      }
      input.addEventListener("keydown", function (event) {
        event.stopPropagation();
        if (event.key === "Enter") {
          event.preventDefault();
          commitRename();
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancelRename(item.getElement?.(), true);
        }
      });
      input.addEventListener("blur", function (event) {
        if (renameChanged()) {
          commitRenameAway(event.relatedTarget);
          return;
        }
        cancelRename(event.relatedTarget, false);
      }, { once: true });
      pointerAwayArmed = true;
      document.addEventListener("pointerdown", onRenamePointerAway, true);
      row.append(input);
      queueMicrotask(function () {
        if (!input.isConnected || renameCommitted) return;
        input.focus({ preventScroll: true });
        input.select();
      });
      return row;
    }

    const label = document.createElement("span");
    label.className = "ace-ht-label";
    label.textContent = item.getItemName();
    row.append(label);

    if (data.kind === "code") {
      const count = document.createElement("span");
      count.className = "ace-ht-count";
      count.textContent = data.count ? String(data.count) : "";
      count.setAttribute("aria-hidden", "true");
      row.append(count);

      const chip = document.createElement("span");
      chip.className = data.chord ? "ace-ht-chip ace-ht-chip--chord" : "ace-ht-chip";
      chip.setAttribute("aria-hidden", "true");
      if (!codeApplicationDisabled()) {
        const label = data.chord || keyLabel(codeRank(item.getId()));
        chip.textContent = label;
        chip.setAttribute(
          "title",
          data.chord
            ? `Press ; then ${data.chord} or Enter to apply ${data.name}`
            : (label ? `Press ${label} or Enter to apply ${data.name}` : `Apply ${data.name}`)
        );
      }
      chip.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        item.setFocused();
        applyCode(item);
      });
      row.append(chip);
    }

    return row;
  }

  function renderTree() {
    const mount = document.getElementById("ace-headless-tree-mount");
    if (!mount || !tree) return;

    const rows = visibleTreeItems().map(rowForItem);
    const createRow = createSearchRow();
    if (createRow) rows.push(createRow);
    mount.replaceChildren(...rows);
    const dragLine = document.createElement("div");
    dragLine.className = "ace-ht-drag-line";
    Object.assign(dragLine.style, tree.getDragLineStyle?.() || { display: "none" });
    mount.append(dragLine);
    const announcer = document.createElement("div");
    announcer.id = "ace-ht-dnd-announcer";
    announcer.className = "ace-sr-only";
    announcer.setAttribute("role", "status");
    announcer.setAttribute("aria-live", "polite");
    announcer.setAttribute("aria-atomic", "true");
    mount.append(announcer);
    updateDndAnnouncement();

    const active = document.activeElement;
    if (suppressNextRefocus) {
      suppressNextRefocus = false;
      clearCodebookActiveState();
      return;
    }
    if (!tree.getRenamingItem?.() && (!active || active === document.body || mount.contains(active))) {
      tree.getFocusedItem()?.getElement()?.focus({ preventScroll: true });
    }
  }

  function scheduleDragStateRender() {
    if (dragRenderQueued) return;
    dragRenderQueued = true;
    queueMicrotask(function () {
      dragRenderQueued = false;
      renderDragState();
    });
  }

  function renderDragState() {
    const mount = document.getElementById("ace-headless-tree-mount");
    if (!mount || !tree) return;

    const dropReceiverId = dropReceiverFolderId();
    mount.querySelectorAll(".ace-ht-row[data-item-id]").forEach(function (row) {
      row.classList.remove("ace-ht-row--drop-receiver");
      row.removeAttribute("data-drop-target");
    });

    visibleTreeItems().forEach(function (item) {
      const row = rowByItemId(item.getId());
      if (!row) return;
      if (dropReceiverId === item.getId()) row.classList.add("ace-ht-row--drop-receiver");
      if (item.isDragTargetAbove?.()) row.dataset.dropTarget = "above";
      if (item.isDragTargetBelow?.()) row.dataset.dropTarget = "below";
      if (item.isUnorderedDragTarget?.()) row.dataset.dropTarget = "inside";
    });

    const dragLine = mount.querySelector(".ace-ht-drag-line");
    if (dragLine) {
      dragLine.style.cssText = "";
      Object.assign(dragLine.style, tree.getDragLineStyle?.() || { display: "none" });
    }
    updateDndAnnouncement();
  }

  function buildTree() {
    tree = createTree({
      rootItemId: ROOT_ID,
      initialState: {
        expandedItems: folderIds(),
        focusedItem: childrenOf(ROOT_ID)[0],
      },
      getItemName: function (item) { return item.getItemData().name; },
      isItemFolder: function (item) { return item.getItemData().kind === "folder"; },
      dataLoader: {
        getItem: function (id) { return itemData(id); },
        getChildren: function (id) { return childrenOf(id); },
      },
      indent: 14,
      reorderAreaPercentage: 0.30,
      setDragImage: tinyDragImage,
      createForeignDragObject: nativeDragPayload,
      canDrag: function (draggedItems) {
        if (codebookEditingDisabled()) return false;
        return draggedItems.every(function (item) { return item.getId() !== ROOT_ID; });
      },
      canDrop,
      onDrop: handleDrop,
      onRename: function (item, value) {
        const next = value.trim();
        if (!next) return;
        items[item.getId()].name = next;
        tree.rebuildTree();
        scheduleRender();
      },
      setExpandedItems: scheduleRender,
      setFocusedItem: scheduleRender,
      setRenamingItem: scheduleRender,
      setRenamingValue: function () {},
      setDndState: scheduleDragStateRender,
      setAssistiveDndState: scheduleDragStateRender,
      features: [
        syncDataLoaderFeature,
        hotkeysCoreFeature,
        dragAndDropFeature,
        keyboardDragAndDropFeature,
        renamingFeature,
      ],
    });
  }

  function createController() {
    function rootElement() {
      return mountedElement?.isConnected ? mountedElement : null;
    }

    function refresh() {
      const root = rootElement();
      if (root) root.setAttribute("data-ace-tree-controller", "headless");
      return api;
    }

    function getTreeItems() {
      const root = rootElement();
      return root ? Array.from(root.querySelectorAll('[role="treeitem"]')) : [];
    }

    function getActiveTreeItem() {
      const root = rootElement();
      return root ? root.querySelector('[role="treeitem"][tabindex="0"]') : null;
    }

    function itemForElement(element) {
      const id = itemIdFromElement(element);
      return id && tree ? tree.getItemInstance(id) : null;
    }

    function focusTreeItem(element) {
      const item = itemForElement(element);
      if (!item) return;
      item.setFocused();
      scheduleRender();
      queueMicrotask(function () {
        item.getElement()?.focus({ preventScroll: true });
      });
    }

    function isFolderRow(element) {
      return element?.getAttribute?.("data-kind") === "folder";
    }

    function parentFolderRow(element) {
      const parentId = findParentId(itemIdFromElement(element));
      return parentId && parentId !== ROOT_ID ? rowByItemId(parentId) : null;
    }

    function firstChildOfFolderRow(element) {
      const id = itemIdFromElement(element);
      const childId = id ? childrenOf(id)[0] : null;
      return childId ? rowByItemId(childId) : null;
    }

    function expandFolder(element) {
      const item = itemForElement(element);
      if (item?.isFolder?.()) {
        item.expand();
        scheduleRender();
      }
    }

    function collapseFolder(element) {
      const item = itemForElement(element);
      if (item?.isFolder?.()) {
        item.collapse();
        scheduleRender();
      }
    }

    function toggleFolderCollapse(element) {
      const item = itemForElement(element);
      if (!item?.isFolder?.()) return;
      if (item.isExpanded()) item.collapse();
      else item.expand();
      scheduleRender();
    }

    function moveItemInDirection(itemId, direction) {
      const parentId = findParentId(itemId) || ROOT_ID;
      const order = [...childrenOf(parentId)];
      const index = order.indexOf(itemId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= order.length) return;
      order.splice(index, 1);
      order.splice(nextIndex, 0, itemId);
      items[parentId].children = order;
      tree.rebuildTree();
      focusItemById(itemId);
      setStatus("Saving");
      htmxSwap("POST", "/api/codes/reorder-in-scope", {
        code_ids: JSON.stringify(order),
        parent_id: formParentId(parentId),
        current_index: currentIndex(),
      }).then(function () {
        setStatus("");
      }).catch(function (error) {
        setStatus("Move failed");
        window.__aceHeadlessTreePreviewError = String(error && error.message || error);
      });
    }

    function startRenaming(itemId) {
      const item = itemId && tree ? tree.getItemInstance(itemId) : null;
      if (!item?.startRenaming) return;
      item.startRenaming();
      scheduleRender();
    }

    function firstCodeItem() {
      const item = visibleTreeItems().find(function (candidate) {
        return candidate.getItemData().kind === "code";
      });
      return item ? rowByItemId(item.getId()) : null;
    }

    function activeCodeItem() {
      const active = getActiveTreeItem();
      return active?.getAttribute("data-kind") === "code" ? active : null;
    }

    function setChordFilter(active) {
      const next = !!active;
      if (chordFilterActive === next) return;
      chordFilterActive = next;
      scheduleRender();
    }

    const api = {
      kind: "headless",
      refresh,
      rootElement,
      initSortable: function () {},
      restoreCollapseState: scheduleRender,
      toggleFolderCollapse,
      expandFolder,
      collapseFolder,
      getTreeItems,
      focusTreeItem,
      getActiveTreeItem,
      isFolderRow,
      containingGroupForItem: function () { return null; },
      parentFolderRow,
      isHiddenByCollapsedAncestor: function () { return false; },
      itemIdFromTreeElement: itemIdFromElement,
      directChildItemIds: function (container) {
        if (container === rootElement()) return [...childrenOf(ROOT_ID)];
        const id = itemIdFromElement(container);
        return id ? [...childrenOf(id)] : [];
      },
      firstChildOfFolderRow,
      moveItemInDirection,
      startRenaming,
      firstCodeItem,
      activeCodeItem,
      setChordFilter,
    };

    return api;
  }

  let controller = createController();

  async function init() {
    const mount = document.getElementById("ace-headless-tree-mount");
    if (!mount) return;
    if (mount === mountedElement && tree) return;
    mountedElement = mount;
    dropLog = [];
    try {
      setStatus("Loading");
      const response = await fetch("/api/codes/tree", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`status ${response.status}`);
      const payload = await response.json();
      items = payload.items || {};
      buildTree();
      applyProps(mount, tree.getContainerProps("Codebook tree"));
      tree.setMounted(true);
      tree.rebuildTree();
      renderTree();
      controller.refresh();
      window.__aceHeadlessTreeController = controller;
      setStatus("");
      window.__aceHeadlessTreePreview = {
        get tree() { return tree; },
        get items() { return items; },
        get dropLog() { return dropLog; },
        getController: function () { return controller.refresh(); },
        snapshot: function () {
          return {
            rootChildren: [...childrenOf(ROOT_ID)],
            visibleIds: visibleTreeItems().map(function (item) { return item.getId(); }),
            itemCount: Object.keys(items).length,
            dropLog: dropLog.map(function (entry) { return { ...entry }; }),
          };
        },
      };
    } catch (error) {
      setStatus("Unavailable");
      mount.textContent = "Could not load the preview.";
      window.__aceHeadlessTreePreviewError = String(error && error.message || error);
    }
  }

  window.__aceHeadlessTreeController = controller;
  window.AceHeadlessTreePreview = {
    init,
    getController: function () { return controller.refresh(); },
  };

  function initIfHeadlessTarget(target) {
    if (
      target?.id === "code-sidebar" ||
      target?.querySelector?.("#ace-headless-tree-mount")
    ) {
      init();
    }
  }

  document.addEventListener("htmx:afterSettle", function (event) {
    initIfHeadlessTarget(event.target);
  });

  document.addEventListener("htmx:oobAfterSwap", function (event) {
    initIfHeadlessTarget(event.detail?.target || event.target);
  });

  function headlessSearchIsActive(event) {
    return event.target?.id === "code-search-input" && mountedElement?.isConnected && tree;
  }

  function handleSearchKeydown(event) {
    if (!headlessSearchIsActive(event)) return;
    const input = event.target;
    const value = input.value.trim();

    if (event.key === "Escape") {
      if (!value) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      clearSearchInput();
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const items = visibleTreeItems();
      const item = event.key === "ArrowDown" ? items[0] : items[items.length - 1];
      if (!item) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      item.setFocused();
      scheduleRender();
      queueMicrotask(function () {
        item.getElement()?.focus({ preventScroll: true });
      });
      return;
    }

    if (event.key !== "Enter") return;
    if (!value) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    if (event.metaKey || event.ctrlKey) {
      createCode(value);
      return;
    }
    if (event.shiftKey) {
      createFolder(value);
      return;
    }
    if (value.startsWith("/")) {
      if (!commitSlashCommand(value)) setStatus("Type /code Name or /folder Name");
      return;
    }

    const match = firstVisibleCodeItem();
    if (match) {
      clearSearchInput();
      applyCode(match);
      return;
    }
    createCode(value);
  }

  document.addEventListener("input", function (event) {
    if (!headlessSearchIsActive(event)) return;
    event.stopImmediatePropagation();
    const value = event.target.value || "";
    searchRaw = value.trim();
    searchText = searchRaw.startsWith("/") ? "" : searchRaw.toLowerCase();
    scheduleRender();
  }, true);

  document.addEventListener("keydown", handleSearchKeydown, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
