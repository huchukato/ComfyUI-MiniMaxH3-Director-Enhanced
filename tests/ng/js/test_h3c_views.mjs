// The Context card pieces on a minimal DOM: what they show for a state and which action each click triggers.
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const parts = await import("../../../js/ng/h3c_parts.js");
const { textBody } = await import("../../../js/ng/h3c_text.js");

function recorder() {
  const calls = [];
  return { calls, actions: new Proxy({}, { get: (_t, name) => (...args) => { calls.push([name, ...args]); } }) };
}
const state = (extra = {}) => ({ media: "image", values: { name: "Alice", image: "alice.png", description: "", preserve: "high", text: "", ...extra.values },
  opts: { preserve: { identity: "high", pose: "low" }, start_s: 0, end_s: 0, video_audio: "ignore" }, content: ["character", "face"], usage: "reference",
  ai: true, busy: false, analyzed: false, mode: "ref2va", files: ["alice.png", "robot.png"], owners: { current: [], choices: [{ id: "bob", name: "Bob" }] },
  suggestion: null, presets: ["Alice_Default"], presetName: "", accent: "#6AA6F8", status: "", els: {},
  textMode: "note", hasAiText: false, build: { block: "global", seconds: 8 }, ...extra });

// What is in it: ticks show the stored roles, a click toggles one; Analyze needs a connected AI.
{
  const { actions, calls } = recorder();
  const view = parts.contentBox(state(), actions);
  const ticks = view.byTag("button").filter((node) => node.classList.contains("h3c-chk"));
  assert.deepEqual(ticks.map((node) => node.attributes["aria-pressed"]), ["true", "true", "false", "false", "false", "false"]);
  ticks[2].onclick();
  assert.deepEqual(calls.at(-1), ["toggleContent", "outfit"]);
  assert.equal(parts.contentBox(state({ ai: false }), actions).button("✦ Analyze").disabled, true);
  parts.contentBox(state({ busy: "analyze" }), actions).button("Cancel").onclick();
  assert.deepEqual(calls.at(-1), ["cancel"], "a running analysis can be cancelled on the card");
}

// Use as: one choice, and the Director's mode turns a useless choice into a warning.
{
  const { actions, calls } = recorder();
  const view = parts.usageBox(state(), actions);
  view.button("Last frame").onclick();
  assert.deepEqual(calls.at(-1), ["pickUsage", "last_frame"]);
  assert.ok(!view.byClass("h3c-warn").length);
  // Since 2026-10-12 a reference picture is a reference in FL2VA too (next to the frames), so it is explained, not flagged.
  assert.ok(!parts.usageBox(state({ mode: "fl2va" }), actions).byClass("h3c-warn").length, "a reference in FL2VA is used as a reference");
}

// Control source notes stay editable without promising a narrative prompt instruction.
{
  const { actions } = recorder();
  const note = parts.descriptionBox(state({ media: "video", usage: "control", values: { description: "Source actor in a red coat." } }), actions).byTag("textarea")[0];
  assert.equal(note.value, "Source actor in a red coat.");
  assert.match(note.getAttribute("placeholder"), /note about this steering source/);
  assert.equal(note.title, note.getAttribute("placeholder"));
  for (const usage of ["motion", "camera", "structure", "continue"])
    assert.match(parts.descriptionBox(state({ media: "video", usage }), actions).byTag("textarea")[0].getAttribute("placeholder"), /goes into the prompt/);
}

// Keep in the video: stored level is highlighted; background has its own words.
{
  const { actions, calls } = recorder();
  const view = parts.keepBox(state(), actions);
  const on = view.find((node) => node.tagName === "BUTTON" && node.classList.contains("on")).map((node) => node.attributes["aria-label"]);
  assert.deepEqual(on, ["Identity high", "Outfit high", "Pose low", "Background ignore"]);
  view.find((node) => node.attributes["aria-label"] === "Background keep")[0].onclick();
  assert.deepEqual(calls.at(-1), ["setKeep", "background", "keep"]);
}

