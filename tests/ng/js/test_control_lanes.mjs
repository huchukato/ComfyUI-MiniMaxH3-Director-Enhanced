import assert from "node:assert/strict";
import { readProject, writeProject, renamedDirector, dragTo, placeAt, trimToDuration } from "../../../js/ng/h3s_model.js";
import { controlGraph, controlSetup } from "../../../js/ng/h3c_control_graph.js";
import { runJob } from "../../../js/ng/h3b_queue.js";
import { modelsApi } from "./fake_models.mjs";

const control = [{ schema_version: 1, id: "pose", context_id: "motion", lane: "control", start: 1, end: 4, offset: 2 }];
const text = writeProject({ shots: [], audio: [], lanes: [], control });
assert.deepEqual(readProject(text).control, control, "control-only projects must survive save/reload");
assert.deepEqual(JSON.parse(text).control_lanes, ["control"]);
const renamed = renamedDirector({ idea: "@Old walks", shots: writeProject({ shots: [], audio: [], lanes: [], control, look: "@Old in a hall" }) },
  (s) => s.replaceAll("@Old", "@New"));
assert.deepEqual(readProject(renamed.shots).control, control, "renames must not erase the lane");
assert.equal(readProject(renamed.shots).look, "@New in a hall");
const moved = dragTo(control, { id: "pose", mode: "move", start: 1, end: 4 }, 2, 10).items;
assert.deepEqual([moved[0].start, moved[0].end, moved[0].offset], [3, 6, 2]);
assert.equal(placeAt(control, 2, 10, 2), null, "a second control clip may not overlap");
assert.equal(trimToDuration(control, 2).items[0].end, 2);
assert.ok(readProject(JSON.stringify({ ...JSON.parse(text), control: [{ ...control[0], end: 0 }] })).error);

for (const kind of ["canny", "pose", "depth"]) {
  const graph = controlGraph(kind, "walk.mp4", { detector: "detector", pose: "pose", depth: "depth", engine: "moge2" }, "id");
  assert.deepEqual(graph.video.inputs.fps, ["components", 2], "never speed up a 30 fps source by declaring 24 fps");
  assert.equal(graph.save.inputs.filename_prefix, `h3-control/id_${kind}`);
  assert.equal(graph.load.inputs.file, "walk.mp4");
  if (kind === "canny") assert.equal(graph.batch.inputs.batch_size, 16, "keep Canny inside the tested memory budget");
  if (kind === "pose") assert.equal(graph.boxes.class_type, "RTDETR_detect");
  if (kind === "depth") assert.equal(graph.depth.class_type, "LoadMoGeModel");
}
const da3 = controlGraph("depth", "walk.mp4", { depth: "da3_base.safetensors", engine: "da3" }, "id");
assert.equal(da3.infer.class_type, "DepthAnything_V3");
assert.equal(da3.depth.class_type, "DownloadAndLoadDepthAnythingV3Model");
const api = modelsApi();
await assert.rejects(controlSetup(api, "pose"), /sdpose_wholebody/);
await assert.rejects(controlSetup(api, "depth"), /moge_2/);
await assert.rejects(controlSetup(api, "invalid"), /Choose/);
assert.deepEqual(await controlSetup(api, "canny"), {});

const multiple = { fetchApi: async (url) => ({ json: async () => url === "/prompt" ? { prompt_id: "id" }
  : { id: { outputs: { save: { images: [{ filename: "one.mp4" }, { filename: "two.mp4" }] } } } } }) };
await assert.rejects(runJob(multiple, {}, "save"), /several files/, "never silently keep only the first 4096-frame batch");
const interrupted = { fetchApi: async (url) => ({ json: async () => url === "/prompt" ? { prompt_id: "id" }
  : { id: { status: { status_str: "error", completed: false, messages: [["execution_interrupted", {}]] } } } }) };
await assert.rejects(runJob(interrupted, {}, "save"), /interrupted/, "an interrupted job must release the card, not poll for 30 minutes");

const { installDom } = await import("./fake_dom.mjs");
installDom();
const { controlSettings, controlPanel } = await import("../../../js/ng/h3s_control.js");
const { controlBox } = await import("../../../js/ng/h3c_control.js");
const calls = [], entry = { id: "motion", name: "Walk", media: "video", usage: ["control"], controlKind: "pose" };
const S = { contexts: [entry], byId: new Map([[entry.id, entry]]), controlConnected: true, values: {}, plan: { issues: [], chunks: [] } };
const actions = { setWidget: (...args) => calls.push(args), setControl: (...args) => calls.push(args), deleteControl: (...args) => calls.push(args) };
const settings = controlSettings(S, actions), numbers = settings.byTag("input");
assert.deepEqual(numbers.map((e) => e.value), [1, 0, 1]);
assert.deepEqual(numbers.map((e) => [e.getAttribute("min"), e.getAttribute("max")]), [["0", "10"], ["0", "1"], ["0", "1"]]);
numbers[0].onchange({ target: { value: "0.5" } });
assert.deepEqual(calls.at(-1), ["control_strength", .5]);
settings.byTag("details")[0].ontoggle({ currentTarget: { isConnected: true, open: true } });
assert.equal(controlSettings(S, actions).byTag("details")[0].getAttribute("open"), "", "planning redraws keep the denoising controls open");
const panel = controlPanel(S, actions, control[0]);
panel.byTag("input")[2].onchange({ target: { value: "3.2" } });
assert.deepEqual(calls.at(-1), ["pose", "offset", 3.2]);
const cardState = { usage: "control", opts: { control_kind: "depth" }, values: { video: "walk.mp4" }, els: {}, busy: false, da3: false };
assert.ok(!controlBox(cardState, {}).innerText.includes("Depth Anything 3"), "do not offer unloaded DA3 nodes");
assert.ok(controlBox({ ...cardState, da3: true }, {}).innerText.includes("Depth Anything 3"));
console.log("control lanes ok");
