// The gear: every setting a first video does not need, in one window instead of in the Studio's page. The page keeps the
// Prompt, Content, Timeline, Mode, Turbo on/off, Duration and Resolution (user, 2026-10-18: "much less text, a gear menu
// with all presets"). A manual prompt is shown on the page as long as it is set, because it replaces every part's prompt.
import { h, icon, field, select, tip } from "./h3s_dom.js";
import { fmt, turboProfile } from "./h3s_model.js";
import { ASPECTS, RESIZE, nearestAspect, canvasInfo, isAuto, NATIVE_MP } from "./h3s_canvas.js";
import { controlSettings } from "./h3s_control.js";
import { PLACE_MODELS, chosenModels, modelState, modelsMenu, modelsList } from "./ng_models.js";

const CONTINUITY = [["video_audio", "Continue picture and sound"], ["video", "Continue picture only"], ["none", "Hard cuts"]];
// Sampler + scheduler pairs that spoil H3 pictures: res_multistep + beta overexposed and oversharpened (own A/B, 2026-10-20, M16);
// dpmpp_2m_sde + karras is reported to leave noise (H3 community notes, not measured here).
const BAD_PAIRS = { "res_multistep|beta": "res_multistep with beta overexposes and oversharpens H3 (measured). Use simple.",
  "dpmpp_2m_sde|karras": "dpmpp_2m_sde with karras is reported to leave noise in H3. res_multistep + simple is the tested pair." };
// Spectrum is the user's own install (xmarre/ComfyUI-Spectrum-MiniMax-H3); the switch shows only when ComfyUI knows its node.
const spectrumInstalled = () => Boolean(globalThis.LiteGraph?.registered_node_types?.SpectrumApplyMiniMaxH3);
const SPECTRUM_HINT = "Forecasts some sampling steps instead of computing them: about a third faster at 20 steps, same quality "
  + "in our test. Only with Turbo off.";
const STYLES = [["None", "No style"], ["Cinematic", "Cinematic"], ["Anime", "Anime"], ["Documentary", "Documentary"], ["Photorealistic", "Photorealistic"]];

function withCurrent(options, value, label) {
  return options.some(([v]) => String(v) === String(value)) ? options : [...options, [String(value), label(value)]];
}

function number(value, onchange, props = {}) {
  return h("input", { class: "h3s-in", type: "number", value, onchange: (event) => onchange(Number(event.target.value)), ...props });
}

function section(title, hint, ...children) {
  return [h("h3", {}, title, " ", hint ? tip(hint) : null), h("div", { class: "h3s-modal-sec" }, ...children.flat().filter(Boolean))];
}

function switchRow(on, label, hint, onclick) {
  return h("button", { class: "h3s-toggle", "aria-pressed": String(on), onclick },
    h("span", { class: on ? "h3s-switch on" : "h3s-switch" }), h("span", { class: "h3s-strong" }, label), tip(hint));
}

function videoSection(S, actions) {
  const v = S.values, [info, tone] = canvasInfo(v.width, v.height);
  const mp = (isAuto(v.width, v.height) ? NATIVE_MP : v.width * v.height / 1e6).toFixed(2);
  const parts = withCurrent([["0", "Auto"], ["5", "5 s"], ["8", "8 s"], ["10", "10 s"], ["15", "15 s"], ["30", "30 s (small sizes)"]], v.chunk_seconds, (d) => fmt(Number(d)));
  return section("Video", "H3 renders the video in parts of up to about 10 s that continue into each other.",
    field("Render part", select(parts, String(v.chunk_seconds), (value) => actions.setWidget("chunk_seconds", Number(value)))),
    field("Width", number(isAuto(v.width, v.height) ? "" : v.width, (value) => actions.setSize("width", value), { step: "32", min: "0", placeholder: "auto", style: { width: "88px" } })),
    field("Height", number(isAuto(v.width, v.height) ? "" : v.height, (value) => actions.setSize("height", value), { step: "32", min: "0", placeholder: "auto", style: { width: "88px" } })),
    field("Aspect ratio", select([["", "–"], ...ASPECTS.map(([label]) => [label, label])], nearestAspect(v.width, v.height), actions.setAspect)),
    field("Megapixels", number(mp, actions.setMegapixels, { step: "0.05", min: "0.1", max: "8", style: { width: "88px" } })),
    field("Fit pictures", select(RESIZE, v.resize_method, (value) => actions.setWidget("resize_method", value))),
    field("Reference images", select([["match", "Like video (fast)"], ["max", "Large, 2048 px (more identity, slower)"]], v.ref_image_size,
      (value) => actions.setWidget("ref_image_size", value), { disabled: v.mode === "fl2va" })),
    h("span", { class: tone === "warn" ? "h3s-warn" : "h3s-muted", style: { flex: "1 1 260px", fontSize: "13px" } }, info));
}

