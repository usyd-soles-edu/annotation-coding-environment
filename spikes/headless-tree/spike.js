import {
  createOnDropHandler,
  createTree,
  dragAndDropFeature,
  hotkeysCoreFeature,
  keyboardDragAndDropFeature,
  renamingFeature,
  syncDataLoaderFeature,
} from "@headless-tree/core";

const ROOT_ID = "root";

const ACE_ROWS = [
  {
    id: "folder-positive",
    name: "Used, positive feedback",
    kind: "folder",
    children: [
      {
        id: "folder-suggestions",
        name: "Suggestions",
        kind: "folder",
        children: [
          {
            id: "code-specific",
            name: "Specific improvements",
            kind: "code",
            colour: "#A23BC2",
            count: 3,
          },
          {
            id: "code-clarity",
            name: "Clarification of content",
            kind: "code",
            colour: "#44AA99",
            count: 1,
          },
        ],
      },
      {
        id: "code-structure",
        name: "Suggestions about structure",
        kind: "code",
        colour: "#6C5CE7",
        count: 4,
      },
    ],
  },
  {
    id: "code-literature",
    name: "Feedback on literature",
    kind: "code",
    colour: "#CC79A7",
    count: 2,
  },
  {
    id: "code-draft",
    name: "To give feedback on draft",
    kind: "code",
    colour: "#66CDAA",
    count: 3,
  },
];

function itemsFromAceRows(rows) {
  const result = {
    [ROOT_ID]: {
      id: ROOT_ID,
      name: "Root",
      kind: "folder",
      children: [],
    },
  };

  function visit(row, parentId) {
    const item = {
      id: row.id,
      name: row.name,
      kind: row.kind,
      colour: row.colour || "",
      chord: row.chord || "",
      count: row.count || 0,
    };
    if (row.kind === "folder") item.children = [];
    result[row.id] = item;
    result[parentId].children.push(row.id);

    if (row.kind === "folder") {
      (row.children || []).forEach((child) => visit(child, row.id));
    }
  }

  rows.forEach((row) => visit(row, ROOT_ID));
  return result;
}

function cloneChildrenByParent(items) {
  const snapshot = {};
  Object.entries(items).forEach(([id, item]) => {
    if (Array.isArray(item.children)) snapshot[id] = [...item.children];
  });
  return snapshot;
}

function arraysEqual(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
}

const items = itemsFromAceRows(ACE_ROWS);
const operations = [];
let renderQueued = false;
let tree;

function itemData(id) {
  return items[id];
}

function childrenOf(id) {
  return itemData(id)?.children ?? [];
}

function findParentId(itemId) {
  for (const [id, item] of Object.entries(items)) {
    if ((item.children ?? []).includes(itemId)) return id;
  }
  return null;
}

function apiParentId(parentId) {
  return parentId === ROOT_ID ? "" : parentId;
}

function formatOperation(operation) {
  if (operation.type === "move-parent") {
    return [
      "move-parent:",
      operation.itemId,
      "->",
      operation.parentId,
      ":[",
      operation.targetOrderIds.join(","),
      "]",
    ].join("");
  }
  if (operation.type === "reorder-scope") {
    return [
      "reorder-scope:",
      operation.parentId,
      ":[",
      operation.orderedIds.join(","),
      "]",
    ].join("");
  }
  if (operation.type === "rename") {
    return `rename:${operation.itemId}=${operation.name}`;
  }
  return JSON.stringify(operation);
}

function recordOperation(operation) {
  operations.push(operation);
  renderOperations();
}

function renderOperations() {
  const out = document.getElementById("ace-spike-operations");
  if (!out) return;
  out.textContent = operations.map(formatOperation).join("\n");
}

function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  queueMicrotask(() => {
    renderQueued = false;
    renderTree();
  });
}

function onChangeChildren(item, nextChildren) {
  items[item.getId()].children = [...nextChildren];
}

const applyLibraryDrop = createOnDropHandler(onChangeChildren);

