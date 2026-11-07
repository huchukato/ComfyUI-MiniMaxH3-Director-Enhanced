import { h } from "./h3s_dom.js";
import { mediaURL } from "./h3c_media.js";
import { maskBox } from "./h3c_mask.js";

export function controlBox(S, actions) {
  if (S.usage !== "control") return null;
  const kind = S.opts.control_kind || "canny";
  const choose = h("select", { class: "h3c-in", "aria-label": "Control kind", disabled: Boolean(S.busy),
    onchange: (event) => actions.controlKind(event.target.value) },
    ["canny", "pose", "depth", "mask"].map((value) => h("option", { value }, { canny: "Canny", pose: "Pose", depth: "Depth", mask: "Inpaint (mask + source)" }[value])));
  choose.value = kind;
  if (kind === "mask") return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Control video"), choose, maskBox(S, actions));
  const engine = h("select", { class: "h3c-in", "aria-label": "Depth engine", disabled: Boolean(S.busy),
    onchange: (event) => actions.controlEngine(event.target.value) },
    h("option", { value: "moge2" }, "MoGe 2"), S.da3 ? h("option", { value: "da3" }, "Depth Anything 3") : null);
  engine.value = S.depthEngine || "moge2";
  const original = S.opts.control_result === S.values.video ? S.opts.control_original : "";
  if (original && S.els.original.getAttribute("src") !== mediaURL(original, S.api)) S.els.original.src = mediaURL(original, S.api);
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Control video"),
    h("div", { class: "h3c-row" }, choose, kind === "depth" ? engine : null,
      h("button", { class: "h3c-btn", disabled: Boolean(S.busy) || !S.values.video, onclick: actions.generateControl },
        S.busy === "control" ? "Generating …" : `Generate ${kind === "canny" ? "Canny" : kind === "pose" ? "Pose" : "Depth"}`)),
    h("span", { class: "h3c-hint" }, "Load a ready control video and choose its kind, or load a normal video and press Generate. Place the result on the Director's Control lane."),
    original ? h("details", { ontoggle: actions.resize }, h("summary", {}, "Original video (compare)"), h("div", { class: "h3c-preview" }, S.els.original)) : null,
    h("span", { class: "h3c-hint" }, "Generation runs once through ComfyUI's queue and saves the result. Rendering reuses that file."));
}
