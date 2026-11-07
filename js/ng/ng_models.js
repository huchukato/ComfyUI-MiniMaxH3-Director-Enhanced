// Every model file the pack uses, H3's own and the extra ones (SAM3, Qwen Image, Whisper, ...): js/ng/models.json, read by
// adapters/model_files.py too.
// A card's Models menu stores {purpose: file} in its node (properties.ng_models, the Director in its "models" widget);
// an empty choice is Automatic: the official name or the first file that fits (the server decides, one place for the patterns).
import { h } from "./h3s_dom.js";

export const CARD_MODELS = { image: ["sam3", "pose_detector", "pose", "moge"], video: ["sam3", "pose_detector", "pose", "moge", "da3"], audio: ["whisper"] };
export const STORYBOARD_MODELS = ["qwen_image", "qwen_encoder", "qwen_vae", "background_removal"];
export const PLACE_MODELS = ["sam3", "qwen_image", "qwen_encoder", "qwen_vae"];

export async function modelState(api, purposes) {
  return (await api.fetchApi(`/ng/models?purposes=${purposes.join(",")}`)).json();
}

// The file a job uses: the chosen one while it is there, else the automatic one (null when the model is missing).
export function resolveModel(state, purpose, chosen) {
  const entry = state?.[purpose];
  if (!entry) return null;
  return chosen && entry.files.includes(chosen) ? chosen : entry.auto;
}

export async function findModel(api, purpose, chosen) {
  return resolveModel(await modelState(api, [purpose]), purpose, chosen);
}

export function missingText(entry) {
  return `${entry.label} needs ${entry.file} in models/${entry.folder}${entry.size ? ` (${entry.size})` : ""}.`;
}

// The Director's list of every file: grouped, each found (with its file) or missing, always with its download.
export const MODEL_GROUPS = [["h3", "H3, every workflow"], ["turbo", "Turbo"], ["control", "Control videos and masks"],
  ["pictures", "Pictures, storyboard and places"], ["sound", "Sound"]];

export function modelsList(state, css = "h3s") {
  if (!state) return [h("span", { class: `${css}-lbl` }, "Looking for models …")];
  return MODEL_GROUPS.map(([group, title]) => {
    const rows = Object.values(state).filter((entry) => entry.group === group).map((entry) => h("div", { class: `${css}-model` },
      h("span", { class: "h3s-strong" }, entry.label), h("span", { class: `${css}-lbl` }, entry.use),
      entry.auto ? h("span", { class: `${css}-lbl`, style: { color: "#7FD3A0" } }, `✓ ${entry.auto}`)
        : h("span", { class: `${css}-warn`, style: { fontSize: "12px" } }, `Missing: ${entry.file} in models/${entry.folder}`),
      entry.url ? h("a", { href: entry.url, target: "_blank", rel: "noopener", style: { color: "#8CC8FF" } }, `Download (${entry.size})`)
        : h("span", { class: `${css}-lbl` }, entry.note || "")));
    return rows.length ? h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } },
      h("span", { class: `${css}-lbl`, style: { textTransform: "uppercase", letterSpacing: "0.04em" } }, title), ...rows) : null;
  });
}

export function chosenModels(text) {
  try { const value = JSON.parse(text || "{}"); return value && typeof value === "object" && !Array.isArray(value) ? value : {}; } catch { return {}; }
}

// One row per purpose: what it is for, a choice of the folder's files (Automatic first) and whether a file is there.
// css is the card family's class prefix ("h3c" on Context cards, "h3s" in the Studio and the Storyboard).
export function modelsMenu(state, chosen, onChange, css = "h3c") {
  if (!state) return [h("span", { class: `${css}-lbl` }, "Looking for models …")];
  if (!Object.keys(state).length) return [h("span", { class: `${css}-warn` }, "ComfyUI did not answer with the model list; restart it after updating H3 Director.")];
  return Object.entries(state).map(([purpose, entry]) => {
    const used = resolveModel(state, purpose, chosen[purpose]);
    const lost = chosen[purpose] && !entry.files.includes(chosen[purpose]);
    const pick = h("select", { class: `${css}-in`, "aria-label": `${entry.label} file`, onchange: (event) => onChange(purpose, event.target.value) },
      h("option", { value: "" }, `Automatic${entry.auto ? `: ${entry.auto}` : " (none found)"}`),
      ...entry.files.map((name) => h("option", { value: name }, name)));
    pick.value = lost ? "" : chosen[purpose] || "";
    const status = used ? h("span", { class: `${css}-lbl`, style: { color: "#7FD3A0" } }, `✓ ${used}`)
      : h("span", { class: `${css}-warn`, style: { fontSize: "12px" } }, missingText(entry), " ",
        entry.url ? h("a", { href: entry.url, target: "_blank", rel: "noopener", style: { color: "#8CC8FF" } }, "Download") : null);
    return h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } },
      h("span", { style: { fontWeight: 600 } }, entry.label, h("span", { class: `${css}-lbl`, style: { marginLeft: "6px" } }, entry.use)),
      pick, status, lost ? h("span", { class: `${css}-warn`, style: { fontSize: "12px" } }, `${chosen[purpose]} is gone; Automatic is used.`) : null,
      entry.note ? h("span", { class: `${css}-lbl` }, entry.note) : null);
  });
}
