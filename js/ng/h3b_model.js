// The H3 Storyboard's data: a board of numbered panels, each a stack of layers, and the geometry of the sheet the
// browser draws (title line on top, panels in a grid, each with its picture and a caption under it). No DOM here, so
// the rules can be tested with node. ng/core/storyboard.py reads the same board.
export const FORMAT = "h3-storyboard";
export const MAX_PANELS = 9;
export const ASPECTS = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:3": [4, 3], "3:4": [3, 4], "21:9": [21, 9] };
export const SHEET_WIDTH = 1672;   // the width of the user's ChatGPT boards (1672 x 941 for four 16:9 panels)
export const PICTURE_LONG = 1280;  // a panel's own picture, long side

const MARGIN = 10, GAP = 12, TITLE = 64, CAPTION = 74, CAST_H = 76;

export function newId(prefix) {
  return `${prefix}${Math.random().toString(36).slice(2, 9)}`;
}

export function newPanel(seconds = 2.5) {
  return { id: newId("p"), seconds, title: "", caption: "", shot: "", first_frame: false, last_frame: false, layers: [] };
}

export function newBoard() {
  return { format: FORMAT, schema_version: 1, id: newId("sb"), title: "", subtitle: "", aspect: "16:9", idea: "",
    panels: [1, 2, 3, 4].map(() => newPanel(2.5)), library: [] };
}

// A layer's place is relative to its panel's picture: x/y the centre (0..1 of width/height), scale the width of a picture
// layer as a part of the panel's width, size the height of a text line as a part of the panel's height.
export function newLayer(kind, extra = {}) {
  const base = { id: newId("l"), kind, name: "", x: 0.5, y: 0.5, rotation: 0, flip: false, opacity: 1, hidden: false };
  // redrawn: the panel redrawn by the image model (stage 3); it is left out of the collage the next redraw starts from.
  if (kind === "image") return { ...base, src: null, scale: 0.6, redrawn: false, ...extra };
  if (kind === "text") return { ...base, text: "Text", size: 0.08, color: "#FFFFFF", ...extra };
  return { ...base, kind: "fill", color: "#1B2233", ...extra };
}

const num = (value, fallback, lo, hi) => {
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
};

