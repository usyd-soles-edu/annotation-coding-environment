(function () {
  "use strict";

  function createController(options) {
    options = options || {};
    const collapsedFolders = options.collapsedFolders || {};
    const rootSelector = options.rootSelector || "#code-tree";
    let sortableInstances = [];
    let dropLine = null;
    let lastDropIntent = null;
    let lastPointerY = null;
    let pointerTrackingBound = false;

    function root() {
      return document.querySelector(rootSelector);
    }

    function refresh() {
      const tree = root();
      if (tree) tree.setAttribute("data-ace-tree-controller", "ready");
      return api;
    }

    function isFolderRow(item) {
      return item && item.classList.contains("ace-code-folder-row");
    }

    function containingGroupForItem(item) {
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

    function parentFolderRow(item) {
      const group = containingGroupForItem(item);
      const row = group ? group.previousElementSibling : null;
      return isFolderRow(row) ? row : null;
    }

    function isHiddenByCollapsedAncestor(item) {
      let group = containingGroupForItem(item);
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

    function getTreeItems() {
      const tree = root();
      if (!tree) return [];
      const result = [];
      tree.querySelectorAll('[role="treeitem"]').forEach(function (item) {
        if (item.style.display === "none") return;
        if (item.getAttribute("aria-hidden") === "true") return;
        if (isHiddenByCollapsedAncestor(item)) return;
        result.push(item);
      });
      return result;
    }

    function getActiveTreeItem() {
      const tree = root();
      return tree ? tree.querySelector('[role="treeitem"][tabindex="0"]') : null;
    }

    function focusTreeItem(item) {
      if (!item) return;
      const prev = getActiveTreeItem();
      if (prev) prev.setAttribute("tabindex", "-1");
      item.setAttribute("tabindex", "0");
      item.focus();
    }

    function expandFolder(folderRow) {
      if (!folderRow) return;
      folderRow.setAttribute("aria-expanded", "true");
      const id = folderRow.getAttribute("data-folder-id");
      if (id) collapsedFolders[id] = false;
    }

    function collapseFolder(folderRow) {
      if (!folderRow) return;
      folderRow.setAttribute("aria-expanded", "false");
      const id = folderRow.getAttribute("data-folder-id");
      if (id) collapsedFolders[id] = true;
    }

    function toggleFolderCollapse(folderRow) {
      if (!folderRow) return;
      if (folderRow.getAttribute("aria-expanded") === "true") {
        collapseFolder(folderRow);
      } else {
        expandFolder(folderRow);
      }
    }

    function restoreCollapseState() {
      const tree = root();
      if (!tree) return;
      tree.querySelectorAll(".ace-code-folder-row").forEach(function (row) {
        const folderId = row.getAttribute("data-folder-id");
        if (folderId && collapsedFolders[folderId]) {
          collapseFolder(row);
        }
      });
    }

    function itemIdFromTreeElement(el) {
      if (!el || !el.getAttribute) return null;
      if (el.classList.contains("ace-folder-block")) return el.getAttribute("data-folder-id");
      return el.getAttribute("data-code-id") || el.getAttribute("data-folder-id");
    }

    function directChildForContainer(container, el) {
      let current = el;
      while (current && current.parentElement !== container) {
        current = current.parentElement;
      }
      return current && current.parentElement === container ? current : null;
    }

    function directChildItemIds(container) {
      return Array.from(container.children)
        .map(function (el) { return itemIdFromTreeElement(el); })
        .filter(Boolean);
    }

    function ensureDropLine() {
      const tree = root();
      if (!tree) return null;
      if (!dropLine || !tree.contains(dropLine)) {
        dropLine = document.createElement("div");
        dropLine.className = "ace-codebook-drop-line";
        dropLine.setAttribute("aria-hidden", "true");
        tree.appendChild(dropLine);
      }
      return dropLine;
    }

    function hideDropLine() {
      if (dropLine) dropLine.classList.remove("is-visible");
    }

    function targetLevel(container, related) {
      if (container && container.getAttribute("role") === "group") {
        const folderRow = container.previousElementSibling;
        const parentLevel = folderRow
          ? parseInt(folderRow.getAttribute("aria-level") || "1", 10)
          : 1;
        return parentLevel + 1;
      }
      const item = related && related.classList && related.classList.contains("ace-folder-block")
        ? related.querySelector(".ace-code-folder-row")
        : related;
      return item ? parseInt(item.getAttribute("aria-level") || "1", 10) : 1;
    }

    function clientYFromEvent(evt) {
      if (!evt) return null;
      if (typeof evt.clientY === "number") return evt.clientY;
      if (evt.touches && evt.touches[0] && typeof evt.touches[0].clientY === "number") {
        return evt.touches[0].clientY;
      }
      if (evt.changedTouches && evt.changedTouches[0] && typeof evt.changedTouches[0].clientY === "number") {
        return evt.changedTouches[0].clientY;
      }
      if (typeof evt.pageY === "number") return evt.pageY - window.scrollY;
      return null;
    }

    function showDropLine(evt) {
      const tree = root();
      const line = ensureDropLine();
      if (!tree || !line || !evt || !evt.related) {
        hideDropLine();
        return;
      }
      const related = evt.related;
      const visualTarget = related.classList.contains("ace-folder-block")
        ? related
        : related.closest(".ace-code-row, .ace-folder-block, .ace-code-folder-row");
      if (!visualTarget) {
        hideDropLine();
        return;
      }

      const treeRect = tree.getBoundingClientRect();
      const targetRect = visualTarget.getBoundingClientRect();
      const level = targetLevel(evt.to, related);
      const left = 8 + ((level - 1) * 10);
      const eventPointerY = clientYFromEvent(evt.originalEvent);
      const pointerY = typeof lastPointerY === "number" ? lastPointerY : eventPointerY;
      const insertAfter = pointerY === null
        ? !!evt.willInsertAfter
        : pointerY > (targetRect.top + targetRect.height / 2);
      const top = (insertAfter ? targetRect.bottom : targetRect.top) -
        treeRect.top + tree.scrollTop;

      line.style.left = left + "px";
      line.style.right = "12px";
      line.style.top = top + "px";
      line.classList.add("is-visible");
      lastDropIntent = {
        container: evt.to,
        related: related,
        insertAfter: insertAfter,
      };
    }

    function applyDropIntent(container, item) {
      if (!lastDropIntent || lastDropIntent.container !== container || !lastDropIntent.related) return;
      const relatedChild = directChildForContainer(container, lastDropIntent.related);
      if (!relatedChild || relatedChild === item) return;
      if (lastDropIntent.insertAfter) {
        container.insertBefore(item, relatedChild.nextSibling);
      } else {
        container.insertBefore(item, relatedChild);
      }
    }

    function applyOrderIds(container, item, orderedIds) {
      if (!container || !item || !Array.isArray(orderedIds)) return;
      const byId = new Map();
      Array.from(container.children).forEach(function (child) {
        const id = itemIdFromTreeElement(child);
        if (id) byId.set(id, child);
      });
      const itemId = itemIdFromTreeElement(item);
      if (itemId) byId.set(itemId, item);
      orderedIds.forEach(function (id) {
        const child = byId.get(id);
        if (child) container.appendChild(child);
      });
    }

    function orderedIdsForDrop(container, item, preferLineOrder) {
      const itemId = itemIdFromTreeElement(item);
      if (!itemId) return directChildItemIds(container);
      if (preferLineOrder) {
        const lineOrder = orderedIdsFromDropLine(container, item);
        if (lineOrder) return lineOrder;
      }
      const ids = directChildItemIds(container).filter(function (id) {
        return id !== itemId;
      });
      if (!lastDropIntent || lastDropIntent.container !== container || !lastDropIntent.related) {
        return directChildItemIds(container);
      }
      const relatedId = itemIdFromTreeElement(lastDropIntent.related);
      const idx = ids.indexOf(relatedId);
      if (idx < 0) return directChildItemIds(container);
      ids.splice(idx + (lastDropIntent.insertAfter ? 1 : 0), 0, itemId);
      return ids;
    }

    function orderedIdsFromDropLine(container, item) {
      const itemId = itemIdFromTreeElement(item);
      if (
        !itemId ||
        !dropLine ||
        !dropLine.classList.contains("is-visible") ||
        !lastDropIntent ||
        lastDropIntent.container !== container
      ) {
        return null;
      }
      const lineTop = dropLine.getBoundingClientRect().top;
      const ids = [];
      let inserted = false;
      Array.from(container.children).forEach(function (child) {
        const id = itemIdFromTreeElement(child);
        if (!id || id === itemId) return;
        const rect = child.getBoundingClientRect();
        if (!inserted && lineTop <= rect.top + (rect.height / 2)) {
          ids.push(itemId);
          inserted = true;
        }
        ids.push(id);
      });
      if (!inserted) ids.push(itemId);
      return ids;
    }

    function destroySortable() {
      sortableInstances.forEach(function (sortable) {
        try { sortable.destroy(); } catch (_) {}
      });
      sortableInstances = [];
    }

    function initSortable(config) {
      config = config || {};
      const SortableCtor = config.Sortable || window.Sortable;
      if (typeof SortableCtor === "undefined") return;

      destroySortable();
      const tree = root();
      if (!tree) return;

      function tauriRuntime() {
        return !!(window.__TAURI__ || window.__TAURI_INTERNALS__);
      }

      if (tree.dataset.aceDragSelectionBound !== "1") {
        tree.dataset.aceDragSelectionBound = "1";
        tree.addEventListener("mousedown", function (evt) {
          if (evt.target.closest("input, textarea, button, a, [contenteditable='true']")) return;
          if (!evt.target.closest(".ace-code-row, .ace-code-folder-row")) return;
          if (evt.cancelable) evt.preventDefault();
          const selection = window.getSelection && window.getSelection();
          if (selection && selection.removeAllRanges) selection.removeAllRanges();
        }, true);
      }

      function setDragging(value) {
        if (typeof config.onDragStateChange === "function") {
          config.onDragStateChange(value);
        }
      }

      function trackPointer(evt) {
        const pointerY = clientYFromEvent(evt);
        if (pointerY !== null) lastPointerY = pointerY;
      }

      if (!pointerTrackingBound) {
        pointerTrackingBound = true;
        document.addEventListener("mousemove", trackPointer, true);
        document.addEventListener("pointermove", trackPointer, true);
        document.addEventListener("dragover", trackPointer, true);
      }

      function isInvalidFolderDrop(container, dragEl) {
        if (!dragEl.classList.contains("ace-folder-block")) return false;
        return dragEl.contains(container);
      }

      function handleItemEnd(evt) {
        const itemId = itemIdFromTreeElement(evt.item);
        if (!itemId) {
          hideDropLine();
          return;
        }
        const newContainer = evt.to;
        const newParentId = newContainer.getAttribute("data-folder-children") || "";
        const oldContainer = evt.from;
        const oldParentId = oldContainer.getAttribute("data-folder-children") || "";
        if (isInvalidFolderDrop(newContainer, evt.item)) {
          hideDropLine();
          lastDropIntent = null;
          if (typeof config.onInvalidDrop === "function") config.onInvalidDrop();
          return;
        }

        const targetOrderIds = orderedIdsForDrop(
          newContainer,
          evt.item,
          newParentId === oldParentId
        );
        hideDropLine();
        if (newParentId === oldParentId) {
          applyDropIntent(newContainer, evt.item);
          applyOrderIds(newContainer, evt.item, targetOrderIds);
          lastDropIntent = null;
          if (typeof config.onPersistScopeOrder === "function") {
            config.onPersistScopeOrder(newContainer, targetOrderIds);
          }
        } else if (typeof config.onMoveParent === "function") {
          applyDropIntent(newContainer, evt.item);
          applyOrderIds(newContainer, evt.item, targetOrderIds);
          lastDropIntent = null;
          config.onMoveParent(itemId, newParentId, targetOrderIds);
        }
      }

      function commonOpts() {
        const useFallbackDrag = true;
        return {
          group: "codes",
          animation: 0,
          delay: 200,
          delayOnTouchOnly: true,
          forceFallback: useFallbackDrag,
          fallbackOnBody: useFallbackDrag,
          fallbackTolerance: useFallbackDrag ? 4 : 0,
          fallbackClass: "ace-codebook-drag-clone",
          ghostClass: "ace-codebook-sort-placeholder",
          onStart: function () {
            setDragging(true);
            lastPointerY = null;
            ensureDropLine();
          },
          onMove: function (evt) {
            if (isInvalidFolderDrop(evt.to, evt.dragged)) {
              hideDropLine();
              lastDropIntent = null;
              return false;
            }
            showDropLine(evt);
            return true;
          },
        };
      }

      const rootInstance = new SortableCtor(tree, Object.assign(commonOpts(), {
        handle: ".ace-code-row, .ace-code-folder-row",
        draggable: ".ace-code-row, .ace-folder-block",
        onEnd: function (evt) {
          setDragging(false);
          handleItemEnd(evt);
        },
      }));
      sortableInstances.push(rootInstance);

      document.querySelectorAll('#code-tree [role="group"]').forEach(function (container) {
        const instance = new SortableCtor(container, Object.assign(commonOpts(), {
          group: {
            name: "codes",
            put: function (to, _from, dragEl) {
              return !isInvalidFolderDrop(to.el, dragEl);
            },
          },
          handle: ".ace-code-row, .ace-code-folder-row",
          draggable: ".ace-code-row, .ace-folder-block",
          onEnd: function (evt) {
            setDragging(false);
            handleItemEnd(evt);
          },
        }));
        sortableInstances.push(instance);
      });
    }

    const api = {
      refresh: refresh,
      initSortable: initSortable,
      restoreCollapseState: restoreCollapseState,
      toggleFolderCollapse: toggleFolderCollapse,
      expandFolder: expandFolder,
      collapseFolder: collapseFolder,
      getTreeItems: getTreeItems,
      focusTreeItem: focusTreeItem,
      getActiveTreeItem: getActiveTreeItem,
      isFolderRow: isFolderRow,
      containingGroupForItem: containingGroupForItem,
      parentFolderRow: parentFolderRow,
      isHiddenByCollapsedAncestor: isHiddenByCollapsedAncestor,
      itemIdFromTreeElement: itemIdFromTreeElement,
      directChildItemIds: directChildItemIds,
    };

    return refresh();
  }

  window.AceCodebookTree = {
    createController: createController,
  };
})();