function samplingSection(S, actions) {
  const v = S.values, set = (name) => (value) => actions.setWidget(name, value);
  const sampler = (S.options.sampler_name || [v.sampler_name]).map((value) => [value, value]);
  const scheduler = (S.options.scheduler || [v.scheduler]).map((value) => [value, value]);
  return section("Sampling", v.turbo ? "With a known turbo LoRA its own steps, sampler and scheduler are used; these apply to unknown LoRAs and Turbo off." : "",
    field("Seed", h("span", { class: "h3s-row", style: { gap: "6px", flexWrap: "nowrap" } }, number(v.seed, set("seed"), { style: { width: "130px" } }),
      h("button", { class: "h3s-btn", title: "Random seed", "aria-label": "Random seed", onclick: () => actions.setWidget("seed", Math.floor(Math.random() * 1e9)) }, icon("dice")))),
    field("Steps", number(v.steps, (value) => actions.setWidget("steps", Math.max(1, Math.min(100, Math.round(value) || 1))), { min: "1", max: "100", style: { width: "80px" } })),
    field("Sampler", select(sampler, v.sampler_name, set("sampler_name"))),
    field("Scheduler", select(scheduler, v.scheduler, set("scheduler"))),
    BAD_PAIRS[`${v.sampler_name}|${v.scheduler}`] ? h("span", { class: "h3s-warn", style: { flex: "1 1 260px", fontSize: "13px" } },
      BAD_PAIRS[`${v.sampler_name}|${v.scheduler}`]) : null,
    spectrumInstalled() || v.spectrum ? switchRow(v.spectrum === true, `Spectrum ${v.spectrum ? "on" : "off"}${v.turbo ? " (Turbo is on: not used)" : ""}`,
      SPECTRUM_HINT, () => actions.setWidget("spectrum", v.spectrum !== true)) : null,
    field("Shift video", number(v.shift_video, set("shift_video"), { step: "0.1", style: { width: "88px" } })),
    field("Shift audio", number(v.shift_audio, set("shift_audio"), { step: "0.1", style: { width: "88px" } })));
}

function turboSection(S, actions) {
  const mode = S.values.mode, rows = [];
  for (const [name, label] of [["turbo_lora_fl2va", "Turbo LoRA first / last frame"], ["turbo_lora_ref2va", "Turbo LoRA references"]]) {
    if ((mode === "fl2va" && name.endsWith("ref2va")) || (mode === "ref2va" && name.endsWith("fl2va"))) continue;
    const options = withCurrent((S.options[name] || ["none"]).map((value) => [value, value]), S.values[name], (file) => `${file} (not installed)`);
    // pictures take a LoRA's "still" values where it has them (core/turbo_profiles.py)
    const profile = turboProfile(S.turboProfiles, S.values[name]);
    const known = (S.values.output === "images" && profile?.still) || (profile?.steps ? profile : null);
    rows.push(field(label, select(options, S.values[name], (value) => actions.setTurboLora(name, value), { style: { maxWidth: "380px" } })),
      h("span", { class: S.values[name] === "none" ? "h3s-warn" : "h3s-lbl", style: { fontSize: "12px", flex: "1 1 220px" }, title: known?.source || "" },
        S.values[name] === "none" ? "No LoRA: Turbo gives no usable picture." : known
          ? `Known LoRA: ${known.steps} steps · ${known.sampler_name} · ${known.scheduler}.` : "Unknown LoRA: uses the Sampling values."));
  }
  return section("Turbo", "Turbo uses a few-step LoRA: fast for trying things out. Switch it on or off on the page.", rows);
}

function resumeSection(S, actions) {
  const resume = S.values.resume !== false, deleteDone = S.values.resume_delete_done !== false;
  return section("After a crash", "",
    switchRow(resume, `Resume ${resume ? "on" : "off"}`, "Finished parts are kept in output/h3-director-resume; queued again, only the missing parts render.",
      () => actions.setWidget("resume", !resume)),
    resume ? h("label", { class: "h3s-lbl", style: { display: "flex", gap: "8px", alignItems: "center", cursor: "pointer" } },
      h("input", { type: "checkbox", checked: deleteDone, onchange: () => actions.setWidget("resume_delete_done", !deleteDone) }),
      "Delete the kept parts when the video is done") : null);
}