function readLayer(raw) {
  if (!raw || typeof raw !== "object" || !["image", "text", "fill"].includes(raw.kind)) return null;
  const layer = newLayer(raw.kind, { id: String(raw.id || newId("l")), name: String(raw.name || "") });
  Object.assign(layer, { x: num(raw.x, 0.5, -1, 2), y: num(raw.y, 0.5, -1, 2), rotation: num(raw.rotation, 0, -360, 360),
    flip: Boolean(raw.flip), opacity: num(raw.opacity, 1, 0, 1), hidden: Boolean(raw.hidden) });
  if (raw.kind === "image") {
    const src = raw.src && typeof raw.src === "object" && raw.src.filename ? { filename: String(raw.src.filename),
      subfolder: String(raw.src.subfolder || ""), type: raw.src.type === "output" ? "output" : "input" } : null;
    Object.assign(layer, { src, scale: num(raw.scale, 0.6, 0.02, 5), redrawn: Boolean(raw.redrawn) });
  } else if (raw.kind === "text") Object.assign(layer, { text: String(raw.text ?? ""), size: num(raw.size, 0.08, 0.01, 0.5),
    color: /^#[0-9a-f]{6}$/i.test(raw.color) ? raw.color : "#FFFFFF" });
  else layer.color = /^#[0-9a-f]{6}$/i.test(raw.color) ? raw.color : "#1B2233";
  return layer;
}

// The board's own pictures (figures and backgrounds made with Qwen Image 2.1), offered on every panel.
function readItem(raw) {
  const layer = raw && readLayer({ kind: "image", src: raw.src });
  return layer?.src ? { id: String(raw.id || newId("a")), name: String(raw.name || ""), kind: raw.kind === "background" ? "background" : "figure",
    src: layer.src } : null;
}

// { board, error }: a saved board, repaired where it can be; an empty text is a new board.
export function readBoard(text) {
  if (!String(text || "").trim()) return { board: newBoard(), error: "" };
  let raw;
  try { raw = JSON.parse(text); } catch (error) { return { board: newBoard(), error: `The saved storyboard is not readable (${error.message}); a new one is shown.` }; }
  if (!raw || raw.format !== FORMAT) return { board: newBoard(), error: "The saved data is no H3 storyboard; a new one is shown." };
  const panels = (Array.isArray(raw.panels) ? raw.panels : []).slice(0, MAX_PANELS).map((p) => ({
    id: String(p?.id || newId("p")), seconds: num(p?.seconds, 2.5, 0.1, 600), title: String(p?.title || ""),
    caption: String(p?.caption || ""), shot: String(p?.shot || ""), first_frame: Boolean(p?.first_frame), last_frame: Boolean(p?.last_frame),
    layers: (Array.isArray(p?.layers) ? p.layers : []).map(readLayer).filter(Boolean) }));
  return { board: { format: FORMAT, schema_version: 1, id: String(raw.id || newId("sb")), title: String(raw.title || ""),
    subtitle: String(raw.subtitle || ""), aspect: ASPECTS[raw.aspect] ? raw.aspect : "16:9", idea: String(raw.idea || ""),
    panels: panels.length ? panels : [newPanel()], library: (Array.isArray(raw.library) ? raw.library : []).map(readItem).filter(Boolean) }, error: "" };
}

export function writeBoard(board) {
  return JSON.stringify(board);
}

// [start, end] in seconds of each panel, end to end from 0.
export function panelTimes(board) {
  let start = 0;
  return board.panels.map((panel) => { const end = Math.round((start + Number(panel.seconds)) * 1000) / 1000; const span = [start, end]; start = end; return span; });
}

export function fmtSeconds(value) {
  return String(Math.round(value * 10) / 10);
}

export function setPanelCount(board, count) {
  const n = Math.max(1, Math.min(MAX_PANELS, Math.round(count)));
  const last = board.panels[board.panels.length - 1]?.seconds || 2.5;
  const panels = board.panels.slice(0, n);
  while (panels.length < n) panels.push(newPanel(last));
  return { ...board, panels };
}

// Columns and rows of the sheet: landscape panels two side by side up to four, three up to nine; portrait panels in up
// to two rows.
export function grid(count, aspect) {
  const [w, h] = ASPECTS[aspect] || ASPECTS["16:9"];
  let cols;
  if (h > w) cols = count <= 4 ? count : Math.ceil(count / 2);
  else if (w === h) cols = count <= 3 ? count : count <= 4 ? 2 : 3;
  else cols = count <= 2 ? count : count <= 4 ? 2 : 3;
  return { cols, rows: Math.ceil(count / cols) };
}

// Where everything sits on the sheet, in sheet pixels.
export function sheetLayout(board, width = SHEET_WIDTH, cast = []) {
  const [aw, ah] = ASPECTS[board.aspect] || ASPECTS["16:9"];
  const { cols, rows } = grid(board.panels.length, board.aspect);
  const title = board.title || board.subtitle ? TITLE : 0;
  const actors = (Array.isArray(cast) ? cast : []).filter((c) => c && c.name && c.src).slice(0, 8);
  const castBand = actors.length ? CAST_H + GAP : 0;
  const cw = actors.length ? Math.min(240, (width - 2 * MARGIN - (actors.length - 1) * GAP) / actors.length) : 0;
  const castX0 = Math.round((width - (actors.length * cw + Math.max(0, actors.length - 1) * GAP)) / 2);
  const castBoxes = actors.map((actor, i) => ({ x: Math.round(castX0 + i * (cw + GAP)), y: MARGIN + title,
    w: Math.round(cw), h: CAST_H, name: String(actor.name), src: actor.src }));
  const pw = (width - 2 * MARGIN - (cols - 1) * GAP) / cols, ph = pw * ah / aw;
  const panels = board.panels.map((_, index) => {
    const col = index % cols, row = Math.floor(index / cols);
    const x = MARGIN + col * (pw + GAP), y = MARGIN + title + castBand + row * (ph + CAPTION + GAP);
    return { x, y, w: pw, h: ph + CAPTION, pic: { x, y, w: pw, h: ph }, cap: { x, y: y + ph, w: pw, h: CAPTION } };
  });
  return { width, height: Math.round(2 * MARGIN + title + castBand + rows * (ph + CAPTION) + (rows - 1) * GAP), title, cast: castBoxes, panels };
}

// The size of one panel's own picture (the panels output), long side PICTURE_LONG.
export function pictureSize(aspect) {
  const [w, h] = ASPECTS[aspect] || ASPECTS["16:9"];
  return w >= h ? [PICTURE_LONG, Math.round(PICTURE_LONG * h / w)] : [Math.round(PICTURE_LONG * w / h), PICTURE_LONG];
}

// A layer's box in a picture of width pw and height ph: centre, width and height before rotation. natural: the
// [width, height] of a picture layer's file.
export function layerBox(layer, pw, ph, natural = [1, 1]) {
  const cx = layer.x * pw, cy = layer.y * ph;
  if (layer.kind === "fill") return { cx: pw / 2, cy: ph / 2, w: pw, h: ph };
  if (layer.kind === "text") {
    const size = layer.size * ph, lines = String(layer.text || " ").split("\n");
    const longest = Math.max(...lines.map((line) => line.length), 1);
    return { cx, cy, w: Math.max(size, longest * size * 0.55), h: size * 1.2 * lines.length };
  }
  const w = layer.scale * pw;
  return { cx, cy, w, h: w * (natural[1] || 1) / (natural[0] || 1) };
}

// Whether the point (px, py) of the picture lies on the layer, rotation included.
export function hits(layer, px, py, pw, ph, natural) {
  const box = layerBox(layer, pw, ph, natural);
  const a = -layer.rotation * Math.PI / 180, dx = px - box.cx, dy = py - box.cy;
  const rx = dx * Math.cos(a) - dy * Math.sin(a), ry = dx * Math.sin(a) + dy * Math.cos(a);
  return Math.abs(rx) <= box.w / 2 && Math.abs(ry) <= box.h / 2;
}

// The view URL of a picture layer's file.
export function srcUrl(src) {
  if (!src) return "";
  const q = new URLSearchParams({ filename: src.filename, subfolder: src.subfolder || "", type: src.type || "input" });
  return `/view?${q}`;
}

// The name LoadImage reads a layer's file by ("h3-storyboard/a.png", or "... [output]" for a cut-out).
export function loadName(src) {
  const name = src.subfolder ? `${src.subfolder}/${src.filename}` : src.filename;
  return src.type === "output" ? `${name} [output]` : name;
}

// The shot texts of the panels as the Director's shot document (the node's "shots" output computes the same).
export function shotsDocument(board) {
  const times = panelTimes(board);
  return { format: "h3-director-shots", schema_version: 1, shots: board.panels.map((panel, index) => ({
    id: `sb-${panel.id}`, start: times[index][0], end: times[index][1],
    text: (panel.shot || panel.caption || panel.title || "").trim(), media: [], spoken: [], locked_fields: [], draft: null })) };
}

const BEAT_MARK = /\d+(?:[.,]\d+)?\s*s?\s*[–-]\s*\d+(?:[.,]\d+)?\s*s\s*:\s*/g;

// The image model's instruction for redrawing one panel: image 1 is the collage (it sets composition and size), images 2..
// are the character references, in the order of refs ([{name, description}]).
export function redrawPrompt(board, index, refs = []) {
  const panel = board.panels[index];
  const story = (panel.caption || panel.shot || panel.title || "").replace(BEAT_MARK, "").replace(/@(\S)/g, "$1").trim();
  const parts = [
    `Redraw <image1> as one finished, polished storyboard frame${refs.length ? " in the art style of the character references" : ""}.`,
    "Keep its composition exactly: the same figures at the same places, with the same sizes, poses and directions, the same "
      + "background layout and the same framing.",
    "Remove every cut-out edge, collage seam and pasted look: one consistent scene with consistent light and shadows.",
    ...refs.map((ref, i) => `${ref.name} looks exactly as in <image${i + 2}>: face, hair, outfit and colours${ref.description ? ` (${ref.description.replace(/\.$/, "")})` : ""}.`),
    story ? `What happens: ${story}` : "",
    "No text, no captions, no labels, no panel border.",
  ];
  return parts.filter(Boolean).join(" ");
}

// A figure from a character sheet (<image1>) in a new pose, on a transparent background: the RGBA wording of ComfyUI's
// Qwen Image 2.1 template, which then decodes a picture with an alpha channel.
export function figurePrompt(name, pose) {
  return `This is an RGBA format image with transparency. A single full-body figure of ${name || "the character"} as shown in <image1>, with `
    + `exactly the same face, hair, outfit, colours and props: ${String(pose || "standing, facing the camera").trim().replace(/\.$/, "")}. `
    + "Only this one figure, no character sheet layout, no text, no other people. The image has an alpha channel and a transparent background.";
}

// An empty background for a panel; figures are placed on it as layers.
export function backgroundPrompt(place) {
  return `${String(place || "").trim().replace(/\.$/, "")}. An empty scene for a storyboard panel: no people, no characters, no text.`;
}

// The size of a picture made for this panel format, about one megapixel at multiples of 32 (16:9 is 1376 x 768).
export function makeSize(aspect) {
  const [w, h] = ASPECTS[aspect] || ASPECTS["16:9"];
  return [Math.round(Math.sqrt(1024 * 1024 * w / h) / 32) * 32, Math.round(Math.sqrt(1024 * 1024 * h / w) / 32) * 32];
}

// The pictures any panel can take: the board's own, then every picture already on a panel (cut-outs, uploads), once each.
export function libraryItems(board) {
  const seen = new Set(), out = [];
  const add = (item) => { const url = srcUrl(item.src); if (!seen.has(url)) { seen.add(url); out.push(item); } };
  (board.library || []).forEach(add);
  board.panels.flatMap((p) => p.layers).filter((l) => l.kind === "image" && l.src && !l.redrawn)
    .forEach((l) => add({ id: l.id, name: l.name, kind: "picture", src: l.src }));
  return out;
}

// The Director's shots of the board: one shot per panel, the storyboard card on every shot and a panel's own card as the
// first or last frame of its shot. ids.frames / ids.lastFrames map panel index to context id.
export function directorShots(board, ids = {}) {
  return shotsDocument(board).shots.map((shot, index) => ({ ...shot, media: [
    ...(ids.storyboard ? [{ schema_version: 1, context_id: ids.storyboard, role: "storyboard" }] : []),
    ...(ids.frames?.[index] ? [{ schema_version: 1, context_id: ids.frames[index], role: "first_frame" }] : []),
    ...(ids.lastFrames?.[index] ? [{ schema_version: 1, context_id: ids.lastFrames[index], role: "last_frame" }] : []) ] }));
}

const round3 = (v) => Math.round(Number(v || 0) * 1000) / 1000;
const hasCard = (shot, id) => (shot.media || []).some((m) => m.role === "storyboard" && m.context_id === id);
const anyCard = (shot) => (shot.media || []).find((m) => m.role === "storyboard")?.context_id || "";

// Updates this board's shots in the Director's shot list in-place (preserving spoken lines, locks, extra media and other
// scenes, shifting later scenes if the board's length changed), or appends the board as the next scene after existing shots.
export function mergeDirectorShots(existingShots, board, ids = {}, { replaceAll = false } = {}) {
  const fresh = directorShots(board, ids);
  if (!Array.isArray(existingShots) || !existingShots.length || replaceAll) return fresh;
  const panelSet = new Set(board.panels.map((p) => `sb-${p.id}`));
  const byCard = Boolean(ids.storyboard) && existingShots.some((s) => hasCard(s, ids.storyboard));
  const isOwned = (shot) => byCard ? hasCard(shot, ids.storyboard)
    : panelSet.has(shot.id) && (!ids.storyboard || !anyCard(shot) || anyCard(shot) === ids.storyboard);
  const ownedIdx = existingShots.map((s, i) => (isOwned(s) ? i : -1)).filter((i) => i >= 0);
  const taken = new Set(existingShots.filter((_, i) => !ownedIdx.includes(i)).map((s) => s.id));
  if (!ownedIdx.length) {
    const offset = round3(Math.max(0, ...existingShots.map((s) => Number(s.end) || 0)));
    const appended = fresh.map((shot, index) => {
      const pid = board.panels[index].id;
      const id = taken.has(shot.id) ? `sb-${ids.storyboard || board.id}-${pid}` : shot.id;
      taken.add(id);
      return { ...shot, id, start: round3(offset + shot.start), end: round3(offset + shot.end) };
    });
    return [...existingShots, ...appended];
  }
  const first = ownedIdx[0], last = ownedIdx[ownedIdx.length - 1];
  const offset = round3(existingShots[first].start), oldEnd = round3(existingShots[last].end);
  const owned = ownedIdx.map((i) => existingShots[i]);
  const updated = fresh.map((shot, index) => {
    const pid = board.panels[index].id;
    const prev = owned.find((s) => s.id === `sb-${pid}` || String(s.id || "").endsWith(`-${pid}`)) || owned[index];
    let id = prev?.id && !taken.has(prev.id) ? prev.id : shot.id;
    if (taken.has(id)) id = `sb-${ids.storyboard || board.id}-${pid}`;
    taken.add(id);
    const locked = Array.isArray(prev?.locked_fields) ? prev.locked_fields : [];
    const extra = (prev?.media || []).filter((m) => !["storyboard", "first_frame", "last_frame"].includes(m.role));
    return { ...shot, id, start: round3(offset + shot.start), end: round3(offset + shot.end),
      text: locked.includes("text") && typeof prev?.text === "string" ? prev.text : shot.text,
      media: locked.includes("media") && Array.isArray(prev?.media) ? prev.media : [...shot.media, ...extra],
      spoken: Array.isArray(prev?.spoken) ? prev.spoken : [], locked_fields: locked, draft: prev?.draft ?? null };
  });
  const delta = round3((updated.at(-1)?.end ?? offset) - oldEnd);
  const before = existingShots.slice(0, first).filter((_, i) => !ownedIdx.includes(i));
  const after = existingShots.slice(first + 1).filter((_, i) => !ownedIdx.includes(first + 1 + i))
    .map((s) => ({ ...s, start: round3(s.start + delta), end: round3(s.end + delta) }));
  return [...before, ...updated, ...after];
}

// Pulls updated panel durations and shot texts from the connected Director back into the board's panels.
export function syncFromDirector(board, shots, storyboardId = "") {
  if (!Array.isArray(shots) || !shots.length) return { updated: 0, matched: 0 };
  const byCard = Boolean(storyboardId) && shots.some((s) => hasCard(s, storyboardId));
  const panelSet = new Set(board.panels.map((p) => `sb-${p.id}`));
  const byId = shots.filter((s) => (panelSet.has(s.id) || board.panels.some((p) => String(s.id || "").endsWith(`-${p.id}`)))
    && (!storyboardId || !anyCard(s) || anyCard(s) === storyboardId));
  const owned = byCard ? shots.filter((s) => hasCard(s, storyboardId))
    : byId.length ? byId : !shots.some(anyCard) && shots.length === board.panels.length ? shots : [];
  if (!owned.length) return { updated: 0, matched: 0 };
  let updated = 0, matched = 0;
  board.panels.forEach((panel, index) => {
    const shot = owned.find((s) => s.id === `sb-${panel.id}` || String(s.id || "").endsWith(`-${panel.id}`)) || owned[index];
    if (!shot) return;
    matched += 1;
    const seconds = num(round3(Number(shot.end) - Number(shot.start)), panel.seconds, 0.1, 600);
    const text = typeof shot.text === "string" ? shot.text.trim() : "";
    const cur = (panel.shot || panel.caption || panel.title || "").trim();
    let changed = false;
    if (Math.abs(seconds - panel.seconds) > 1e-4) { panel.seconds = seconds; changed = true; }
    if (typeof shot.text === "string" && text !== cur && (text || panel.shot)) { panel.shot = text; changed = true; }
    if (changed) updated += 1;
  });
  return { updated, matched };
}

const PNG_SIG = [137, 80, 78, 71, 13, 10, 26, 10];
const TEXT_KEY = "h3-storyboard\0";
const CRC_TABLE = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// Embeds the storyboard project JSON into a PNG tEXt chunk ("h3-storyboard") before IEND so the sheet PNG can reload the board.
export function embedBoardPng(pngBytes, board) {
  const src = pngBytes instanceof Uint8Array ? pngBytes : new Uint8Array(pngBytes || []);
  if (src.length < 20 || PNG_SIG.some((b, i) => src[i] !== b)) return src;
  const payload = new TextEncoder().encode(TEXT_KEY + (typeof board === "string" ? board : writeBoard(board)));
  const chunk = new Uint8Array(12 + payload.length), view = new DataView(chunk.buffer);
  view.setUint32(0, payload.length);
  chunk.set([116, 69, 88, 116], 4);
  chunk.set(payload, 8);
  view.setUint32(8 + payload.length, crc32(chunk.subarray(4, 8 + payload.length)));
  let iend = src.length - 12, pos = 8;
  while (pos + 8 <= src.length) {
    const len = new DataView(src.buffer, src.byteOffset + pos, 8).getUint32(0);
    if (String.fromCharCode(src[pos + 4], src[pos + 5], src[pos + 6], src[pos + 7]) === "IEND") { iend = pos; break; }
    pos += 12 + len;
  }
  const out = new Uint8Array(src.length + chunk.length);
  out.set(src.subarray(0, iend), 0);
  out.set(chunk, iend);
  out.set(src.subarray(iend), iend + chunk.length);
  return out;
}

// Extracts and validates an embedded storyboard project from a PNG file's "h3-storyboard" tEXt chunk, or returns null.
export function extractBoardPng(pngBytes) {
  const src = pngBytes instanceof Uint8Array ? pngBytes : new Uint8Array(pngBytes || []);
  if (src.length < 20 || PNG_SIG.some((b, i) => src[i] !== b)) return null;
  const keyBytes = new TextEncoder().encode(TEXT_KEY);
  let pos = 8;
  while (pos + 12 <= src.length) {
    const len = new DataView(src.buffer, src.byteOffset + pos, 8).getUint32(0);
    if (pos + 12 + len > src.length) break;
    const type = String.fromCharCode(src[pos + 4], src[pos + 5], src[pos + 6], src[pos + 7]);
    if (type === "tEXt" && len > keyBytes.length) {
      const data = src.subarray(pos + 8, pos + 8 + len);
      if (keyBytes.every((b, i) => data[i] === b)) {
        const { board, error } = readBoard(new TextDecoder().decode(data.subarray(keyBytes.length)));
        if (!error) return board;
      }
    }
    if (type === "IEND") break;
    pos += 12 + len;
  }
  return null;
}
