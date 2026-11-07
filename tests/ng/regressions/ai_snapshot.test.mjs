import assert from "node:assert/strict";
import test from "node:test";
import { studioAI } from "../../../js/ng/h3s_ai.js";
import { newShot, writeProject } from "../../../js/ng/h3s_model.js";
import { fixture, patch } from "./studio_fixture.mjs";

test("control: an unchanged shot receives a proposal without changing its saved text", async () => {
  const f = fixture(), ai = studioAI(f.S, f.app, f.api, () => {});
  const pending = ai.suggest("shot_a");
  assert.equal(f.requests[0].path, "/ng/direct");
  f.reply(patch()); await pending;
  assert.equal(f.S.suggestions.shot_a, "AI proposal.");
  assert.equal(f.S.shots[0].text, "Original shot.");
});

test("BUG-011: a reply based on an older shot must not become an applicable proposal", async () => {
  const f = fixture(), ai = studioAI(f.S, f.app, f.api, () => {});
  const pending = ai.suggest("shot_a");
  f.S.shots = [{ ...f.S.shots[0], text: "My newer manual edit." }];
  f.setWidget("shots", writeProject({ shots: f.S.shots, audio: [], lanes: [] }));
  f.reply(patch()); await pending;
  assert.equal(f.S.suggestions.shot_a, undefined, "outdated AI text remains available to Accept");
  assert.equal(f.S.shots[0].text, "My newer manual edit.");
});

test("BUG-011: changing the prompt while splitting invalidates the old scene replacement", async () => {
  const f = fixture(), ai = studioAI(f.S, f.app, f.api, () => {});
  const pending = ai.split();
  f.setWidget("idea", "A completely new idea.");
  f.reply({ shots: writeProject({ shots: [{ ...newShot(0, 10), text: "Scenes for the old idea." }], audio: [], lanes: [] }) });
  await pending;
  assert.deepEqual(f.S.ghosts, [], "outdated scene replacement remains available to Accept");
});

test("control: cancel discards a delayed reply even when the transport ignores AbortSignal", async () => {
  const f = fixture(), ai = studioAI(f.S, f.app, f.api, () => {});
  const pending = ai.suggest("shot_a");
  ai.cancel(); f.reply(patch()); await pending;
  assert.deepEqual(f.S.suggestions, {});
  assert.equal(f.S.busy, "");
});

for (const changed of ["Context", "provider"]) {
  test(`BUG-011: a ${changed} change invalidates an outstanding proposal`, async () => {
    const f = fixture({ audio: true }), ai = studioAI(f.S, f.app, f.api, () => {});
    const pending = ai.suggest("shot_a");
    if (changed === "Context") f.sound.widgets.find((widget) => widget.name === "name").value = "A new sound identity";
    else f.provider.widgets.find((widget) => widget.name === "model").value = "Another model";
    f.reply(patch()); await pending;
    assert.equal(f.S.suggestions.shot_a, undefined, `reply for the old ${changed} remains applicable`);
  });
}
