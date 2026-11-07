import assert from "node:assert/strict";
import { controlGraph, controlSetup } from "../../../js/ng/h3c_control_graph.js";
import { activeMask, maskBox, uploadMask } from "../../../js/ng/h3c_mask.js";
import { installDom } from "./fake_dom.mjs";
import { modelsApi } from "./fake_models.mjs";

const graph = controlGraph("mask", "walk.mp4", { checkpoint: "sam3.1_multiplex_fp16.safetensors", prompt: "red ball" }, "id");
assert.equal(graph.detect.class_type, "SAM3_Detect");
assert.equal(graph.detect.inputs.individual_masks, false, "one mask per source frame, including when several objects match");
assert.equal(graph.batch.inputs.batch_size, 1);
assert.equal(graph.text.inputs.text, "red ball");
assert.deepEqual(graph.video.inputs.fps, ["components", 2]);
assert.deepEqual(graph.image.inputs.mask, ["detect", 0], "save raw masks; shape/grow stay editable without SAM3 reruns");
assert.equal(graph.save.inputs.filename_prefix, "h3-control/id_mask");
assert.throws(() => controlGraph("mask", "walk.mp4", { prompt: " " }, "id"), /Describe what to mask/);
await assert.rejects(controlSetup(modelsApi(), "mask"), /SAM3 needs sam3\.1_multiplex_fp16\.safetensors in models\/checkpoints/);
const api = modelsApi({ sam3: ["my_sam3_custom.safetensors", "sam3.1_multiplex_fp16.safetensors"] });
assert.deepEqual(await controlSetup(api, "mask"), { checkpoint: "sam3.1_multiplex_fp16.safetensors" }, "Automatic: the official name first");
// The card's Models menu: a renamed or own file is used while it is there, else Automatic.
assert.deepEqual(await controlSetup(api, "mask", "moge2", { sam3: "my_sam3_custom.safetensors" }), { checkpoint: "my_sam3_custom.safetensors" });
assert.deepEqual(await controlSetup(api, "mask", "moge2", { sam3: "deleted.safetensors" }), { checkpoint: "sam3.1_multiplex_fp16.safetensors" });
assert.equal(activeMask({ control_mask: "mask.mp4", control_result: "old.mp4" }, "new.mp4"), "");
assert.equal(activeMask({ control_mask: "mask.mp4", control_result: "source.mp4" }, "source.mp4"), "mask.mp4");

installDom();
const calls = [], player = document.createElement("video");
const state = { api, opts: { control_kind: "mask", control_mask: "mask.mp4" }, values: { video: "source.mp4" }, els: { mask: player }, files: [] };
const box = maskBox(state, { setOptions: (v) => calls.push(v), setMask: (v) => calls.push(v) });
assert.ok(box.innerText.includes("White in the mask is regenerated"));
assert.equal(box.byTag("select")[0].value, "mask.mp4");
assert.equal(box.byTag("select")[1].value, "box");
const grow = box.byTag("input").find((e) => e.getAttribute("aria-label") === "Mask grow");
assert.equal(grow.value, 16);
grow.onchange({ target: { value: "8" } });
assert.deepEqual(calls.pop(), { mask_grow: 8 });
box.byTag("select")[0].onchange({ target: { value: "ready.mp4" } });
assert.equal(calls.pop(), "ready.mp4");
let uploaded;
const uploadedName = await uploadMask({ fetchApi: async (url, args) => {
  uploaded = { url, data: args.body };
  return { ok: true, json: async () => ({ subfolder: "h3-control", name: "mask.mp4" }) };
} }, new File(["mask bytes"], "mask.mp4", { type: "video/mp4" }));
assert.equal(uploadedName, "h3-control/mask.mp4");
assert.equal(uploaded.url, "/upload/image");
assert.equal(uploaded.data.get("image").name, "mask.mp4");
assert.equal(uploaded.data.get("type"), "input");
console.log("control masks ok");
