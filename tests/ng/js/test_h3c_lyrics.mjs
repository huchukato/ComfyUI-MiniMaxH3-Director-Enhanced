// The Audio card's lyrics: stamping a line by ear, and what the box says and does for a song card.
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const { stamp, stampLine, timedCount, lyricsBox } = await import("../../../js/ng/h3c_lyrics.js");

// Stamp replaces an earlier time on the line at the caret and moves on to the next line.
{
  assert.equal(stamp(75.5), "[01:15.50]");
  const first = stampLine("My master\nI still wait", 3, 1.234);
  assert.equal(first.text, "[00:01.23] My master\nI still wait");
  assert.equal(first.caret, "[00:01.23] My master\n".length);
  assert.equal(stampLine(first.text, 2, 2).text, "[00:02.00] My master\nI still wait", "a second press replaces the time");
  assert.equal(timedCount("[la:English]\n[00:01.00] a\n[00:03.00]\nb"), 1, "a bare stamp is a pause, an unstamped line is untimed");
}

function recorder() {
  const calls = [];
  return { calls, actions: new Proxy({}, { get: (_t, name) => (...args) => { calls.push([name, ...args]); } }) };
}
const state = (extra = {}) => ({ media: "audio", values: { audio: "song.mp3" }, opts: { lyrics: "" }, usage: "lock", busy: "", els: {}, ...extra });

// Whisper and Stamp are buttons on the card; the hint says when lines reach the prompt.
{
  const { actions, calls } = recorder();
  const view = lyricsBox(state({ opts: { lyrics: "[00:01.00] My master\n[00:04.00] I still wait\nThe halls" } }), actions);
  view.button("⟳ Time with Whisper").onclick();
  assert.deepEqual(calls.at(-1), ["timeLyrics"]);
  view.button("Stamp line").onclick();
  assert.deepEqual(calls.at(-1), ["stampLyric"]);
  assert.ok(view.innerText.includes("2 of 3 line(s) timed"), view.innerText);
  assert.ok(lyricsBox(state({ opts: { lyrics: "[00:01.00] a\n[00:03.00]\n[00:05.00] b\n[00:07.00]" } }), actions).innerText.includes("2 of 2 line(s)"),
    "a pause stamp is not a line");
  assert.ok(lyricsBox(state({ usage: "music_style", opts: { lyrics: "[00:01.00] x" } }), actions).innerText.includes("Lock or Copy clip on a Studio audio lane"));
  assert.equal(lyricsBox(state({ busy: "lyrics" }), actions).button("Listening …").disabled, true);
  assert.equal(lyricsBox(state({ values: { audio: "" } }), actions).button("Stamp line").disabled, true);
}

console.log("h3c lyrics ok");
