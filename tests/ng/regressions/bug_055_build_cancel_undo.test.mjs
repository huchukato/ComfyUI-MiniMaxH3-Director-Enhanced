// Make H3 prompt (js/ng/h3s_ai.js build + js/ng/h3s_studio.js buildPrompt): the planning step already writes the
// plan into the node's widgets. Cancelling or a failure after that step must not tell the user "nothing changed"
// and must still offer the documented Undo (docs/NG.md: "Undo in the message puts the shots, Look, sound fields and
// card descriptions back").
import assert from "node:assert/strict";
import test from "node:test";
import { newShot, writeProject, readProject } from "../../../js/ng/h3s_model.js";
import { openStudio } from "../../../js/ng/h3s_studio.js";
import { installStudioDom } from "./studio_fixture.mjs";

const PLAN = { ok: true, width: 1344, height: 768, total_s: 10, total_frames: 240, mode: "ref2va", issues: [],
  director_context: { items: [] },
  chunks: [
    { index: 0, start_s: 0, end_s: 5, delivered_frames: 120, head_frames: 0, mode: "ref2va", prompt: "first compiled",
      prompt_key: "k0", prompt_source: "compiled", refs: [], shots: [{ shot_id: "shot_a" }] },
    { index: 1, start_s: 5, end_s: 10, delivered_frames: 120, head_frames: 0, mode: "ref2va", prompt: "second compiled",
      prompt_key: "k1", prompt_source: "compiled", refs: [], shots: [{ shot_id: "shot_b" }] }] };
const PLANNED = { shots: writeProject({ shots: [{ ...newShot(0, 10), id: "shot_z", text: "AI planned shot." }], audio: [], lanes: [] }),
  look: "AI planned look", soundscape: "AI planned ambience", music: "N/A" };
const ORIGINAL = { shots: ["My own first shot.", "My own second shot."], look: "", soundscape: "my ambience",
  music: "my music", partPrompts: [] };

let made = 0;
function studio() {
  installStudioDom();
  const id = ++made;
  const initial = { shots: [{ ...newShot(0, 5), id: "shot_a", text: "My own first shot." },
    { ...newShot(5, 10), id: "shot_b", text: "My own second shot." }], audio: [], lanes: [] };
  const settings = { idea: "A young woman plays outside with a red ball.", project_seconds: 10, chunk_seconds: 0,
    shots: writeProject(initial), mode: "ref2va", width: 1344, height: 768, steps: 20, cfg: 1, seed: 1,
    sampler_name: "euler", scheduler: "simple", turbo: false, turbo_lora_fl2va: "none", turbo_lora_ref2va: "none",
    resize_method: "crop", ref_image_size: "match", soundscape: "my ambience", music: "my music" };
  const widgets = (data) => Object.entries(data).map(([name, value]) => ({ name, value, options: { values: [value] } }));
  const node = { id, comfyClass: "NGH3Director", properties: {}, widgets: widgets(settings),
    inputs: [{ name: "context", link: id * 10 + 1 }], outputs: [] };
  const connector = { id: id * 10 + 2, comfyClass: "NGContextConnector", widgets: [], inputs: [{ name: "ai_provider", link: id * 10 + 3 }], outputs: [] };
  const provider = { id: id * 10 + 3, comfyClass: "NGAIProvider", widgets: widgets({ source: "local", provider: "ollama", model: "m",
    base_url: "http://fixture.invalid", timeout_seconds: 120, api_key_env: "", vision: false, audio: false, max_tokens: 512 }), inputs: [] };
  const graph = { links: { [id * 10 + 1]: { origin_id: connector.id }, [id * 10 + 3]: { origin_id: provider.id } },
    getNodeById: (n) => [node, connector, provider].find((entry) => entry.id === Number(n)), change() {} };
  for (const entry of [node, connector, provider]) entry.graph = graph;
  const waiters = new Map();
  const defer = (path) => { let resolve; const promise = new Promise((res) => { resolve = res; }); waiters.set(path, { resolve, promise }); return promise; };
  const api = { addEventListener() {}, removeEventListener() {}, async fetchApi(path) {
    if (path === "/ng/plan") return { json: async () => PLAN };
    if (path.startsWith("/ng/build_plan") || path.startsWith("/ng/write_part")) return defer(path);
    return { json: async () => ({ ok: false, error: "unhandled " + path }) }; } };
  const handle = openStudio(node, {}, api);
  const root = document.body.byClass("h3s")[0];
  const widget = (name) => node.widgets.find((entry) => entry.name === name).value;
  const settleWaiter = (path, body) => { const w = waiters.get(path); waiters.delete(path); w.resolve({ json: async () => body }); };
  return { root, handle, node, widget, document: () => readProject(widget("shots")),
    plan: (suggestion) => settleWaiter("/ng/build_plan", { ok: true, suggestion }),
    part: (suggestion) => settleWaiter("/ng/write_part", { ok: true, suggestion }),
    failPart: (message) => settleWaiter("/ng/write_part", { ok: false, error: message }) };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 40));
const project = (s) => ({ shots: s.document().shots.map((shot) => shot.text), look: s.document().look,
  soundscape: s.widget("soundscape"), music: s.widget("music"), partPrompts: s.document().partPrompts });
const toasts = (s) => s.root.byClass("h3s-toast").map((node) => node.innerText);

// control: the plan arrives and every part is written; the message offers Undo and Undo puts everything back.
test("control: a finished Make H3 prompt offers Undo and it restores the project", async (t) => {
  const s = studio(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.plan(PLANNED); await settle();
  s.part({ index: 0, key: "k0", text: "AI part 0", problems: [], unchanged: false }); await settle();
  s.part({ index: 1, key: "k1", text: "AI part 1", problems: [], unchanged: false }); await settle();
  assert.ok(s.root.button("Undo"), "the finished message offers Undo");
  s.root.button("Undo").onclick(); await settle();
  assert.deepEqual(project(s), ORIGINAL, "Undo puts the shots, Look, sound fields and part prompts back");
});

// control: cancelling while the plan is still being made changes nothing, so the message is true.
test("control: cancelling during planning leaves the project alone", async (t) => {
  const s = studio(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.root.button("Cancel").onclick(); await settle();
  assert.deepEqual(project(s), ORIGINAL);
  assert.deepEqual(toasts(s), ["AI cancelled, nothing changed."]);
});

// BUG-055: the plan is already written into the widgets, yet Cancel says nothing changed and drops the Undo.
test("BUG-055: Cancel after the plan was applied must not claim nothing changed and must keep Undo", async (t) => {
  const s = studio(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.plan(PLANNED); await settle();
  assert.deepEqual(project(s).shots, ["AI planned shot."], "the plan replaced the shots before the parts were written");
  s.root.button("Cancel").onclick(); await settle();
  assert.ok(!toasts(s).includes("AI cancelled, nothing changed."),
    "the toast claims nothing changed although the plan replaced the shots, Look and sound fields");
  assert.ok(s.root.button("Undo"), "the plan was applied, so the documented Undo must still be offered");
});

// BUG-055: the same loss without any user action - a failed part writer leaves no way back either.
test("BUG-055: a part writer failure after the plan was applied must keep Undo", async (t) => {
  const s = studio(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.plan(PLANNED); await settle();
  s.failPart("the connected model did not answer within 120 s"); await settle();
  assert.deepEqual(project(s).shots, ["AI planned shot."], "the plan is still applied");
  assert.ok(s.root.button("Undo"), "the plan was applied, so the documented Undo must still be offered");
});

