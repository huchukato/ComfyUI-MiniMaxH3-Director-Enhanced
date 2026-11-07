// Real Director extension callbacks and Studio UI actions; no provider or render calls.
import test from "node:test";
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";
import * as model from "../../../js/ng/h3s_model.js";

installDom();
const proto = Object.getPrototypeOf(document.body), listeners = new Map(), extensions = [];
proto.querySelectorAll = function (selector) {
  const tags = selector.split(",").map((value) => value.trim().toUpperCase());
  return this.find((node) => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : tags.includes(node.tagName));
};
proto.querySelector = function (selector) { return this.querySelectorAll(selector)[0] || null; };
proto.focus = function () { document.activeElement = this; };
document.addEventListener = (name, callback) => { listeners.set(name, [...(listeners.get(name) || []), callback]); };
document.removeEventListener = (name, callback) => { listeners.set(name, (listeners.get(name) || []).filter((v) => v !== callback)); };
document.dispatchEvent = (event) => { for (const callback of listeners.get(event.type) || []) callback(event); };
globalThis.requestAnimationFrame = () => {};
const api = { addEventListener() {}, removeEventListener() {},
  async fetchApi() { return { json: async () => ({ ok: false, error: "Offline lifecycle control." }) }; } };
const app = { registerExtension: (extension) => extensions.push(extension) };
globalThis.window = { comfyAPI: { app: { app }, api: { api } } };
await import("../../../js/ng/h3s_node.js");
const extension = extensions.find((entry) => entry.name === "mmxd.ng.director_studio");
assert.ok(extension);

function fixture(t, project, idea = "A story", prior = { figure: "Alice" }) {
  const settings = { idea, project_seconds: 15, chunk_seconds: 5, mode: "ref2va", shots: model.writeProject(project),
    width: 1344, height: 768, steps: 20, cfg: 1, seed: 1, sampler_name: "euler", scheduler: "simple", turbo: false,
    turbo_lora_fl2va: "none", turbo_lora_ref2va: "none", resize_method: "crop", ref_image_size: "match", soundscape: "", music: "" };
  const widgets = (data) => Object.entries(data).map(([name, value]) => ({ name, value, options: { values: [value] } }));
  const figure = { id: 3, comfyClass: "NGContextImage", widgets: widgets({ context_id: "figure", name: "Alice", image: "figure.png", usage: "reference" }) };
  const connector = { id: 2, comfyClass: "NGContextConnector", widgets: [], inputs: [{ name: "context_image.0", link: 2 }] };
  const director = { id: 1, comfyClass: "NGH3Director", properties: { ng_context_names: { ...prior } }, size: [1400, 1150],
    widgets: widgets(settings), inputs: [{ name: "context", link: 1 }], outputs: [],
    setSize(size) { this.size = size; }, setDirtyCanvas() {},
    addDOMWidget(name, type, root) { this.host = root; const widget = { name, type, serialize: false }; this.widgets.push(widget); return widget; } };
  const all = [director, connector, figure], graph = { _nodes: all,
    links: { 1: { origin_id: 2, target_id: 1 }, 2: { origin_id: 3, target_id: 2 } }, getNodeById: (id) => all.find((node) => node.id === Number(id)), change() {} };
  for (const node of all) node.graph = graph;
  extension.nodeCreated(director);
  t.after(() => director.onRemoved());
  return { director, figure, read: () => model.readProject(director.widgets.find((widget) => widget.name === "shots").value),
    rename(name) { figure.widgets.find((widget) => widget.name === "name").value = name; document.dispatchEvent(new CustomEvent("ng-context-changed")); } };
}
const shot = (extra = {}) => ({ ...model.newShot(0, 4), id: "s1", text: "A scenic shot", ...extra });
const audio = (extra = {}) => ({ schema_version: 1, id: "c1", context_id: "song", start: 4, end: 18, offset: 10, mode: "ref", lane: "l1", ...extra });

