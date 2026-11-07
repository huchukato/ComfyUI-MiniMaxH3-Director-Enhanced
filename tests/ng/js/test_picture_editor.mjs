// The Image card's editor jobs (js/ng/h3c_editor_jobs.js; user 2026-10-19/20: mask, structure and a character sheet in
// our own nodes): which H3 files a sheet uses, how the six views are put side by side, what the SAM and pose jobs queue.
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const jobs = await import("../../../js/ng/h3c_editor_jobs.js");

// A card -> Context Connector, its models from UNETLoader (through a LoRA), CLIPLoader and VAELoader.
function graphWith({ ref2va = true } = {}) {
  const nodes = new Map(), links = {};
  let next = 1;
  const add = (id, comfyClass, widgets = {}, inputs = [], outputs = 1) => {
    const node = { id, comfyClass, widgets: Object.entries(widgets).map(([name, value]) => ({ name, value })),
      inputs: inputs.map((name) => ({ name, link: null })), outputs: Array.from({ length: outputs }, () => ({ links: [] })) };
    nodes.set(id, node); return node;
  };
  const link = (from, to, input) => {
    const id = next++, slot = to.inputs.findIndex((entry) => entry.name === input);
    links[id] = { origin_id: from.id, target_id: to.id }; to.inputs[slot].link = id; from.outputs[0].links.push(id);
  };
  const graph = { links, getNodeById: (id) => nodes.get(id) };
  const unet = add(1, "UNETLoader", { unet_name: ref2va ? "MiniMax-H3\minimax_h3_ref2va.safetensors" : "fl2va.safetensors" });
  const lora = add(2, "LoraLoaderModelOnly", { lora_name: "turbo.safetensors" }, ["model"]);
  const clip = add(3, "CLIPLoader", { clip_name: "qwen3vl_32b.safetensors" });
  const vae = add(4, "VAELoader", { vae_name: "minimax_h3_video_vae_fp16.safetensors" });
  const card = add(5, "NGContextImage", { image: "luna.png" });
  const connector = add(6, "NGContextConnector", {}, ["clip", "vae", "model_fl2va", "model_ref2va", "context_image.image_0"]);
  link(unet, lora, "model"); link(lora, connector, ref2va ? "model_ref2va" : "model_fl2va");
  link(clip, connector, "clip"); link(vae, connector, "vae"); link(card, connector, "context_image.image_0");
  for (const node of nodes.values()) node.graph = graph;
  return card;
}

assert.deepEqual(jobs.connectedH3(graphWith()), { model: "MiniMax-H3\minimax_h3_ref2va.safetensors", clip: "qwen3vl_32b.safetensors",
  vae: "minimax_h3_video_vae_fp16.safetensors", ref2va: true }, "the loader behind a LoRA");
assert.equal(jobs.connectedH3(graphWith({ ref2va: false })).ref2va, false, "FL2VA only: still usable, without the ref2v turbo");
const lonely = { id: 9, comfyClass: "NGContextImage", outputs: [{ links: [] }], graph: { links: {}, getNodeById: () => null } };
assert.throws(() => jobs.connectedH3(lonely), /Context Connector/);

// The sheet: the ref2v turbo LoRA when installed (6 steps), six measured frames stitched into one row, one saved picture.
const api = { fetchApi: async () => ({ json: async () => ({ LoraLoaderModelOnly: { input: { required: {
  lora_name: [["other.safetensors", "minimax-h3\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"]] } } } }) }) };
const sheet = await jobs.sheetGraph(api, "luna.png", jobs.connectedH3(graphWith()), "p");
assert.equal(sheet.lora.inputs.lora_name, "minimax-h3\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors");
assert.equal(sheet.sigmas.inputs.steps, 6);
assert.deepEqual(Object.values(sheet).filter((n) => n.class_type === "ImageFromBatch").map((n) => n.inputs.batch_index), jobs.SHEET_FRAMES);
assert.equal(Object.values(sheet).filter((n) => n.class_type === "ImageStitch").length, 5);
assert.equal(sheet.cond.inputs.length, 124);
assert.match(sheet.cond.inputs.prompt, /^<Picture 1>/);
assert.equal(sheet.save.inputs.filename_prefix, "h3-picture-edit/p_sheet");
const noTurbo = { fetchApi: async () => ({ json: async () => ({ LoraLoaderModelOnly: { input: { required: { lora_name: [["other.safetensors"]] } } } }) }) };
const plain = await jobs.sheetGraph(noTurbo, "luna.png", jobs.connectedH3(graphWith()), "p");
assert.equal(plain.lora, undefined); assert.equal(plain.sigmas.inputs.steps, 20);
// The place sheet: the room turning once (10 s, landscape), six views in two rows of three.
const place = await jobs.sheetGraph(api, "tavern.png", jobs.connectedH3(graphWith()), "p", "place");
assert.deepEqual([place.cond.inputs.width, place.cond.inputs.height, place.cond.inputs.length], [1280, 704, 243]);
assert.deepEqual(Object.values(place).filter((n) => n.class_type === "ImageFromBatch").map((n) => n.inputs.batch_index), jobs.PLACE_FRAMES);
assert.deepEqual(Object.values(place).filter((n) => n.class_type === "ImageStitch").map((n) => n.inputs.direction).sort(),
  ["down", "right", "right", "right", "right"]);
assert.equal(place.save.inputs.filename_prefix, "h3-picture-edit/p_place_sheet");
assert.match(place.cond.inputs.prompt, /frozen/);

// SAM on a picture, and a pose picture: the card's own file in, one picture saved under h3-picture-edit.
const mask = jobs.maskGraph("room.png", "mug", "sam3.1.safetensors", "q");
assert.equal(mask.detect.inputs.image[0], "load"); assert.equal(mask.text.inputs.text, "mug");
assert.equal(mask.save.inputs.filename_prefix, "h3-picture-edit/q_mask");
const pose = jobs.structureGraph("pose", "woman.png", { detector: "rtdetr.safetensors", pose: "sdpose.safetensors" }, "r");
assert.equal(pose.save.inputs.images[0], "draw"); assert.equal(pose.save.inputs.filename_prefix, "h3-picture-edit/r_pose");
assert.equal(jobs.structureGraph("canny", "woman.png", {}, "r").edges.class_type, "Canny");
assert.equal(jobs.structureGraph("depth", "woman.png", { depth: "moge.safetensors" }, "r").depth.inputs.model_name, "moge.safetensors");
console.log("picture editor jobs: ok");
