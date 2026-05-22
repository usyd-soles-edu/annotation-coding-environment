var AceHeadlessTreeSpike = (() => {
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

  // spikes/headless-tree/spike.js
  var require_spike = __commonJS({
    "spikes/headless-tree/spike.js"() {
      init_dist();
      var ROOT_ID = "root";
      var ACE_ROWS = [
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
                  count: 3
                },
                {
                  id: "code-clarity",
                  name: "Clarification of content",
                  kind: "code",
                  colour: "#44AA99",
                  count: 1
                }
              ]
            },
            {
              id: "code-structure",
              name: "Suggestions about structure",
              kind: "code",
              colour: "#6C5CE7",
              count: 4
            }
          ]
        },
        {
          id: "code-literature",
          name: "Feedback on literature",
          kind: "code",
          colour: "#CC79A7",
          count: 2
        },
        {
          id: "code-draft",
          name: "To give feedback on draft",
          kind: "code",
          colour: "#66CDAA",
          count: 3
        }
      ];
      function itemsFromAceRows(rows) {
        const result = {
          [ROOT_ID]: {
            id: ROOT_ID,
            name: "Root",
            kind: "folder",
            children: []
          }
        };
        function visit(row, parentId) {
          const item = {
            id: row.id,
            name: row.name,
            kind: row.kind,
            colour: row.colour || "",
            chord: row.chord || "",
            count: row.count || 0
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
      function cloneChildrenByParent(items2) {
        const snapshot2 = {};
        Object.entries(items2).forEach(([id, item]) => {
          if (Array.isArray(item.children)) snapshot2[id] = [...item.children];
        });
        return snapshot2;
      }
      function arraysEqual(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b)) return false;
        if (a.length !== b.length) return false;
        return a.every((value, index) => value === b[index]);
      }
      var items = itemsFromAceRows(ACE_ROWS);
      var operations = [];
      var renderQueued = false;
      var tree;
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
            "]"
          ].join("");
        }
        if (operation.type === "reorder-scope") {
          return [
            "reorder-scope:",
            operation.parentId,
            ":[",
            operation.orderedIds.join(","),
            "]"
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
      var applyLibraryDrop = createOnDropHandler(onChangeChildren);
      async function handleDrop(draggedItems, target) {
        const draggedIds = draggedItems.map((item) => item.getId());
        const previousParents = new Map(
          draggedIds.map((id) => [id, findParentId(id)])
        );
        const previousChildren = cloneChildrenByParent(items);
        await applyLibraryDrop(draggedItems, target);
        const movedParentIds = /* @__PURE__ */ new Set();
        draggedIds.forEach((id) => {
          const oldParent = previousParents.get(id);
          const nextParent = findParentId(id);
          if (oldParent !== nextParent) {
            movedParentIds.add(id);
            recordOperation({
              type: "move-parent",
              itemId: id,
              parentId: apiParentId(nextParent),
              targetOrderIds: [...childrenOf(nextParent)]
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
            orderedIds: [...nextChildren]
          });
        });
        tree.rebuildTree();
        scheduleRender();
      }
      function canDrop2(draggedItems, target) {
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
        toggle.textContent = item.isFolder() ? item.isExpanded() ? "v" : ">" : "";
        row.append(toggle);
        if (item.isRenaming?.()) {
          let commitRename = function() {
            if (renameCommitted) return;
            renameCommitted = true;
            const next = input.value.trim();
            if (next) {
              items[item.getId()].name = next;
              recordOperation({
                type: "rename",
                itemId: item.getId(),
                name: next
              });
              tree.rebuildTree();
              scheduleRender();
            }
            tree.abortRenaming();
          };
          const input = document.createElement("input");
          input.className = "ace-spike-rename";
          input.setAttribute("aria-label", `Rename ${data.name}`);
          const renameProps = { ...item.getRenameInputProps() };
          delete renameProps.onKeyDown;
          delete renameProps.onBlur;
          applyProps(input, renameProps);
          let renameCommitted = false;
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
            focusedItem: "folder-positive"
          },
          getItemName: (item) => item.getItemData().name,
          isItemFolder: (item) => item.getItemData().kind === "folder",
          dataLoader: {
            getItem: (id) => itemData(id),
            getChildren: (id) => childrenOf(id)
          },
          indent: 18,
          canDrag: (draggedItems) => draggedItems.every((item) => item.getId() !== ROOT_ID),
          canDrop: canDrop2,
          onDrop: handleDrop,
          onRename: (item, value) => {
            if (items[item.getId()].name === value.trim()) return;
            const next = value.trim();
            if (!next) return;
            items[item.getId()].name = next;
            recordOperation({
              type: "rename",
              itemId: item.getId(),
              name: next
            });
            tree.rebuildTree();
            scheduleRender();
          },
          setExpandedItems: scheduleRender,
          setFocusedItem: scheduleRender,
          setRenamingItem: scheduleRender,
          setRenamingValue: () => {
          },
          setDndState: scheduleRender,
          setAssistiveDndState: scheduleRender,
          features: [
            syncDataLoaderFeature,
            hotkeysCoreFeature,
            dragAndDropFeature,
            keyboardDragAndDropFeature,
            renamingFeature
          ]
        });
      }
      async function moveLiteratureIntoSuggestions() {
        await handleDrop([tree.getItemInstance("code-literature")], {
          item: tree.getItemInstance("folder-suggestions")
        });
      }
      async function moveLiteratureToTopOfSuggestions() {
        await handleDrop([tree.getItemInstance("code-literature")], {
          item: tree.getItemInstance("folder-suggestions"),
          childIndex: 0,
          insertionIndex: 0,
          dragLineIndex: 0,
          dragLineLevel: 2
        });
      }
      async function moveDraftIntoPositiveMiddle() {
        await handleDrop([tree.getItemInstance("code-draft")], {
          item: tree.getItemInstance("folder-positive"),
          childIndex: 1,
          insertionIndex: 1,
          dragLineIndex: 1,
          dragLineLevel: 2
        });
      }
      function snapshot() {
        return {
          rootChildren: [...childrenOf(ROOT_ID)],
          positiveChildren: [...childrenOf("folder-positive")],
          suggestionsChildren: [...childrenOf("folder-suggestions")],
          operations: operations.map((operation) => ({ ...operation })),
          operationText: operations.map(formatOperation)
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
        document.getElementById("move-literature-into").addEventListener("click", moveLiteratureIntoSuggestions);
        document.getElementById("move-literature-top").addEventListener("click", moveLiteratureToTopOfSuggestions);
        document.getElementById("move-draft-middle").addEventListener("click", moveDraftIntoPositiveMiddle);
        window.__aceHeadlessTreeSpike = {
          tree,
          items,
          operations,
          itemsFromAceRows,
          moveDraftIntoPositiveMiddle,
          moveLiteratureIntoSuggestions,
          moveLiteratureToTopOfSuggestions,
          snapshot
        };
      }
      init();
    }
  });
  return require_spike();
})();
