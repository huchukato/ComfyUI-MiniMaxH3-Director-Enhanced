// An inpaint card keeps its source video; its separate mask uses the same file time and source offset.
import { h } from "./h3s_dom.js";
import { mediaURL } from "./h3c_media.js";

export function activeMask(options, source) {
  return !options.control_result || options.control_result === source ? options.control_mask || "" : "";
}

export function maskBox(S, actions) {
  const file = activeMask(S.opts, S.values.video), busy = Boolean(S.busy);
  const files = [...new Set([file, ...(S.files || [])].filter(Boolean))];
  const choose = h("select", { class: "h3c-in", "aria-label": "Mask video", disabled: busy,
    onchange: (event) => actions.setMask(event.target.value) }, h("option", { value: "" }, "Choose a ready mask video …"),
    files.map((value) => h("option", { value }, value)));
  choose.value = file;
  const shape = h("select", { class: "h3c-in", "aria-label": "Mask shape", disabled: busy,
    onchange: (event) => actions.setOptions({ mask_shape: event.target.value }) },
    h("option", { value: "box" }, "Bounding box (recommended)"), h("option", { value: "outline" }, "Silhouette"));
  shape.value = S.opts.mask_shape || "box";
  if (file && S.els.mask.getAttribute("src") !== mediaURL(file, S.api)) S.els.mask.src = mediaURL(file, S.api);
  return h("div", { class: "h3c-box" },
    h("span", { class: "h3c-hint" }, "The main video is your source. White in the mask is regenerated; black supplies the background."),
    h("label", { class: "h3c-lbl" }, "What to mask", h("input", { class: "h3c-in", value: S.opts.mask_prompt ?? "person", disabled: busy,
      "aria-label": "Mask object", placeholder: "person, red ball …", onchange: (event) => actions.setOptions({ mask_prompt: event.target.value }) })),
    h("button", { class: "h3c-btn", disabled: busy || !S.values.video, onclick: actions.generateControl }, S.busy === "control" ? "Generating …" : "Generate mask (SAM3)"),
    h("div", { class: "h3c-row" }, choose, h("input", { type: "file", accept: "video/*", "aria-label": "Upload mask video", disabled: busy,
      onchange: (event) => { const uploaded = event.target.files?.[0]; if (uploaded) actions.uploadMask(uploaded); } })),
    file ? h("div", { class: "h3c-preview" }, S.els.mask) : h("span", { class: "h3c-hint" }, "Generate or choose a mask before rendering this card."),
    h("div", { class: "h3c-row" }, shape, h("label", { class: "h3c-lbl" }, "Grow (pixels)", h("input", { class: "h3c-in", type: "number", min: 0,
      max: 256, step: 1, value: S.opts.mask_grow ?? 16, disabled: busy, "aria-label": "Mask grow",
      onchange: (event) => actions.setOptions({ mask_grow: Number(event.target.value) }) }))),
    h("span", { class: "h3c-hint" }, "The preview shows the raw mask. The render uses the selected shape and grow at its output size. A box gives a new figure more room than the source silhouette."),
    h("span", { class: "h3c-hint" }, "Mask and source must start at the same file time. The card range and timeline offset apply to both; shorter files hold their last frame."));
}

export async function uploadMask(api, file) {
  const data = new FormData();
  data.append("image", file); data.append("type", "input"); data.append("subfolder", "h3-control");
  const response = await api.fetchApi("/upload/image", { method: "POST", body: data });
  if (!response.ok) throw new Error("Mask upload failed. Upload a video through ComfyUI or choose an existing mask.");
  const saved = await response.json();
  return [saved.subfolder, saved.name].filter(Boolean).join("/");
}
