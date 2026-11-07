// The Studio's data rules without a DOM: the shot document with audio lanes, mouse edits on a 0.1 s grid,
// render-part colours and the canvas presets. Everything here is checked with node (tests/ng/js/test_h3s_model.mjs).
import { readStory, createShot, SHOT_FORMAT } from "./ng_story_model.js";

export const GRID = 0.1;
export const MIN_LENGTH = 0.5;
export const CLIP_MODES = ["lock", "copy", "ref"];
export const DURATIONS = [5, 8, 10, 15, 20, 30, 60, 120];
export const PART_COLORS = [["#4FB8C4", "#12272B"], ["#E58A5C", "#2C1C14"], ["#9C8CE8", "#1E1A33"],
  ["#CFC05A", "#272514"], ["#6FBF73", "#16271A"], ["#E07A9B", "#2C1520"]];

export const r1 = (value) => Math.round(value * 10) / 10;
// Mouse and number edits snap to the 0.1 s grid, but never past a bound: a neighbour's edge may be off the grid
// (imported or older data), and rounding after clamping used to push a shot over it.
// Returns null when no value fits (lo > hi, e.g. an imported shot already shorter than MIN_LENGTH): the edit is refused.
export function snapWithin(value, lo, hi) {
  if (lo > hi + 1e-9) return null;
  const snapped = r1(value);
  return snapped < lo ? lo : snapped > hi ? hi : snapped;
}
const exact = (value) => Math.round(value * 1e6) / 1e6;
export function fmt(seconds) {
  const value = r1(seconds);
  return `${Number.isInteger(value) ? value : value.toFixed(1)} s`;
}
export const span = (a, b) => `${fmt(a).replace(" s", "")}–${fmt(b)}`;
export const sorted = (items) => [...items].sort((x, y) => x.start - y.start);
export const partColor = (index) => PART_COLORS[index % PART_COLORS.length];

function uid(prefix) {
  return `${prefix}_${globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2)}`;
}

function validClip(clip) {
  return clip && clip.schema_version === 1 && typeof clip.id === "string" && clip.id && typeof clip.context_id === "string"
    && clip.context_id && [clip.start, clip.end].every((v) => typeof v === "number" && Number.isFinite(v) && v >= 0)
    && clip.end > clip.start && CLIP_MODES.includes(clip.mode ?? "ref") && (clip.offset === undefined || (Number.isFinite(clip.offset) && clip.offset >= 0));
}

// shots: the Story editor's records; audio: lane clips; lanes: lane order, including empty lanes; look: what every
// render part shares (style, place, light), sent in place of the Prompt once there are shots; partPrompts: a render
// part's own prompt {index, key, text, by}, used while `key` is still that of the part's compiled prompt.
// skipped: ids of audio clips that are invalid or repeat an id; they are left out, the rest stays editable.
// Cards that are both on a shot and on an audio lane: both play (shot_bindings.py), which is easy to miss (BUG-004).
export function boundAndLaned(shots, audio) {
  const bound = new Set(shots.flatMap((shot) => (shot.media || []).map((binding) => binding.context_id)));
  return [...new Set(audio.map((clip) => clip.context_id).filter((id) => bound.has(id)))];
}

export function readProject(text) {
  const story = readStory(text || "");
  if (story.error || !(text || "").trimStart().startsWith("{")) return { shots: story.shots, audio: [], lanes: [], control: [], look: "", partPrompts: [], skipped: [], error: story.error };
  const data = JSON.parse(text), audio = [], skipped = [], seen = new Set();
  for (const clip of Array.isArray(data.audio) ? data.audio : []) {
    if (validClip(clip) && !seen.has(clip.id)) { seen.add(clip.id); audio.push({ offset: 0, mode: "ref", lane: "", ...clip }); }
    else skipped.push(typeof clip?.id === "string" && clip.id ? clip.id : "(no id)");
  }
  const lanes = [...new Set([...(data.audio_lanes || []), ...audio.map((clip) => clip.lane)])].filter(Boolean);
  const partPrompts = (Array.isArray(data.part_prompts) ? data.part_prompts : [])
    .filter((entry) => Number.isInteger(entry?.index) && entry.index >= 0 && typeof entry.key === "string" && typeof entry.text === "string");
  const control = Array.isArray(data.control) ? data.control : [], controlIds = new Set();
  const badControl = (data.control !== undefined && !Array.isArray(data.control)) || control.some((clip) => {
    if (!validClip({ ...clip, mode: "ref" }) || controlIds.has(clip.id)) return true;
    controlIds.add(clip.id); return false;
  });
  return { shots: story.shots, audio, lanes, control, look: typeof data.look === "string" ? data.look : "", partPrompts, skipped,
    error: badControl ? "The saved control clips are invalid. Repair their timing or IDs before editing this project." : "",
    conflicts: boundAndLaned(story.shots, audio) };
}

