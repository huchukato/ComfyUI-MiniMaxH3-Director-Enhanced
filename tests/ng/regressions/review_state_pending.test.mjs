// Additional BUG-011 cases: the response arrived before the user changed the project.
// Verified on ab5ab44 and registered with the normal NG suite.
import assert from "node:assert/strict";
import test from "node:test";
import { studioAI } from "../../../js/ng/h3s_ai.js";
import { newShot, writeProject } from "../../../js/ng/h3s_model.js";
import { fixture, patch, studio } from "./studio_fixture.mjs";

const scenes = (extra = {}) => ({ shots: writeProject({ shots: [{ ...newShot(0, 10), text: "The AI's original scene." }], audio: [], lanes: [] }), ...extra });

for (const changed of ["Context", "provider", "prompt"]) {
  test(`BUG-011: Accept rejects an already displayed text proposal after ${changed} changes`, async (t) => {
    const f = studio(t, { audio: true }); f.select();
    const pending = f.root.button("AI: improve text").onclick();
    f.reply(patch()); await pending;
    assert.ok(f.root.button("Accept"), "the initial proposal is displayed");
    if (changed === "Context") f.sound.widgets.find((widget) => widget.name === "name").value = "Changed sound";
    else if (changed === "provider") f.provider.widgets.find((widget) => widget.name === "model").value = "Changed model";
    else f.setWidget("idea", "A new project idea.");
    f.handle.refresh(); f.acceptIfAvailable();
    assert.equal(f.read().shots[0].text, "Original shot.", "stale text was still applied after the project changed");
  });
}

test("BUG-011: accepting an old scene split cannot delete a newer manual shot edit", async (t) => {
  const f = studio(t);
  const pending = f.root.button("AI: split into shots").onclick();
  f.reply(scenes()); await pending;
  assert.ok(f.root.button("Accept"), "the scene replacement is displayed");
  f.select(); f.edit("My newer manually written scene.");
  f.acceptIfAvailable();
  assert.equal(f.read().shots[0].text, "My newer manually written scene.");
});

for (const field of ["music", "soundscape"]) {
  test(`BUG-011: changing ${field} during a scene request prevents overwriting the new value`, async (t) => {
    const f = studio(t);
    const pending = f.root.button("AI: split into shots").onclick();
    f.setWidget(field, "My newer sound instruction."); f.handle.refresh();
    f.reply(scenes({ [field]: "An older AI sound instruction." })); await pending;
    f.acceptIfAvailable();
    assert.equal(f.node.widgets.find((widget) => widget.name === field).value, "My newer sound instruction.");
  });
}

test("control: a reviewed scene split can be accepted while its input remains unchanged", async (t) => {
  const f = studio(t);
  const pending = f.root.button("AI: split into shots").onclick();
  f.reply(scenes()); await pending; f.acceptIfAvailable();
  assert.equal(f.read().shots[0].text, "The AI's original scene.");
});

test("control: disposing an AI action discards a late response", async () => {
  const f = fixture(), ai = studioAI(f.S, f.app, f.api, () => {});
  const pending = ai.suggest("shot_a"); ai.dispose(); f.reply(patch()); await pending;
  assert.deepEqual(f.S.suggestions, {});
});
