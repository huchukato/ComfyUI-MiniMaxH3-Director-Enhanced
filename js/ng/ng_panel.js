// Live plan panel on the NG Director: chunks, notes and the prompt of every chunk, updated as widgets and wires change.
import { followNodeWidth } from "./ng_widgets.js";
import { ensureStyle } from "./ng_style.js";
import { isContextNode, readPayload } from "./ng_read.js";
import { renderPlan } from "./ng_view.js";

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const DIRECTOR = "NGDirector";
const DEBOUNCE_MS = 350;
const panels = new Map();   // node -> panel (new nodes have no unique id yet)

async function fetchPlan(payload) {
  const response = await api.fetchApi("/ng/plan", { method: "POST", body: JSON.stringify(payload) });
  return response.json();
}

async function refresh(panel) {
  const serial = ++panel.serial;
  let data;
  try {
    data = await fetchPlan(readPayload(panel.node));
  } catch (error) {
    data = { ok: false, error: `could not reach the server: ${error.message || error}` };
  }
  if (serial === panel.serial) renderPlan(panel.root, data);
}

function schedule(panel) {
  clearTimeout(panel.timer);
  panel.serial++;
  panel.timer = setTimeout(() => refresh(panel), DEBOUNCE_MS);
}

export function scheduleAll() {
  for (const panel of panels.values()) schedule(panel);
}

// Any widget edit on a node that feeds the plan calls back into the panels.
function watchWidgets(node) {
  for (const widget of node.widgets || []) {
    const original = widget.callback;
    widget.callback = function (...args) {
      const result = original ? original.apply(this, args) : undefined;
      scheduleAll();
      return result;
    };
  }
  const connections = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = connections ? connections.apply(this, args) : undefined;
    scheduleAll();
    return result;
  };
}

function attach(node) {
  ensureStyle();
  const root = document.createElement("div");
  root.className = "ng-plan";
  node.properties ||= {};
  delete node.properties.ng_view_mode;
  const configured = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = configured?.apply(this, args);
    delete node.properties.ng_view_mode;
    schedule(panel);
    return result;
  };
  const widget = followNodeWidth(node.addDOMWidget("ng_plan", "ng_plan", root, { serialize: false, hideOnZoom: false }));
  widget.computeSize = (width) => [width, 260];
  const panel = { node, root, timer: null, serial: 0 };
  panels.set(node, panel);
  watchWidgets(node);
  renderPlan(root, null);
  schedule(panel);
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    clearTimeout(panel.timer);
    panel.serial++;
    panels.delete(node);
    return removed ? removed.apply(this, args) : undefined;
  };
}

app.registerExtension({
  name: "mmxd.ng.plan_panel",
  nodeCreated(node) {
    if (node.comfyClass === DIRECTOR) attach(node);
    else if (isContextNode(node)) watchWidgets(node);
  },
  loadedGraphNode() {
    scheduleAll();
  },
});

document.addEventListener("ng-context-changed", scheduleAll);