export function writeProject({ shots, audio, lanes, control = [], look = "", partPrompts = [] }) {
  if (!shots.length && !audio.length && !lanes.length && !control.length && !look.trim() && !partPrompts.length) return "";
  return JSON.stringify({ format: SHOT_FORMAT, schema_version: 1, shots, audio, audio_lanes: lanes, ...(look.trim() ? { look } : {}),
    ...(partPrompts.length ? { part_prompts: partPrompts } : {}), ...(control.length ? { control, control_lanes: ["control"] } : {}) });
}

// The Director's widgets after a Context rename: the Prompt, timed text, or the shot document's shot texts, spoken lines,
// Look and render-part prompts (BUG-079). Returns only what changed.
export function renamedDirector(now, rename) {
  const changes = {}, idea = rename(now.idea || "");
  if (idea !== (now.idea || "")) changes.idea = idea;
  const project = readProject(now.shots || "");
  if (project.error) return changes;
  if (!(now.shots || "").trimStart().startsWith("{")) {
    const text = rename(now.shots || "");
    if (text !== (now.shots || "")) changes.shots = text;
    return changes;
  }
  const look = rename(project.look);
  const partPrompts = project.partPrompts.map((part) => ({ ...part, text: rename(part.text) }));
  const shots = project.shots.map((shot) => ({ ...shot, text: rename(shot.text),
    spoken: shot.spoken.map((line) => typeof line.text === "string" ? { ...line, text: rename(line.text) } : line) }));
  const changed = look !== project.look || partPrompts.some((part, index) => part.text !== project.partPrompts[index].text)
    || shots.some((shot, index) => shot.text !== project.shots[index].text
      || shot.spoken.some((line, at) => line.text !== project.shots[index].spoken[at].text));
  if (changed) changes.shots = writeProject({ ...project, shots, look, partPrompts });
  return changes;
}

// A removed audio lane takes its clips with it: readProject rebuilds lanes from the clips, so a clip left behind brought
// the lane back on the next load (BUG-023).
export function removeLane({ lanes, audio }, lane) {
  return { lanes: lanes.filter((entry) => entry !== lane), audio: audio.filter((clip) => clip.lane !== lane) };
}

// A part's own prompt replaces any earlier one of that part; text "" removes it.
export function setPartPrompt(list, index, key, text, by) {
  const rest = (list || []).filter((entry) => entry.index !== index);
  return text.trim() ? [...rest, { index, key, text, by }].sort((a, b) => a.index - b.index) : rest;
}

// A picture's role in one shot: its own choice, or the card's ("context"). Only pictures have a choice here.
export const PICTURE_ROLES = [["context", "Card's role"], ["reference", "Reference"], ["first_frame", "First frame"],
  ["last_frame", "Last frame"], ["keyframe", "Keyframe"]];
export function isKeyframe(binding, entry) {
  return binding.role === "keyframe" || ((binding.role || "context") === "context" && Boolean(entry?.usage?.includes("keyframe")));
}
// A Keyframe sits at its own time in the shot (seconds after the shot's start); new ones start in the middle.
export const middleOf = (shot) => r1((shot.end - shot.start) / 2);
export function keyframeAt(binding, shot) {
  return Number(binding.at_s) >= 0 ? Math.min(Number(binding.at_s), shot.end - shot.start) : 0;
}
// Where the plan put it: the last frame of a render part (FL2VA: the trained slot, the shot runs on), or inside one.
export function keyframeLanding(plan, shotId, contextId) {
  for (const chunk of plan?.chunks || []) {
    if (!chunk.shots.some((entry) => entry.shot_id === shotId)) continue;
    const ref = chunk.refs.find((entry) => entry.ctx_id === contextId && ["last_frame", "keyframe"].includes(entry.kind));
    if (ref?.kind === "last_frame")
      return { seconds: Math.round((chunk.story_end_f - 1) / (plan.fps || 24) * 100) / 100, part: chunk.index + 1, inside: false };
    if (ref) return { seconds: null, part: chunk.index + 1, inside: true };
  }
  return null;
}

export function newShot(start, end, media = []) {
  return createShot({ start, end, media: media.map((id) => ({ schema_version: 1, context_id: id, role: "context" })) });
}

