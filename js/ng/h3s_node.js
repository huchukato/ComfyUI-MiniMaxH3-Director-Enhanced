// The H3 Director in the graph is the Studio itself: the node's face is the whole Studio, as tall as its content.
// "Full screen" in its header lifts the same Studio over the window; there is no second, compact view.
import { h } from "./h3s_dom.js";
import { ensureStudioStyle } from "./h3s_style.js";
import { renamedDirector } from "./h3s_model.js";
import { openStudio, closeStudio } from "./h3s_studio.js";
import { values, applyValues, followNodeWidth } from "./ng_widgets.js";
import { readContexts } from "./ng_read.js";
import { renameReferences } from "./ng_references.js";
import { hideNative } from "./ng_editor_fields.js";
import { noteGrowth, followDraggedHeight, pushOnGrowth } from "./ng_layout.js";

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;
const nodes = new Map(); // follow renames -> full refresh, per Director node
// Below this width the Studio stacks its side panel under the timeline; the default leaves room for both side by side.
const MIN_WIDTH = 900, WIDTH = 1400, HEIGHT = 1150;
// Widgets added after the first NG workflows were saved. Those workflows carry one empty trailing value from the former
// in-node editor, which lands on the first new widget; anything that is not a valid value falls back to the default.
const LATER = { turbo: false, turbo_lora_fl2va: "none", turbo_lora_ref2va: "none", resize_method: "crop", ref_image_size: "match" };

// Widgets inserted among the saved ones, oldest first. ComfyUI restores widget values by position, so a workflow saved before
// "resume" gave it the value of the widget after it (prompt_override's text while resume was required, now the Studio's own
// entry). A list short by k lacks the k newest: those get their defaults, every other widget its saved value in order.
const INSERTED = [["resume", true], ["resume_delete_done", true], ["control_strength", 1], ["control_start", 0], ["control_end", 1], ["models", ""], ["output", "video"], ["spectrum", false]];
export function repairInsertedWidgets(node, saved, named) {
  const widgets = node.widgets || [];
  const inserted = INSERTED.filter(([name]) => widgets.some((widget) => widget.name === name));
  // Modern ComfyUI saves names and omits nonserialized DOM widgets. A shorter positional list then does not mean
  // a setting is missing; rotating it again shifted the ControlNet settings on Save As and reload.
  if (named && inserted.every(([name]) => Object.hasOwn(named, name))) {
    for (const widget of widgets) if (inserted.some(([name]) => name === widget.name)) widget.value = named[widget.name];
    return;
  }
  const missing = Array.isArray(saved) ? widgets.length - saved.length : 0;
  if (missing < 1 || missing > inserted.length) return;
  const defaults = new Map(inserted.slice(-missing));
  if (!widgets.some((widget) => defaults.has(widget.name))) return;
  let next = 0;
  for (const widget of widgets) widget.value = defaults.has(widget.name) ? defaults.get(widget.name) : saved[next++];
}

export function repairLaterWidgets(node) {
  // For a few hours on 2026-10-13 "resume" was a required input and so stood before prompt_override; a workflow saved then
  // swaps the two on load (the Prompt override became true, "expected text, got bool"). Text never belongs to the switch.
  // The text box turns a boolean into the text "true"/"false" as it is set (ComfyUI frontend 1.55, 2026-10-18: every part's
  // prompt became "true" and the AI's prompts were refused), so that text counts as the misplaced switch as well.
  const override = node.widgets?.find((w) => w.name === "prompt_override"), resume = node.widgets?.find((w) => w.name === "resume");
  if (override && (typeof override.value === "boolean" || ["true", "false"].includes(override.value))) {
    const text = typeof resume?.value === "string" ? resume.value : "";
    if (resume && typeof resume.value !== "boolean") resume.value = String(override.value) === "true";
    override.value = text;
  }
  for (const widget of node.widgets || []) {
    if (!(widget.name in LATER)) continue;
    // A LoRA file that is not installed (yet) keeps its name: ComfyUI's missing-model check offers its download, and the
    // Studio says it is missing. Only a value that is no file name at all was shifted into this widget.
    const missingFile = widget.name.startsWith("turbo_lora") && /\.safetensors$/i.test(String(widget.value));
    const valid = widget.name === "turbo" ? typeof widget.value === "boolean" : missingFile || (widget.options?.values || []).includes(widget.value);
    if (!valid) widget.value = LATER[widget.name];
  }
}

