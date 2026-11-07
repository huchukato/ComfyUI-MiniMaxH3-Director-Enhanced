import assert from "node:assert/strict";
import test from "node:test";
import { newShot, writeProject, readProject } from "../../../js/ng/h3s_model.js";
import { openStudio } from "../../../js/ng/h3s_studio.js";
import { installStudioDom } from "../regressions/studio_fixture.mjs";
const settle = () => new Promise((resolve) => setTimeout(resolve, 40));
let made = 200;
function fixture({ cardDescriptions = ["", ""], deferPlan = false } = {}) {
  installStudioDom();
  const id = ++made;
  const widgets = (data) => Object.entries(data).map(([name, value]) => ({ name, value, options: { values: [value] } }));
  const settings = { idea: "A woman walks through a grand stone hall.", project_seconds: 10, chunk_seconds: 0,
    shots: writeProject({ shots: [{ ...newShot(0, 10), id: "s1", text: "My original shot." }], audio: [], lanes: [], look: "my original look",
      partPrompts: [{ index: 0, key: "oldkey", text: "my original part prompt", by: "user" }] }),
    mode: "ref2va", width: 1344, height: 768, steps: 20, cfg: 1, seed: 1,
    sampler_name: "euler", scheduler: "simple", turbo: false, turbo_lora_fl2va: "none", turbo_lora_ref2va: "none",
    resize_method: "crop", ref_image_size: "match", soundscape: "old ambience", music: "old music" };
  const node = { id, comfyClass: "NGH3Director", properties: {}, widgets: widgets(settings), inputs: [{ name: "context", link: 1 }], outputs: [] };
  const connector = { id: id + 1000, comfyClass: "NGContextConnector", widgets: [],
    inputs: [{ name: "ai_provider", link: 2 }, { name: "context_image.image_0", link: 3 }, { name: "context_image.image_1", link: 4 }], outputs: [] };
  const provider = { id: id + 2000, comfyClass: "NGAIProvider", widgets: widgets({ source: "local", provider: "ollama", model: "m",
    base_url: "http://fixture.invalid", timeout_seconds: 120, api_key_env: "", vision: true, audio: false, max_tokens: 512 }), inputs: [] };
  const cards = [0, 1].map((n) => ({ id: id + 3000 + n, comfyClass: "NGContextImage", properties: {},
    widgets: widgets({ image: "fixture" + n + ".png", name: "Figure " + n, context_id: "figure" + n, usage: "reference", content: "character", description: cardDescriptions[n] }), inputs: [], outputs: [] }));
  const all = [node, connector, provider, ...cards];
  const graph = { links: { 1: { origin_id: connector.id }, 2: { origin_id: provider.id }, 3: { origin_id: cards[0].id }, 4: { origin_id: cards[1].id } },
    getNodeById: (n) => all.find((entry) => entry.id === Number(n)), change() {} };
  for (const entry of all) entry.graph = graph;
  const waits = [], calls = [];
  const plan = { ok: true, width: 1344, height: 768, total_s: 10, total_frames: 240, mode: "ref2va", issues: [], director_context: { items: [] },
    chunks: [{ index: 0, start_s: 0, end_s: 10, delivered_frames: 240, head_frames: 0, mode: "ref2va", prompt: "compiled",
      prompt_key: "k0", prompt_source: "compiled", refs: [], shots: [{ shot_id: "s1" }] }] };
  const api = { addEventListener() {}, removeEventListener() {}, async fetchApi(path) {
    if (path === "/ng/plan") {
      if (!deferPlan) return { json: async () => plan };
      calls.push(path);
      return new Promise((resolve) => waits.push({ path, resolve }));
    }
    if (["/ng/build_plan", "/ng/analyze", "/ng/write_part"].includes(path)) {
      calls.push(path);
      return new Promise((resolve) => waits.push({ path, resolve })); // Deliberately ignores AbortSignal.
    }
    return { json: async () => ({ ok: false, error: "fixture has no media data" }) };
  } };
  const handle = openStudio(node, {}, api);
  const root = document.body.byClass("h3s")[0];
  const reply = (path, suggestion) => {
    const i = waits.findIndex((w) => w.path === path);
    assert.notEqual(i, -1, "the product must actually have requested " + path);
    waits.splice(i, 1)[0].resolve({ json: async () => ({ ok: true, suggestion }) });
  };
  const widget = (name) => node.widgets.find((w) => w.name === name).value;
  const project = () => readProject(widget("shots"));
  const original = { project: project(), soundscape: widget("soundscape"), music: widget("music") };
  const fail = (path, error) => {
    const i = waits.findIndex((w) => w.path === path);
    assert.notEqual(i, -1, "the product must actually have requested " + path);
    waits.splice(i, 1)[0].resolve({ json: async () => ({ ok: false, error }) });
  };
  const resolvePlan = () => {
    const i = waits.findIndex((w) => w.path === "/ng/plan");
    assert.notEqual(i, -1, "the product requested a deferred replan");
    waits.splice(i, 1)[0].resolve({ json: async () => plan });
  };
  return { root, handle, cards, calls, reply, fail, resolvePlan, original,
    snapshot: () => ({ project: project(), soundscape: widget("soundscape"), music: widget("music") }),
    description: (n) => cards[n].widgets.find((w) => w.name === "description").value };
}

