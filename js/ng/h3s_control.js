// ControlNet settings and the selected control clip, separate from Shot bindings and audio roles.
import { h, field, icon } from "./h3s_dom.js";
import { span } from "./h3s_model.js";

export function controlSettings(S, actions) {
  if (!S.contexts.some((entry) => entry.media === "video" && entry.usage.includes("control"))) return null;
  const number = (name, max, step, fallback, label) => h("input", { class: "h3s-in", type: "number", min: 0, max, step,
    value: S.values[name] ?? fallback, "aria-label": label, onchange: (event) => actions.setWidget(name, Number(event.target.value)) });
  return h("section", { class: "h3s-card" }, h("strong", {}, "ControlNet"),
    S.controlConnected ? [
      field("Strength", number("control_strength", 10, 0.01, 1, "Control strength")),
      h("span", { class: "h3s-lbl" }, "1 follows the source closely; try 0.5 to keep your figure's own shape."),
      h("details", { open: Boolean(S.controlAdvanced), ontoggle: (event) => {
        if (event.currentTarget.isConnected) S.controlAdvanced = event.currentTarget.open;
      } }, h("summary", {}, "Denoising range (advanced)"),
        field("Start (0–1)", number("control_start", 1, 0.001, 0, "Control denoising start")),
        field("End (0–1)", number("control_end", 1, 0.001, 1, "Control denoising end")),
        h("span", { class: "h3s-lbl" }, "These are fractions of denoising, not seconds of the video."))
    ] : h("span", { class: "h3s-warn" }, "Connect ModelPatchLoader (H3 Fun ControlNet-Union 2.0) to the Context Connector's model_patch."),
    h("span", { class: "h3s-lbl" }, "Only parts with control clips use ControlNet. For partial coverage H3 holds edge frames to the render-part edges."),
    (S.plan?.issues || []).filter((issue) => issue.code.startsWith("control_")).map((issue) => h("span", { class: "h3s-warn", style: { fontSize: "12px" } },
      `${issue.ref ? issue.ref + ": " : ""}${issue.text}`)));
}

export function controlPanel(S, actions, clip) {
  const entry = S.byId.get(clip.context_id);
  const number = (key, label) => field(label, h("input", { class: "h3s-in", type: "number", min: 0, step: 0.1, value: clip[key] || 0,
    "aria-label": "Control clip " + key, onchange: (event) => actions.setControl(clip.id, key, Number(event.target.value)) }));
  return h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },
    h("div", { class: "h3s-row" }, h("strong", {}, entry?.name || "Not connected"), h("span", { class: "h3s-lbl" }, entry?.controlKind || "Control"),
      h("span", { class: "h3s-grow" }), h("button", { class: "h3s-btn ghost", "aria-label": "Remove control clip", onclick: () => actions.deleteControl(clip.id) }, icon("trash"))),
    number("start", "Start (s)"), number("end", "End (s)"), number("offset", "From second in file"),
    h("span", { class: "h3s-lbl" }, "Clips cannot overlap. A partly covered render part holds the first and last control frames to its edges; gaps hold the preceding frame."),
    ...(S.plan?.chunks || []).filter((part) => part.start_s < clip.end && part.end_s > clip.start).map((part) =>
      h("span", { class: "h3s-item" }, `Part ${part.index + 1}: control active over ${span(part.start_s, part.end_s)}`)));
}