test("076: duration UI removes newly cut tiny fragments and Undo restores exact media", (t) => {
  const project = { shots: [shot({ start: 9.7, end: 13 })], audio: [audio({ start: 9.7, end: 13, mode: "lock" })], lanes: ["l1"] };
  const f = fixture(t, project), before = f.read();
  const input = f.director.host.byTag("input").find((field) => field.attributes["aria-label"] === "Duration in seconds");
  assert.ok(input);
  input.value = "10"; input.onchange({ target: input });
  assert.deepEqual(f.read().shots, []);
  assert.deepEqual(f.read().audio, []);
  const undo = f.director.host.button("Undo");
  assert.ok(undo, "the real Duration notice must retain Undo");
  undo.onclick();
  assert.deepEqual(f.read().shots, before.shots);
  assert.deepEqual(f.read().audio, before.audio);
});

test("076: exact minimum and imported complete short records remain compatible", () => {
  const complete = audio({ id: "imported", start: 2, end: 2.2 });
  const boundary = audio({ id: "boundary", start: 9.5, end: 14 });
  const remove = audio({ id: "removed", start: 9.7, end: 14 });
  const result = model.trimToDuration([complete, boundary, remove], 10);
  assert.deepEqual(result.removed, ["removed"]);
  assert.deepEqual(result.shortened, ["boundary"]);
  assert.deepEqual(result.items[0], complete, "do not discard existing short imported data that still fits whole");
  assert.equal(result.items[1].end - result.items[1].start, model.MIN_LENGTH);
});

test("078: every touched part receives the left-trimmed reference window; move keeps it", () => {
  const original = audio(), drag = { id: original.id, start: original.start, end: original.end, mode: "left" };
  const cut = model.dragTo([original], drag, 4, 20).items[0];
  assert.equal(cut.offset, 14);
  assert.deepEqual(model.clipParts(cut, [{ index: 0, start_s: 0, end_s: 10 }, { index: 1, start_s: 10, end_s: 20 }]).map((part) => part.file), [[14, 24], [14, 24]]);
  const moved = model.dragTo([cut], { id: cut.id, start: cut.start, end: cut.end, mode: "move" }, -2, 20).items[0];
  assert.equal(moved.offset, 14);
  assert.equal(moved.end - moved.start, 10);
  assert.deepEqual(model.readProject(model.writeProject({ shots: [], audio: [cut], lanes: ["l1"] })).audio[0], cut);
});

for (const field of ["look", "part", "spoken", "empty"]) {
  test(`079: actual Context rename event updates ${field} and repeated rename keeps identity`, (t) => {
    const line = { schema_version: 1, text: "Wait for @Alice", speaker_id: "figure", voice: "", language: "English", delivery: "says" };
    const project = { shots: field === "empty" ? [] : [shot({ spoken: field === "spoken" ? [line] : [] })],
      audio: [audio()], lanes: ["l1"], look: ["look", "empty"].includes(field) ? "Following @Alice" : "",
      partPrompts: field === "part" ? [{ index: 0, key: "saved-key", by: "user", text: "@Alice enters" }] : [] };
    const f = fixture(t, project), before = f.read();
    const select = (project) => field === "part" ? project.partPrompts[0].text : field === "spoken" ? project.shots[0].spoken[0].text : project.look;
    f.rename("Bob"); assert.ok(select(f.read()).includes("@Bob"));
    assert.deepEqual(f.read().audio, before.audio);
    assert.deepEqual(f.read().lanes, before.lanes);
    if (field === "part") assert.deepEqual([f.read().partPrompts[0].key, f.read().partPrompts[0].by], ["saved-key", "user"]);
    if (field === "spoken") assert.equal(f.read().shots[0].spoken[0].speaker_id, "figure");
    f.rename("Cara"); assert.ok(select(f.read()).includes("@Cara"));
    assert.deepEqual(f.director.properties.ng_context_names, { figure: "Cara" });
  });
}

test("079: malformed shot JSON is retained and ordinary unmentioned text is unchanged", (t) => {
  const f = fixture(t, { shots: [shot()], audio: [], lanes: [], look: "No reference here" });
  const widget = f.director.widgets.find((entry) => entry.name === "shots");
  const ordinary = widget.value;
  f.rename("Bob"); assert.equal(widget.value, ordinary);
  widget.value = '{"broken":';
  f.rename("Cara"); assert.equal(widget.value, '{"broken":');
});
