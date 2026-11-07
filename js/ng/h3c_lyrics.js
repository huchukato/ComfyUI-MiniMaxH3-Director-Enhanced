// Lyrics of a song card: LRC lines "[mm:ss.xx] words" in seconds of the file. Where the card plays exactly (lock or
// copy), the Director puts each line into the render part it is sung in. Whisper fills in the times; Stamp sets one by ear.
import { h } from "./h3s_dom.js";

const STAMP = /^\s*\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]\s*/;

export function stamp(seconds) {
  const m = Math.floor(Math.max(0, seconds) / 60), s = Math.max(0, seconds) - m * 60;
  return `[${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}]`;
}

// The line at the caret gets the player's time, replacing an earlier stamp; the next line is selected for the next press.
export function stampLine(text, caret, seconds) {
  const start = text.lastIndexOf("\n", Math.max(0, caret - 1)) + 1, cut = text.indexOf("\n", caret), end = cut < 0 ? text.length : cut;
  const line = `${stamp(seconds)} ${text.slice(start, end).replace(STAMP, "")}`.trimEnd();
  const next = text.slice(0, start) + line + text.slice(end);
  return { text: next, caret: Math.min(next.length, start + line.length + 1) };
}

export function timedCount(text) {
  return String(text || "").split("\n").filter((line) => STAMP.test(line) && line.replace(STAMP, "").trim()).length;
}

export function lyricsBox(S, actions) {
  const text = S.opts.lyrics || "", timed = timedCount(text);
  const lines = String(text).split("\n").filter((line) => line.replace(STAMP, "").trim() && !/^\s*\[la:/i.test(line)).length;
  const editor = h("textarea", { class: "h3c-in", rows: Math.min(12, Math.max(4, lines + 1)), value: text, spellcheck: false, "aria-label": "Lyrics",
    placeholder: "Paste the lyrics, one line per sung line. ⟳ Time with Whisper adds when each line is sung.",
    onchange: (event) => actions.setOptions({ lyrics: event.target.value }) });
  S.els.lyrics = editor;
  const sung = ["lock", "copy"].includes(S.usage);
  const note = !text.trim() ? "Optional. Only for a song or speech whose words should be sung or spoken in the video."
    : !sung ? "Sung where this song plays exactly: Lock or Copy here, or a Lock or Copy clip on a Studio audio lane."
    : `${timed} of ${lines} line(s) timed; each render part gets the lines sung in it.`;
  return h("div", { class: "h3c-box" },
    h("div", { class: "h3c-cap" }, "Lyrics", h("span", { class: "h3c-grow" }),
      h("button", { class: "h3c-btn", disabled: !S.values.audio || S.busy === "lyrics", title: "Time each line with the local Whisper model; without lines it writes down what it hears",
        onclick: () => actions.timeLyrics() }, S.busy === "lyrics" ? "Listening …" : "⟳ Time with Whisper"),
      h("button", { class: "h3c-btn", disabled: !S.values.audio, title: "Play the song and press at the start of the selected line",
        onclick: () => actions.stampLyric() }, "Stamp line")),
    editor, h("span", { class: "h3c-hint" }, note));
}
