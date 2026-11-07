import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const { videoUpload, uploadVideo, videoSource } = await import("../../../js/ng/h3c_upload.js");
const { topRow } = await import("../../../js/ng/h3c_parts.js");
const files = [], view = videoUpload({ busy: false }, { uploadVideo: (file) => files.push(file) });
const picker = view.byTag("input")[0];
let opened = 0;
picker.click = () => opened++;
view.button("Upload").onclick();
assert.equal(opened, 1, "Upload opens the card's file picker even when the native upload widget has no button callback");
const file = new Blob(["video"], { type: "video/mp4" });
picker.onchange({ target: { files: [file] } });
assert.deepEqual(files, [file]);
assert.equal(picker.getAttribute("accept"), "video/*");
const card = topRow({ media: "video", values: { name: "Clip", video: "clip.mp4" }, files: ["clip.mp4"] }, {});
assert.equal(card.byTag("input").filter((entry) => entry.getAttribute("type") === "file").length, 1);
let sent;
const api = { fetchApi: async (endpoint, options) => {
  if (endpoint === "/object_info/NGContextVideo") return { json: async () => ({ NGContextVideo: { input: { required: { video: [["h3-video/clip.mp4"]] } } } }) };
  sent = { endpoint, ...options }; return { ok: true, json: async () => ({ subfolder: "h3-video", name: "clip.mp4" }) };
} };
assert.equal(await uploadVideo(api, file), "h3-video/clip.mp4");
assert.equal(sent.endpoint, "/upload/image");
assert.equal(sent.method, "POST");
assert.equal(sent.body.get("type"), "input");
assert.equal(sent.body.get("subfolder"), "h3-video");
assert.equal(sent.body.get("image").type, "video/mp4");
await assert.rejects(uploadVideo({ fetchApi: async () => ({ ok: false }) }, file), /Video upload failed/);
const windows = { fetchApi: async () => ({ json: async () => ({ NGContextVideo: { input: { required: {
  video: ["COMBO", { options: ["h3-video\\clip.mp4", "h3-control\\new guide.mp4"] }] } } } }) }) };
assert.equal(await videoSource(windows, "h3-video/clip.mp4"), "h3-video\\clip.mp4", "Windows uploads must use a value accepted by the native combo");
assert.equal(await videoSource(windows, "h3-control/new guide.mp4"), "h3-control\\new guide.mp4", "generated Control videos have the same file contract");
await assert.rejects(videoSource(windows, "h3-video/unlisted.mp4"), /ComfyUI.*list/);
console.log("video upload ok");
