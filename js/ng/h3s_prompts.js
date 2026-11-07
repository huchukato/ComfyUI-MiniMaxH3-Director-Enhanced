// Prompts per render part: exactly what goes to the sampler, and each part's own prompt. The AI writes a part out from the
// compiled one (checked on the server: cuts, sung lines and labels unchanged), or the user edits it; either is kept
// with the key of the compiled prompt it came from, and an older one is not used after the plan changes.
import { h, icon } from "./h3s_dom.js";
import { fmt, partColor, chunkBudget } from "./h3s_model.js";
import { issueLine } from "./h3s_issues.js";

const SOURCE = { compiled: ["compiled", "h3s-muted"], ai: ["AI-written", ""], user: ["edited", ""], manual: ["manual prompt", "h3s-warn"] };

// A part has its own prompt, but the plan compiled it again: the plan changed since, and the own prompt is not used.
export function outdated(S, index) {
  return (S.partPrompts || []).some((entry) => entry.index === index) && S.plan?.chunks?.[index]?.prompt_source === "compiled";
}

// What this part's prompt is made from (ng/core/prompt_sources.py): one chip per shot, card, Look, rule and setting; hover shows
// its text, a shot chip selects the shot, the manual prompt opens Settings.
const KINDS = { manual: ["#F2A65A", "Manual"], shot: ["#6CB6FF", "Shot"], look: ["#C9A2FF", "Look"], rule: ["#F7D774", "Rule"],
  picture: ["#5BD08A", "Picture"], video: ["#FF8A8A", "Video"], audio: ["#B38CF5", "Audio"], setting: ["#9AA6B8", "Setting"] };

export function sourcesRow(S, actions, chunk) {
  const sources = chunk.sources || [];
  if (!sources.length) return null;
  return h("div", { class: "h3s-row", style: { padding: "6px 12px 0", gap: "6px" } }, h("span", { class: "h3s-lbl" }, "Made from"),
    sources.map((entry) => {
      const empty = entry.kind === "shot" && entry.text === "(no text)";
      const [color, kind] = empty ? ["#F2A65A", "Shot without text"] : KINDS[entry.kind] || KINDS.setting;
      const label = entry.kind === "shot" && entry.id && actions.shotLabel ? actions.shotLabel(entry.id) : entry.label;
      const click = entry.kind === "shot" && entry.id ? () => actions.select("shot", entry.id) : entry.kind === "manual" ? () => actions.toggle("settingsOpen") : null;
      return h(click ? "button" : "span", { class: "h3s-chip", title: `${kind}: ${entry.text}`, onclick: click,
        style: { border: `1px solid ${color}`, color, background: "transparent", cursor: click ? "pointer" : "help" } }, empty ? `${label}: no text` : label);
    }));
}