function moreSection(S, actions) {
  const v = S.values, set = (name) => (value) => actions.setWidget(name, value);
  const text = (name, label, placeholder) => field(label, h("input", { class: "h3s-in", type: "text", value: v[name] || "", placeholder,
    style: { width: "260px" }, oninput: (event) => actions.setWidget(name, event.target.value, false) }));
  return section("Sound, style and transitions", "",
    text("soundscape", "Ambience", "e.g. a quiet hum of ventilation"),
    text("music", "Music", "N/A = no music"),
    field("Style", select(STYLES, v.style, set("style"))),
    field("Transition between render parts", select(CONTINUITY, v.continuity, set("continuity"))),
    field("Overlap", select(["5", "22", "39", "56"].map((frames) => [frames, `${frames} frames (${fmt(frames / 24)})`]), v.pin_frames, set("pin_frames"))));
}

function manualSection(S, actions) {
  return section("Manual prompt", "Replaces the generated prompt of every render part. Leave it empty unless you write the whole H3 prompt yourself.",
    h("textarea", { class: "h3s-in", rows: 3, value: S.values.prompt_override || "", placeholder: "Empty = the Director writes the prompt (recommended)",
      style: { width: "100%" }, oninput: (event) => actions.setWidget("prompt_override", event.target.value, false) }));
}

export const loadModels = (api) => modelState(api, ["all"]).catch(() => ({}));

// Every file the pack uses with its download (user 2026-10-25: "one place only for that"), then the files for "Place: Like
// Shot N" pictures, kept in the Director's "models" widget (ng/adapters/model_files.py).
function modelsSection(S, actions) {
  const chosen = chosenModels(S.values.models);
  const place = S.models && Object.fromEntries(PLACE_MODELS.filter((purpose) => S.models[purpose]).map((purpose) => [purpose, S.models[purpose]]));
  return [...section("Models", "Every file H3 Director uses: found or missing, and where to download it. H3's own files are chosen in the "
    + "loaders on the left; the extra ones on the card or node that uses them.", modelsList(S.models)),
  ...section("Models for place pictures", "Place pictures: SAM3 finds people, Qwen Image 2.1 paints them out or paints another view. "
    + "Automatic takes the official file names; choose your own file if yours is renamed or another version.",
  modelsMenu(place, chosen, (purpose, file) => actions.setWidget("models", JSON.stringify({ ...chosen, [purpose]: file || undefined })), "h3s"))];
}

export function settingsView(S, actions) {
  if (!S.settingsOpen) return null;
  const close = () => actions.toggle("settingsOpen");
  return h("div", { class: "h3s-modal-bg", onclick: (event) => { if (event.target === event.currentTarget) close(); } },
    h("div", { class: "h3s-modal", role: "dialog", "aria-label": "Settings" },
      h("div", { class: "h3s-row" }, icon("gear"), h("span", { class: "h3s-strong", style: { fontSize: "16px" } }, "Settings"),
        h("span", { class: "h3s-grow" }), h("button", { class: "h3s-btn", onclick: close }, "Done")),
      videoSection(S, actions), samplingSection(S, actions), S.values.turbo ? turboSection(S, actions) : null,
      controlSettings(S, actions), resumeSection(S, actions), moreSection(S, actions), modelsSection(S, actions), manualSection(S, actions)));
}

// Shown on the page while a manual prompt is set: it silently replaced every part's prompt with "true" once (2026-10-18).
export function manualPromptAlert(S, actions) {
  const text = String(S.values.prompt_override || "").trim();
  if (!text) return null;
  return h("div", { class: "h3s-alert", role: "alert" }, h("strong", {}, "Manual prompt is on:"),
    h("span", { style: { flex: "1 1 240px" } }, `every render part gets “${text.length > 80 ? text.slice(0, 80) + "…" : text}” instead of the Director's prompt.`),
    h("button", { class: "h3s-btn small", onclick: () => actions.setWidget("prompt_override", "") }, "Clear"),
    h("button", { class: "h3s-btn small", onclick: () => actions.toggle("settingsOpen") }, icon("gear", 14), "Edit"));
}
