// Prompt field and the Content cards that come from the Context nodes in the graph.
import { h, icon, tip } from "./h3s_dom.js";
import { quickView } from "./h3s_quick.js";
import { contextId } from "./ng_widgets.js";

const KIND = { image: "Image", video: "Video", audio: "Audio", text: "Text" };
const BG = { image: "#172338", video: "#2A2414", audio: "#221A33", text: "#13291F" };
const USAGE = { reference: "Reference", first_frame: "First frame", last_frame: "Last frame", keyframe: "Keyframe", storyboard: "Storyboard",
  motion: "Motion", camera: "Camera", continue: "Continue", structure: "Structure", voice: "Voice", copy: "Copy", lock: "Lock",
  music_style: "Music style", rhythm: "Rhythm", sound_reference: "Sound", style: "Style", rule: "Rule", character: "Character", world: "World",
  scene: "Scene", dialogue: "Dialogue", constraint: "Constraint", instruction: "Instruction", control: "Control video" };
const BARS = [8, 14, 22, 12, 30, 18, 26, 10, 34];

// The card's own selected source range (Start/End on the Context card), in seconds of the file; end 0 = file end.
function selection(widgets) {
  try { const options = JSON.parse(widgets.context_options || "{}"); return [Number(options.start_s) || 0, Number(options.end_s) || 0]; }
  catch { return [0, 0]; }
}

function usageOf(widgets, media) {
  let usage = [widgets.usage];
  if (widgets.usage_roles) try { usage = JSON.parse(widgets.usage_roles); } catch { usage = [widgets.usage]; }
  return (Array.isArray(usage) ? usage : []).filter(Boolean).length ? usage.filter(Boolean) : [{ image: "reference", video: "motion", audio: "voice", text: "style" }[media]];
}

export { contextId } from "./ng_widgets.js";

// One plain record per connected Context node; the cards, panels and timeline all read these.
export function contentEntries(raw, colorOf) {
  return raw.map((entry) => {
    const usage = usageOf(entry.widgets, entry.media);
    return { id: contextId(entry.widgets, entry.media), media: entry.media, name: entry.widgets.name || KIND[entry.media],
      source: entry.widgets[entry.media] || "", selection: selection(entry.widgets), color: colorOf(entry), bg: BG[entry.media], kind: KIND[entry.media], usage,
      role: usage.map((value) => USAGE[value] || value).join(", "),
      controlKind: (() => { try { return JSON.parse(entry.widgets.context_options || "{}").control_kind || "canny"; } catch { return "canny"; } })(), raw: entry };
  });
}

function visual(entry, thumb) {
  const box = h("div", { class: "h3s-ctx-visual", style: { background: entry.bg, color: entry.color } });
  const src = thumb(entry);
  if (src) box.append(h("img", { src, alt: "" }));
  else if (entry.media === "audio") box.append(h("div", { style: { display: "flex", alignItems: "center", gap: "2px", height: "30px" } },
    BARS.map((height) => h("span", { style: { width: "3px", height: `${height * 0.8}px`, borderRadius: "2px", background: "currentColor" } }))));
  else box.append(icon(entry.media === "video" ? "video" : entry.media === "text" ? "text" : "image", 24));
  return box;
}