function partView(S, actions, chunk) {
  const [color, bg] = partColor(chunk.index), use = chunkBudget(chunk), i = chunk.index;
  const [label, tone] = SOURCE[chunk.prompt_source] || SOURCE.compiled, old = outdated(S, i);
  const draft = S.partDrafts?.[i], editing = S.partEdit?.index === i, busy = S.busy === `write${i}`;
  const own = (S.partPrompts || []).some((entry) => entry.index === i);
  const tools = chunk.prompt_source === "manual" ? [] : [
    h("button", { class: "h3s-btn ai small", disabled: !S.ai || Boolean(S.busy), onclick: () => actions.writePart(i),
      title: S.ai ? "The AI writes this part's prompt out in full; cuts, sung lines and labels stay as planned" : "Connect an H3 AI Loader to the Connector for this." },
      icon("spark"), busy ? "Writing …" : "Write with AI"),
    h("button", { class: "h3s-btn small", disabled: editing, onclick: () => actions.editPart(i, chunk.prompt) }, "Edit"),
    own ? h("button", { class: "h3s-btn ghost small", onclick: () => actions.resetPart(i), title: "Use the compiled prompt again" }, "Reset") : null];
  return h("div", { class: "h3s-prompt", style: { borderColor: color } },
    h("div", { class: "h3s-prompt-head", style: { background: bg } }, h("span", { class: "h3s-swatch", style: { background: color, width: "10px", height: "10px" } }),
      h("strong", {}, `${chunk.picture ? "Picture" : "Part"} ${i + 1}`), h("span", { class: "h3s-muted", style: { fontSize: "12px" } }, `${fmt(chunk.start_s)} – ${fmt(chunk.end_s)}`),
      h("span", { class: `h3s-chip ${old ? "h3s-warn" : tone}`, title: old ? "The plan changed after this part's own prompt was written; the compiled prompt is used." : "" },
        old ? "own prompt outdated" : label),
      h("span", { class: "h3s-grow" }), ...tools, h("span", { class: "h3s-lbl" }, chunk.mode.toUpperCase())),
    sourcesRow(S, actions, chunk),
    h("span", { class: "h3s-lbl", style: { padding: "6px 12px 0" }, title: "Reference slots H3 gets in this part (the model's limits)" },
      `Images ${use.image}/9 · Video ${use.video}/3 · Audio ${use.audio}/3 · total ${use.total}/12`),
    draft ? h("div", { class: "h3s-banner", style: { margin: "8px 12px", flexDirection: "column", alignItems: "stretch" } },
      draft.problems.length
        ? h("span", {}, `The AI's version was not used: ${draft.problems.join("; ")}. Nothing changed; write it again or edit by hand.`)
        : h("div", {}, draft.unchanged ? h("span", { class: "h3s-lbl" }, "The AI kept the compiled prompt as it is; write again or edit by hand for more detail.") : null,
          h("pre", { style: { margin: 0 } }, draft.text)),
      h("div", { class: "h3s-row" }, h("span", { class: "h3s-grow" }),
        draft.problems.length ? null : h("button", { class: "h3s-btn ai", onclick: () => actions.acceptPart(i) }, "Accept"),
        h("button", { class: "h3s-btn ghost", onclick: () => actions.dropPart(i) }, draft.problems.length ? "Dismiss" : "Discard"))) : null,
    editing ? h("div", { style: { padding: "8px 12px", display: "grid", gap: "6px" } },
      h("textarea", { class: "h3s-in", rows: 14, value: S.partEdit.text, "aria-label": `Prompt of part ${i + 1}`,
        oninput: (event) => { S.partEdit.text = event.target.value; } }),
      h("div", { class: "h3s-row" }, h("span", { class: "h3s-lbl" }, "Your text goes to the sampler as written, until the plan of this part changes."),
        h("span", { class: "h3s-grow" }), h("button", { class: "h3s-btn ai", onclick: () => actions.savePart(i) }, "Save"),
        h("button", { class: "h3s-btn ghost", onclick: () => actions.editPart(null) }, "Cancel"))) : h("pre", {}, chunk.prompt));
}

export function drawerView(S, actions) {
  const chunks = S.plan?.chunks || [], issues = S.plan?.issues || [];
  const head = h("button", { class: "h3s-drawer-head", "aria-expanded": String(S.promptOpen), onclick: () => actions.toggle("promptOpen") },
    h("span", { style: { display: "inline-flex", color: "#9AA4B5", transform: `rotate(${S.promptOpen ? 90 : 0}deg)` } }, icon("chevron")),
    h("span", { class: "h3s-strong" }, "Prompts per render part"),
    chunks.map((chunk) => { const [color] = partColor(chunk.index);
      return h("span", { class: "h3s-chip", style: { border: `1px solid ${color}`, display: "inline-flex", alignItems: "center", gap: "6px" } },
        h("span", { class: "h3s-swatch", style: { background: color } }), `Part ${chunk.index + 1}`); }),
    issues.length ? h("span", { class: "h3s-chip h3s-warn", style: { border: "1px solid #6B4A2E" } }, `${issues.length} note${issues.length === 1 ? "" : "s"}`) : null,
    h("span", { class: "h3s-lbl" }, "Exactly the prompt that goes to the sampler."));
  if (!S.promptOpen) return h("section", { class: "h3s-drawer" }, head);
  return h("section", { class: "h3s-drawer" }, head,
    chunks.length > 1 && chunks.some((chunk) => chunk.prompt_source !== "manual") ? h("div", { class: "h3s-row", style: { padding: "0 20px 10px" } },
      h("button", { class: "h3s-btn ai", disabled: !S.ai || Boolean(S.busy), onclick: actions.writeAllParts }, icon("spark"), "Write all parts with AI"),
      h("span", { class: "h3s-lbl" }, "One request per part; each answer is checked and waits for your Accept.")) : null,
    issues.length ? h("div", { class: "h3s-issues", style: { padding: "0 20px 12px" } },
      issues.map((issue) => h("span", {}, `⚠ ${issueLine(issue)}`))) : null,
    h("div", { class: "h3s-prompts" }, chunks.map((chunk) => partView(S, actions, chunk))));
}
