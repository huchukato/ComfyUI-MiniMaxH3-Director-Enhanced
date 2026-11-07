// The Models menus (js/ng/ng_models.js, js/ng/models.json): which file a job uses, what the menu shows and stores,
// and where the gear sits on a card (user 2026-10-19: "a gear on every Context node that needs models").
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";
import { TABLE, modelsApi } from "./fake_models.mjs";

installDom();
const models = await import("../../../js/ng/ng_models.js");
const parts = await import("../../../js/ng/h3c_parts.js");
const { qwenSetup } = await import("../../../js/ng/h3b_queue.js");

// Every entry names its folder, a file, patterns that find that file, and an official link (DA3's pack loads its own).
for (const [purpose, entry] of Object.entries(TABLE)) {
  assert.ok(entry.label && entry.use && entry.folder && entry.file && entry.size, purpose);
  assert.ok(entry.patterns.some((pattern) => new RegExp(pattern, "i").test(entry.file)), `${purpose}: the patterns find ${entry.file}`);
  if (purpose !== "da3") assert.match(entry.url, /^https:\/\/(huggingface\.co\/(Comfy-Org|Kijai\/MiniMax-H3-TAE)|openaipublic\.azureedge\.net)\//, purpose);
  assert.ok(models.MODEL_GROUPS.some(([group]) => group === entry.group), `${purpose}: its group is listed`);
}

// The Director's list of every file: found ones with their file, missing ones named, each with its download and size.
{
  const list = models.modelsList({ h3_fl2va: { ...TABLE.h3_fl2va, auto: TABLE.h3_fl2va.file }, sam3: { ...TABLE.sam3, auto: null } });
  const text = list.filter(Boolean).map((group) => group.innerText).join(" ");
  assert.ok(text.includes(`✓ ${TABLE.h3_fl2va.file}`));
  assert.ok(text.includes(`Missing: ${TABLE.sam3.file} in models/checkpoints`));
  assert.equal(list.filter(Boolean).flatMap((group) => group.byTag("a")).length, 2, "every file has its download");
}
for (const list of [models.STORYBOARD_MODELS, models.PLACE_MODELS, ...Object.values(models.CARD_MODELS)])
  for (const purpose of list) assert.ok(TABLE[purpose], purpose);

// The chosen file while it is there, else Automatic; nothing when the model is missing.
const api = modelsApi({ sam3: ["sam3_finetune.safetensors", "sam3.1_multiplex_fp16.safetensors"], whisper: ["medium.pt", "small.pt"] });
const state = await models.modelState(api, ["sam3", "whisper", "qwen_image"]);
assert.equal(models.resolveModel(state, "sam3", ""), "sam3.1_multiplex_fp16.safetensors");
assert.equal(models.resolveModel(state, "sam3", "sam3_finetune.safetensors"), "sam3_finetune.safetensors");
assert.equal(models.resolveModel(state, "sam3", "gone.safetensors"), "sam3.1_multiplex_fp16.safetensors");
assert.equal(models.resolveModel(state, "whisper", ""), "medium.pt", "the larger Whisper hears sung words better");
assert.equal(models.resolveModel(state, "qwen_image", ""), null);
assert.deepEqual(models.chosenModels('{"sam3": "x"}'), { sam3: "x" });
assert.deepEqual(models.chosenModels("not json"), {});
assert.deepEqual(models.chosenModels("[1]"), {});

// The menu: Automatic first with what it found, the folder's files, a tick for the file in use, the missing file with its link.
const changes = [];
const rows = models.modelsMenu(state, { sam3: "gone.safetensors" }, (...change) => changes.push(change));
assert.equal(rows.length, 3);
const pick = rows[0].byTag("select")[0];
assert.deepEqual(pick.children.map((option) => option.innerText),
  ["Automatic: sam3.1_multiplex_fp16.safetensors", "sam3_finetune.safetensors", "sam3.1_multiplex_fp16.safetensors"]);
assert.ok(rows[0].innerText.includes("✓ sam3.1_multiplex_fp16.safetensors"));
assert.ok(rows[0].innerText.includes("gone.safetensors is gone; Automatic is used."));
pick.onchange({ target: { value: "sam3_finetune.safetensors" } });
assert.deepEqual(changes.at(-1), ["sam3", "sam3_finetune.safetensors"]);
assert.ok(rows[2].innerText.includes("Qwen Image 2.1 needs qwen_image_2.1_int8_convrot.safetensors in models/diffusion_models (7.3 GB)."));
assert.equal(rows[2].byTag("a")[0].attributes.href, TABLE.qwen_image.url);
assert.ok(models.modelsMenu(null, {}, () => {})[0].innerText.includes("Looking for models"));
assert.ok(models.modelsMenu({}, {}, () => {})[0].innerText.includes("did not answer"), "a failed list is said, not an empty box");

// Qwen for the Storyboard: all three files or one error naming each missing one; the board's choice wins.
await assert.rejects(qwenSetup(modelsApi()), /Qwen Image 2\.1 needs .* Qwen Image text encoder needs .* Qwen Image VAE needs/);
const qwen = modelsApi({ qwen_image: ["my_qwen.safetensors", "qwen_image_2.1_bf16.safetensors"], qwen_encoder: ["qwen3vl_8b_fp8_scaled.safetensors"],
  qwen_vae: ["qwen_image_2.1_vae_bf16.safetensors"] });
assert.deepEqual(await qwenSetup(qwen), { model: "qwen_image_2.1_bf16.safetensors", encoder: "qwen3vl_8b_fp8_scaled.safetensors",
  vae: "qwen_image_2.1_vae_bf16.safetensors" });
assert.equal((await qwenSetup(qwen, { qwen_image: "my_qwen.safetensors" })).model, "my_qwen.safetensors");

// The gear: on the Video, Audio and Image cards (their jobs use extra models; the Image card's editor since 2026-10-20).
function recorder() {
  const calls = [];
  return { calls, actions: new Proxy({}, { get: (_t, name) => (...args) => { calls.push([name, ...args]); } }) };
}
const card = (media, extra = {}) => ({ media, values: { name: "x", [media]: "f" }, files: ["f"], analyzed: false, node: { properties: {} }, ...extra });
for (const [media, has] of [["video", true], ["audio", true], ["image", true]]) {
  const row = parts.topRow(card(media), recorder().actions);
  assert.equal(row.find((node) => node.attributes?.["aria-label"] === "Models").length, has ? 1 : 0, media);
}
const { actions, calls } = recorder();
parts.topRow(card("audio"), actions).find((node) => node.attributes?.["aria-label"] === "Models")[0].onclick();
assert.deepEqual(calls.at(-1), ["toggleModels"]);
// the Image card's editor button sits beside it, lit while the card has an edit mask
const editor = (opts) => parts.topRow(card("image", { opts }), recorder().actions).find((node) => node.attributes?.["aria-label"] === "Edit picture")[0];
assert.ok(editor({}));
assert.equal(editor({ edit_mask: "h3-picture-edit/m.png" }).className, "h3c-btn on");
assert.equal(parts.modelsBox(card("audio"), actions), null, "closed: nothing");
const open = parts.modelsBox(card("audio", { modelsOpen: true, models: await models.modelState(api, ["whisper"]),
  node: { properties: { ng_models: { whisper: "small.pt" } } } }), actions);
assert.equal(open.byTag("select")[0].value, "small.pt");
open.byTag("select")[0].onchange({ target: { value: "" } });
assert.deepEqual(calls.at(-1), ["setModel", "whisper", ""]);
console.log("ng models ok");
