// The Studio: the H3 Director node's face in the graph (host given), or over the whole window. It reads and writes the
// node's own widgets, so saving, loading and queueing stay ComfyUI's; the shot document keeps shots, clips and lanes.
import { h, icon, keepKeys } from "./h3s_dom.js";
import { ensureStudioStyle } from "./h3s_style.js";
import { readProject, writeProject, newShot, newClip, newLane, placeAt, addShotAt, snapWithin, trimToDuration, growToDuration, editSpoken, addSpoken, removeSpoken, sorted, MIN_LENGTH, r1, turboProfile, fmt, setPartPrompt, clipToFit, isKeyframe, middleOf, removeLane } from "./h3s_model.js";
import { fitAspect, snap32, ASPECTS, isAuto, NATIVE_MP, pictureSize } from "./h3s_canvas.js";
import { contentEntries, promptView, contentView, contextId } from "./h3s_content.js";
import { timelineView } from "./h3s_timeline.js";
import { restoreTimeline, rememberTimeline } from "./h3s_navigation.js";
import { timeView } from "./h3s_time.js";
import { timelineEditor } from "./h3s_edits.js";
import { bindTimelineKeys } from "./h3s_keys.js";
import { updateStudioPage } from "./h3s_focus.js";
import { sideView, loadEffects } from "./h3s_side.js";
import { footerView } from "./h3s_footer.js";
import { settingsView, manualPromptAlert, loadModels } from "./h3s_settings.js";
import { drawerView } from "./h3s_prompts.js";
import { studioAI, basis as aiBasis } from "./h3s_ai.js";
import { readQuick, changeQuick } from "./h3s_quick.js";
import { offerFor } from "./h3c_model.js";
import { values, applyValues, request } from "./ng_widgets.js";
import { readPayload, readContexts, connectedProvider, contextNodes, upstreamNode } from "./ng_read.js";
import { contextColor } from "./ng_identity.js";
import { hasRenderPath, projectRenderIds } from "./ng_graph.js";
import { attachProgress } from "./ng_studio_progress.js";

const STALE = { text: "The project changed after the AI answered, so its suggestion no longer fits and was discarded. Ask again.", error: false };
const COMBOS = ["sampler_name", "scheduler", "turbo_lora_fl2va", "turbo_lora_ref2va"];
const open = new Map(); // node -> Studio; a node's id is not final while it is being created
// Measured settings of known turbo LoRAs, the same table the Python side samples with.
let turboProfiles = {};
const profilesLoaded = fetch(new URL("./turbo_profiles.json", import.meta.url)).then((r) => r.json())
  .then((table) => { turboProfiles = table; }).catch(() => {});

function load(S) {
  S.values = values(S.node);
  S.timeline = timeView(S.node.properties?.ng_timeline);
  S.options = Object.fromEntries(COMBOS.map((name) => [name, S.node.widgets?.find((w) => w.name === name)?.options?.values]));
  S.contexts = contentEntries(readContexts(S.node), contextColor);
  S.byId = new Map(S.contexts.map((entry) => [entry.id, entry]));
  S.ai = Boolean(connectedProvider(S.node));
  const connector = upstreamNode(S.node.graph, S.node.inputs?.find((input) => input.name === "context"));
  S.controlConnected = connector?.inputs?.some((input) => input.name === "model_patch" && input.link != null);
  S.turboProfiles = turboProfiles;
  const project = readProject(S.values.shots || "");
  S.docError = project.error;
  if (project.skipped?.length) S.notice = { error: true, text: `The saved data has ${project.skipped.length} invalid audio clip(s) (${project.skipped.join(", ")}). `
    + "They are left out here and removed with your next edit; everything else is kept." };
  Object.assign(S, { shots: project.shots, audio: project.audio, lanes: project.lanes, control: project.control, look: project.look, partPrompts: project.partPrompts,
    quick: readQuick(S.node) });
}

