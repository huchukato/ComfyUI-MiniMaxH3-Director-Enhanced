// Exercise the real Studio handlers and saved widgets using the existing offline DOM fixture.
import assert from "node:assert/strict";
import test from "node:test";
import { openStudio } from "../../../js/ng/h3s_studio.js";
import { readProject, newShot, newClip } from "../../../js/ng/h3s_model.js";
import { patch, studio } from "./studio_fixture.mjs";

test("control: an unchanged AI proposal is saved only after Accept", async (t) => {
  const f = studio(t); f.select();
  const pending = f.root.button("AI: improve text").onclick();
  f.reply(patch()); await pending;
  assert.equal(f.read().shots[0].text, "Original shot.");
  assert.ok(f.root.button("Accept"));
  f.acceptIfAvailable();
  assert.equal(f.read().shots[0].text, "AI proposal.");
});

test("BUG-011: Accept cannot overwrite a manual edit made after a proposal arrived", async (t) => {
  const f = studio(t); f.select();
  const pending = f.root.button("AI: improve text").onclick();
  f.reply(patch()); await pending;
  f.edit("My newer manual edit.");
  f.acceptIfAvailable();
  assert.equal(f.read().shots[0].text, "My newer manual edit.");
});

test("BUG-011: Accept cannot overwrite a manual edit made while AI was running", async (t) => {
  const f = studio(t); f.select();
  const pending = f.root.button("AI: improve text").onclick();
  f.edit("My newer manual edit.");
  f.reply(patch()); await pending;
  f.acceptIfAvailable();
  assert.equal(f.read().shots[0].text, "My newer manual edit.");
});

test("BUG-012: accepting an AI draft preserves a stored text lock", async (t) => {
  const f = studio(t, { locks: ["text"] }); f.select();
  const pending = f.root.button("AI: improve text").onclick();
  // The draft parser permits a proposal for a locked field; application must respect its lock.
  f.reply(patch()); await pending;
  f.acceptIfAvailable();
  assert.deepEqual(f.read().shots[0].locked_fields, ["text"]);
  assert.equal(f.read().shots[0].text, "Original shot.");
});

function dropAudio(f) {
  const card = f.root.byClass("h3s-ctx").find((entry) => entry.innerText.includes("Music"));
  assert.ok(card, "connected audio Context is shown");
  card.ondragstart({ dataTransfer: { setData() {} } });
  f.root.byClass("h3s-lane-add")[0].ondrop({ preventDefault() {} });
  assert.equal(f.read().audio.length, 1, "audio drop actually creates and saves a clip");
  return f.read().audio[0];
}

test("BUG-013: a new FL2VA audio lane clip uses its supported lock mode", (t) => {
  const f = studio(t, { mode: "fl2va", audio: true });
  assert.equal(dropAudio(f).mode, "lock", "FL2VA cannot consume the default ref clip");
});

test("control: a new Ref2VA clip retains reference mode", (t) => {
  const f = studio(t, { mode: "ref2va", audio: true });
  assert.equal(dropAudio(f).mode, "ref");
});

test("control: editing one dialogue line survives Studio reopen and preserves other project data", (t) => {
  const line = (text, language) => ({ schema_version: 1, text, speaker_id: "", voice: "a narrator", language, delivery: "says" });
  const first = { ...newShot(0, 5), id: "shot_a", text: "First scene.", spoken: [line("First words.", "English"), line("Zweite Zeile.", "German"), line("Third words.", "English")],
    locked_fields: ["timing"], draft: { text: "A retained pending legacy draft." } };
  const second = { ...newShot(5, 10), id: "shot_b", text: "Second scene." };
  const clip = { ...newClip("sound_a", "lane_a", 1, 9), id: "clip_a", offset: 2.25, mode: "lock" };
  const initial = { shots: [first, second], audio: [clip], lanes: ["lane_a", "empty_lane"] };
  const f = studio(t, { project: initial, audio: true }); f.select();
  const input = f.root.byTag("input").find((field) => field.getAttribute("aria-label") === "Spoken line 2");
  assert.ok(input, "every stored line is editable");
  input.value = "Meine neue zweite Zeile."; input.oninput({ target: input });
  const expected = { ...initial, shots: [{ ...first, spoken: [first.spoken[0], { ...first.spoken[1], text: input.value }, first.spoken[2]] }, second] };
  const data = () => {
    const restored = f.read(); assert.equal(restored.error, "");
    return { shots: restored.shots, audio: restored.audio, lanes: restored.lanes };
  };
  assert.deepEqual(data(), expected, "one line edit preserves other shots, lines, locks, draft, clips and empty lanes");
  f.handle.close();
  const reopened = openStudio(f.node, f.app, f.api); t.after(() => reopened.close());
  assert.deepEqual(data(), expected, "opening the saved widget restores the same project");
});

for (const key of ["Start", "End"]) {
  test(`BUG-010: the Studio ${key.toLowerCase()} field respects exact imported neighbours`, (t) => {
    const shots = readProject("0-6.04: First shot.\n6.55-10: Second shot.").shots;
    const f = studio(t, { project: { shots, audio: [], lanes: [] } });
    const block = f.root.byClass("h3s-shot")[key === "Start" ? 1 : 0];
    block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 100, pointerId: 1 }); block.onpointerup();
    const field = f.root.byTag("label").find((label) => label.innerText === `${key} (s)`).byTag("input")[0];
    field.value = key === "Start" ? 5 : 7; field.onchange({ target: field });
    const after = f.read().shots;
    assert.ok(after[0].end <= after[1].start, `numeric edit produced overlap ${after[0].end} > ${after[1].start}`);
  });
}
