// The pieces every Context card is made of. Each takes the card state S and the card's actions and returns elements;
// the card (h3c_card.js) owns the state and redraws on change.
import { h, icon } from "./h3s_dom.js";
import { CONTENT, USAGE, KEEP, KEEP_LEVELS, roleHint } from "./h3c_model.js";
import { CARD_MODELS, modelsMenu } from "./ng_models.js";
import { videoUpload } from "./h3c_upload.js";

export const box = (caption, ...children) => h("div", { class: "h3c-box" }, caption ? h("div", { class: "h3c-cap" }, caption) : null, ...children);
const cap = (text, ...tools) => h("div", { class: "h3c-cap" }, text, h("span", { class: "h3c-grow" }), ...tools);

// Name, file (with ComfyUI's own upload) and whether the AI has looked at this card.
export function topRow(S, actions) {
  const name = h("input", { class: "h3c-in", value: S.values.name || "", placeholder: `Name, e.g. ${S.media === "image" ? "Alice" : S.media === "audio" ? "Alice voice" : "Camera move"}`,
    "aria-label": "Name", oninput: (event) => actions.set("name", event.target.value, false) });
  const badge = h("span", { class: S.analyzed ? "h3c-badge done" : "h3c-badge" }, S.analyzed ? "✦ Analyzed" : "Not analyzed");
  if (S.media === "text") return h("div", { class: "h3c-row" }, h("div", { style: { flex: "1 1 auto", display: "grid" } }, name), badge);
  // minWidth 0: a select is as wide as its longest file name and pushed Upload over the badge (user 2026-10-19)
  const file = h("select", { class: "h3c-in", style: { flex: "1 1 auto", minWidth: "0" }, "aria-label": "File", onchange: (event) => actions.set(S.media, event.target.value) },
    S.files.map((value) => h("option", { value }, value)));
  file.value = S.values[S.media] || "";
  const gear = CARD_MODELS[S.media] ? h("button", { class: "h3c-btn", title: "Models this card uses", "aria-label": "Models",
    "aria-pressed": String(Boolean(S.modelsOpen)), onclick: actions.toggleModels }, icon("gear", 14)) : null;
  return h("div", { class: "h3c-grid", style: { gridTemplateColumns: "minmax(0,1fr) minmax(0,1.2fr) auto" } }, name,
    h("div", { class: "h3c-row", style: { flexWrap: "nowrap" } }, file,
      S.media === "video" ? videoUpload(S, actions) : h("button", { class: "h3c-btn", style: { flex: "0 0 auto" }, onclick: actions.upload }, "Upload")),
    h("div", { class: "h3c-row", style: { flexWrap: "nowrap" } }, badge, S.media === "image" ? editButton(S, actions) : null, gear));
}

// The editor (h3c_editor.js): mask, structure picture, character sheet. Lit while the card has an edit mask.
function editButton(S, actions) {
  const masked = Boolean(S.opts?.edit_mask);
  return h("button", { class: masked ? "h3c-btn on" : "h3c-btn", title: masked ? "Edit: this card has an edit mask" : "Edit: mask, structure, character sheet",
    "aria-label": "Edit picture", disabled: !S.values.image, onclick: actions.openEditor }, icon("brush", 14));
}

// The card's Models menu (gear in the top row): which file each extra model of this card is (ng_models.js).
export function modelsBox(S, actions) {
  return S.modelsOpen ? box("Models", ...modelsMenu(S.models, S.node.properties.ng_models || {}, actions.setModel)) : null;
}

// Analyze and, while it runs, Cancel. On media cards it sits on "What is in it"; the Text card has it on "Use as".
const analyzeTools = (S, actions) => [h("button", { class: "h3c-btn ai", disabled: !S.ai || Boolean(S.busy), title: S.ai ? "Ask the AI what this is; nothing changes until you accept."
  : "Connect an H3 AI Loader to this card or to the Context Connector.", onclick: actions.analyze }, S.busy === "analyze" ? "Analyzing …" : "✦ Analyze"),
  S.busy === "analyze" ? h("button", { class: "h3c-btn", onclick: actions.cancel }, "Cancel") : null];

export function contentBox(S, actions) {
  return h("div", { class: "h3c-box" },
    cap("What is in it", ...analyzeTools(S, actions)),
    CONTENT[S.media].map(([key, label]) => {
      const on = S.content.includes(key);
      return h("button", { class: "h3c-chk", "aria-pressed": String(on), onclick: () => actions.toggleContent(key) },
        h("span", { class: on ? "h3c-box-i on" : "h3c-box-i" }, on ? "✓" : ""), label);
    }));
}

export function usageBox(S, actions, columns = 1) {
  const hint = roleHint(S.media, S.usage, S.mode);
  return h("div", { class: "h3c-box" }, S.media === "text" ? cap("Use as (default)", ...analyzeTools(S, actions)) : h("div", { class: "h3c-cap" }, "Use as (default)"),
    h("div", { style: { display: "grid", gridTemplateColumns: `repeat(${columns},minmax(0,1fr))`, gap: "2px 6px" } },
      // The story belongs in the Director's Prompt: a Text card offers "Scene" only while it still has it (2026-10-18).
      USAGE[S.media].filter(([key]) => !(S.media === "text" && key === "scene" && S.usage !== "scene")).map(([key, label, note]) => h("button", { class: S.usage === key ? "h3c-radio on" : "h3c-radio", "aria-pressed": String(S.usage === key),
        onclick: () => actions.pickUsage(key) }, h("span", { class: "h3c-rd" }), h("span", { class: "h3c-grow" }, label), note ? h("span", { class: "h3c-lbl" }, note) : null))),
    hint.text ? h("span", { class: hint.warn ? "h3c-hint h3c-warn" : "h3c-hint" }, hint.text) : null);
}