// Spoken lines of one shot, in order. Editing keeps every other line as it is; the only line left untouched (no text,
// no speaker, default language) is dropped, so a shot without dialogue stays without one, but a language chosen before
// typing, or kept while retyping, stays. Empty lines do not compile. A new line starts with the previous line's language.
const SPOKEN = { schema_version: 1, text: "", speaker_id: "", voice: "a narrator", language: "English", delivery: "says" };
export function editSpoken(lines, index, change) {
  const next = [...lines];
  next[index] = { ...SPOKEN, ...lines[index], ...change };
  const untouched = !next[0].text.trim() && !next[0].speaker_id && next[0].language === SPOKEN.language && next[0].delivery === SPOKEN.delivery;
  return next.length === 1 && untouched ? [] : next;
}
export const addSpoken = (lines) => [...lines, { ...SPOKEN, language: lines.at(-1)?.language || "English" }];
export const removeSpoken = (lines, index) => lines.filter((_line, at) => at !== index);

export function newClip(contextId, lane, start, end, mode = "ref") {
  return { schema_version: 1, id: uid("clip"), context_id: contextId, start, end, offset: 0, mode, lane };
}

export const newLane = () => uid("lane");

// Free room around `sec` among non-overlapping items: {prev, next}, or null when `sec` is inside one.
export function gapAt(items, sec, total) {
  let prev = 0, next = total;
  for (const item of sorted(items)) {
    if (item.end <= sec) prev = item.end;
    else if (item.start > sec) { next = item.start; break; }
    else return null;
  }
  return { prev, next };
}

// Where a new item dropped at `sec` goes: up to `length` seconds of the free room there.
export function placeAt(items, sec, total, length) {
  const gap = gapAt(items, sec, total);
  if (!gap || gap.next - gap.prev < MIN_LENGTH) return null;
  const start = snapWithin(sec, gap.prev, gap.next - MIN_LENGTH);
  return { start, end: snapWithin(start + length, start + MIN_LENGTH, gap.next) };
}

export function nextClipStart(items, total) {
  const ordered = sorted(items);
  for (const sec of [ordered.at(-1)?.end || 0, 0, ...ordered.map((item) => item.end)]) {
    const gap = gapAt(items, sec, total);
    if (gap && gap.next - sec + 1e-9 >= MIN_LENGTH) return sec;
  }
  return null;
}

// "+ Shot": a 4 s shot in free room after `afterId` (or the last shot), else in the first free room of the project,
// else the anchor shot is halved and the new shot takes its second half. Returns {shots, id, split?} or null.
export function addShotAt(items, afterId, total, length = 4) {
  const list = sorted(items), anchor = list.find((item) => item.id === afterId) || list.at(-1);
  const add = (start, end) => { const shot = newShot(start, end); return { shots: [...items, shot], id: shot.id }; };
  const after = placeAt(items, anchor ? anchor.end : 0, total, length);
  if (after) return add(after.start, after.end);
  for (const sec of [0, ...list.map((item) => item.end)]) {
    const at = placeAt(items, sec, total, length);
    if (at) return add(at.start, at.end);
  }
  const wide = [anchor, ...list].find((item) => item && item.end - item.start >= 2 * MIN_LENGTH);
  if (!wide) return null;
  const middle = snapWithin((wide.start + wide.end) / 2, wide.start + MIN_LENGTH, wide.end - MIN_LENGTH), shot = newShot(middle, wide.end);
  return { shots: [...items.map((item) => (item.id === wide.id ? { ...item, end: middle } : item)), shot], id: shot.id, split: wide.id };
}

function neighbours(items, id, total) {
  const list = sorted(items), index = list.findIndex((item) => item.id === id);
  return { prev: index > 0 ? list[index - 1].end : 0, next: index < list.length - 1 ? list[index + 1].start : total };
}

// drag: {id, mode: move|left|right, start, end, reorder}. Shots may be carried over their neighbours (reorder);
// clips and edge drags stay between their neighbours.
export function dragTo(items, drag, delta, total) {
  const ds = r1(delta), length = drag.end - drag.start;
  const source = items.find((item) => item.id === drag.id);
  const fileClip = typeof source?.context_id === "string" && Number.isFinite(source?.offset);
  let start = drag.start, end = drag.end, target = null;
  if (drag.mode === "move" && drag.reorder) {
    start = snapWithin(drag.start + ds, 0, total - length) ?? drag.start;
    end = exact(start + length);
    // Like a sortable list: the leading edge passing another shot's middle puts the carried shot on its far side.
    const others = sorted(items.filter((item) => item.id !== drag.id)), edge = ds > 0 ? end : start;
    if (others.some((item) => start < item.end && end > item.start))
      target = others.filter((item) => (item.start + item.end) / 2 < edge).length;
  } else {
    const room = neighbours(items, drag.id, total);
    if (drag.mode === "move") {
      start = snapWithin(drag.start + ds, room.prev, room.next - length) ?? drag.start;
      end = start === drag.start ? drag.end : Math.min(exact(start + length), room.next);
    } else if (drag.mode === "left") {
      const earliest = fileClip ? Math.max(room.prev, drag.start - source.offset) : room.prev;
      start = snapWithin(drag.start + ds, earliest, drag.end - MIN_LENGTH) ?? drag.start;
    }
    else end = snapWithin(drag.end + ds, drag.start + MIN_LENGTH, room.next) ?? drag.end;
  }
  const offset = fileClip && drag.mode === "left" ? { offset: exact(source.offset + start - drag.start) } : {};
  return { items: items.map((item) => (item.id === drag.id ? { ...item, start, end, ...offset } : item)), target };
}