// Belongs to, the AI suggestion and the usage line.
{
  const { actions, calls } = recorder();
  const owner = parts.ownerBox(state(), actions, "Independent.");
  owner.byTag("select")[0].onchange({ target: { value: "bob" } });
  assert.deepEqual(calls.at(-1), ["setOwner", "bob"]);
  assert.ok(owner.innerText.includes("Independent."));
  assert.ok(parts.ownerBox(state({ owners: { current: ["bob"], choices: [{ id: "bob", name: "Bob" }] } }), actions, "").innerText.includes("Presented together with Bob."));
  assert.equal(parts.suggestionBox(state(), actions), null);
  const suggestion = parts.suggestionBox(state({ suggestion: { fields: { content: "character", description: "A mage." }, why: "" } }), actions);
  assert.ok(suggestion.innerText.includes("Description: A mage."));
  suggestion.button("Accept").onclick();
  assert.deepEqual(calls.at(-1), ["accept"]);
  assert.equal(parts.statusLine(state()), null, "no message, no line");
  assert.ok(parts.statusLine(state({ status: "Saved." })).innerText.includes("Saved."));
  assert.equal(parts.presetRow(state(), actions).button("Save").disabled, true, "a preset needs a name");
}

// Text: the AI view is only offered once a prompt exists; in it the note tools are off.
{
  const { actions, calls } = recorder();
  const S = state({ media: "text", usage: "style", values: { name: "Rules", text: "Slow camera." } });
  const [main] = textBody(S, actions);
  assert.equal(main.button("✦ Build"), undefined, "no H3 block is built on the card any more: it nested inside the Director's");
  assert.ok(main.innerText.includes("goes into every render part"));
  assert.ok(textBody(state({ media: "text", usage: "scene", values: { text: "She sings." } }), actions)[0].innerText.includes("the AI splits it into shots"));
  main.button("+ Character").onclick();
  assert.deepEqual(calls.at(-1), ["insert", "character"]);
  main.byTag("textarea")[0].oninput({ target: { value: "Slow camera, no cuts." } });
  assert.deepEqual(calls.at(-1), ["setNote", "Slow camera, no cuts."]);
  // The Text card analyzes too: Analyze on "Use as", the suggestion with Accept/Discard under it (the docs' native AI example).
  const all = (S) => ({ find: (test) => textBody(S, actions).flatMap((part) => part.find(test)) });
  const button = (S, text) => all(S).find((node) => node.tagName === "BUTTON" && node.innerText.startsWith(text))[0];
  button(S, "✦ Analyze").onclick();
  assert.deepEqual(calls.at(-1), ["analyze"]);
  const suggested = state({ media: "text", usage: "style", suggestion: { fields: { usage: "rule" }, why: "It states a rule." }, values: { text: "No cuts." } });
  button(suggested, "Accept").onclick();
  assert.deepEqual(calls.at(-1), ["accept"]);
  const analyzing = state({ media: "text", usage: "style", busy: "analyze", values: { text: "No cuts." } });
  assert.equal(button(analyzing, "✦ Analyze"), undefined, "a running analysis shows its own state");
}

// The playhead (user 2026-10-19): it stands where the player is, follows it, can be dragged and stays inside the chosen part;
// a click on the strip without a drag moves it there. The Video card's strip shows the video's own sound when it has one.
{
  const media = await import("../../../js/ng/h3c_media.js");
  const video = Object.assign(document.createElement("video"), { duration: 20, currentTime: 5, paused: true });
  const view = (extra = {}) => media.videoBlock(state({ media: "video", values: { video: "walk.mp4" }, els: { video }, opts: { start_s: 2, end_s: 12 }, ...extra }),
    { beginPointer() {}, endPointer() {}, setRange() { throw new Error("a click is no range"); } });
  let block = view();
  let head = block.querySelectorAll(".h3c-head")[0];
  assert.equal(head.style.left, "25%");
  video.currentTime = 10; media.moveHeads(block, video);
  assert.equal(head.style.left, "50%", "it follows the player");
  head.onpointerdown({ stopPropagation() {}, preventDefault() {}, pointerId: 1 });
  head.onpointermove({ clientX: 900 });
  assert.equal(video.currentTime, 11.95, "dragged past the part's end it stops at the end");
  head.onpointermove({ clientX: 50 });
  assert.equal(video.currentTime, 2, "and before its start at the start");
  head.onpointerup();
  const strip = block.querySelectorAll(".h3c-strip")[0];
  strip.onpointerdown({ currentTarget: strip, clientX: 400, pointerId: 2 });
  strip.onpointerup();
  assert.equal(video.currentTime, 8, "a click moves the playhead there");
  assert.equal(strip.querySelectorAll(".sound").length + (strip.classList.contains("sound") ? 1 : 0), 0, "no sound: a plain strip");
  block = view({ envelope: { peaks: [0.2, 0.5, 0.3], duration_s: 20, sample_rate: 48000, channels: 2 } });
  assert.ok(block.querySelectorAll(".h3c-strip")[0].classList.contains("sound"), "with sound: its waveform under the range");
}

console.log("h3c views ok");
