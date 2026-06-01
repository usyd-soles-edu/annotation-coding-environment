var AceHeadlessTreePreview = (() => {
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __esm = (fn, res) => function __init() {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  };
  var __commonJS = (cb, mod) => function __require() {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  };

  // tmp/headless-tree-build/node_modules/@headless-tree/core/dist/index.mjs
  function functionalUpdate(updater, input) {
    return typeof updater === "function" ? updater(input) : updater;
  }
  function makeStateUpdater(key, instance) {
    return (updater) => {
      instance.setState((old) => {
        return __spreadProps(__spreadValues({}, old), {
          [key]: functionalUpdate(updater, old[key])
        });
      });
    };
  }
  var __defProp, __defProps, __getOwnPropDescs, __getOwnPropSymbols, __hasOwnProp, __propIsEnum, __defNormalProp, __spreadValues, __spreadProps, __async, memo, poll, prefix, throwError, logWarning, treeFeature, buildStaticInstance, verifyFeatures, exhaustiveSort, compareFeatures, sortFeatures, createTree, resolveKeyCode, specialKeys, modifierKeyCodes, testHotkeyMatch, findHotkeyMatch, hotkeysCoreController, hotkeysCoreFeature, undefErrorMessage, promiseErrorMessage, unpromise, syncDataLoaderFeature, isOrderedDragTarget, canDrop, getItemDropCategory, getInsertionIndex, getTargetPlacement, getDragCode, getNthParent, getReparentTarget, getDragTarget, handleAutoOpenFolder, defaultCanDropForeignDragObject, dragAndDropFeature, getNextDragTarget, getNextValidDragTarget, updateScroll, initiateDrag, moveDragPosition, keyboardDragAndDropFeature, searchFeature, renamingFeature, removeItemsFromParents, insertItemsAtTarget, createOnDropHandler;
  var init_dist = __esm({
    "tmp/headless-tree-build/node_modules/@headless-tree/core/dist/index.mjs"() {
      __defProp = Object.defineProperty;
      __defProps = Object.defineProperties;
      __getOwnPropDescs = Object.getOwnPropertyDescriptors;
      __getOwnPropSymbols = Object.getOwnPropertySymbols;
      __hasOwnProp = Object.prototype.hasOwnProperty;
      __propIsEnum = Object.prototype.propertyIsEnumerable;
      __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
      __spreadValues = (a, b) => {
        for (var prop in b || (b = {}))
          if (__hasOwnProp.call(b, prop))
            __defNormalProp(a, prop, b[prop]);
        if (__getOwnPropSymbols)
          for (var prop of __getOwnPropSymbols(b)) {
            if (__propIsEnum.call(b, prop))
              __defNormalProp(a, prop, b[prop]);
          }
        return a;
      };
      __spreadProps = (a, b) => __defProps(a, __getOwnPropDescs(b));
      __async = (__this, __arguments, generator) => {
        return new Promise((resolve, reject) => {
          var fulfilled = (value) => {
            try {
              step(generator.next(value));
            } catch (e) {
              reject(e);
            }
          };
          var rejected = (value) => {
            try {
              step(generator.throw(value));
            } catch (e) {
              reject(e);
            }
          };
          var step = (x) => x.done ? resolve(x.value) : Promise.resolve(x.value).then(fulfilled, rejected);
          step((generator = generator.apply(__this, __arguments)).next());
        });
      };
      memo = (deps, fn) => {
        let value;
        let oldDeps = null;
        return (...a) => {
          const newDeps = deps(...a);
          if (!value) {
            value = fn(...newDeps);
            oldDeps = newDeps;
            return value;
          }
          const match = oldDeps && oldDeps.length === newDeps.length && !oldDeps.some((dep, i) => dep !== newDeps[i]);
          if (match) {
            return value;
          }
          value = fn(...newDeps);
          oldDeps = newDeps;
          return value;
        };
      };
      poll = (fn, interval = 100, timeout = 1e3) => new Promise((resolve) => {
        let clear;
        const i = setInterval(() => {
          if (fn()) {
            resolve();
            clearInterval(i);
            clearTimeout(clear);
          }
        }, interval);
        clear = setTimeout(() => {
          clearInterval(i);
          resolve();
        }, timeout);
      });
      prefix = "Headless Tree: ";
      throwError = (message) => Error(prefix + message);
      logWarning = (message) => console.warn(prefix + message);
      treeFeature = {
        key: "tree",
        getInitialState: (initialState) => __spreadValues({
          expandedItems: [],
          focusedItem: null
        }, initialState),
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          setExpandedItems: makeStateUpdater("expandedItems", tree),
          setFocusedItem: makeStateUpdater("focusedItem", tree)
        }, defaultConfig),
        stateHandlerNames: {
          expandedItems: "setExpandedItems",
          focusedItem: "setFocusedItem"
        },
        treeInstance: {
          getItemsMeta: ({ tree }) => {
            const { rootItemId } = tree.getConfig();
            const { expandedItems } = tree.getState();
            const flatItems = [];
            const expandedItemsSet = new Set(expandedItems);
            const recursiveAdd = (itemId, path, level, setSize, posInSet) => {
              var _a;
              if (path.includes(itemId)) {
                logWarning(`Circular reference for ${path.join(".")}`);
                return;
              }
              flatItems.push({
                itemId,
                level,
                index: flatItems.length,
                parentId: path.at(-1),
                setSize,
                posInSet
              });
              if (expandedItemsSet.has(itemId)) {
                const children2 = (_a = tree.retrieveChildrenIds(itemId)) != null ? _a : [];
                let i2 = 0;
                for (const childId of children2) {
                  recursiveAdd(
                    childId,
                    path.concat(itemId),
                    level + 1,
                    children2.length,
                    i2++
                  );
                }
              }
            };
            const children = tree.retrieveChildrenIds(rootItemId);
            let i = 0;
            for (const itemId of children) {
              recursiveAdd(itemId, [rootItemId], 0, children.length, i++);
            }
            return flatItems;
          },
          getFocusedItem: ({ tree }) => {
            var _a;
            const focusedItemId = tree.getState().focusedItem;
            return (_a = focusedItemId !== null ? tree.getItemInstance(focusedItemId) : null) != null ? _a : tree.getItems()[0];
          },
          getRootItem: ({ tree }) => {
            const { rootItemId } = tree.getConfig();
            return tree.getItemInstance(rootItemId);
          },
          focusNextItem: ({ tree }) => {
            var _a;
            const focused = tree.getFocusedItem().getItemMeta();
            if (!focused) return;
            const nextIndex = Math.min(focused.index + 1, tree.getItems().length - 1);
            (_a = tree.getItems()[nextIndex]) == null ? void 0 : _a.setFocused();
          },
          focusPreviousItem: ({ tree }) => {
            var _a;
            const focused = tree.getFocusedItem().getItemMeta();
            if (!focused) return;
            const nextIndex = Math.max(focused.index - 1, 0);
            (_a = tree.getItems()[nextIndex]) == null ? void 0 : _a.setFocused();
          },
          updateDomFocus: ({ tree }) => {
            setTimeout(() => __async(null, null, function* () {
              var _a, _b, _c, _d, _e;
              const focusedItem = tree.getFocusedItem();
              (_b = (_a = tree.getConfig()).scrollToItem) == null ? void 0 : _b.call(_a, focusedItem);
              yield poll(() => focusedItem.getElement() !== null, 20, 500);
              const focusedElement = focusedItem.getElement();
              if (!focusedElement) {
                (_c = tree.getItems()[0]) == null ? void 0 : _c.setFocused();
                (_e = (_d = tree.getItems()[0]) == null ? void 0 : _d.getElement()) == null ? void 0 : _e.focus();
                return;
              }
              focusedElement.focus();
            }));
          },
          getContainerProps: ({ prev, tree }, treeLabel) => __spreadProps(__spreadValues({}, prev == null ? void 0 : prev()), {
            role: "tree",
            "aria-label": treeLabel != null ? treeLabel : "",
            ref: tree.registerElement
          }),
          // relevant for hotkeys of this feature
          isSearchOpen: () => false
        },
        itemInstance: {
          scrollTo: (_0, _1) => __async(null, [_0, _1], function* ({ tree, item }, scrollIntoViewArg) {
            var _a, _b, _c;
            (_b = (_a = tree.getConfig()).scrollToItem) == null ? void 0 : _b.call(_a, item);
            yield poll(() => item.getElement() !== null, 20);
            (_c = item.getElement()) == null ? void 0 : _c.scrollIntoView(scrollIntoViewArg);
          }),
          getId: ({ itemId }) => itemId,
          getKey: ({ itemId }) => itemId,
          // TODO apply to all stories to use
          getProps: ({ item, prev }) => {
            const itemMeta = item.getItemMeta();
            return __spreadProps(__spreadValues({}, prev == null ? void 0 : prev()), {
              ref: item.registerElement,
              role: "treeitem",
              "aria-setsize": itemMeta.setSize,
              "aria-posinset": itemMeta.posInSet + 1,
              "aria-selected": "false",
              "aria-label": item.getItemName(),
              "aria-level": itemMeta.level + 1,
              "aria-expanded": item.isFolder() ? item.isExpanded() : void 0,
              tabIndex: item.isFocused() ? 0 : -1,
              onClick: (e) => {
                item.setFocused();
                item.primaryAction();
                if (e.ctrlKey || e.shiftKey || e.metaKey) {
                  return;
                }
                if (!item.isFolder()) {
                  return;
                }
                if (item.isExpanded()) {
                  item.collapse();
                } else {
                  item.expand();
                }
              }
            });
          },
          expand: ({ tree, item, itemId }) => {
            var _a;
            if (!item.isFolder()) {
              return;
            }
            if ((_a = tree.getState().loadingItemChildrens) == null ? void 0 : _a.includes(itemId)) {
              return;
            }
            tree.applySubStateUpdate("expandedItems", (expandedItems) => [
              ...expandedItems,
              itemId
            ]);
            tree.rebuildTree();
          },
          collapse: ({ tree, item, itemId }) => {
            if (!item.isFolder()) {
              return;
            }
            tree.applySubStateUpdate(
              "expandedItems",
              (expandedItems) => expandedItems.filter((id) => id !== itemId)
            );
            tree.rebuildTree();
          },
          getItemData: ({ tree, itemId }) => tree.retrieveItemData(itemId),
          equals: ({ item }, other) => item.getId() === (other == null ? void 0 : other.getId()),
          isExpanded: ({ tree, itemId }) => tree.getState().expandedItems.includes(itemId),
          isDescendentOf: ({ item }, parentId) => {
            const parent = item.getParent();
            return Boolean(
              (parent == null ? void 0 : parent.getId()) === parentId || (parent == null ? void 0 : parent.isDescendentOf(parentId))
            );
          },
          isFocused: ({ tree, item, itemId }) => tree.getState().focusedItem === itemId || tree.getState().focusedItem === null && item.getItemMeta().index === 0,
          isFolder: ({ tree, item, itemId }) => itemId === tree.getConfig().rootItemId || tree.getConfig().isItemFolder(item),
          getItemName: ({ tree, item }) => {
            const config = tree.getConfig();
            return config.getItemName(item);
          },
          setFocused: ({ tree, itemId }) => {
            tree.applySubStateUpdate("focusedItem", itemId);
          },
          primaryAction: ({ tree, item }) => {
            var _a, _b;
            return (_b = (_a = tree.getConfig()).onPrimaryAction) == null ? void 0 : _b.call(_a, item);
          },
          getParent: ({ tree, item }) => item.getItemMeta().parentId ? tree.getItemInstance(item.getItemMeta().parentId) : void 0,
          getIndexInParent: ({ item }) => item.getItemMeta().posInSet,
          getChildren: ({ tree, itemId }) => tree.retrieveChildrenIds(itemId).map((id) => tree.getItemInstance(id)),
          getTree: ({ tree }) => tree,
          getItemAbove: ({ tree, item }) => tree.getItems()[item.getItemMeta().index - 1],
          getItemBelow: ({ tree, item }) => tree.getItems()[item.getItemMeta().index + 1]
        },
        hotkeys: {
          focusNextItem: {
            hotkey: "ArrowDown",
            canRepeat: true,
            preventDefault: true,
            isEnabled: (tree) => {
              var _a, _b;
              return !((_b = (_a = tree.isSearchOpen) == null ? void 0 : _a.call(tree)) != null ? _b : false) && !tree.getState().dnd;
            },
            // TODO what happens when the feature doesnt exist? proxy method still claims to exist
            handler: (e, tree) => {
              tree.focusNextItem();
              tree.updateDomFocus();
            }
          },
          focusPreviousItem: {
            hotkey: "ArrowUp",
            canRepeat: true,
            preventDefault: true,
            isEnabled: (tree) => {
              var _a, _b;
              return !((_b = (_a = tree.isSearchOpen) == null ? void 0 : _a.call(tree)) != null ? _b : false) && !tree.getState().dnd;
            },
            handler: (e, tree) => {
              tree.focusPreviousItem();
              tree.updateDomFocus();
            }
          },
          expandOrDown: {
            hotkey: "ArrowRight",
            canRepeat: true,
            handler: (e, tree) => {
              const item = tree.getFocusedItem();
              if (item.isExpanded() || !item.isFolder()) {
                tree.focusNextItem();
                tree.updateDomFocus();
              } else {
                item.expand();
              }
            }
          },
          collapseOrUp: {
            hotkey: "ArrowLeft",
            canRepeat: true,
            handler: (e, tree) => {
              var _a;
              const item = tree.getFocusedItem();
              if ((!item.isExpanded() || !item.isFolder()) && item.getItemMeta().level !== 0) {
                (_a = item.getParent()) == null ? void 0 : _a.setFocused();
                tree.updateDomFocus();
              } else {
                item.collapse();
              }
            }
          },
          focusFirstItem: {
            hotkey: "Home",
            handler: (e, tree) => {
              var _a;
              (_a = tree.getItems()[0]) == null ? void 0 : _a.setFocused();
              tree.updateDomFocus();
            }
          },
          focusLastItem: {
            hotkey: "End",
            handler: (e, tree) => {
              var _a;
              (_a = tree.getItems()[tree.getItems().length - 1]) == null ? void 0 : _a.setFocused();
              tree.updateDomFocus();
            }
          }
        }
      };
      buildStaticInstance = (features, instanceType, buildOpts) => {
        const instance = {};
        const finalize = () => {
          const opts = buildOpts(instance);
          featureLoop: for (let i = 0; i < features.length; i++) {
            const definition = features[i][instanceType];
            if (!definition) continue featureLoop;
            methodLoop: for (const [key, method] of Object.entries(definition)) {
              if (!method) continue methodLoop;
              const prev = instance[key];
              instance[key] = (...args) => {
                return method(__spreadProps(__spreadValues({}, opts), { prev }), ...args);
              };
            }
          }
        };
        return [instance, finalize];
      };
      verifyFeatures = (features) => {
        var _a;
        const loadedFeatures = features == null ? void 0 : features.map((feature) => feature.key);
        for (const feature of features != null ? features : []) {
          const missingDependency = (_a = feature.deps) == null ? void 0 : _a.find(
            (dep) => !(loadedFeatures == null ? void 0 : loadedFeatures.includes(dep))
          );
          if (missingDependency) {
            throw throwError(`${feature.key} needs ${missingDependency}`);
          }
        }
      };
      exhaustiveSort = (arr, compareFn) => {
        const n = arr.length;
        for (let i = 0; i < n; i++) {
          for (let j = i + 1; j < n; j++) {
            if (compareFn(arr[j], arr[i]) < 0) {
              [arr[i], arr[j]] = [arr[j], arr[i]];
            }
          }
        }
        return arr;
      };
      compareFeatures = (originalOrder) => (feature1, feature2) => {
        var _a, _b;
        if (feature2.key && ((_a = feature1.overwrites) == null ? void 0 : _a.includes(feature2.key))) {
          return 1;
        }
        if (feature1.key && ((_b = feature2.overwrites) == null ? void 0 : _b.includes(feature1.key))) {
          return -1;
        }
        return originalOrder.indexOf(feature1) - originalOrder.indexOf(feature2);
      };
      sortFeatures = (features = []) => exhaustiveSort(features, compareFeatures(features));
      createTree = (initialConfig) => {
        var _a, _b, _c, _d;
        const buildInstance = (_a = initialConfig.instanceBuilder) != null ? _a : buildStaticInstance;
        const additionalFeatures = [
          treeFeature,
          ...sortFeatures(initialConfig.features)
        ];
        verifyFeatures(additionalFeatures);
        const features = [...additionalFeatures];
        const [treeInstance, finalizeTree] = buildInstance(
          features,
          "treeInstance",
          (tree) => ({ tree })
        );
        let state = additionalFeatures.reduce(
          (acc, feature) => {
            var _a2, _b2;
            return (_b2 = (_a2 = feature.getInitialState) == null ? void 0 : _a2.call(feature, acc, treeInstance)) != null ? _b2 : acc;
          },
          (_c = (_b = initialConfig.initialState) != null ? _b : initialConfig.state) != null ? _c : {}
        );
        let config = additionalFeatures.reduce(
          (acc, feature) => {
            var _a2, _b2;
            return (_b2 = (_a2 = feature.getDefaultConfig) == null ? void 0 : _a2.call(feature, acc, treeInstance)) != null ? _b2 : acc;
          },
          initialConfig
        );
        const stateHandlerNames = additionalFeatures.reduce(
          (acc, feature) => __spreadValues(__spreadValues({}, acc), feature.stateHandlerNames),
          {}
        );
        let treeElement;
        const treeDataRef = { current: {} };
        let rebuildScheduled = false;
        const itemInstancesMap = {};
        let itemInstances = [];
        const itemElementsMap = {};
        const itemDataRefs = {};
        let itemMetaMap = {};
        const hotkeyPresets = {};
        const rebuildItemMeta = () => {
          itemInstances = [];
          itemMetaMap = {};
          const [rootInstance, finalizeRootInstance] = buildInstance(
            features,
            "itemInstance",
            (item) => ({ item, tree: treeInstance, itemId: config.rootItemId })
          );
          finalizeRootInstance();
          itemInstancesMap[config.rootItemId] = rootInstance;
          itemMetaMap[config.rootItemId] = {
            itemId: config.rootItemId,
            index: -1,
            parentId: null,
            level: -1,
            posInSet: 0,
            setSize: 1
          };
          for (const item of treeInstance.getItemsMeta()) {
            itemMetaMap[item.itemId] = item;
            if (!itemInstancesMap[item.itemId]) {
              const [instance, finalizeInstance] = buildInstance(
                features,
                "itemInstance",
                (instance2) => ({
                  item: instance2,
                  tree: treeInstance,
                  itemId: item.itemId
                })
              );
              finalizeInstance();
              itemInstancesMap[item.itemId] = instance;
              itemInstances.push(instance);
            } else {
              itemInstances.push(itemInstancesMap[item.itemId]);
            }
          }
          rebuildScheduled = false;
        };
        const eachFeature = (fn) => {
          for (const feature of additionalFeatures) {
            fn(feature);
          }
        };
        const mainFeature = {
          key: "main",
          treeInstance: {
            getState: () => state,
            setState: ({}, updater) => {
              var _a2;
              (_a2 = config.setState) == null ? void 0 : _a2.call(config, state);
            },
            setMounted: ({}, isMounted) => {
              var _a2;
              const ref = treeDataRef.current;
              ref.isMounted = isMounted;
              if (isMounted) {
                (_a2 = ref.waitingForMount) == null ? void 0 : _a2.forEach((cb) => cb());
                ref.waitingForMount = [];
              }
            },
            applySubStateUpdate: ({}, stateName, updater) => {
              var _a2;
              const apply = () => {
                state[stateName] = typeof updater === "function" ? updater(state[stateName]) : updater;
                const externalStateSetter = config[stateHandlerNames[stateName]];
                externalStateSetter == null ? void 0 : externalStateSetter(state[stateName]);
              };
              const ref = treeDataRef.current;
              if (ref.isMounted) {
                apply();
              } else {
                (_a2 = ref.waitingForMount) != null ? _a2 : ref.waitingForMount = [];
                ref.waitingForMount.push(apply);
              }
            },
            // TODO rebuildSubTree: (itemId: string) => void;
            rebuildTree: () => {
              var _a2, _b2;
              const ref = treeDataRef.current;
              if (ref.isMounted) {
                rebuildItemMeta();
                (_a2 = config.setState) == null ? void 0 : _a2.call(config, state);
              } else {
                (_b2 = ref.waitingForMount) != null ? _b2 : ref.waitingForMount = [];
                ref.waitingForMount.push(() => {
                  var _a3;
                  rebuildItemMeta();
                  (_a3 = config.setState) == null ? void 0 : _a3.call(config, state);
                });
              }
            },
            scheduleRebuildTree: () => {
              rebuildScheduled = true;
            },
            getConfig: () => config,
            setConfig: (_, updater) => {
              var _a2, _b2, _c2;
              const newConfig = typeof updater === "function" ? updater(config) : updater;
              const hasChangedExpandedItems = ((_a2 = newConfig.state) == null ? void 0 : _a2.expandedItems) && ((_b2 = newConfig.state) == null ? void 0 : _b2.expandedItems) !== state.expandedItems;
              config = newConfig;
              if (newConfig.state) {
                state = __spreadValues(__spreadValues({}, state), newConfig.state);
              }
              if (hasChangedExpandedItems) {
                rebuildItemMeta();
                (_c2 = config.setState) == null ? void 0 : _c2.call(config, state);
              }
            },
            getItemInstance: ({}, itemId) => {
              const existingInstance = itemInstancesMap[itemId];
              if (!existingInstance) {
                const [instance, finalizeInstance] = buildInstance(
                  features,
                  "itemInstance",
                  (instance2) => ({
                    item: instance2,
                    tree: treeInstance,
                    itemId
                  })
                );
                finalizeInstance();
                return instance;
              }
              return existingInstance;
            },
            getItems: () => {
              if (rebuildScheduled) rebuildItemMeta();
              return itemInstances;
            },
            registerElement: ({}, element) => {
              if (treeElement === element) {
                return;
              }
              if (treeElement && !element) {
                eachFeature(
                  (feature) => {
                    var _a2;
                    return (_a2 = feature.onTreeUnmount) == null ? void 0 : _a2.call(feature, treeInstance, treeElement);
                  }
                );
              } else if (!treeElement && element) {
                eachFeature(
                  (feature) => {
                    var _a2;
                    return (_a2 = feature.onTreeMount) == null ? void 0 : _a2.call(feature, treeInstance, element);
                  }
                );
              }
              treeElement = element;
            },
            getElement: () => treeElement,
            getDataRef: () => treeDataRef,
            getHotkeyPresets: () => hotkeyPresets
          },
          itemInstance: {
            registerElement: ({ itemId, item }, element) => {
              if (itemElementsMap[itemId] === element) {
                return;
              }
              const oldElement = itemElementsMap[itemId];
              if (oldElement && !element) {
                eachFeature(
                  (feature) => {
                    var _a2;
                    return (_a2 = feature.onItemUnmount) == null ? void 0 : _a2.call(feature, item, oldElement, treeInstance);
                  }
                );
              } else if (!oldElement && element) {
                eachFeature(
                  (feature) => {
                    var _a2;
                    return (_a2 = feature.onItemMount) == null ? void 0 : _a2.call(feature, item, element, treeInstance);
                  }
                );
              }
              itemElementsMap[itemId] = element;
            },
            getElement: ({ itemId }) => itemElementsMap[itemId],
            // eslint-disable-next-line no-return-assign
            getDataRef: ({ itemId }) => {
              var _a2;
              return (_a2 = itemDataRefs[itemId]) != null ? _a2 : itemDataRefs[itemId] = { current: {} };
            },
            getItemMeta: ({ itemId }) => {
              var _a2;
              return (_a2 = itemMetaMap[itemId]) != null ? _a2 : {
                itemId,
                parentId: null,
                level: -1,
                index: -1,
                posInSet: 0,
                setSize: 1
              };
            }
          }
        };
        features.unshift(mainFeature);
        for (const feature of features) {
          Object.assign(hotkeyPresets, (_d = feature.hotkeys) != null ? _d : {});
        }
        finalizeTree();
        return treeInstance;
      };
      resolveKeyCode = (event) => event.code !== "" && event.code !== "Unidentified" ? event.code : event.key;
      specialKeys = {
        letter: /^Key[A-Z]$/,
        letterornumber: /^(Key[A-Z]|Digit[0-9])$/,
        plus: /^(NumpadAdd|Plus)$/,
        minus: /^(NumpadSubtract|Minus)$/,
        control: /^(ControlLeft|ControlRight)$/,
        shift: /^(ShiftLeft|ShiftRight)$/,
        metaorcontrol: /^(MetaLeft|MetaRight|ControlLeft|ControlRight)$/,
        enter: /^(Enter|NumpadEnter)$/
      };
      modifierKeyCodes = /* @__PURE__ */ new Set([
        "MetaLeft",
        "MetaRight",
        "Meta",
        "ControlLeft",
        "ControlRight",
        "Control",
        "AltLeft",
        "AltRight",
        "Alt",
        "ShiftLeft",
        "ShiftRight",
        "Shift"
      ]);
      testHotkeyMatch = (pressedKeys, tree, hotkey) => {
        const supposedKeys = hotkey.hotkey.toLowerCase().split("+");
        const doKeysMatch = supposedKeys.every((key) => {
          if (key in specialKeys) {
            return [...pressedKeys].some(
              (pressedKey) => specialKeys[key].test(pressedKey)
            );
          }
          const pressedKeysLowerCase = [...pressedKeys].map(
            (pressedKey) => pressedKey.toLowerCase()
          );
          return pressedKeysLowerCase.includes(key.toLowerCase()) || pressedKeysLowerCase.includes(`key${key.toLowerCase()}`);
        });
        const isEnabled = !hotkey.isEnabled || hotkey.isEnabled(tree);
        return doKeysMatch && isEnabled && pressedKeys.size === supposedKeys.length;
      };
      findHotkeyMatch = (pressedKeys, tree, config1, config2) => {
        var _a;
        return (_a = Object.entries(__spreadValues(__spreadValues({}, config1), config2)).find(
          ([, hotkey]) => testHotkeyMatch(pressedKeys, tree, hotkey)
        )) == null ? void 0 : _a[0];
      };
      hotkeysCoreController = {
        clearPressedKeys: (dataRef) => {
          dataRef.current.pressedKeys = /* @__PURE__ */ new Set();
        },
        dispatchKeyDown: (tree, dataRef, eventLike, options = {}) => {
          var _a, _b, _c, _d, _e;
          const { isInputFocused = false, releaseAfterDispatch = false } = options;
          const { ignoreHotkeysOnInputs, onTreeHotkey, hotkeys } = tree.getConfig();
          if (isInputFocused && ignoreHotkeysOnInputs) {
            return;
          }
          const resolvedCode = resolveKeyCode({
            code: (_a = eventLike.code) != null ? _a : "",
            key: (_b = eventLike.key) != null ? _b : ""
          });
          (_d = (_c = dataRef.current).pressedKeys) != null ? _d : _c.pressedKeys = /* @__PURE__ */ new Set();
          const isNewKey = !dataRef.current.pressedKeys.has(resolvedCode);
          if (resolvedCode) {
            dataRef.current.pressedKeys.add(resolvedCode);
          }
          const hotkeyName = findHotkeyMatch(
            dataRef.current.pressedKeys,
            tree,
            tree.getHotkeyPresets(),
            hotkeys
          );
          if (releaseAfterDispatch && resolvedCode) {
            dataRef.current.pressedKeys.delete(resolvedCode);
          }
          if (!hotkeyName) {
            return;
          }
          const hotkeyConfig = __spreadValues(__spreadValues({}, tree.getHotkeyPresets()[hotkeyName]), hotkeys == null ? void 0 : hotkeys[hotkeyName]);
          if (!hotkeyConfig) {
            return;
          }
          if (!hotkeyConfig.allowWhenInputFocused && isInputFocused) {
            return;
          }
          if (!hotkeyConfig.canRepeat && !isNewKey) {
            return;
          }
          if (hotkeyConfig.preventDefault) {
            (_e = eventLike.preventDefault) == null ? void 0 : _e.call(eventLike);
          }
          hotkeyConfig.handler(eventLike, tree);
          onTreeHotkey == null ? void 0 : onTreeHotkey(hotkeyName, eventLike);
        },
        dispatchKeyUp: (dataRef, eventLike) => {
          var _a, _b, _c, _d;
          const resolvedCode = resolveKeyCode({
            code: (_a = eventLike.code) != null ? _a : "",
            key: (_b = eventLike.key) != null ? _b : ""
          });
          if (!resolvedCode) {
            return;
          }
          (_d = (_c = dataRef.current).pressedKeys) != null ? _d : _c.pressedKeys = /* @__PURE__ */ new Set();
          if (modifierKeyCodes.has(resolvedCode)) {
            dataRef.current.pressedKeys = new Set(
              [...dataRef.current.pressedKeys].filter(
                (pressedKey) => modifierKeyCodes.has(pressedKey)
              )
            );
          }
          dataRef.current.pressedKeys.delete(resolvedCode);
        }
      };
      hotkeysCoreFeature = {
        key: "hotkeys-core",
        onTreeMount: (tree, element) => {
          const data = tree.getDataRef();
          const keydown = (e) => {
            const isInputFocused = e.target instanceof HTMLInputElement;
            hotkeysCoreController.dispatchKeyDown(tree, data, e, {
              isInputFocused,
              releaseAfterDispatch: isInputFocused
            });
          };
          const keyup = (e) => {
            hotkeysCoreController.dispatchKeyUp(data, e);
          };
          const reset = () => {
            hotkeysCoreController.clearPressedKeys(data);
          };
          element.addEventListener("keydown", keydown);
          document.addEventListener("keyup", keyup);
          window.addEventListener("focus", reset);
          data.current.keydownHandler = keydown;
          data.current.keyupHandler = keyup;
          data.current.resetHandler = reset;
        },
        onTreeUnmount: (tree, element) => {
          const data = tree.getDataRef();
          if (data.current.keyupHandler) {
            document.removeEventListener("keyup", data.current.keyupHandler);
            delete data.current.keyupHandler;
          }
          if (data.current.keydownHandler) {
            element.removeEventListener("keydown", data.current.keydownHandler);
            delete data.current.keydownHandler;
          }
          if (data.current.resetHandler) {
            window.removeEventListener("focus", data.current.resetHandler);
            delete data.current.resetHandler;
          }
        }
      };
      undefErrorMessage = "sync dataLoader returned undefined";
      promiseErrorMessage = "sync dataLoader returned promise";
      unpromise = (data) => {
        if (!data) {
          throw throwError(undefErrorMessage);
        }
        if (typeof data === "object" && "then" in data) {
          throw throwError(promiseErrorMessage);
        }
        return data;
      };
      syncDataLoaderFeature = {
        key: "sync-data-loader",
        getInitialState: (initialState) => __spreadValues({
          loadingItemData: [],
          loadingItemChildrens: []
        }, initialState),
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          setLoadingItemData: makeStateUpdater("loadingItemData", tree),
          setLoadingItemChildrens: makeStateUpdater("loadingItemChildrens", tree)
        }, defaultConfig),
        stateHandlerNames: {
          loadingItemData: "setLoadingItemData",
          loadingItemChildrens: "setLoadingItemChildrens"
        },
        treeInstance: {
          waitForItemDataLoaded: () => __async(null, null, function* () {
          }),
          waitForItemChildrenLoaded: () => __async(null, null, function* () {
          }),
          retrieveItemData: ({ tree }, itemId) => {
            return unpromise(tree.getConfig().dataLoader.getItem(itemId));
          },
          retrieveChildrenIds: ({ tree }, itemId) => {
            const { dataLoader } = tree.getConfig();
            if ("getChildren" in dataLoader) {
              return unpromise(dataLoader.getChildren(itemId));
            }
            return unpromise(dataLoader.getChildrenWithData(itemId)).map(
              (c) => c.data
            );
          },
          loadItemData: ({ tree }, itemId) => tree.retrieveItemData(itemId),
          loadChildrenIds: ({ tree }, itemId) => tree.retrieveChildrenIds(itemId)
        },
        itemInstance: {
          isLoading: () => false,
          hasLoadedData: () => true
        }
      };
      isOrderedDragTarget = (dragTarget) => "childIndex" in dragTarget;
      canDrop = (dataTransfer, target, tree) => {
        var _a, _b, _c;
        const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
        const config = tree.getConfig();
        if (draggedItems && !((_c = (_b = config.canDrop) == null ? void 0 : _b.call(config, draggedItems, target)) != null ? _c : true)) {
          return false;
        }
        if (draggedItems && draggedItems.some(
          (draggedItem) => target.item.getId() === draggedItem.getId() || target.item.isDescendentOf(draggedItem.getId())
        )) {
          return false;
        }
        if (!draggedItems && dataTransfer && config.canDropForeignDragObject && !config.canDropForeignDragObject(dataTransfer, target)) {
          return false;
        }
        return true;
      };
      getItemDropCategory = (item) => {
        if (item.isExpanded()) {
          return 1;
        }
        const parent = item.getParent();
        if (parent && item.getIndexInParent() === item.getItemMeta().setSize - 1) {
          return 2;
        }
        return 0;
      };
      getInsertionIndex = (children, childIndex, draggedItems) => {
        var _a;
        const numberOfDragItemsBeforeTarget = (_a = children.slice(0, childIndex).reduce(
          (counter, child) => child && (draggedItems == null ? void 0 : draggedItems.some((i) => i.getId() === child.getId())) ? ++counter : counter,
          0
        )) != null ? _a : 0;
        return childIndex - numberOfDragItemsBeforeTarget;
      };
      getTargetPlacement = (e, item, tree, canMakeChild) => {
        var _a, _b, _c, _d, _e;
        const config = tree.getConfig();
        if (!config.canReorder) {
          return canMakeChild ? {
            type: 2
            /* MakeChild */
          } : {
            type: 1
            /* ReorderBelow */
          };
        }
        const bb = (_a = item.getElement()) == null ? void 0 : _a.getBoundingClientRect();
        const topPercent = bb ? (e.clientY - bb.top) / bb.height : 0.5;
        const leftPixels = bb ? e.clientX - bb.left : 0;
        const targetDropCategory = getItemDropCategory(item);
        const reorderAreaPercentage = !canMakeChild ? 0.5 : (_b = config.reorderAreaPercentage) != null ? _b : 0.3;
        const indent = (_c = config.indent) != null ? _c : 20;
        const makeChildType = canMakeChild ? 2 : 1;
        if (targetDropCategory === 1) {
          if (topPercent < reorderAreaPercentage) {
            return {
              type: 0
              /* ReorderAbove */
            };
          }
          return { type: makeChildType };
        }
        if (targetDropCategory === 2) {
          if (leftPixels < item.getItemMeta().level * indent) {
            if (topPercent < 0.5) {
              return {
                type: 0
                /* ReorderAbove */
              };
            }
            const minLevel = (_e = (_d = item.getItemBelow()) == null ? void 0 : _d.getItemMeta().level) != null ? _e : 0;
            return {
              type: 3,
              reparentLevel: Math.max(minLevel, Math.floor(leftPixels / indent))
            };
          }
        }
        if (topPercent < reorderAreaPercentage) {
          return {
            type: 0
            /* ReorderAbove */
          };
        }
        if (topPercent > 1 - reorderAreaPercentage) {
          return {
            type: 1
            /* ReorderBelow */
          };
        }
        return { type: makeChildType };
      };
      getDragCode = (item, placement) => {
        return [
          item.getId(),
          placement.type,
          placement.type === 3 ? placement.reparentLevel : 0
        ].join("__");
      };
      getNthParent = (item, n) => {
        if (n === item.getItemMeta().level) {
          return item;
        }
        return getNthParent(item.getParent(), n);
      };
      getReparentTarget = (item, reparentLevel, draggedItems) => {
        const itemMeta = item.getItemMeta();
        const reparentedTarget = getNthParent(item, reparentLevel - 1);
        const targetItemAbove = getNthParent(item, reparentLevel);
        const targetIndex = targetItemAbove.getIndexInParent() + 1;
        return {
          item: reparentedTarget,
          childIndex: targetIndex,
          insertionIndex: getInsertionIndex(
            reparentedTarget.getChildren(),
            targetIndex,
            draggedItems
          ),
          dragLineIndex: itemMeta.index + 1,
          dragLineLevel: reparentLevel
        };
      };
      getDragTarget = (e, item, tree, hasDataTransferPayload, canReorder = tree.getConfig().canReorder) => {
        var _a;
        const dataTransfer = hasDataTransferPayload ? e.dataTransfer : null;
        const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
        const itemMeta = item.getItemMeta();
        const parent = item.getParent();
        const itemTarget = { item };
        const parentTarget = parent ? { item: parent } : null;
        const canBecomeSibling = parentTarget && canDrop(dataTransfer, parentTarget, tree);
        const canMakeChild = canDrop(dataTransfer, itemTarget, tree);
        const placement = getTargetPlacement(e, item, tree, canMakeChild);
        if (!canReorder && parent && canBecomeSibling && placement.type !== 2) {
          if (draggedItems == null ? void 0 : draggedItems.some((item2) => item2.isDescendentOf(parent.getId()))) {
            return itemTarget;
          }
          return parentTarget;
        }
        if (placement.type === 2) {
          return itemTarget;
        }
        if (!canReorder && parent && !canBecomeSibling) {
          return getDragTarget(e, parent, tree, hasDataTransferPayload, false);
        }
        if (!parent) {
          return itemTarget;
        }
        if (!canBecomeSibling) {
          return getDragTarget(e, parent, tree, hasDataTransferPayload, false);
        }
        if (placement.type === 3) {
          return getReparentTarget(item, placement.reparentLevel, draggedItems);
        }
        const maybeAddOneForBelow = placement.type === 0 ? 0 : 1;
        const childIndex = item.getIndexInParent() + maybeAddOneForBelow;
        return {
          item: parent,
          dragLineIndex: itemMeta.index + maybeAddOneForBelow,
          dragLineLevel: itemMeta.level,
          childIndex,
          // TODO performance could be improved by computing this only when dragcode changed
          insertionIndex: getInsertionIndex(
            parent.getChildren(),
            childIndex,
            draggedItems
          )
        };
      };
      handleAutoOpenFolder = (dataRef, tree, item, placement) => {
        const { openOnDropDelay } = tree.getConfig();
        const dragCode = dataRef.current.lastDragCode;
        if (!openOnDropDelay || !item.isFolder() || item.isExpanded() || placement.type !== 2) {
          return;
        }
        clearTimeout(dataRef.current.autoExpandTimeout);
        dataRef.current.autoExpandTimeout = setTimeout(() => {
          if (dragCode !== dataRef.current.lastDragCode || !dataRef.current.lastAllowDrop)
            return;
          item.expand();
        }, openOnDropDelay);
      };
      defaultCanDropForeignDragObject = () => false;
      dragAndDropFeature = {
        key: "drag-and-drop",
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          canDrop: (_, target) => target.item.isFolder(),
          canDropForeignDragObject: defaultCanDropForeignDragObject,
          canDragForeignDragObjectOver: defaultConfig.canDropForeignDragObject !== defaultCanDropForeignDragObject ? (dataTransfer) => dataTransfer.effectAllowed !== "none" : () => false,
          setDndState: makeStateUpdater("dnd", tree),
          canReorder: true,
          openOnDropDelay: 800,
          draggedItemOverwritesSelection: true
        }, defaultConfig),
        stateHandlerNames: {
          dnd: "setDndState"
        },
        onTreeMount: (tree) => {
          const listener = () => {
            tree.applySubStateUpdate("dnd", null);
          };
          tree.getDataRef().current.windowDragEndListener = listener;
          window.addEventListener("dragend", listener);
        },
        onTreeUnmount: (tree) => {
          const { windowDragEndListener } = tree.getDataRef().current;
          if (!windowDragEndListener) return;
          window.removeEventListener("dragend", windowDragEndListener);
        },
        treeInstance: {
          getDragTarget: ({ tree }) => {
            var _a, _b;
            return (_b = (_a = tree.getState().dnd) == null ? void 0 : _a.dragTarget) != null ? _b : null;
          },
          getDragLineData: ({ tree }) => {
            var _a, _b, _c, _d, _e, _f;
            const target = tree.getDragTarget();
            const indent = ((_a = target == null ? void 0 : target.item.getItemMeta().level) != null ? _a : 0) + 1;
            const treeBb = (_b = tree.getElement()) == null ? void 0 : _b.getBoundingClientRect();
            if (!target || !treeBb || !isOrderedDragTarget(target)) return null;
            const leftOffset = target.dragLineLevel * ((_c = tree.getConfig().indent) != null ? _c : 1);
            const targetItem = tree.getItems()[target.dragLineIndex];
            if (!targetItem) {
              const bb2 = (_e = (_d = tree.getItems()[target.dragLineIndex - 1]) == null ? void 0 : _d.getElement()) == null ? void 0 : _e.getBoundingClientRect();
              if (bb2) {
                return {
                  indent,
                  top: bb2.bottom - treeBb.top,
                  left: bb2.left + leftOffset - treeBb.left,
                  width: bb2.width - leftOffset
                };
              }
            }
            const bb = (_f = targetItem == null ? void 0 : targetItem.getElement()) == null ? void 0 : _f.getBoundingClientRect();
            if (bb) {
              return {
                indent,
                top: bb.top - treeBb.top,
                left: bb.left + leftOffset - treeBb.left,
                width: bb.width - leftOffset
              };
            }
            return null;
          },
          getDragLineStyle: ({ tree }, topOffset = -1, leftOffset = -8) => {
            const dragLine = tree.getDragLineData();
            return dragLine ? {
              position: "absolute",
              top: `${dragLine.top + topOffset}px`,
              left: `${dragLine.left + leftOffset}px`,
              width: `${dragLine.width - leftOffset}px`,
              pointerEvents: "none"
              // important to prevent capturing drag events
            } : { display: "none" };
          },
          getContainerProps: ({ prev, tree }, treeLabel) => {
            const prevProps = prev == null ? void 0 : prev(treeLabel);
            return __spreadProps(__spreadValues({}, prevProps), {
              onDragOver: (e) => {
                e.preventDefault();
              },
              onDrop: (e) => __async(null, null, function* () {
                var _a, _b, _c;
                const dataRef = tree.getDataRef();
                const target = { item: tree.getRootItem() };
                if (!canDrop(e.dataTransfer, target, tree)) {
                  return;
                }
                e.preventDefault();
                const config = tree.getConfig();
                const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
                dataRef.current.lastDragCode = void 0;
                if (draggedItems) {
                  yield (_b = config.onDrop) == null ? void 0 : _b.call(config, draggedItems, target);
                } else if (e.dataTransfer) {
                  yield (_c = config.onDropForeignDragObject) == null ? void 0 : _c.call(config, e.dataTransfer, target);
                }
              }),
              style: __spreadProps(__spreadValues({}, prevProps == null ? void 0 : prevProps.style), {
                position: "relative"
              })
            });
          }
        },
        itemInstance: {
          getProps: ({ tree, item, prev }) => __spreadProps(__spreadValues(__spreadValues({}, prev == null ? void 0 : prev()), tree.getConfig().seperateDragHandle ? {} : item.getDragHandleProps()), {
            onDragEnter: (e) => e.preventDefault(),
            onDragOver: (e) => {
              var _a, _b, _c;
              e.stopPropagation();
              const dataRef = tree.getDataRef();
              const placement = getTargetPlacement(e, item, tree, true);
              const nextDragCode = getDragCode(item, placement);
              if (nextDragCode === dataRef.current.lastDragCode) {
                if (dataRef.current.lastAllowDrop) {
                  e.preventDefault();
                }
                return;
              }
              dataRef.current.lastDragCode = nextDragCode;
              dataRef.current.lastDragEnter = Date.now();
              handleAutoOpenFolder(dataRef, tree, item, placement);
              const target = getDragTarget(e, item, tree, false);
              if (!((_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems) && (!e.dataTransfer || !((_c = (_b = tree.getConfig()).canDragForeignDragObjectOver) == null ? void 0 : _c.call(_b, e.dataTransfer, target)))) {
                dataRef.current.lastAllowDrop = false;
                return;
              }
              if (!canDrop(null, target, tree)) {
                dataRef.current.lastAllowDrop = false;
                return;
              }
              tree.applySubStateUpdate("dnd", (state) => __spreadProps(__spreadValues({}, state), {
                dragTarget: target,
                draggingOverItem: item
              }));
              dataRef.current.lastAllowDrop = true;
              e.preventDefault();
            },
            onDragLeave: () => {
              setTimeout(() => {
                var _a;
                const dataRef = tree.getDataRef();
                if (((_a = dataRef.current.lastDragEnter) != null ? _a : 0) + 100 >= Date.now()) return;
                dataRef.current.lastDragCode = "no-drag";
                tree.applySubStateUpdate("dnd", (state) => __spreadProps(__spreadValues({}, state), {
                  draggingOverItem: void 0,
                  dragTarget: void 0
                }));
              }, 100);
            },
            onDrop: (e) => __async(null, null, function* () {
              var _a, _b, _c;
              e.stopPropagation();
              const dataRef = tree.getDataRef();
              const target = getDragTarget(e, item, tree, true);
              const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
              const isValidDrop = canDrop(e.dataTransfer, target, tree);
              tree.applySubStateUpdate("dnd", {
                draggedItems: void 0,
                draggingOverItem: void 0,
                dragTarget: void 0
              });
              if (!isValidDrop) {
                return;
              }
              e.preventDefault();
              const config = tree.getConfig();
              dataRef.current.lastDragCode = void 0;
              if (draggedItems) {
                yield (_b = config.onDrop) == null ? void 0 : _b.call(config, draggedItems, target);
                draggedItems[0].setFocused();
              } else if (e.dataTransfer) {
                yield (_c = config.onDropForeignDragObject) == null ? void 0 : _c.call(config, e.dataTransfer, target);
              }
              tree.applySubStateUpdate("dnd", null);
              tree.updateDomFocus();
            })
          }),
          getDragHandleProps: ({ tree, item, prev }) => __spreadProps(__spreadValues({}, prev == null ? void 0 : prev()), {
            draggable: true,
            onDragStart: (e) => {
              var _a, _b, _c, _d;
              const { draggedItemOverwritesSelection } = tree.getConfig();
              const selectedItems = tree.getSelectedItems ? tree.getSelectedItems() : [tree.getFocusedItem()];
              const overwriteSelection = !selectedItems.includes(item) && draggedItemOverwritesSelection;
              const items = overwriteSelection ? [item] : selectedItems;
              const config = tree.getConfig();
              if (overwriteSelection) {
                (_a = tree.setSelectedItems) == null ? void 0 : _a.call(tree, [item.getItemMeta().itemId]);
              }
              if (!((_c = (_b = config.canDrag) == null ? void 0 : _b.call(config, items)) != null ? _c : true)) {
                e.preventDefault();
                return;
              }
              if (config.setDragImage) {
                const { imgElement, xOffset, yOffset } = config.setDragImage(items);
                (_d = e.dataTransfer) == null ? void 0 : _d.setDragImage(imgElement, xOffset != null ? xOffset : 0, yOffset != null ? yOffset : 0);
              }
              if (config.createForeignDragObject && e.dataTransfer) {
                const { format, data, dropEffect, effectAllowed } = config.createForeignDragObject(items);
                e.dataTransfer.setData(format, data);
                if (dropEffect) e.dataTransfer.dropEffect = dropEffect;
                if (effectAllowed) e.dataTransfer.effectAllowed = effectAllowed;
              }
              tree.applySubStateUpdate("dnd", {
                draggedItems: items,
                draggingOverItem: tree.getFocusedItem()
              });
            },
            onDragEnd: (e) => {
              var _a, _b;
              const { onCompleteForeignDrop, canDragForeignDragObjectOver } = tree.getConfig();
              const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
              if (((_b = e.dataTransfer) == null ? void 0 : _b.dropEffect) === "none" || !draggedItems) {
                return;
              }
              const target = getDragTarget(e, item, tree, false);
              if (canDragForeignDragObjectOver && e.dataTransfer && !canDragForeignDragObjectOver(e.dataTransfer, target)) {
                return;
              }
              onCompleteForeignDrop == null ? void 0 : onCompleteForeignDrop(draggedItems);
            }
          }),
          isDragTarget: ({ tree, item }) => {
            const target = tree.getDragTarget();
            return target ? target.item.getId() === item.getId() : false;
          },
          isUnorderedDragTarget: ({ tree, item }) => {
            const target = tree.getDragTarget();
            return target ? !isOrderedDragTarget(target) && target.item.getId() === item.getId() : false;
          },
          isDragTargetAbove: ({ tree, item }) => {
            const target = tree.getDragTarget();
            if (!target || !isOrderedDragTarget(target) || target.item !== item.getParent())
              return false;
            return target.childIndex === item.getItemMeta().posInSet;
          },
          isDragTargetBelow: ({ tree, item }) => {
            const target = tree.getDragTarget();
            if (!target || !isOrderedDragTarget(target) || target.item !== item.getParent())
              return false;
            return target.childIndex - 1 === item.getItemMeta().posInSet;
          },
          isDraggingOver: ({ tree, item }) => {
            var _a, _b;
            return ((_b = (_a = tree.getState().dnd) == null ? void 0 : _a.draggingOverItem) == null ? void 0 : _b.getId()) === item.getId();
          }
        }
      };
      getNextDragTarget = (tree, isUp, dragTarget) => {
        var _a, _b, _c, _d;
        const direction = isUp ? 0 : 1;
        const draggedItems = (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems;
        if (isOrderedDragTarget(dragTarget)) {
          const parent = dragTarget.item.getParent();
          const targetedItem = tree.getItems()[dragTarget.dragLineIndex - 1];
          const targetCategory = targetedItem ? getItemDropCategory(targetedItem) : 0;
          const maxLevel = (_b = targetedItem == null ? void 0 : targetedItem.getItemMeta().level) != null ? _b : 0;
          const minLevel = (_d = (_c = targetedItem == null ? void 0 : targetedItem.getItemBelow()) == null ? void 0 : _c.getItemMeta().level) != null ? _d : 0;
          if (targetCategory === 2) {
            if (isUp && dragTarget.dragLineLevel < maxLevel) {
              return getReparentTarget(
                targetedItem,
                dragTarget.dragLineLevel + 1,
                draggedItems
              );
            }
            if (!isUp && dragTarget.dragLineLevel > minLevel && parent) {
              return getReparentTarget(
                targetedItem,
                dragTarget.dragLineLevel - 1,
                draggedItems
              );
            }
          }
          const newIndex = dragTarget.dragLineIndex - 1 + direction;
          const item = tree.getItems()[newIndex];
          return item ? { item } : void 0;
        }
        const targetingExpandedFolder = getItemDropCategory(dragTarget.item) === 1;
        if (targetingExpandedFolder && !isUp) {
          return {
            item: dragTarget.item,
            childIndex: 0,
            insertionIndex: getInsertionIndex(
              dragTarget.item.getChildren(),
              0,
              draggedItems
            ),
            dragLineIndex: dragTarget.item.getItemMeta().index + direction,
            dragLineLevel: dragTarget.item.getItemMeta().level + 1
          };
        }
        const childIndex = dragTarget.item.getIndexInParent() + direction;
        return {
          item: dragTarget.item.getParent(),
          childIndex,
          insertionIndex: getInsertionIndex(
            dragTarget.item.getParent().getChildren(),
            childIndex,
            draggedItems
          ),
          dragLineIndex: dragTarget.item.getItemMeta().index + direction,
          dragLineLevel: dragTarget.item.getItemMeta().level
        };
      };
      getNextValidDragTarget = (tree, isUp, previousTarget = ((_a) => (_a = tree.getState().dnd) == null ? void 0 : _a.dragTarget)()) => {
        var _a2;
        if (!previousTarget) return void 0;
        const nextTarget = getNextDragTarget(tree, isUp, previousTarget);
        const dataTransfer = (_a2 = tree.getDataRef().current.kDndDataTransfer) != null ? _a2 : null;
        if (!nextTarget) return void 0;
        if (canDrop(dataTransfer, nextTarget, tree)) {
          return nextTarget;
        }
        return getNextValidDragTarget(tree, isUp, nextTarget);
      };
      updateScroll = (tree) => {
        const state = tree.getState().dnd;
        if (!(state == null ? void 0 : state.dragTarget) || isOrderedDragTarget(state.dragTarget)) return;
        state.dragTarget.item.scrollTo({ block: "nearest", inline: "nearest" });
      };
      initiateDrag = (tree, draggedItems, dataTransfer) => {
        var _a, _b;
        const focusedItem = tree.getFocusedItem();
        const { canDrag } = tree.getConfig();
        if (draggedItems && canDrag && !canDrag(draggedItems)) {
          return;
        }
        if (draggedItems) {
          tree.applySubStateUpdate("dnd", { draggedItems });
          (_b = (_a = tree.getConfig()).onStartKeyboardDrag) == null ? void 0 : _b.call(_a, draggedItems);
        } else if (dataTransfer) {
          tree.getDataRef().current.kDndDataTransfer = dataTransfer;
        }
        const dragTarget = getNextValidDragTarget(tree, false, {
          item: focusedItem
        });
        if (!dragTarget) return;
        tree.applySubStateUpdate("dnd", {
          draggedItems,
          dragTarget
        });
        tree.applySubStateUpdate(
          "assistiveDndState",
          1
          /* Started */
        );
        updateScroll(tree);
      };
      moveDragPosition = (tree, isUp) => {
        var _a;
        const dragTarget = getNextValidDragTarget(tree, isUp);
        if (!dragTarget) return;
        tree.applySubStateUpdate("dnd", {
          draggedItems: (_a = tree.getState().dnd) == null ? void 0 : _a.draggedItems,
          dragTarget
        });
        tree.applySubStateUpdate(
          "assistiveDndState",
          2
          /* Dragging */
        );
        if (!isOrderedDragTarget(dragTarget)) {
          dragTarget.item.setFocused();
        }
        updateScroll(tree);
      };
      keyboardDragAndDropFeature = {
        key: "keyboard-drag-and-drop",
        deps: ["drag-and-drop"],
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          setAssistiveDndState: makeStateUpdater("assistiveDndState", tree)
        }, defaultConfig),
        stateHandlerNames: {
          assistiveDndState: "setAssistiveDndState"
        },
        treeInstance: {
          startKeyboardDrag: ({ tree }, draggedItems) => {
            initiateDrag(tree, draggedItems, void 0);
          },
          startKeyboardDragOnForeignObject: ({ tree }, dataTransfer) => {
            initiateDrag(tree, void 0, dataTransfer);
          },
          stopKeyboardDrag: ({ tree }) => {
            tree.getDataRef().current.kDndDataTransfer = void 0;
            tree.applySubStateUpdate("dnd", null);
            tree.applySubStateUpdate(
              "assistiveDndState",
              0
              /* None */
            );
          }
        },
        hotkeys: {
          startDrag: {
            hotkey: "Control+Shift+KeyD",
            preventDefault: true,
            isEnabled: (tree) => !tree.getState().dnd,
            handler: (_, tree) => {
              var _a, _b;
              const selectedItems = (_b = (_a = tree.getSelectedItems) == null ? void 0 : _a.call(tree)) != null ? _b : [
                tree.getFocusedItem()
              ];
              const focusedItem = tree.getFocusedItem();
              tree.startKeyboardDrag(
                selectedItems.includes(focusedItem) ? selectedItems : selectedItems.concat(focusedItem)
              );
            }
          },
          dragUp: {
            hotkey: "ArrowUp",
            preventDefault: true,
            isEnabled: (tree) => !!tree.getState().dnd,
            handler: (_, tree) => {
              moveDragPosition(tree, true);
            }
          },
          dragDown: {
            hotkey: "ArrowDown",
            preventDefault: true,
            isEnabled: (tree) => !!tree.getState().dnd,
            handler: (_, tree) => {
              moveDragPosition(tree, false);
            }
          },
          cancelDrag: {
            hotkey: "Escape",
            isEnabled: (tree) => !!tree.getState().dnd,
            handler: (_, tree) => {
              tree.stopKeyboardDrag();
            }
          },
          completeDrag: {
            hotkey: "Enter",
            preventDefault: true,
            isEnabled: (tree) => !!tree.getState().dnd,
            handler: (e, tree) => __async(null, null, function* () {
              var _a, _b, _c, _d;
              e.stopPropagation();
              const dataRef = tree.getDataRef();
              const target = tree.getDragTarget();
              const dataTransfer = (_a = dataRef.current.kDndDataTransfer) != null ? _a : null;
              if (!target || !canDrop(dataTransfer, target, tree)) {
                return;
              }
              const config = tree.getConfig();
              const draggedItems = (_b = tree.getState().dnd) == null ? void 0 : _b.draggedItems;
              dataRef.current.lastDragCode = void 0;
              tree.applySubStateUpdate("dnd", null);
              if (draggedItems) {
                yield (_c = config.onDrop) == null ? void 0 : _c.call(config, draggedItems, target);
                tree.getItemInstance(draggedItems[0].getId()).setFocused();
              } else if (dataTransfer) {
                yield (_d = config.onDropForeignDragObject) == null ? void 0 : _d.call(config, dataTransfer, target);
              }
              tree.updateDomFocus();
              tree.applySubStateUpdate(
                "assistiveDndState",
                3
                /* Completed */
              );
            })
          }
        }
      };
      searchFeature = {
        key: "search",
        getInitialState: (initialState) => __spreadValues({
          search: null
        }, initialState),
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          setSearch: makeStateUpdater("search", tree),
          isSearchMatchingItem: (search, item) => search.length > 0 && item.getItemName().toLowerCase().includes(search.toLowerCase())
        }, defaultConfig),
        stateHandlerNames: {
          search: "setSearch"
        },
        treeInstance: {
          setSearch: ({ tree }, search) => {
            var _a;
            tree.applySubStateUpdate("search", search);
            (_a = tree.getItems().find(
              (item) => {
                var _a2, _b;
                return (_b = (_a2 = tree.getConfig()).isSearchMatchingItem) == null ? void 0 : _b.call(_a2, tree.getSearchValue(), item);
              }
            )) == null ? void 0 : _a.setFocused();
          },
          openSearch: ({ tree }, initialValue = "") => {
            var _a, _b;
            tree.setSearch(initialValue);
            (_b = (_a = tree.getConfig()).onOpenSearch) == null ? void 0 : _b.call(_a);
            setTimeout(() => {
              var _a2;
              (_a2 = tree.getDataRef().current.searchInput) == null ? void 0 : _a2.focus();
            });
          },
          closeSearch: ({ tree }) => {
            var _a, _b;
            tree.setSearch(null);
            (_b = (_a = tree.getConfig()).onCloseSearch) == null ? void 0 : _b.call(_a);
            tree.updateDomFocus();
          },
          isSearchOpen: ({ tree }) => tree.getState().search !== null,
          getSearchValue: ({ tree }) => tree.getState().search || "",
          registerSearchInputElement: ({ tree }, element) => {
            const dataRef = tree.getDataRef();
            dataRef.current.searchInput = element;
            if (element && dataRef.current.keydownHandler) {
              element.addEventListener("keydown", dataRef.current.keydownHandler);
            }
          },
          getSearchInputElement: ({ tree }) => {
            var _a;
            return (_a = tree.getDataRef().current.searchInput) != null ? _a : null;
          },
          // TODO memoize with propMemoizationFeature
          getSearchInputElementProps: ({ tree }) => ({
            value: tree.getSearchValue(),
            onChange: (e) => tree.setSearch(e.target.value),
            onBlur: () => tree.closeSearch(),
            ref: tree.registerSearchInputElement
          }),
          getSearchMatchingItems: memo(
            ({ tree }) => [
              tree.getSearchValue(),
              tree.getItems(),
              tree.getConfig().isSearchMatchingItem
            ],
            (search, items, isSearchMatchingItem) => items.filter((item) => search && (isSearchMatchingItem == null ? void 0 : isSearchMatchingItem(search, item)))
          )
        },
        itemInstance: {
          isMatchingSearch: ({ tree, item }) => tree.getSearchMatchingItems().some((i) => i.getId() === item.getId())
        },
        hotkeys: {
          openSearch: {
            hotkey: "LetterOrNumber",
            preventDefault: true,
            // TODO make true default
            isEnabled: (tree) => !tree.isSearchOpen(),
            handler: (e, tree) => {
              e.stopPropagation();
              tree.openSearch(e.key);
            }
          },
          closeSearch: {
            // TODO allow multiple, i.e. Enter
            hotkey: "Escape",
            allowWhenInputFocused: true,
            isEnabled: (tree) => tree.isSearchOpen(),
            handler: (e, tree) => {
              tree.closeSearch();
            }
          },
          submitSearch: {
            hotkey: "Enter",
            allowWhenInputFocused: true,
            isEnabled: (tree) => tree.isSearchOpen(),
            handler: (e, tree) => {
              tree.closeSearch();
              tree.setSelectedItems([tree.getFocusedItem().getId()]);
            }
          },
          nextSearchItem: {
            hotkey: "ArrowDown",
            allowWhenInputFocused: true,
            canRepeat: true,
            isEnabled: (tree) => tree.isSearchOpen(),
            handler: (e, tree) => {
              const focusItem = tree.getSearchMatchingItems().find(
                (item) => item.getItemMeta().index > tree.getFocusedItem().getItemMeta().index
              );
              focusItem == null ? void 0 : focusItem.setFocused();
              focusItem == null ? void 0 : focusItem.scrollTo({ block: "nearest", inline: "nearest" });
            }
          },
          previousSearchItem: {
            hotkey: "ArrowUp",
            allowWhenInputFocused: true,
            canRepeat: true,
            isEnabled: (tree) => tree.isSearchOpen(),
            handler: (e, tree) => {
              const focusItem = [...tree.getSearchMatchingItems()].reverse().find(
                (item) => item.getItemMeta().index < tree.getFocusedItem().getItemMeta().index
              );
              focusItem == null ? void 0 : focusItem.setFocused();
              focusItem == null ? void 0 : focusItem.scrollTo({ block: "nearest", inline: "nearest" });
            }
          }
        }
      };
      renamingFeature = {
        key: "renaming",
        overwrites: ["drag-and-drop"],
        getDefaultConfig: (defaultConfig, tree) => __spreadValues({
          setRenamingItem: makeStateUpdater("renamingItem", tree),
          setRenamingValue: makeStateUpdater("renamingValue", tree),
          canRename: () => true
        }, defaultConfig),
        stateHandlerNames: {
          renamingItem: "setRenamingItem",
          renamingValue: "setRenamingValue"
        },
        treeInstance: {
          getRenamingItem: ({ tree }) => {
            const itemId = tree.getState().renamingItem;
            return itemId ? tree.getItemInstance(itemId) : null;
          },
          getRenamingValue: ({ tree }) => tree.getState().renamingValue || "",
          abortRenaming: ({ tree }) => {
            tree.applySubStateUpdate("renamingItem", null);
            tree.updateDomFocus();
          },
          completeRenaming: ({ tree }) => {
            var _a;
            const config = tree.getConfig();
            const item = tree.getRenamingItem();
            if (item) {
              (_a = config.onRename) == null ? void 0 : _a.call(config, item, tree.getState().renamingValue || "");
            }
            tree.applySubStateUpdate("renamingItem", null);
            tree.updateDomFocus();
          },
          isRenamingItem: ({ tree }) => !!tree.getState().renamingItem
        },
        itemInstance: {
          startRenaming: ({ tree, item, itemId }) => {
            if (!item.canRename()) {
              return;
            }
            tree.applySubStateUpdate("renamingItem", itemId);
            tree.applySubStateUpdate("renamingValue", item.getItemName());
          },
          getRenameInputProps: ({ tree }) => ({
            ref: (r) => r == null ? void 0 : r.focus(),
            onBlur: () => tree.abortRenaming(),
            value: tree.getRenamingValue(),
            onChange: (e) => {
              var _a;
              tree.applySubStateUpdate("renamingValue", (_a = e.target) == null ? void 0 : _a.value);
            }
          }),
          canRename: ({ tree, item }) => {
            var _a, _b, _c;
            return (_c = (_b = (_a = tree.getConfig()).canRename) == null ? void 0 : _b.call(_a, item)) != null ? _c : true;
          },
          isRenaming: ({ tree, item }) => item.getId() === tree.getState().renamingItem,
          getProps: ({ prev, item }) => {
            var _a;
            const isRenaming = item.isRenaming();
            const prevProps = (_a = prev == null ? void 0 : prev()) != null ? _a : {};
            return isRenaming ? __spreadProps(__spreadValues({}, prevProps), {
              draggable: false,
              onDragStart: () => {
              }
            }) : prevProps;
          }
        },
        hotkeys: {
          renameItem: {
            hotkey: "F2",
            handler: (e, tree) => {
              tree.getFocusedItem().startRenaming();
            }
          },
          abortRenaming: {
            hotkey: "Escape",
            allowWhenInputFocused: true,
            isEnabled: (tree) => tree.isRenamingItem(),
            handler: (e, tree) => {
              tree.abortRenaming();
            }
          },
          completeRenaming: {
            hotkey: "Enter",
            allowWhenInputFocused: true,
            isEnabled: (tree) => tree.isRenamingItem(),
            handler: (e, tree) => {
              tree.completeRenaming();
            }
          }
        }
      };
      removeItemsFromParents = (movedItems, onChangeChildren) => __async(null, null, function* () {
        const movedItemsIds = movedItems.map((item) => item.getId());
        const uniqueParents = [
          ...new Set(movedItems.map((item) => item.getParent()))
        ];
        for (const parent of uniqueParents) {
          const siblings = parent == null ? void 0 : parent.getChildren();
          if (siblings && parent) {
            const newChildren = siblings.filter((sibling) => !movedItemsIds.includes(sibling.getId())).map((i) => i.getId());
            yield onChangeChildren(parent, newChildren);
            if (parent && "updateCachedChildrenIds" in parent) {
              parent == null ? void 0 : parent.updateCachedChildrenIds(newChildren);
            }
          }
        }
        movedItems[0].getTree().rebuildTree();
      });
      insertItemsAtTarget = (itemIds, target, onChangeChildren) => __async(null, null, function* () {
        yield target.item.getTree().waitForItemChildrenLoaded(target.item.getId());
        const oldChildrenIds = target.item.getTree().retrieveChildrenIds(target.item.getId());
        if (!("childIndex" in target)) {
          const newChildren2 = [...oldChildrenIds, ...itemIds];
          yield onChangeChildren(target.item, newChildren2);
          if (target.item && "updateCachedChildrenIds" in target.item) {
            target.item.updateCachedChildrenIds(newChildren2);
          }
          target.item.getTree().rebuildTree();
          return;
        }
        const newChildren = [
          ...oldChildrenIds.slice(0, target.insertionIndex),
          ...itemIds,
          ...oldChildrenIds.slice(target.insertionIndex)
        ];
        yield onChangeChildren(target.item, newChildren);
        if (target.item && "updateCachedChildrenIds" in target.item) {
          target.item.updateCachedChildrenIds(newChildren);
        }
        target.item.getTree().rebuildTree();
      });
      createOnDropHandler = (onChangeChildren) => (items, target) => __async(null, null, function* () {
        const itemIds = items.map((item) => item.getId());
        yield removeItemsFromParents(items, onChangeChildren);
        yield insertItemsAtTarget(itemIds, target, onChangeChildren);
      });
    }
  });

  // src/ace/static/js/codebook_headless_tree_source.js
  var require_codebook_headless_tree_source = __commonJS({
    "src/ace/static/js/codebook_headless_tree_source.js"() {
      init_dist();
      (function() {
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
        let searchRaw = "";
        let searchText = "";
        const TRANSPARENT_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
        const RESERVED_SINGLE_KEYS = /* @__PURE__ */ new Set(["q", "x", "z", "n", "v"]);
        function itemData(id) {
          return items[id];
        }
        function childrenOf(id) {
          return itemData(id)?.children ?? [];
        }
        function snapshotChildrenByParent() {
          const snapshot = {};
          Object.entries(items).forEach(function([id, item]) {
            if (Array.isArray(item.children)) snapshot[id] = [...item.children];
          });
          return snapshot;
        }
        function restoreChildrenByParent(snapshot) {
          if (!snapshot) return;
          Object.entries(snapshot).forEach(function([id, children]) {
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
          return Object.values(items).filter((item) => item.kind === "folder" && item.id !== ROOT_ID).map((item) => item.id);
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
          const codeIds = Object.values(items).filter((item) => item.kind === "code").sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)).map((item) => item.id);
          return codeIds.indexOf(itemId);
        }
        function itemMatchesSearch(id) {
          if (!searchText) return true;
          const item = itemData(id);
          if (!item) return false;
          if ((item.name || "").toLowerCase().includes(searchText)) return true;
          return childrenOf(id).some(itemMatchesSearch);
        }
        function visibleTreeItems() {
          const current = tree.getItems();
          if (!searchText) return current;
          return current.filter((item) => itemMatchesSearch(item.getId()));
        }
        function visibleCodeItems() {
          return visibleTreeItems().filter(function(item) {
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
          return Object.values(items).find(function(item) {
            return item.kind === kind && normalisedName(item.name) === target;
          }) || null;
        }
        function pathNamesFor(id) {
          const names = [];
          let current = id;
          const seen = /* @__PURE__ */ new Set();
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
          const seen = /* @__PURE__ */ new Set();
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
            data: draggedItems.map(function(item) {
              return item.getItemName?.() || "";
            }).filter(Boolean).join("\n"),
            dropEffect: "move",
            effectAllowed: "move"
          };
        }
        function dragTargetText(target) {
          if (!target) return "Choose a destination.";
          const targetName = target.item.getId() === ROOT_ID ? "the top level" : target.item.getItemName();
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
          setStatus("Saving");
          try {
            if (previousParent === nextParent) {
              await htmxSwap("POST", "/api/codes/reorder-in-scope", {
                code_ids: JSON.stringify(order),
                parent_id: formParentId(nextParent),
                current_index: currentIndex()
              });
            } else {
              await htmxSwap("PUT", `/api/codes/${id}/parent`, {
                parent_id: formParentId(nextParent),
                target_order_ids: JSON.stringify(order),
                current_index: currentIndex()
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
          queueMicrotask(function() {
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
        function formParentId(parentId) {
          return parentId && parentId !== ROOT_ID ? parentId : "";
        }
        async function htmxSwap(method, url, values) {
          if (!window.htmx || typeof window.htmx.ajax !== "function") {
            throw new Error("HTMX is unavailable");
          }
          return window.htmx.ajax(method, url, {
            target: "#text-panel",
            swap: "outerHTML",
            values
          });
        }
        async function htmxSidebarSwap(method, url, values) {
          if (!window.htmx || typeof window.htmx.ajax !== "function") {
            throw new Error("HTMX is unavailable");
          }
          return window.htmx.ajax(method, url, {
            target: "#code-sidebar",
            swap: "outerHTML",
            values
          });
        }
        function applyProps(element, props) {
          Object.entries(props).forEach(function([key, value]) {
            if (value === void 0 || value === null) return;
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
          changedDropScopes = /* @__PURE__ */ new Map();
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
            order
          });
          tree.rebuildTree();
          scheduleRender();
          await persistDrop(id, previousParent, nextParent, order, restoreSnapshot);
        }
        function canDrop2(draggedItems, target) {
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
          document.dispatchEvent(new CustomEvent("ace:apply-code", {
            detail: {
              codeId: item.getId(),
              codeName: data.name || ""
            }
          }));
        }
        function persistRename(item, name) {
          const next = name.trim();
          if (!next || next === item.getItemData().name) return;
          document.dispatchEvent(new CustomEvent("ace:rename-codebook-item", {
            detail: {
              itemId: item.getId(),
              name: next
            }
          }));
        }
        function deleteItem(item) {
          if (item.getId() === ROOT_ID) return;
          document.dispatchEvent(new CustomEvent("ace:delete-codebook-item", {
            detail: { itemId: item.getId() }
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
            current_index: currentIndex()
          }).then(function() {
            setStatus("");
          }).catch(function(error) {
            setStatus("Create failed");
            window.__aceHeadlessTreePreviewError = String(error && error.message || error);
          });
        }
        function createFolder(name) {
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
            current_index: currentIndex()
          }).then(function() {
            setStatus("");
          }).catch(function(error) {
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
          row.addEventListener("keydown", function(event) {
            if (event.key === "Enter") commit(event);
          });
          return row;
        }
        function rowForItem(item) {
          const data = item.getItemData();
          const row = document.createElement("div");
          const focusedId = tree.getFocusedItem?.()?.getId?.() || "";
          const focusedAncestors = focusedId ? ancestorIdsFor(focusedId) : /* @__PURE__ */ new Set();
          const dropReceiverId = dropReceiverFolderId();
          const itemProps = { ...item.getProps() };
          const defaultKeyDown = itemProps.onKeyDown;
          itemProps.onKeyDown = function(event) {
            if (event.key === "Enter" && data.kind === "code") {
              event.preventDefault();
              event.stopPropagation();
              applyCode(item);
              return;
            }
            if ((event.key === "Delete" || event.key === "Backspace") && item.getId() !== ROOT_ID) {
              event.preventDefault();
              event.stopPropagation();
              deleteItem(item);
              return;
            }
            if (typeof defaultKeyDown === "function") defaultKeyDown(event);
          };
          applyProps(row, itemProps);
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
          row.title = path.length > 1 ? `${data.kind === "folder" ? "Folder" : "Code"} path: ${path.join(" / ")}` : `${data.kind === "folder" ? "Folder" : "Code"} level ${level}`;
          row.style.setProperty("--ht-indent", `${Math.max(0, level - 1) * 14}px`);
          if (data.colour) row.style.setProperty("--row-colour", data.colour);
          if (item.isDragTargetAbove?.()) row.dataset.dropTarget = "above";
          if (item.isDragTargetBelow?.()) row.dataset.dropTarget = "below";
          if (item.isUnorderedDragTarget?.()) row.dataset.dropTarget = "inside";
          const toggle = document.createElement("span");
          toggle.className = "ace-ht-toggle";
          toggle.setAttribute("aria-hidden", "true");
          toggle.textContent = item.isFolder() ? item.isExpanded() ? "v" : ">" : "";
          row.append(toggle);
          if (item.isRenaming?.()) {
            let commitRename = function() {
              if (renameCommitted) return;
              renameCommitted = true;
              persistRename(item, input.value);
              tree.completeRenaming();
            };
            const input = document.createElement("input");
            input.className = "ace-ht-rename";
            input.setAttribute("aria-label", `Rename ${data.name}`);
            input.dataset.itemId = item.getId();
            const renameProps = { ...item.getRenameInputProps() };
            delete renameProps.onKeyDown;
            delete renameProps.onBlur;
            applyProps(input, renameProps);
            let renameCommitted = false;
            input.addEventListener("keydown", function(event) {
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
            input.addEventListener("blur", function() {
              commitRename();
            }, { once: true });
            row.append(input);
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
            const label2 = data.chord || keyLabel(codeRank(item.getId()));
            chip.textContent = label2;
            chip.setAttribute("aria-hidden", "true");
            chip.setAttribute(
              "title",
              data.chord ? `Press ; then ${data.chord} or Enter to apply ${data.name}` : label2 ? `Press ${label2} or Enter to apply ${data.name}` : `Apply ${data.name}`
            );
            chip.addEventListener("click", function(event) {
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
          if (!tree.getRenamingItem?.() && (!active || active === document.body || mount.contains(active))) {
            tree.getFocusedItem()?.getElement()?.focus({ preventScroll: true });
          }
        }
        function scheduleDragStateRender() {
          if (dragRenderQueued) return;
          dragRenderQueued = true;
          queueMicrotask(function() {
            dragRenderQueued = false;
            renderDragState();
          });
        }
        function renderDragState() {
          const mount = document.getElementById("ace-headless-tree-mount");
          if (!mount || !tree) return;
          const dropReceiverId = dropReceiverFolderId();
          mount.querySelectorAll(".ace-ht-row[data-item-id]").forEach(function(row) {
            row.classList.remove("ace-ht-row--drop-receiver");
            row.removeAttribute("data-drop-target");
          });
          visibleTreeItems().forEach(function(item) {
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
              focusedItem: childrenOf(ROOT_ID)[0]
            },
            getItemName: function(item) {
              return item.getItemData().name;
            },
            isItemFolder: function(item) {
              return item.getItemData().kind === "folder";
            },
            dataLoader: {
              getItem: function(id) {
                return itemData(id);
              },
              getChildren: function(id) {
                return childrenOf(id);
              }
            },
            indent: 14,
            reorderAreaPercentage: 0.3,
            setDragImage: tinyDragImage,
            createForeignDragObject: nativeDragPayload,
            canDrag: function(draggedItems) {
              return draggedItems.every(function(item) {
                return item.getId() !== ROOT_ID;
              });
            },
            canDrop: canDrop2,
            onDrop: handleDrop,
            onRename: function(item, value) {
              const next = value.trim();
              if (!next) return;
              items[item.getId()].name = next;
              tree.rebuildTree();
              scheduleRender();
            },
            setExpandedItems: scheduleRender,
            setFocusedItem: scheduleRender,
            setRenamingItem: scheduleRender,
            setRenamingValue: function() {
            },
            setDndState: scheduleDragStateRender,
            setAssistiveDndState: scheduleDragStateRender,
            features: [
              syncDataLoaderFeature,
              hotkeysCoreFeature,
              dragAndDropFeature,
              keyboardDragAndDropFeature,
              renamingFeature
            ]
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
            queueMicrotask(function() {
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
              current_index: currentIndex()
            }).then(function() {
              setStatus("");
            }).catch(function(error) {
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
            const item = visibleTreeItems().find(function(candidate) {
              return candidate.getItemData().kind === "code";
            });
            return item ? rowByItemId(item.getId()) : null;
          }
          function activeCodeItem() {
            const active = getActiveTreeItem();
            return active?.getAttribute("data-kind") === "code" ? active : null;
          }
          const api = {
            kind: "headless",
            refresh,
            rootElement,
            initSortable: function() {
            },
            restoreCollapseState: scheduleRender,
            toggleFolderCollapse,
            expandFolder,
            collapseFolder,
            getTreeItems,
            focusTreeItem,
            getActiveTreeItem,
            isFolderRow,
            containingGroupForItem: function() {
              return null;
            },
            parentFolderRow,
            isHiddenByCollapsedAncestor: function() {
              return false;
            },
            itemIdFromTreeElement: itemIdFromElement,
            directChildItemIds: function(container) {
              if (container === rootElement()) return [...childrenOf(ROOT_ID)];
              const id = itemIdFromElement(container);
              return id ? [...childrenOf(id)] : [];
            },
            firstChildOfFolderRow,
            moveItemInDirection,
            startRenaming,
            firstCodeItem,
            activeCodeItem
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
              get tree() {
                return tree;
              },
              get items() {
                return items;
              },
              get dropLog() {
                return dropLog;
              },
              getController: function() {
                return controller.refresh();
              },
              snapshot: function() {
                return {
                  rootChildren: [...childrenOf(ROOT_ID)],
                  visibleIds: visibleTreeItems().map(function(item) {
                    return item.getId();
                  }),
                  itemCount: Object.keys(items).length,
                  dropLog: dropLog.map(function(entry) {
                    return { ...entry };
                  })
                };
              }
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
          getController: function() {
            return controller.refresh();
          }
        };
        function initIfHeadlessTarget(target) {
          if (target?.id === "code-sidebar" || target?.querySelector?.("#ace-headless-tree-mount")) {
            init();
          }
        }
        document.addEventListener("htmx:afterSettle", function(event) {
          initIfHeadlessTarget(event.target);
        });
        document.addEventListener("htmx:oobAfterSwap", function(event) {
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
            const items2 = visibleTreeItems();
            const item = event.key === "ArrowDown" ? items2[0] : items2[items2.length - 1];
            if (!item) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            item.setFocused();
            scheduleRender();
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
        document.addEventListener("input", function(event) {
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
    }
  });
  return require_codebook_headless_tree_source();
})();