async function handleDrop(draggedItems, target) {
  const draggedIds = draggedItems.map((item) => item.getId());
  const previousParents = new Map(
    draggedIds.map((id) => [id, findParentId(id)])
  );
  const previousChildren = cloneChildrenByParent(items);

  await applyLibraryDrop(draggedItems, target);

  const movedParentIds = new Set();
  draggedIds.forEach((id) => {
    const oldParent = previousParents.get(id);
    const nextParent = findParentId(id);
    if (oldParent !== nextParent) {
      movedParentIds.add(id);
      recordOperation({
        type: "move-parent",
        itemId: id,
        parentId: apiParentId(nextParent),
        targetOrderIds: [...childrenOf(nextParent)],
      });
    }
  });

  Object.entries(cloneChildrenByParent(items)).forEach(([parentId, nextChildren]) => {
    const oldChildren = previousChildren[parentId] || [];
    if (arraysEqual(oldChildren, nextChildren)) return;
    const parentHadMovedItem = oldChildren.some((id) => movedParentIds.has(id));
    const parentHasMovedItem = nextChildren.some((id) => movedParentIds.has(id));
    if (parentHadMovedItem || parentHasMovedItem) return;
    recordOperation({
      type: "reorder-scope",
      parentId: apiParentId(parentId),
      orderedIds: [...nextChildren],
    });
  });

  tree.rebuildTree();
  scheduleRender();
}

function canDrop(draggedItems, target) {
  if (!target || !target.item) return false;
  const targetId = target.item.getId();
  if (!("insertionIndex" in target) && !target.item.isFolder()) return false;
  return draggedItems.every((item) => {
    if (item.getId() === ROOT_ID) return false;
    if (item.getId() === targetId) return false;
    if (target.item.isDescendentOf(item.getId())) return false;
    return true;
  });
}

function applyProps(element, props) {
  Object.entries(props).forEach(([key, value]) => {
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
    element.setAttribute(key, String(value));
  });
}

function rowForItem(item) {
  const data = item.getItemData();
  const row = document.createElement("div");
  const props = item.getProps();
  applyProps(row, props);
  row.classList.add("ace-spike-row");
  row.dataset.itemId = item.getId();
  row.dataset.kind = data.kind;
  row.style.paddingLeft = `${8 + item.getItemMeta().level * 18}px`;
  if (data.colour) {
    row.style.setProperty("--row-colour", data.colour);
  }
  if (item.isUnorderedDragTarget?.()) row.dataset.dropTarget = "item";
  if (item.isDragTargetAbove?.()) row.dataset.dropTarget = "above";
  if (item.isDragTargetBelow?.()) row.dataset.dropTarget = "below";

  const toggle = document.createElement("span");
  toggle.className = "ace-spike-toggle";
  toggle.setAttribute("aria-hidden", "true");
  toggle.textContent = item.isFolder() ? (item.isExpanded() ? "v" : ">") : "";
  row.append(toggle);

  if (item.isRenaming?.()) {
    const input = document.createElement("input");
    input.className = "ace-spike-rename";
    input.setAttribute("aria-label", `Rename ${data.name}`);
    const renameProps = { ...item.getRenameInputProps() };
    delete renameProps.onKeyDown;
    delete renameProps.onBlur;
    applyProps(input, renameProps);
    let renameCommitted = false;
    function commitRename() {
      if (renameCommitted) return;
      renameCommitted = true;
      const next = input.value.trim();
      if (next) {
        items[item.getId()].name = next;
        recordOperation({
          type: "rename",
          itemId: item.getId(),
          name: next,
        });
        tree.rebuildTree();
        scheduleRender();
      }
      tree.abortRenaming();
    }
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        commitRename();
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        renameCommitted = true;
        tree.abortRenaming();
      }
    });
    row.append(input);
  } else {
    const label = document.createElement("span");
    label.className = "ace-spike-label";
    label.textContent = item.getItemName();
    row.append(label);

    if (data.kind === "code") {
      const count = document.createElement("span");
      count.className = "ace-spike-count";
      count.textContent = data.count ? `${data.count}x` : "";
      count.setAttribute("aria-hidden", "true");
      row.append(count);
    }
  }

  return row;
}