// A renamed Context keeps its @Name mentions in the Prompt and in every shot; the audio lanes travel along untouched.
function followRenames(node) {
  const previous = node.properties.ng_context_names || {}, entries = readContexts(node);
  const changes = renamedDirector(values(node), (text) => renameReferences(text, previous, entries));
  node.properties.ng_context_names = Object.fromEntries(entries.filter((entry) => entry.widgets.context_id && entry.widgets.name)
    .map((entry) => [entry.widgets.context_id, entry.widgets.name]));
  if (Object.keys(changes).length) applyValues(node, changes);
}

function attach(node) {
  ensureStudioStyle();
  node.properties ||= {};
  for (const key of ["ng_view_mode", "ng_selected_shot_id"]) delete node.properties[key];
  node.color = "#172a48"; node.bgcolor = "#101a2c";
  const host = h("div", { class: "h3s-host" });
  hideNative(node, (node.widgets || []).map((widget) => widget.name));
  const dom = followNodeWidth(node.addDOMWidget("h3_director", "h3_director", host, { serialize: false, hideOnZoom: false }));
  // The node is as tall as its Studio, so the DOM never spills over the nodes below it. ComfyUI hides DOM widgets of
  // nodes outside the view; a hidden Studio measures 0, so only a visible one is measured, again whenever it resizes.
  let measured = 900, removed = false;
  dom.computeSize = undefined;
  // the node's minimum is its content without the grown part, so it can be dragged smaller again
  const grown = () => node.properties.ng_grow || 0;   // the height a drag gave the growing part (ng_layout.followDraggedHeight)
  dom.computeLayoutSize = () => ({ minHeight: measured - grown(), maxHeight: measured, minWidth: MIN_WIDTH - 20 });
  const studio = openStudio(node, app, api, host);
  function fit() {
    requestAnimationFrame(() => {
      if (removed || !host.isConnected || studio.root.parentNode !== host) return;
      const height = studio.root.scrollHeight;
      if (height < 200) return;
      measured = Math.ceil(height) + 8;
      const target = (node.computeSize?.()[1] ?? measured) + grown(), width = Math.max(node.size?.[0] || 0, MIN_WIDTH);
      if (!node.size || Math.abs(node.size[1] - target) > 2 || node.size[0] < MIN_WIDTH) node.setSize([width, target]);
      node.setDirtyCanvas?.(true, true);
    });
  }
  const watcher = typeof ResizeObserver === "function" ? new ResizeObserver(() => fit()) : null;
  watcher?.observe(studio.root);
  // dragged taller, the timeline's shot lane takes the extra height and its shots show more of their text
  followDraggedHeight(node, (px) => { host.style.setProperty("--h3s-grow", `${px}px`); host.style.setProperty("--h3s-lines", String(2 + Math.floor(px / 16))); }, fit);
  pushOnGrowth(node);
  // The Studio writes the widgets itself and hears outside changes on its own; the node keeps @Name mentions in step.
  const follow = () => followRenames(node);
  const refresh = () => { followRenames(node); studio.refresh(); fit(); };
  for (const widget of node.widgets || []) {
    if (widget === dom) continue;
    const original = widget.callback;
    widget.callback = function (...args) { const result = original?.apply(this, args); follow(); return result; };
  }
  const connected = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) { const result = connected?.apply(this, args); refresh(); return result; };
  const configured = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = configured?.apply(this, args);
    for (const key of ["ng_view_mode", "ng_selected_shot_id"]) delete node.properties[key];
    repairInsertedWidgets(node, args[0]?.widgets_values, args[0]?.widgets_values_named);
    repairLaterWidgets(node);
    // Saved by the former compact node: the Studio needs the room once, and the nodes around it move along.
    if (node.size?.[0] < MIN_WIDTH) { noteGrowth(node, [...node.size]); node.setSize([WIDTH, Math.max(node.size[1], HEIGHT)]); }
    refresh(); return result;
  };
  const gone = node.onRemoved;
  node.onRemoved = function (...args) {
    removed = true; watcher?.disconnect(); nodes.delete(follow); closeStudio(node); return gone?.apply(this, args);
  };
  node.setSize([WIDTH, measured]);
  nodes.set(follow, refresh); follow();
}

app.registerExtension({
  name: "mmxd.ng.director_studio",
  nodeCreated(node) { if (["NGH3Director", "NGDirectorStudio"].includes(node.comfyClass)) attach(node); },
  loadedGraphNode() { nodes.forEach((refresh) => refresh()); },
});
document.addEventListener("ng-context-changed", () => nodes.forEach((_refresh, follow) => follow()));