export function keepBox(S, actions) {
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Keep in the video"),
    KEEP.map(([key, label]) => {
      const current = S.opts.preserve?.[key] || (key === "background" ? "ignore" : S.values.preserve || "high");
      return h("div", { style: { display: "grid", gridTemplateColumns: "88px 1fr", alignItems: "center", gap: "8px" } }, h("span", {}, label),
        h("div", { class: "h3c-segs" }, KEEP_LEVELS[key].map((level) => h("button", { class: current === level ? "on" : "", "aria-label": `${label} ${level}`,
          onclick: () => actions.setKeep(key, level) }, level[0].toUpperCase() + level.slice(1)))));
    }),
    h("span", { class: "h3c-hint" }, "Guidance for H3, not pixel-exact."));
}

// "Belongs to": the Subjects (independent reference pictures) this asset is presented with. Empty = independent.
export function ownerBox(S, actions, hint) {
  const current = S.owners.current;
  const choose = h("select", { class: "h3c-in", "aria-label": "Belongs to", onchange: (event) => actions.setOwner(event.target.value) },
    h("option", { value: "" }, S.media === "image" ? "Independent (its own figure)" : "Independent"),
    S.owners.choices.map((choice) => h("option", { value: choice.id }, choice.name)));
  choose.value = current[0] || "";
  const text = current.length ? `Presented together with ${S.owners.choices.filter((choice) => current.includes(choice.id)).map((choice) => choice.name).join(" + ") || current.join(", ")}.`
    : hint;
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Belongs to"), choose, h("span", { class: "h3c-hint" }, text));
}

export function descriptionBox(S, actions) {
  const hint = S.media === "video" && S.usage === "control"
    ? "A note about this steering source; describe the target figure and scene in the shot."
    : "One sentence about what this is; it goes into the prompt.";
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Description"),
    h("textarea", { class: "h3c-in", rows: 3, value: S.values.description || "", placeholder: hint,
      title: hint,
      "aria-label": "Description", oninput: (event) => actions.set("description", event.target.value, false) }));
}

export function suggestionBox(S, actions) {
  if (!S.suggestion) return null;
  // Roles are shown by the label of the button Accept will press, not by their stored key.
  const label = (name, value) => ({ content: CONTENT, usage: USAGE }[name]?.[S.media]?.find(([key]) => key === value)?.[1] || value);
  const lines = Object.entries(S.suggestion.fields).map(([name, value]) => `${{ description: "Description", content: "Content", usage: "Use as" }[name] || name}: ${label(name, value)}`);
  return h("div", { class: "h3c-box h3c-suggest" }, h("span", { class: "h3c-lbl", style: { color: "#C9BBFF" } }, "AI suggestion (nothing changes until you accept)"),
    lines.map((line) => h("span", { style: { color: "#ECE6FF" } }, line)),
    S.suggestion.why ? h("span", { class: "h3c-hint" }, S.suggestion.why) : null,
    h("div", { class: "h3c-row" }, h("button", { class: "h3c-btn ai", onclick: actions.accept }, "Accept"), h("button", { class: "h3c-btn", onclick: actions.discard }, "Discard")));
}

export function presetRow(S, actions) {
  const save = h("button", { class: "h3c-btn", onclick: actions.savePreset, disabled: !S.presetName.trim() }, "Save");
  // Typing does not redraw the card (the caret would jump), so the button follows the field itself.
  const name = h("input", { class: "h3c-in", style: { flex: "1 1 120px" }, value: S.presetName, placeholder: "Preset name", "aria-label": "Preset name",
    oninput: (event) => { actions.presetName(event.target.value); save.disabled = !event.target.value.trim(); } });
  const list = h("select", { class: "h3c-in", style: { flex: "1 1 120px" }, "aria-label": "Saved presets" },
    S.presets.length ? S.presets.map((value) => h("option", { value }, value)) : h("option", { value: "" }, "No presets yet"));
  list.value = S.presets.includes(S.presetName) ? S.presetName : S.presets[0] || "";
  const color = h("input", { type: "color", class: "h3c-swatch", value: S.accent, title: "Context colour", "aria-label": "Context colour",
    oninput: (event) => actions.set("color", event.target.value, false) });
  return h("div", { class: "h3c-row" }, h("span", { class: "h3c-lbl" }, "Preset"), name,
    save, list,
    h("button", { class: "h3c-btn", onclick: () => actions.loadPreset(list.value), disabled: !S.presets.length }, "Load"),
    h("span", { class: "h3c-lbl", style: { marginLeft: "6px" } }, "Color"), color,
    h("button", { class: "h3c-btn", onclick: actions.autoColor, title: "Pick the colour automatically" }, "Auto"));
}

export function statusLine(S) {
  return S.status ? h("div", { class: "h3c-use" }, h("span", { class: S.statusWarn ? "h3c-hint h3c-warn" : "h3c-hint" }, S.status)) : null;
}
