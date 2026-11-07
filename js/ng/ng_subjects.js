// Which context items are figures a voice or an asset can belong to. Pure functions, so they can be checked
// with `node` without a browser; the panels in ng_cards.js only render what these decide.
import {referenceSubject} from "./ng_asset_relations.js";
import {contextId} from "./ng_widgets.js";

export const SUBJECT_ROLES = ["character", "face", "animal"];

// A subject needs a file to be drawn from, so an empty image context never appears as a speaker choice.
// A context node's widget values keep the file under its medium name (`image`); `source` only exists on the
// finished ContextItem, so both are accepted here.
export function isSubject(entry) {
  if (!referenceSubject(entry)) return false;
  const widgets = entry.widgets || {};
  if (!String(widgets.source || widgets.image || "").trim()) return false;
  const roles = widgets.content_roles ? safeList(widgets.content_roles)
    : widgets.content ? [widgets.content] : [];
  return roles.length === 0 || roles.some((role) => SUBJECT_ROLES.includes(role));
}

// The dropdown a voice card shows: every connected figure, named, with its id as the stored value.
// The Python side matches `speaker` against item ids; a card with an empty ID field has the derived id there
// (`image_<name>`), so that id is offered and resolves.
export function subjectChoices(entries, current = "") {
  const found = new Map();
  for (const entry of entries || []) {
    if (!isSubject(entry)) continue;
    const id = contextId(entry.widgets, entry.media);     // the id the plan gives a card with an empty field (BUG-051)
    if (found.has(id)) continue;
    found.set(id, { id, name: entry.widgets.name || "Figure" });
  }
  const list = [...found.values()];
  // A stored speaker that is no longer listed must still be visible, otherwise the value silently disappears.
  if (current && !list.some((entry) => entry.id === current)) list.push({ id: current, name: current + " (not connected)" });
  return list;
}

// One figure may own several voice cards; the note tells the user which one actually fills the subject's slot.
export function voiceAssignment(entries) {
  const taken = new Map();
  for (const entry of entries || []) {
    const speaker = entry.widgets?.speaker;
    if (!speaker) continue;
    taken.set(speaker, (taken.get(speaker) || 0) + 1);
  }
  return (speaker, selfId) => {
    const count = taken.get(speaker) || 0;
    if (!speaker) return "";
    if (count <= 1) return "";
    const name = (entries || []).find((entry) => entry.widgets?.context_id === selfId)?.widgets?.name || "This take";
    return count === 2 ? "Another take also names this figure; the first one fills the voice slot."
                       : `${count} voice cards name this figure; the first one fills the voice slot.`;
  };
}

function safeList(text) {
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed.filter((value) => typeof value === "string") : [];
  } catch {
    return [];
  }
}
