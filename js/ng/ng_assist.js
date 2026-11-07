// The three assistance modes, the field picker for one suggestion, and the plan for Analyze All.
// Everything that decides something is a plain function, so it can be checked with `node` without a browser.

export const MODES = ["manual", "assist", "auto"];

// Manual never asks the provider for a scene, so Auto Direct stays disabled there even with a loader connected.
export function canAutoDirect(mode, provider, busy = false) {
  return Boolean(provider) && !busy && mode === "auto";
}

// Which widget fields a suggestion may write. A field the analysis left empty is never in this list, so Apply
// cannot blank something the user typed.
export function offeredFields(suggestion) {
  const found = {};
  for (const name of ["description", "content", "usage"]) {
    const value = suggestion?.[name];
    if (typeof value === "string" && value.trim()) found[name] = value.trim();
  }
  return found;
}

// The Apply payload. `selected` is what the user ticked, so one suggestion can fill only its description.
export function applyChanges(suggestion, selected) {
  const offered = offeredFields(suggestion);
  const changes = {};
  for (const name of selected) {
    if (!(name in offered)) continue;
    changes[name] = offered[name];
    if (name === "content" || name === "usage") changes[name + "_roles"] = JSON.stringify([offered[name]]);
  }
  return changes;
}

// The one line that explains a suggestion below its fields. Empty when the provider gave no reason.
export function reasonLine(suggestion) {
  return suggestion?.why?.trim() ? `Why: ${suggestion.why.trim()}` : "";
}

// Analyze All asks the backend, which owns the media rules; the panel only shows what came back.
export function summarizeBatch(data) {
  const results = Array.isArray(data?.results) ? data.results : [];
  const done = results.filter((entry) => entry.ok);
  const failed = results.filter((entry) => !entry.ok);
  const parts = [];
  if (done.length) parts.push(`${done.length} analyzed`);
  if (failed.length) parts.push(`${failed.length} failed`);
  return { part: parts.join(" · ") || "Nothing analyzed", failed: failed.map((entry) => entry.error), skipped: data?.skipped || [] };
}