export function promptView(S, actions) {
  const shots = S.shots.length > 0;
  return h("section", { class: "h3s-card" },
    h("div", { class: "h3s-row" }, h("label", { class: "h3s-strong", for: "h3s-prompt" }, "Prompt"),
      tip(shots ? "Your story. H3 gets the shots made from it (Timeline), plus the Look. What H3 really receives: Show prompts."
        : "Describe what should happen. Nothing else is needed.")),
    h("textarea", { class: "h3s-in", id: "h3s-prompt", rows: 3, value: S.values.idea || "", placeholder: "A young woman plays outside with a red ball …",
      oninput: (event) => actions.setWidget("idea", event.target.value, false) }),
    h("div", { class: "h3s-row" }, h("label", { class: "h3s-lbl", for: "h3s-look" }, "Look"),
      h("input", { class: "h3s-in", id: "h3s-look", value: S.look || "", placeholder: shots ? "Dark gothic hall, cinematic anime style, warm amber rim light …" : "Used once there are shots",
        style: { flex: "1" }, oninput: (event) => actions.setLook(event.target.value) }),
      tip("Style, place and light that every render part shares; it opens each part's prompt.")),
    h("div", { class: "h3s-row", style: { gap: "8px" } }, ...quickView(S, actions).filter(Boolean), h("span", { class: "h3s-grow" }),
      h("button", { class: "h3s-btn ai", disabled: !S.ai || Boolean(S.busy), onclick: actions.splitPrompt,
        title: S.ai ? "The AI suggests shots only; you accept or discard them." : "Connect an H3 AI Loader to the Connector for this." },
        icon("spark"), S.busy === "split" ? "AI working …" : "AI: split into shots"),
      S.busy === "split" ? h("button", { class: "h3s-btn ghost", onclick: actions.cancelAI }, "Cancel") : null,
      h("button", { class: "h3s-btn", onclick: actions.promptAsShot, title: "Your Prompt becomes one shot over the whole video, without AI" }, "Whole prompt = one shot")));
}

export function contentView(S, actions) {
  const selectedShot = S.selected?.kind === "shot" ? S.shots.find((shot) => shot.id === S.selected.id) : null;
  const drag = (id) => (event) => { actions.setDragged(id); try { event.dataTransfer.setData("text/plain", id); event.dataTransfer.effectAllowed = "copy"; } catch {} };
  const cards = [h("button", { class: "h3s-ctx", draggable: true, ondragstart: drag("__text"), ondragend: actions.endDrag,
    onclick: () => actions.newShot(null, "__text"), title: "Empty shot with text only" },
    h("div", { class: "h3s-ctx-visual", style: { color: "#9AA4B5", background: "#121722" } }, icon("plus", 24)),
    h("div", { class: "h3s-ctx-text" }, h("span", { class: "h3s-strong" }, "Text-Shot"), h("span", { class: "h3s-lbl" }, "text only, no media")))];
  for (const entry of S.contexts) {
    const assigned = Boolean(selectedShot?.media.some((binding) => binding.context_id === entry.id));
    const control = entry.usage.includes("control");
    const unused = S.values.mode === "fl2va" && entry.media === "video" && !control && !entry.usage.includes("continue");
    const tip = control ? "Drag onto the Control lane, or click to place it at the start" : unused ? "Not used in First/last frame mode (FL2VA)" : entry.media === "audio"
      ? "Drag onto an audio lane = plays throughout · onto a shot = only in that shot"
      : selectedShot ? `Click: ${assigned ? "remove from" : "add to"} ${actions.shotLabel(selectedShot.id)}` : "Drag onto the timeline";
    cards.push(h("button", { class: `h3s-ctx${assigned ? " on" : ""}${unused ? " off" : ""}`, draggable: true, title: tip,
      ondragstart: drag(entry.id), ondragend: actions.endDrag, onclick: () => actions.toggleBinding(entry.id) },
      visual(entry, actions.thumb),
      assigned ? h("span", { class: "h3s-badge" }, "in shot") : null,
      h("div", { class: "h3s-ctx-text" }, h("span", { class: "h3s-strong", style: { display: "flex", alignItems: "center", gap: "6px" } },
        h("span", { class: "h3s-swatch", style: { background: entry.color } }), entry.name), h("span", { class: "h3s-lbl" }, `${entry.kind} · ${entry.role}`))));
  }
  if (!S.contexts.length) cards.push(h("div", { class: "h3s-hint" }, "No Content yet: connect Context nodes to the Context Connector. Text alone works too."));
  return h("section", { class: "h3s-card" },
    h("div", { class: "h3s-row" }, h("span", { class: "h3s-strong" }, "Content"),
      tip("Drag a card onto the timeline = new shot · onto a shot, or click = add it to the selected shot · audio onto an audio lane · control videos onto the Control lane. More cards come from Context nodes in the graph.")),
    h("div", { class: "h3s-content" }, cards));
}
