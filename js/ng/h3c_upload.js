// The card owns its file picker: some frontend versions expose the native video upload as a selector, not a button callback.
import { h } from "./h3s_dom.js";
import { comboOptions } from "./h3b_queue.js";

// Upload/import responses use '/', but Windows node schemas list '\\'. The
// preview accepts both; native prompt validation requires the exact combo value.
export async function videoSource(api, source) {
  const choices = await comboOptions(api, "NGContextVideo", "video");
  const normalize = (value) => String(value).replaceAll("\\", "/");
  const found = choices.find((value) => normalize(value) === normalize(source));
  if (!found) throw new Error("The video was saved, but ComfyUI does not list it. Refresh node definitions and select the saved file.");
  return found;
}

export function videoUpload(S, actions) {
  const input = h("input", { type: "file", accept: "video/*", "aria-label": "Upload video", hidden: true,
    onchange: (event) => { const file = event.target.files?.[0]; if (file) actions.uploadVideo(file); } });
  return h("span", { class: "h3c-row", style: { flex: "0 0 auto" } }, input,
    h("button", { class: "h3c-btn", disabled: Boolean(S.busy), onclick: () => input.click() }, "Upload"));
}

export async function uploadVideo(api, file) {
  const data = new FormData();
  data.append("image", file); data.append("type", "input"); data.append("subfolder", "h3-video");
  const response = await api.fetchApi("/upload/image", { method: "POST", body: data });
  if (!response.ok) throw new Error("Video upload failed. Choose a video file and try again.");
  const saved = await response.json();
  return videoSource(api, [saved.subfolder, saved.name].filter(Boolean).join("/"));
}
