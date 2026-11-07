// Real Context card extension hooks, offline host DOM/API, and serialized values before Queue's STRING coercion.
import assert from "node:assert/strict";
import test from "node:test";
import { installDom } from "./fake_dom.mjs";

test("Context card lifecycle repairs only nullable text before payload and Queue serialization", async (t) => {
  installDom();
  const proto = Object.getPrototypeOf(document.body);
  proto.querySelectorAll = function (selector) {
    const tags = selector.split(",").map((value) => value.trim().toUpperCase());
    return this.find((node) => tags.includes(node.tagName));
  };
  proto.querySelector = function (selector) { return this.querySelectorAll(selector)[0] || null; };
  proto.pause = function () {};
  const createElement = document.createElement;
  document.createElement = function (tag) { const element = createElement(tag); element.style.setProperty = function (name, value) { this[name] = value; }; return element; };
  globalThis.Image = class extends proto.constructor { constructor() { super("img"); } };
  globalThis.requestAnimationFrame = () => {};
  const extensions = [];
  const api = { apiURL: (path) => path, fetchApi: async () => ({ json: async () => ({ ok: true, names: [], peaks: [], duration_s: 0 }) }) };
  globalThis.window = { comfyAPI: { app: { app: { registerExtension: (extension) => extensions.push(extension) } }, api: { api } } };
  await import("../../../js/ng/h3c_card.js");
  const extension = extensions.find((entry) => entry.name === "mmxd.ng.context_cards");
  assert.ok(extension, "execute the actual product extension");
  const initial = { audio: "voice.wav", name: null, description: null, content: "voice", usage: "voice", preserve: "high", speaker: null,
    context_id: "ctx_voice", color: null, content_roles: "", usage_roles: "", context_options: "", subject_ids: "", unrelated: null };
  const card = { id: 1, comfyClass: "NGContextAudio", properties: {}, size: [800, 800], inputs: [], outputs: [{ links: [1] }],
    widgets: Object.entries(initial).map(([name, value]) => ({ name, value, options: { values: [value] } })),
    setSize(size) { this.size = size; }, setDirtyCanvas() {},
    addDOMWidget(name, type, root) { this.root = root; const widget = { name, type, serialize: false }; this.widgets.push(widget); return widget; },
    // Installed LGraphNode.configure restores present named/positional values verbatim before calling this hook.
    onConfigure(saved) {
      for (const [index, widget] of this.widgets.entries()) {
        if (widget.serialize === false) continue;
        if (saved.widgets_values_named && Object.hasOwn(saved.widgets_values_named, widget.name)) widget.value = saved.widgets_values_named[widget.name];
        else if (index < (saved.widgets_values || []).length) widget.value = saved.widgets_values[index];
      }
    } };
  const connector = { id: 2, comfyClass: "NGContextConnector", inputs: [{ name: "contexts.0", link: 1 }], widgets: [], outputs: [] };
  const director = { id: 3, comfyClass: "NGH3Director", inputs: [{ name: "context", link: 2 }], widgets: [] };
  const all = [card, connector, director];
  const graph = { _nodes: all, links: { 1: { origin_id: 1, target_id: 2 }, 2: { origin_id: 2, target_id: 3 } }, getNodeById: (id) => all.find((node) => node.id === id) };
  for (const node of all) node.graph = graph;
  t.after(() => card.onRemoved());
  const { values } = await import("../../../js/ng/ng_widgets.js");
  const { readPayload } = await import("../../../js/ng/ng_read.js");
  const fields = ["name", "description", "speaker"];
  const check = () => {
    const now = values(card);
    for (const field of fields) assert.equal(now[field], "");
    assert.match(now.color, /^#[0-9a-f]{6}$/i, "an unset color receives the existing automatic accent");
    assert.equal(now.context_id, "ctx_voice");
    assert.equal(now.unrelated, null, "leave every other nullable field untouched");
    const payload = JSON.parse(JSON.stringify(readPayload(director)));
    for (const field of fields) assert.equal(payload.contexts[0].widgets[field], "");
    // Queue's graphToPrompt reads/serializes these same ordinary widget values. The separate Python test executes
    // real ComfyUI validate_inputs, where a raw null would turn into the literal text "None".
    const serialized = Object.fromEntries(card.widgets.filter((widget) => widget.serialize !== false).map((widget) => [widget.name, widget.value]));
    for (const field of fields) assert.equal(serialized[field], "", "Queue must receive empty text before Python STRING coercion");
  };
  await t.test("initial card attachment repairs explicit null", () => { extension.nodeCreated(card); check(); });
  await t.test("positional saved null restores as empty before payload or Queue", () => {
    card.onConfigure({ widgets_values: card.widgets.map((widget) => Object.hasOwn(initial, widget.name) ? initial[widget.name] : widget.value) }); check();
  });
  await t.test("named saved null restores as empty before payload or Queue", () => { card.onConfigure({ widgets_values_named: initial }); check(); });
  await t.test("explicit text, including literal None and whitespace, remains intact", () => {
    const named = { ...initial, name: "None", description: "  A narrator.  ", speaker: "Ålice", color: "#123456" };
    card.onConfigure({ widgets_values_named: named });
    const now = values(card);
    for (const field of [...fields, "color"]) assert.equal(now[field], named[field]);
    card.onConfigure({ widgets_values_named: now });
    assert.equal(values(card).name, "None");
  });
});
