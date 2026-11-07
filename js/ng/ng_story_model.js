// The existing String widget carries a versioned document after the first edit.
// Old timed text is read without changing the stored workflow until it is edited.
import { renameReferences } from "./ng_references.js";
export const SHOT_FORMAT = "h3-director-shots";
export const LOCK_FIELDS = ["timing", "text", "media", "spoken"];
const TIME = "(?:\\d+:)?\\d+(?:\\.\\d+)?s?";
const HEADER = new RegExp(`^\\s*(${TIME})\\s*(?:-|–|—|to)\\s*(${TIME})\\s*(?::|\\s)\\s*(.*)$`);

function seconds(token) {
  const parts = token.replace(/s$/, "").split(":").map(Number);
  return parts.length === 2 ? parts[0] * 60 + parts[1] : parts[0];
}

export function readStory(text) {
  if (text.trimStart().startsWith("{")) {
    try {
      const data = JSON.parse(text), seen = new Set();
      if (data.format !== SHOT_FORMAT || data.schema_version !== 1 || !Array.isArray(data.shots)) throw Error("Unsupported shot document.");
      for (const shot of data.shots) {
        if (!shot || typeof shot.id !== "string" || !shot.id.trim() || seen.has(shot.id)) throw Error("Shot IDs must be nonempty and unique.");
        seen.add(shot.id);
        if (![shot.start, shot.end].every(value => typeof value === "number" && Number.isFinite(value) && value >= 0) || typeof shot.text !== "string") throw Error("Invalid shot timing or text.");
        for (const key of ["media", "spoken", "locked_fields"]) if (shot[key] !== undefined && !Array.isArray(shot[key])) throw Error(`Invalid ${key}.`);
        if ((shot.locked_fields || []).some(key => !LOCK_FIELDS.includes(key))) throw Error("Unknown protected field.");
        for (const binding of shot.media || []) if (!binding || binding.schema_version !== 1 || typeof binding.context_id !== "string" || !binding.context_id.trim() || typeof (binding.role ?? "context") !== "string") throw Error("Invalid media binding.");
        for (const spoken of shot.spoken || []) {
          if (!spoken || spoken.schema_version !== 1) throw Error("Invalid spoken line.");
          for (const key of ["text", "speaker_id", "voice", "language", "delivery"]) if (spoken[key] !== undefined && typeof spoken[key] !== "string") throw Error("Invalid spoken field.");
          if (/\r|\n/.test(spoken.text || "") || ["speaker_id", "voice", "language", "delivery"].some(key => /[\r\n\[\]():]/.test(spoken[key] || ""))) throw Error("Dialogue contains a syntax delimiter.");
        }
        if (shot.draft != null && (typeof shot.draft !== "object" || Array.isArray(shot.draft))) throw Error("Invalid shot draft.");
      }
      return { shots: data.shots.map(shot => createShot(shot)), error: "" };
    } catch (error) { return { shots: [], error: `${error.message} Original data retained below.` }; }
  }
  const shots = [];
  for (const line of text.split("\n")) {
    const match = HEADER.exec(line);
    if (match) shots.push({ start: seconds(match[1]), end: seconds(match[2]), text: match[3] });
    else if (shots.length) shots[shots.length - 1].text += "\n" + line;
    else if (line.trim()) return { shots: [], error: "This shot text has no time range. Edit the original text below; it has been retained." };
  }
  return { shots: shots.map((shot, index) => createShot({ ...shot, id: `legacy-shot-${index + 1}`, text: shot.text.trim() })), error: "" };
}

export function writeStory(shots) {
  return shots.length ? JSON.stringify({ format: SHOT_FORMAT, schema_version: 1, shots }) : "";
}

export function createShot(values = {}) {
  const identity = globalThis.crypto?.randomUUID?.() || `shot-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return { id: identity, start: 0, end: 10, text: "", media: [], spoken: [], locked_fields: [], draft: null, ...values };
}

export function renameStoryReferences(text, previous, entries) {
  if (!text.trimStart().startsWith("{")) return renameReferences(text, previous, entries);
  const data = readStory(text); if (data.error) return text;
  let changed = false;
  const shots = data.shots.map(shot => {
    const next = renameReferences(shot.text, previous, entries);
    changed ||= next !== shot.text;
    return { ...shot, text: next };
  });
  return changed ? writeStory(shots) : text;
}

export function sceneApplyProblem(text) {
  const current = readStory(text); if (current.error) return current.error;
  return current.shots.some(shot => shot.media.length || shot.spoken.length || shot.locked_fields.length)
    ? "This scene contains bindings, dialogue or protected fields. A scene replacement cannot preserve them yet; edit the shots directly." : "";
}

export function moveShot(shot, delta, part, duration) {
  if (part === "start") return { ...shot, start: Math.max(0, Math.min(shot.end - 1 / 24, shot.start + delta)) };
  if (part === "end") return { ...shot, end: Math.min(duration, Math.max(shot.start + 1 / 24, shot.end + delta)) };
  const shift = Math.max(-shot.start, Math.min(duration - shot.end, delta));
  return { ...shot, start: shot.start + shift, end: shot.end + shift };
}
