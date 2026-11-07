// The fixed bar under the Studio: duration, resolution and the way to the settings.
import { h, icon, field, select } from "./h3s_dom.js";
import { DURATIONS, fmt, turboProfile } from "./h3s_model.js";
import { PRESET_GROUPS, PICTURE_TIERS, presetValue, pictureSize, isAuto, nearestAspect } from "./h3s_canvas.js";

// The steps the parts really sample with: with Turbo, each part takes its model's LoRA profile (core/turbo_profiles.py);
// the footer said "4 steps" while the parts ran with 6 (Ref2VA) or 8 (FL2VA).
function stepsText(S) {
  const v = S.values;
  if (!v.turbo) return `${v.steps} steps`;
  const models = new Set((S.plan?.chunks || []).map((chunk) => (chunk.mode === "ref2va" ? "ref2va" : "fl2va")));
  if (!models.size) models.add(v.mode === "ref2va" ? "ref2va" : "fl2va");
  const steps = [...models].map((model) => {
    const profile = turboProfile(S.turboProfiles, v[`turbo_lora_${model}`]);
    return ((v.output === "images" && profile?.still) || (profile?.steps ? profile : null))?.steps ?? v.steps;
  });
  return `${[...new Set(steps)].join(" / ")} steps`;
}

function number(value, onchange, props = {}) {
  return h("input", { class: "h3s-in", type: "number", value, onchange: (event) => onchange(Number(event.target.value)), ...props });
}

// Any length on the 0.1 s grid, the usual ones offered as suggestions; a music video takes the length of its song.
// A fixed list offered no 27 s, so a 27 s song could not set the project's length.
function durationField(S, actions) {
  const v = S.values, set = (value) => { if (value > 0) actions.setDuration(Math.min(3600, Math.round(value * 10) / 10)); };
  const song = S.contexts.filter((entry) => entry.media === "audio" && S.lengths.get(entry.id) > 0)
    .sort((a, b) => S.lengths.get(b.id) - S.lengths.get(a.id))[0];
  const length = song && Math.round(S.lengths.get(song.id) * 10) / 10;
  return field("Duration", h("span", { class: "h3s-row", style: { gap: "6px", flexWrap: "nowrap" } },
    number(v.project_seconds, set, { min: "0.5", max: "3600", step: "0.1", list: "h3s-durations", "aria-label": "Duration in seconds", style: { width: "84px" } }),
    h("datalist", { id: "h3s-durations" }, DURATIONS.map((d) => h("option", { value: String(d) }))),
    song && length !== Number(v.project_seconds) ? h("button", { class: "h3s-btn small", title: `Set the duration to the length of ${song.name} (${fmt(length)})`,
      onclick: () => set(length) }, `= ${song.name}`) : null));
}

// The page keeps only what a first video needs; everything else is behind the gear (h3s_settings.js).
export function footerView(S, actions) {
  const v = S.values;
  // The first picture's own shape at three sizes; the fixed formats below it.
  const picture = S.picture, shape = picture && (nearestAspect(...pictureSize(picture.ratio, "native")) || picture.ratio.toFixed(2));
  const own = picture ? [{ group: `Like ${picture.name} (${shape}, keeps its shape)`, items: PICTURE_TIERS.map(([key, label]) => {
    const [w, hh] = pictureSize(picture.ratio, key);
    return [`picture:${key}`, `${label} · ${w}×${hh}`];
  }) }] : [];
  const presets = [["auto", "From first picture (H3 chooses)"], ...own, ...PRESET_GROUPS.map(([group, list]) => ({ group, items: list.map(([label, w, hh]) => [`${w}x${hh}`, `${label} · ${w}×${hh}`]) })),
    ["custom", "Custom size"]];
  const plan = S.plan, size = isAuto(v.width, v.height) ? (plan ? `${plan.width}×${plan.height} from picture` : "size from picture") : `${v.width}×${v.height}`;
  const parts = plan ? plan.chunks.length : "?";
  return h("footer", { class: "h3s-foot" }, h("div", { class: "h3s-foot-row" },
    durationField(S, actions),
    field("Resolution", select(presets, presetValue(v.width, v.height, picture?.ratio), actions.setPreset, { style: { maxWidth: "300px" } })),
    h("button", { class: "h3s-btn", onclick: () => actions.toggle("settingsOpen"), title: "Render part, size, seed, steps, sampler, turbo LoRA, resume, ControlNet, sound and style" },
      icon("gear"), "Settings"),
    h("span", { class: "h3s-grow" }),
    h("span", { class: "h3s-strong" }, `${fmt(v.project_seconds)} · ${S.shots.length} shot${S.shots.length === 1 ? "" : "s"} · ${parts} render part${parts === 1 ? "" : "s"} · ${size}`),
    h("span", { class: "h3s-lbl" }, `${v.mode === "fl2va" ? "FL2VA" : v.mode === "ref2va" ? "Ref2VA" : "Auto"}${v.turbo ? " Turbo" : ""} · ${stepsText(S)}`)));
}