// With a host the Studio lives in it (the node); "Full screen" lifts the same Studio over the window and Esc puts it back.
export function openStudio(node, app, api, host = null) {
  if (open.has(node)) { open.get(node).root.focus(); return open.get(node); }
  ensureStudioStyle();
  let full = !host;
  const root = h("div", { class: full ? "h3s full" : "h3s", tabindex: "-1", role: full ? "dialog" : "region", "aria-label": "H3 Director Studio" });
  const page = h("div", { class: "h3s-page" });
  root.append(page);
  const S = { node, root, selected: null, ghosts: [], ghostSound: null, suggestions: {}, partDrafts: {}, partEdit: null, plan: null, planError: "", promptOpen: false,
    settingsOpen: false, busy: "", toast: "", notice: null, suggestionBase: {}, aiStarted: 0, aiTimeout: 0, dragged: null, dragging: false, pending: false, thumbs: new Map(), ratios: new Map(), lengths: new Map() };
  load(S);
  let timer = null, serial = 0, toastTimer = null, tick = null, closed = false;
  const status = h("span", { class: "h3s-lbl" });
  const progress = attachProgress(node, api, status, () => projectRenderIds(node));
  const ai = studioAI(S, app, api, () => render());
  profilesLoaded.then(() => { if (!closed) { S.turboProfiles = turboProfiles; render(); } }); loadModels(api).then((state) => { if (!closed) { S.models = state; render(); } }); loadEffects(api).then((names) => { if (!closed) { S.effects = names; render(); } });

  let echo = false;
  function write(changes) { echo = true; try { applyValues(node, changes); } finally { echo = false; } }
  function profileFields(lora) {
    const profile = turboProfile(S.turboProfiles, lora), known = (values(node).output === "images" && profile?.still) || (profile?.steps ? profile : null);
    return known ? { steps: known.steps, sampler_name: known.sampler_name, scheduler: known.scheduler } : {};
  }
  const labels = () => new Map(sorted(S.shots).map((shot, index) => [shot.id, `Shot ${index + 1}`]));
  function save() {
    const text = S.docError ? null : writeProject({ shots: S.shots, audio: S.audio, lanes: S.lanes, control: S.control, look: S.look, partPrompts: S.partPrompts });
    if (text !== null && text !== (values(node).shots || "")) { write({ shots: text }); node.graph?.change?.(); }
    S.values = values(node); edits.record(); schedulePlan();
  }
  function flash(message) {
    S.toast = message; clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { S.toast = ""; render(); }, 3200);
  }
  function setWidget(name, value, rerender = true) {
    write({ [name]: value }); node.graph?.change?.();
    S.values = values(node); schedulePlan();
    if (rerender) render();
    // the cards word their "Use as" hint for the Director's mode; they kept the old one until something else redrew them
    if (name === "mode") document.dispatchEvent(new CustomEvent("ng-context-changed"));
  }
  // The plan of what is saved right now, for a step that needs it before going on (Make H3 prompt writes each part of it).
  async function planNow() {
    clearTimeout(timer); const mine = ++serial;
    const data = await request(api, "/ng/plan", readPayload(node));
    if (mine === serial && !closed) { S.plan = data; S.planError = ""; }
    return data;
  }
  function schedulePlan() {
    S.plan = null; S.planError = "";
    clearTimeout(timer); const mine = ++serial;
    timer = setTimeout(async () => {
      try {
        const data = await request(api, "/ng/plan", readPayload(node));
        if (closed || mine !== serial) return;
        S.plan = data; S.planError = "";
        S.lengths = new Map((data.director_context?.items || []).map((item) => [item.id, item.length_s]));
      } catch (error) { if (closed || mine !== serial) return; S.plan = null; S.planError = error.message; }
      render();
    }, 250);
  }
  function thumb(entry) {
    if (!["image", "video"].includes(entry.media) || !entry.source) return "";
    const key = `${entry.media}|${entry.source}`;
    if (!S.thumbs.has(key)) {
      S.thumbs.set(key, "");
      request(api, "/ng/media?" + new URLSearchParams({ media: entry.media, source: entry.source }))
        .then((data) => { if (data.thumbnail?.startsWith("data:image/")) { S.thumbs.set(key, data.thumbnail); render(); } }).catch(() => {});
    }
    return S.thumbs.get(key);
  }
  // The picture the server takes the size from (ng/core/project.py auto_canvas): the first frame, else the first image.
  // Its shape comes from its preview, which keeps the aspect ratio.
  function firstPicture() {
    const images = S.contexts.filter((entry) => entry.media === "image" && entry.source);
    const entry = images.find((item) => (item.usage || []).includes("first_frame")) || images[0];
    const src = entry ? thumb(entry) : "";
    if (!src) return null;
    if (!S.ratios.has(src)) {
      S.ratios.set(src, 0);
      const image = new Image();
      image.onload = () => { S.ratios.set(src, image.naturalWidth / image.naturalHeight); render(); };
      image.src = src;
    }
    return S.ratios.get(src) ? { name: entry.name, ratio: S.ratios.get(src) } : null;
  }
  function selectedRange() {
    const item = S.selected && (S.selected.kind === "shot" ? S.shots : S.selected.kind === "control" ? S.control : S.audio).find((entry) => entry.id === S.selected.id);
    return item ? [item.start, item.end] : null;
  }
  function setItems(kind, items, selectId) {
    const previous = kind === "shot" ? S.shots : kind === "control" ? S.control : S.audio;
    if (kind === "shot") S.shots = items; else if (kind === "control") S.control = items; else S.audio = items;
    if (selectId) { S.selected = { kind, id: selectId }; if (!previous.some((item) => item.id === selectId)) S.timelineFocus = { ...S.selected }; }
    save(); render();
  }
  function patchShot(id, change, rerender = true) {
    S.shots = S.shots.map((shot) => (shot.id === id ? { ...shot, ...change } : shot));
    save(); if (rerender) render();
  }
  function room(items, id) {
    const list = sorted(items), index = list.findIndex((entry) => entry.id === id);
    return [index > 0 ? list[index - 1].end : 0, index < list.length - 1 ? list[index + 1].start : S.values.project_seconds];
  }
  function timed(item, items, key, value) {
    const [prev, next] = room(items, item.id);
    if (!Number.isFinite(value)) return item;
    return key === "start" ? { ...item, start: snapWithin(value, prev, item.end - MIN_LENGTH) ?? item.start }
      : { ...item, end: snapWithin(value, item.start + MIN_LENGTH, next) ?? item.end };
  }

  const actions = {
    shotLabel: (id) => labels().get(id) || "Shot",
    undoTimeline: () => edits.undo(), redoTimeline: () => edits.redo(),
    setTimeline(view) { rememberTimeline(S, view); node.graph?.change?.(); render(); },
    select(kind, id) { S.selected = { kind, id }; render(); },
    setShots: (shots, id) => setItems("shot", shots, id),
    setClips: (audio, id) => setItems("clip", audio, id),
    setControls: (clips, id) => setItems("control", clips, id),
    setDragged(id) { S.dragged = id; },
    endDrag() { setTimeout(() => { S.dragged = null; }, 0); },
    takeDragged() { const id = S.dragged; S.dragged = null; return id; },
    beginPointer() { S.dragging = true; },
    endPointer() { S.dragging = false; if (S.pending) render(); },
    addShot() {
      const made = addShotAt(S.shots, S.selected?.kind === "shot" ? S.selected.id : null, S.values.project_seconds);
      if (!made) { flash("No room for a new shot: every shot is already at its shortest length."); return; }
      if (made.split) flash(`${actions.shotLabel(made.split)} was halved to make room for the new shot.`);
      setItems("shot", made.shots, made.id);
    },
    newShot(sec, id) {
      if (id === null) return;
      if (S.byId.get(id)?.usage.includes("control")) { actions.newControl(sec || 0, id); return; }
      if (sec === null || sec === undefined) { if (id === "__text") { actions.addShot(); return; } sec = sorted(S.shots).at(-1)?.end ?? 0; }
      const at = placeAt(S.shots, sec, S.values.project_seconds, 4);
      if (!at) { flash("There is no room for a new shot there. Drop it on a free spot, or use + Shot."); return; }
      const media = id && id !== "__text" && S.byId.has(id) ? [id] : [];
      const shot = newShot(at.start, at.end, media);
      setItems("shot", [...S.shots, shot], shot.id);
    },
    assign(shotId, id) {
      if (!id || id === "__text" || !S.byId.has(id)) return;
      if (S.byId.get(id)?.usage.includes("control")) { flash("Drag control videos onto the Control lane."); return; }
      const shot = S.shots.find((entry) => entry.id === shotId);
      if (!shot.media.some((binding) => binding.context_id === id)) {
        const binding = { schema_version: 1, context_id: id, role: "context" };
        if (isKeyframe(binding, S.byId.get(id))) binding.at_s = middleOf(shot);      // a Keyframe starts in the shot's middle
        patchShot(shotId, { media: [...shot.media, binding] }, false);
      }
      S.selected = { kind: "shot", id: shotId }; render();
    },
    setBinding(shotId, id, change) {
      const shot = S.shots.find((entry) => entry.id === shotId);
      const media = shot.media.map((binding) => {
        if (binding.context_id !== id) return binding;
        const next = { ...binding, ...change };
        // A typed time is kept inside the shot; a binding that becomes a Keyframe without one starts in the middle.
        if (isKeyframe(next, S.byId.get(id))) next.at_s = snapWithin(Number.isFinite(Number(next.at_s)) && next.at_s !== undefined && next.at_s !== ""
          ? Number(next.at_s) : middleOf(shot), 0, r1(shot.end - shot.start));
        else delete next.at_s;
        return next;
      });
      patchShot(shotId, { media });
    },
    unassign(shotId, id) {
      patchShot(shotId, { media: S.shots.find((entry) => entry.id === shotId).media.filter((binding) => binding.context_id !== id) });
    },
    setShot(shotId, change, rerender = true) { patchShot(shotId, change, rerender); },     // place (core/places.py), effect
    toggleBinding(id) {
      if (S.byId.get(id)?.usage.includes("control")) { actions.newControl(0, id); return; }
      const shot = S.selected?.kind === "shot" && S.shots.find((entry) => entry.id === S.selected.id);
      if (!shot) { flash("Click a shot first, or drag the Content onto the timeline."); return; }
      if (shot.media.some((binding) => binding.context_id === id)) actions.unassign(shot.id, id); else actions.assign(shot.id, id);
    },
    newClip(lane, sec, id) {
      const entry = S.byId.get(id);
      if (!entry || entry.media !== "audio") { if (id) flash("Only audio Content goes on the audio lanes."); return; }
      // A new clip plays the card's selected range: its offset is the selection start, in seconds of the file.
      const [from, to] = entry.selection || [0, 0], end = to || S.lengths.get(id) || from + 8;
      const length = Math.min(Math.max(end - from, MIN_LENGTH), S.values.project_seconds);
      const at = placeAt(S.audio.filter((clip) => clip.lane === lane), sec, S.values.project_seconds, length);
      if (!at) { flash("There is no room on this audio lane there."); return; }
      // First / last frame mode can only take sound as a lock; a reference clip would not reach the model.
      const mode = S.values.mode === "fl2va" || entry.usage.includes("lock") ? "lock" : entry.usage.includes("copy") ? "copy" : "ref";
      const clip = { ...newClip(id, lane, at.start, at.end, mode), offset: from };
      setItems("clip", [...S.audio, clip], clip.id);
    },
    addLane(id) {
      const lane = newLane();
      S.lanes = [...S.lanes, lane];
      if (id && S.byId.get(id)?.media === "audio") actions.newClip(lane, 0, id);
      else { if (id) flash("Only audio Content goes on the audio lanes."); save(); render(); }
    },
    removeLane(lane) { Object.assign(S, removeLane(S, lane)); save(); render(); },
    newControl(sec, id) {
      const entry = S.byId.get(id);
      if (!entry || entry.media !== "video" || !entry.usage.includes("control")) { if (id) flash("Choose Use as: Control video on a Video card first."); return; }
      const [from, to] = entry.selection || [0, 0], end = to || S.lengths.get(id) || from + 8;
      const at = placeAt(S.control, sec, S.values.project_seconds, Math.max(MIN_LENGTH, end - from));
      if (!at) { flash("There is no room on the Control lane there."); return; }
      const clip = { ...newClip(id, "control", at.start, at.end), offset: from };
      delete clip.mode;
      setItems("control", [...S.control, clip], clip.id);
    },
    setControl(id, key, value) {
      const clip = S.control.find((entry) => entry.id === id);
      const entry = S.byId.get(clip.context_id), [from, to] = entry?.selection || [0, 0];
      const upper = to || S.lengths.get(clip.context_id) || Infinity;
      const next = key === "offset" ? { ...clip, offset: Math.max(from, Math.min(upper - 1 / 24, r1(value) || 0)) } : timed(clip, S.control, key, value);
      setItems("control", S.control.map((entry) => entry.id === id ? next : entry), id);
    },
    deleteControl(id) { S.control = S.control.filter((clip) => clip.id !== id); S.selected = null; save(); render(); },
    setWidget,
    // Turbo on: 4 steps, or the measured settings of the chosen LoRA. Off brings back the settings used before.
    setTurbo(on) {
      const kept = ["steps", "sampler_name", "scheduler"];
      if (on && !S.values.turbo) node.properties.ng_before_turbo = Object.fromEntries(kept.map((name) => [name, S.values[name]]));
      // ng_steps_before_turbo: what workflows saved before the profiles kept
      const before = node.properties.ng_before_turbo || { steps: Number(node.properties.ng_steps_before_turbo) || 20 };
      if (!on) { delete node.properties.ng_before_turbo; delete node.properties.ng_steps_before_turbo; }
      const lora = S.values[(S.values.mode === "auto" ? S.plan?.mode : S.values.mode) === "ref2va" ? "turbo_lora_ref2va" : "turbo_lora_fl2va"];
      write(on ? { turbo: true, steps: 4, ...profileFields(lora) } : { turbo: false, ...before }); setWidget("turbo", on);
    },
    // A known LoRA brings its measured steps, sampler and scheduler; the parts of its model render with them.
    setTurboLora(name, value) { write(profileFields(value)); setWidget(name, value); },
    setDuration(seconds) {
      const before = { shots: S.shots, audio: S.audio, control: S.control, seconds: S.values.project_seconds, names: labels() };
      const shots = trimToDuration(S.shots, seconds), audio = trimToDuration(S.audio, seconds);
      const grown = growToDuration(shots.items, Number(before.seconds), seconds);
      S.shots = grown.items; S.audio = audio.items; S.ghosts = [];
      const control = trimToDuration(S.control, seconds); S.control = control.items;
      write({ project_seconds: seconds }); save();
      const cut = [shots.removed.length && `removed ${shots.removed.map((id) => before.names.get(id)).join(", ")}`,
        shots.shortened.length && `shortened ${shots.shortened.map((id) => before.names.get(id)).join(", ")}`,
        (audio.removed.length || audio.shortened.length) && `cut ${audio.removed.length + audio.shortened.length} audio clip(s)`,
        (control.removed.length || control.shortened.length) && `cut ${control.removed.length + control.shortened.length} control clip(s)`,
        grown.grown.length && `${before.names.get(grown.grown[0])} now runs to the new end`].filter(Boolean);
      if (cut.length) S.notice = { text: `Duration ${fmt(seconds)}: ${cut.join("; ")}.`, undo: () => {
        S.shots = before.shots; S.audio = before.audio; S.control = before.control; write({ project_seconds: before.seconds }); save(); render(); } };
      render();
    },
    setPreset(value) {
      if (value === "auto") write({ width: 0, height: 0 });
      else if (value.startsWith("picture:") && S.picture) { const [w, hh] = pictureSize(S.picture.ratio, value.slice(8)); write({ width: w, height: hh }); }
      else if (value !== "custom") { const [w, hh] = value.split("x").map(Number); write({ width: w, height: hh }); }
      else if (isAuto(S.values.width, S.values.height)) write({ width: 1344, height: 768 });
      setWidget("width", values(node).width);
    },
    setSize(name, value) {
      const other = name === "width" ? "height" : "width";
      if (!(value > 0)) { write({ width: 0, height: 0 }); setWidget("width", 0); return; }
      write({ [name]: snap32(value), [other]: S.values[other] > 0 ? S.values[other] : name === "width" ? 768 : 1344 });
      setWidget(name, values(node)[name]);
    },
    setAspect(label) {
      const ratio = ASPECTS.find(([name]) => name === label)?.[1]; if (!ratio) return;
      const pixels = isAuto(S.values.width, S.values.height) ? NATIVE_MP * 1e6 : S.values.width * S.values.height;
      const [w, hh] = fitAspect(pixels, ratio); write({ width: w, height: hh }); setWidget("width", w);
    },
    setMegapixels(mp) {
      if (!(mp > 0)) return;
      const ratio = isAuto(S.values.width, S.values.height) ? 1344 / 768 : S.values.width / S.values.height;
      const [w, hh] = fitAspect(mp * 1e6, ratio); write({ width: w, height: hh }); setWidget("width", w);
    },
    toggle(key) { S[key] = !S[key]; render(); },
    setShotTime(id, key, value) { const shot = S.shots.find((entry) => entry.id === id); patchShot(id, timed(shot, S.shots, key, value)); },
    // A manual edit makes a pending AI text for this shot outdated.
    setShotText(id, text) { if (S.suggestions[id] !== undefined) { delete S.suggestions[id]; patchShot(id, { text }); } else patchShot(id, { text }, false); },
    deleteShot(id) { S.shots = S.shots.filter((shot) => shot.id !== id); S.selected = null; delete S.suggestions[id]; save(); render(); },
    setSpoken(id, index, change, rerender = true) { patchShot(id, { spoken: editSpoken(S.shots.find((entry) => entry.id === id).spoken, index, change) }, rerender); },
    addSpoken(id) { patchShot(id, { spoken: addSpoken(S.shots.find((entry) => entry.id === id).spoken) }); },
    removeSpoken(id, index) { patchShot(id, { spoken: removeSpoken(S.shots.find((entry) => entry.id === id).spoken, index) }); },
    suggest: (id) => ai.suggest(id),
    acceptSuggestion(id) {
      const text = S.suggestions[id], shot = S.shots.find((entry) => entry.id === id);
      delete S.suggestions[id];
      if (S.suggestionBasis !== aiBasis(node, false)) { S.suggestions = {}; S.notice = STALE; render(); return; }
      if (text === undefined || !shot || shot.text !== S.suggestionBase[id] || (shot.locked_fields || []).includes("text")) { render(); return; }
      patchShot(id, { text });
    },
    dropSuggestion(id) { delete S.suggestions[id]; render(); },
    cancelAI: () => ai.cancel(),
    splitPrompt: () => ai.split(),
    setLook(text) { S.look = text; save(); },
    // Prompts per render part. An AI version and an edit are kept with the key of the compiled prompt they belong to.
    writePart: (index) => ai.writePart(index),
    async writeAllParts() { for (const chunk of S.plan?.chunks || []) if (!(await ai.writePart(chunk.index))) break; },
    acceptPart(index) {
      const draft = S.partDrafts[index], chunk = S.plan?.chunks?.[index];
      delete S.partDrafts[index];
      if (!draft || !chunk || draft.key !== chunk.prompt_key) { S.notice = STALE; render(); return; }
      S.partPrompts = setPartPrompt(S.partPrompts, index, draft.key, draft.text, "ai"); save(); render();
    },
    dropPart(index) { delete S.partDrafts[index]; render(); },
    editPart(index, text = "") { S.partEdit = index === null ? null : { index, text }; render(); },
    savePart(index) {
      const chunk = S.plan?.chunks?.[index], edit = S.partEdit;
      S.partEdit = null;
      if (!chunk || !edit) { render(); return; }
      S.partPrompts = setPartPrompt(S.partPrompts, index, chunk.prompt_key, edit.text, "user"); save(); render();
    },
    resetPart(index) { S.partPrompts = setPartPrompt(S.partPrompts, index, "", "", "user"); save(); render(); },
    promptAsShot() { const shot = newShot(0, S.values.project_seconds); shot.text = S.values.idea || ""; S.ghosts = []; setItems("shot", [shot], shot.id); },
    acceptGhosts() {
      if (S.ghostBasis !== aiBasis(node, true)) { S.ghosts = []; S.ghostSound = null; S.notice = STALE; render(); return; }
      const shots = S.ghosts.map((ghost) => ({ ...newShot(ghost.start, ghost.end), text: ghost.text, spoken: ghost.spoken || [] }));
      const sound = S.ghostSound || {};
      for (const name of ["soundscape", "music"]) if (sound[name]?.trim()) write({ [name]: sound[name].trim() });
      if (sound.look?.trim()) S.look = sound.look.trim();
      // New shots are a new plan: the parts' own prompts were written for the old one.
      S.partPrompts = []; S.partDrafts = {};
      S.ghosts = []; S.ghostSound = null; setItems("shot", shots, shots[0]?.id);
    },
    setQuick(key, value) { S.quick = changeQuick(S.quick, key, value); node.properties.ng_quick = S.quick; node.graph?.change?.(); render(); },
    async buildPrompt() {
      const before = { shots: S.shots, look: S.look, partPrompts: S.partPrompts, soundscape: S.values.soundscape, music: S.values.music, cards: [] };
      const undo = () => { Object.assign(S, { shots: before.shots, look: before.look, partPrompts: before.partPrompts });
        for (const card of before.cards) applyValues(card, { description: "" });
        write({ soundscape: before.soundscape, music: before.music }); save(); render(); };
      const apply = (plan) => {
        // A picture without a description gets the plan's: the compiler names the figure with it in every part.
        for (const { media, node: card } of contextNodes(node)) {
          const text = plan.descriptions?.[contextId(values(card), media)];
          if (media !== "image" || !text || (values(card).description || "").trim()) continue;
          before.cards.push(card); applyValues(card, { description: text });
        }
        S.shots = clipToFit(readProject(plan.shots || "").shots, S.values.project_seconds).map((shot) => ({ ...newShot(shot.start, shot.end, []),
          text: shot.text, media: shot.media || [], spoken: shot.spoken || [] }));
        S.look = (plan.look || "").trim(); S.partPrompts = []; S.partDrafts = {}; S.ghosts = []; S.ghostSound = null; S.selected = null;
        write({ soundscape: (plan.soundscape || "").trim(), music: (plan.music || "").trim() });
        save(); render(); return undo;
      };
      const keep = (index, draft) => { S.partPrompts = setPartPrompt(S.partPrompts, index, draft.key, draft.text, "ai"); save(); };
      const describe = async (ask) => {
        for (const { media, node: card } of contextNodes(node)) {
          if (media !== "image" || (values(card).description || "").trim()) continue;
          const text = await ask({ media, widgets: values(card), offer: offerFor(media) }).then((data) => data.suggestion?.description?.trim(), () => "");
          if (text) { before.cards.push(card); applyValues(card, { description: text }); }
        }
      };
      const result = await ai.build(apply, planNow, keep, describe);
      if (!result) return;
      const notes = [result.refused && `${result.refused} part${result.refused === 1 ? "" : "s"} kept the compiled prompt because the AI's text broke a rule`,
        result.unchanged && `${result.unchanged} part${result.unchanged === 1 ? "" : "s"} came back unchanged`,
        result.unseen.length && `the AI could not look at ${result.unseen.join(", ")} and used the card descriptions`,
        before.cards.length && `${before.cards.length} picture card${before.cards.length === 1 ? "" : "s"} got a description`].filter(Boolean);
      S.promptOpen = true;
      S.notice = { text: `H3 prompt ready: ${result.written} of ${result.parts} part${result.parts === 1 ? "" : "s"} written by the AI`
        + (notes.length ? ` (${notes.join("; ")})` : "") + ". See Prompts per render part below; Write with AI tries a part again.", undo };
      render();
    },
    dropGhosts() { S.ghosts = []; S.ghostSound = null; render(); },
    setClip(id, key, value) {
      const clip = S.audio.find((entry) => entry.id === id), lane = S.audio.filter((entry) => entry.lane === clip.lane);
      const next = key === "mode" ? { ...clip, mode: value } : key === "offset" ? { ...clip, offset: Math.max(0, r1(value) || 0) } : timed(clip, lane, key, value);
      setItems("clip", S.audio.map((entry) => (entry.id === id ? next : entry)), id);
    },
    deleteClip(id) { S.audio = S.audio.filter((clip) => clip.id !== id); S.selected = null; save(); render(); },
    thumb,
  };

  const edits = timelineEditor(S, { actions, write, plan: schedulePlan, render, reload: () => load(S) });

  function setFull(on) {
    if (!host || on === full) return;
    full = on; root.classList.toggle("full", on); root.setAttribute("role", on ? "dialog" : "region");
    (on ? document.body : host).append(root);
    render(); if (on) root.focus();
  }
  function header() {
    const ready = hasRenderPath(node);
    const back = host ? h("button", { class: "h3s-btn ghost", onclick: () => setFull(!full), title: full ? "Back into the graph (Esc)" : "Use the whole window" },
      icon(full ? "back" : "expand"), full ? "Back to graph" : "Full screen")
      : h("button", { class: "h3s-btn ghost", onclick: close, title: "Back to the graph (Esc)" }, icon("back"), "Back to graph");
    return h("header", { class: "h3s-head" }, back,
      ...(full ? [h("span", { style: { width: "1px", height: "24px", background: "#2A3342" } }),
        h("span", { class: "h3s-title" }, "H3 Director"), h("span", { class: "h3s-muted" }, "Studio")] : []),
      h("span", { class: "h3s-grow" }), status,
      h("span", { class: "h3s-row", style: { gap: "6px" }, title: "Green when an H3 AI Loader is connected to the Context Connector" },
        h("span", { class: "h3s-swatch", style: { background: S.ai ? "#5BD08A" : "#6B7383", borderRadius: "50%" } }), S.ai ? "AI connected" : "AI off"),
      h("button", { class: "h3s-btn", onclick: () => actions.toggle("promptOpen") }, icon("doc"), S.promptOpen ? "Hide prompts" : "Show prompts"),
      h("button", { class: "h3s-btn", onclick: () => actions.toggle("settingsOpen"), title: "All settings", "aria-label": "Settings" }, icon("gear")),
      h("button", { class: "h3s-btn go", disabled: !ready || Boolean(S.planError), title: S.planError ? `The plan failed: ${S.planError}` : ready ? "Queues the connected workflow in ComfyUI" :
        "Connect Director Output to H3 Render Sequence or a sampler and a video output", onclick: generate }, icon("play"), "Generate"));
  }
  function generate() {
    app.queuePrompt(0, 1);
    flash(`Queued: ${S.plan ? S.plan.chunks.length : "?"} render part(s). Progress at the top, result in the Save Video node.`);
    render();
  }

  function render() {
    if (closed) return;
    if (S.dragging) { S.pending = true; return; }
    S.pending = false; S.selectedRange = selectedRange(); S.duration = Number(S.values.project_seconds) || 1; S.picture = firstPicture();
    const top = root.scrollTop;
    updateStudioPage(page, [header(),
      S.docError ? h("div", { class: "h3s-toast h3s-warn" }, `The saved shot data is invalid and is left unchanged: ${S.docError}`) : null,
      manualPromptAlert(S, actions),
      h("div", { class: "h3s-body" },
        h("main", { class: "h3s-main" }, promptView(S, actions), contentView(S, actions), timelineView(S, actions)),
        h("div", { class: "h3s-side" }, sideView(S, actions))),
      footerView(S, actions), drawerView(S, actions), settingsView(S, actions), floating()].filter(Boolean));
    clearInterval(tick); tick = S.busy ? setInterval(() => { const clock = root.querySelector(".h3s-ai-clock"); if (clock) clock.textContent = aiClock(); }, 1000) : null;
    root.scrollTop = top;
    restoreTimeline(root, S);
  }

  function refresh() { if (S.dragging) return; load(S); edits.refresh(); schedulePlan(); render(); }
  function aiClock() { return `${fmt(Math.floor((Date.now() - S.aiStarted) / 1000))} of at most ${fmt(S.aiTimeout)}`; }
  // Messages float over the bottom of the window, so they are seen wherever the Studio is scrolled to.
  function floating() {
    const items = [];
    if (S.busy) items.push(h("div", { class: "h3s-toast busy", role: "status" }, icon("spark"),
      h("span", {}, S.busy === "build" ? S.buildStep : S.busy === "split" ? "AI is splitting the prompt into shots …"
        : S.busy.startsWith("write") ? "AI is writing the part's prompt …" : "AI is writing a text for this shot …"),
      h("span", { class: "h3s-ai-clock h3s-muted" }, aiClock()), h("button", { class: "h3s-btn ghost small", onclick: actions.cancelAI }, "Cancel")));
    if (S.notice) items.push(h("div", { class: S.notice.error ? "h3s-toast error" : "h3s-toast", role: S.notice.error ? "alert" : "status" },
      h("span", {}, S.notice.text), S.notice.undo ? h("button", { class: "h3s-btn small", onclick: () => { const undo = S.notice.undo; S.notice = null; undo(); } }, "Undo") : null,
      h("button", { class: "h3s-btn ghost small", title: "Dismiss", "aria-label": "Dismiss",
        onclick: () => { S.notice = null; render(); } }, icon("close", 14))));
    if (S.toast) items.push(h("div", { class: "h3s-toast", role: "status" }, S.toast));
    return items.length ? h("div", { class: "h3s-float" }, items) : null;
  }
  function close() {
    closed = true; clearTimeout(timer); clearTimeout(toastTimer); clearInterval(tick); ai.dispose(); progress.dispose();
    releaseKeys();
    document.removeEventListener("ng-context-changed", outside);
    open.delete(node); root.remove();
    if (!host) document.dispatchEvent(new CustomEvent("ng-context-changed"));
  }
  // Changes from elsewhere (a Context node edited, a link changed) reach an open Studio, but not its own writes.
  function outside() { if (!echo) refresh(); }
  root.onkeydown = (event) => {
    if (event.defaultPrevented || edits.key(event)) return;
    if (event.key !== "Escape" || event.target.closest?.("select") || !full) return;
    event.stopPropagation(); if (host) setFull(false); else close();
  };
  document.addEventListener("ng-context-changed", outside);
  const releaseKeys = bindTimelineKeys(root, (event) => edits.key(event));
  if (host) keepKeys(root); // in the graph and lifted to full screen alike
  (host || document.body).append(root);
  const handle = { root, close, refresh, setFull };
  open.set(node, handle);
  render(); schedulePlan(); if (full) root.focus();
  return handle;
}

export function closeStudio(node) { open.get(node)?.close(); }