function renderTree() {
  const mount = document.getElementById("ace-spike-tree");
  if (!mount || !tree) return;
  mount.replaceChildren(...tree.getItems().map(rowForItem));
  const dragLine = document.createElement("div");
  dragLine.className = "ace-spike-drag-line";
  Object.assign(dragLine.style, tree.getDragLineStyle?.() ?? { display: "none" });
  mount.append(dragLine);

  if (!tree.getRenamingItem?.()) {
    tree.getFocusedItem()?.getElement()?.focus({ preventScroll: true });
  }
}

function buildTree() {
  tree = createTree({
    rootItemId: ROOT_ID,
    initialState: {
      expandedItems: ["folder-positive", "folder-suggestions"],
      focusedItem: "folder-positive",
    },
    getItemName: (item) => item.getItemData().name,
    isItemFolder: (item) => item.getItemData().kind === "folder",
    dataLoader: {
      getItem: (id) => itemData(id),
      getChildren: (id) => childrenOf(id),
    },
    indent: 18,
    canDrag: (draggedItems) => draggedItems.every((item) => item.getId() !== ROOT_ID),
    canDrop,
    onDrop: handleDrop,
    onRename: (item, value) => {
      if (items[item.getId()].name === value.trim()) return;
      const next = value.trim();
      if (!next) return;
      items[item.getId()].name = next;
      recordOperation({
        type: "rename",
        itemId: item.getId(),
        name: next,
      });
      tree.rebuildTree();
      scheduleRender();
    },
    setExpandedItems: scheduleRender,
    setFocusedItem: scheduleRender,
    setRenamingItem: scheduleRender,
    setRenamingValue: () => {},
    setDndState: scheduleRender,
    setAssistiveDndState: scheduleRender,
    features: [
      syncDataLoaderFeature,
      hotkeysCoreFeature,
      dragAndDropFeature,
      keyboardDragAndDropFeature,
      renamingFeature,
    ],
  });
}

async function moveLiteratureIntoSuggestions() {
  await handleDrop([tree.getItemInstance("code-literature")], {
    item: tree.getItemInstance("folder-suggestions"),
  });
}

async function moveLiteratureToTopOfSuggestions() {
  await handleDrop([tree.getItemInstance("code-literature")], {
    item: tree.getItemInstance("folder-suggestions"),
    childIndex: 0,
    insertionIndex: 0,
    dragLineIndex: 0,
    dragLineLevel: 2,
  });
}

async function moveDraftIntoPositiveMiddle() {
  await handleDrop([tree.getItemInstance("code-draft")], {
    item: tree.getItemInstance("folder-positive"),
    childIndex: 1,
    insertionIndex: 1,
    dragLineIndex: 1,
    dragLineLevel: 2,
  });
}

function snapshot() {
  return {
    rootChildren: [...childrenOf(ROOT_ID)],
    positiveChildren: [...childrenOf("folder-positive")],
    suggestionsChildren: [...childrenOf("folder-suggestions")],
    operations: operations.map((operation) => ({ ...operation })),
    operationText: operations.map(formatOperation),
  };
}

function init() {
  buildTree();
  const mount = document.getElementById("ace-spike-tree");
  const containerProps = tree.getContainerProps("Headless Tree codebook spike");
  applyProps(mount, containerProps);
  tree.setMounted(true);
  tree.rebuildTree();
  renderTree();
  renderOperations();

  document
    .getElementById("move-literature-into")
    .addEventListener("click", moveLiteratureIntoSuggestions);
  document
    .getElementById("move-literature-top")
    .addEventListener("click", moveLiteratureToTopOfSuggestions);
  document
    .getElementById("move-draft-middle")
    .addEventListener("click", moveDraftIntoPositiveMiddle);

  window.__aceHeadlessTreeSpike = {
    tree,
    items,
    operations,
    itemsFromAceRows,
    moveDraftIntoPositiveMiddle,
    moveLiteratureIntoSuggestions,
    moveLiteratureToTopOfSuggestions,
    snapshot,
  };
}

init();