// Drop a carried shot at `target` among the others; lengths stay and the gaps of the layout before the drag are kept.
export function reorder(items, id, target, layout) {
  const byId = new Map(items.map((item) => [item.id, item]));
  const order = sorted(items.filter((item) => item.id !== id)).map((item) => item.id);
  order.splice(target, 0, id);
  const gaps = layout.map((item, index) => (index ? item.start - layout[index - 1].end : item.start));
  let time = gaps[0];
  const placed = new Map(order.map((key, index) => {
    const length = byId.get(key).end - byId.get(key).start, at = { start: exact(time), end: exact(time + length) };
    time += length + (gaps[index + 1] || 0);
    return [key, at];
  }));
  return items.map((item) => ({ ...item, ...placed.get(item.id) }));
}

// Which part of the source file a lane clip plays in each render part; plan chunks give their story range in seconds.
// A lock or copy clip is placed: each part plays its slice. A reference clip is not placed: every part it touches
// receives the clip's whole file window as a reference (legacy_bridge._lane_references).
export function clipParts(clip, chunks) {
  return chunks.filter((chunk) => clip.start < chunk.end_s && clip.end > chunk.start_s).map((chunk) => {
    const a = Math.max(clip.start, chunk.start_s), b = Math.min(clip.end, chunk.end_s);
    const file = clip.mode === "ref" ? [clip.offset, clip.offset + clip.end - clip.start] : [clip.offset + a - clip.start, clip.offset + b - clip.start];
    return { index: chunk.index, story: [a, b], file, reference: clip.mode === "ref" };
  });
}

// A shorter project: what is cut away (ids) and what is only shortened, so the Studio can name it and offer Undo.
export function trimToDuration(items, total) {
  const kept = clipToFit(items, total), ids = new Set(kept.map((item) => item.id));
  return { items: kept, removed: items.filter((item) => !ids.has(item.id)).map((item) => item.id),
    shortened: kept.filter((item) => item.end < items.find((old) => old.id === item.id).end).map((item) => item.id) };
}

// A longer project: the shot that reached the old end goes on to the new one. Otherwise the added time had no shot,
// and its render parts no text: a 10 s shot carrying the whole song's text left 17-27 s of a 27 s music video empty.
export function growToDuration(items, from, total) {
  const last = sorted(items).at(-1);
  if (!(total > from) || !last || Math.abs(last.end - from) > 0.05) return { items, grown: [] };
  return { items: items.map((item) => (item.id === last.id ? { ...item, end: total } : item)), grown: [last.id] };
}

export function clipToFit(items, total) {
  // Preserve short imported items that fit whole; do not create new fragments
  // below the editor's minimum when the project end cuts through an item.
  return items.filter((item) => item.start < total && (item.end <= total || total - item.start >= MIN_LENGTH - 1e-9))
    .map((item) => ({ ...item, end: Math.min(item.end, total) }));
}

// Native reference slots one render part uses. A shared image is presented once per Subject and takes a slot each time;
// a first/last frame that is already a Picture reuses that slot; guides and locked sound are not reference tokens.
export function chunkBudget(chunk) {
  const ids = { image: new Set(), video: new Set(), audio: new Set() };
  const pictures = new Set(chunk.refs.filter((ref) => ref.kind === "picture").map((ref) => ref.ctx_id));
  chunk.refs.forEach((ref, index) => {
    if (["first_frame", "last_frame"].includes(ref.kind) && pictures.has(ref.ctx_id)) return;
    const media = { picture: "image", first_frame: "image", last_frame: "image", video: "video", audio: "audio" }[ref.kind];
    if (media) ids[media].add(["picture", "audio"].includes(ref.kind) ? `${index}:${ref.ctx_id}` : `${ref.kind}:${ref.ctx_id}`);
  });
  return { image: ids.image.size, video: ids.video.size, audio: ids.audio.size, total: ids.image.size + ids.video.size + ids.audio.size };
}

// Measured settings of a known turbo LoRA (turbo_profiles.json, the table the Python side samples with), or null.
export function turboProfile(profiles, loraName) {
  const base = String(loraName || "").replace(/\\/g, "/").split("/").pop().replace(/\.[^.]+$/, "").toLowerCase();
  return Object.entries(profiles || {}).find(([name]) => name.toLowerCase() === base)?.[1] || null;
}
