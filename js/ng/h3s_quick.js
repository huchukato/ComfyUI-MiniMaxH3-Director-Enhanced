// Make H3 prompt: pick a direction and whether anyone speaks, press one button. The AI plans the shots from the pictures,
// the Prompt (optional with pictures) and the Director's length, then writes every render part out; ng/core/builder.py and
// ng/core/directions.py hold the rules. The keys and default speech match DIRECTIONS there (tests/ng/test_builder.py).
import { h, icon, select, tip } from "./h3s_dom.js";

export const DIRECTIONS = [["auto", "Let the AI decide", "none"], ["music_video", "Music video", "none"], ["song", "Song (singing)", "singing"],
  ["story", "Story", "none"], ["action", "Action / fight", "none"], ["calm", "Calm scene", "none"], ["dance", "Dance", "none"],
  ["horror", "Horror / suspense", "none"], ["comedy", "Comedy", "none"], ["romance", "Romance", "none"], ["spicy", "Spicy 18+", "none"]];
export const SPEECH = [["none", "No speech"], ["dialogue", "Dialogue"], ["voiceover", "Narrator (voice-over)"], ["singing", "Singing"]];
const LANGUAGES = ["English", "German", "French", "Spanish", "Italian", "Japanese", "Chinese"].map((name) => [name, name]);

export function readQuick(node) {
  const saved = node.properties?.ng_quick || {};
  return { direction: DIRECTIONS.some(([key]) => key === saved.direction) ? saved.direction : "auto",
    speech: SPEECH.some(([key]) => key === saved.speech) ? saved.speech : "none",
    language: LANGUAGES.some(([key]) => key === saved.language) ? saved.language : "English" };
}

// A new direction brings its own speech (Song sings, the others are silent until the user says otherwise).
export function changeQuick(quick, key, value) {
  if (key !== "direction") return { ...quick, [key]: value };
  const speech = DIRECTIONS.find(([name]) => name === value)?.[2] || "none";
  return { ...quick, direction: value, speech: speech === "singing" || quick.speech === "singing" ? speech : quick.speech };
}

// The options and the button, as one row inside the Prompt card; what goes into the plan is in the i.
export function quickView(S, actions) {
  const quick = S.quick || readQuick({}), busy = S.busy === "build", pictures = S.contexts.filter((entry) => entry.media === "image").length;
  const ready = S.ai && !S.busy && (pictures || (S.values.idea || "").trim());
  const why = !S.ai ? "Connect an H3 AI Loader to the Connector for this."
    : !ready && !S.busy ? "Add a picture on a Context node, or write a few words in the Prompt." : "";
  const about = `The AI plans the shots from ${pictures ? `${pictures} picture${pictures === 1 ? "" : "s"}` : "no picture"}, `
    + `${(S.values.idea || "").trim() ? "your Prompt" : "no Prompt (optional with pictures)"} and ${S.values.project_seconds} s, then writes every render part's H3 prompt. Undo puts everything back. `
    + (quick.speech === "none" ? "Nobody speaks." : quick.speech === "singing" ? "Lyrics on the audio card or in the Prompt are sung word for word, otherwise the AI writes them."
      : "Words you write in quotes are used as they are, otherwise the AI writes short lines.")
    + (quick.direction === "spicy" ? " Adults only: a request that speaks of a minor is refused." : "");
  const small = { style: { width: "auto", padding: "4px 8px", fontSize: "13px" } };
  return [h("button", { class: "h3s-btn ai", disabled: !ready, title: why || about, onclick: actions.buildPrompt }, icon("spark"),
      busy ? S.buildStep || "AI working …" : "Make H3 prompt"),
    busy ? h("button", { class: "h3s-btn ghost", onclick: actions.cancelAI }, "Cancel") : null,
    select(DIRECTIONS.map(([key, label]) => [key, label]), quick.direction, (value) => actions.setQuick("direction", value), { "aria-label": "Direction", ...small }),
    select(SPEECH, quick.speech, (value) => actions.setQuick("speech", value), { "aria-label": "Speech", ...small }),
    quick.speech === "none" ? null : select(LANGUAGES, quick.language, (value) => actions.setQuick("language", value), { "aria-label": "Language of the words", ...small }),
    tip(about), why ? h("span", { class: "h3s-warn", style: { fontSize: "12px" } }, why) : null];
}