for (const phase of ["first replan", "final replan"]) {
  test(`BUG-055: Cancel and Undo during ${phase} ignore its late completion`, async (t) => {
    const s = fixture({ cardDescriptions: ["Known first figure.", "Known second figure."], deferPlan: true });
    t.after(() => s.handle.close());
    s.root.button("Make H3 prompt").onclick(); await settle();
    s.reply("/ng/build_plan", { shots: writeProject({ shots: [{ ...newShot(0, 10), text: "AI shot." }], audio: [], lanes: [] }),
      look: "AI look", soundscape: "AI ambience", music: "AI music" });
    await settle();
    if (phase === "final replan") {
      s.resolvePlan(); await settle();
      s.reply("/ng/write_part", { index: 0, key: "k0", text: "AI finished part", problems: [], unchanged: false });
      await settle();
    }
    const writesBefore = s.calls.filter((path) => path === "/ng/write_part").length;
    s.root.button("Cancel").onclick(); await settle();
    assert.ok(s.root.button("Undo"));
    s.root.button("Undo").onclick(); await settle();
    assert.deepEqual(s.snapshot(), s.original);
    s.resolvePlan(); await settle();
    assert.deepEqual(s.snapshot(), s.original);
    assert.equal(s.calls.filter((path) => path === "/ng/write_part").length, writesBefore);
    assert.equal(s.root.byClass("h3s-toast").some((toast) => toast.innerText.includes("H3 prompt ready")), false,
      "old build completion cannot announce success after cancellation and Undo");
  });
}

test("BUG-055: canceled picture description ignores a late response and stops before the next card", async (t) => {
  const s = fixture(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.reply("/ng/build_plan", { shots: writeProject({ shots: [{ ...newShot(0, 10), text: "AI shot." }], audio: [], lanes: [] }), look: "AI look" });
  await settle();
  assert.equal(s.calls.filter((path) => path === "/ng/analyze").length, 1);
  s.root.button("Cancel").onclick(); await settle();
  const undo = s.root.button("Undo");
  assert.ok(undo, "the canceled applied plan offers Undo immediately while its description request is still pending");
  undo.onclick();
  assert.deepEqual(s.snapshot(), s.original, "Undo restores original shots, Look, sound and existing part prompt");
  s.reply("/ng/analyze", { description: "Late canceled AI description." }); await settle();
  assert.equal(s.description(0), "", "a canceled old build must not write to cards after cancellation or Undo");
  assert.equal(s.description(1), "");
  assert.equal(s.calls.filter((path) => path === "/ng/analyze").length, 1, "cancellation must stop the picture loop");
});

test("BUG-055: an old picture reply cannot edit a card or replace notice while a newer build is planning", async (t) => {
  const s = fixture(); t.after(() => s.handle.close());
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.reply("/ng/build_plan", { shots: writeProject({ shots: [{ ...newShot(0, 10), text: "AI shot." }], audio: [], lanes: [] }), look: "AI look" });
  await settle();
  s.root.button("Cancel").onclick(); await settle();
  s.root.button("Make H3 prompt").onclick(); await settle();
  s.reply("/ng/analyze", { description: "Old request description arriving during the new run." }); await settle();
  assert.equal(s.description(0), "", "the old run must not mutate the new run's source cards");
  assert.equal(s.calls.filter((path) => path === "/ng/analyze").length, 1);
  assert.ok(s.root.button("Cancel"), "the newer run stays busy");
});

for (const kind of ["Cancel", "part failure"]) {
  test(`BUG-055: actual Undo after ${kind} restores project and plan-provided card descriptions`, async (t) => {
    const originalDescription = "Known existing description of the second figure.";
    const s = fixture({ cardDescriptions: ["", originalDescription] }); t.after(() => s.handle.close());
    s.root.button("Make H3 prompt").onclick(); await settle();
    s.reply("/ng/build_plan", { shots: writeProject({ shots: [{ ...newShot(0, 10), text: "AI shot." }], audio: [], lanes: [] }),
      look: "AI look", music: "AI music", soundscape: "AI ambience", descriptions: { figure0: "AI description of first figure." } });
    await settle();
    assert.equal(s.description(0), "AI description of first figure.");
    if (kind === "Cancel") s.root.button("Cancel").onclick();
    else s.fail("/ng/write_part", "the connected model did not answer within 120 s");
    await settle();
    assert.ok(s.root.button("Undo"));
    s.root.button("Undo").onclick(); await settle();
    assert.deepEqual(s.snapshot(), s.original);
    assert.equal(s.description(0), "");
    assert.equal(s.description(1), originalDescription, "an already described card retains the user's description");
  });
}
