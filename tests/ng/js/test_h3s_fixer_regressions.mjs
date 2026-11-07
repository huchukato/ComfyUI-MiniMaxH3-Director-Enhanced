// Confirmed cases remain at their original paths and also run with the standard frontend suite.
import "../regressions/bug_044_spoken_line_button.test.mjs";
import "../regressions/bug_055_build_cancel_undo.test.mjs";
import assert from "node:assert/strict";
import test from "node:test";
import { studio } from "../regressions/studio_fixture.mjs";
import { newShot } from "../../../js/ng/h3s_model.js";
import { ownLines } from "../../../js/ng/h3s_ai.js";

test("typing the first dialogue reveals controls while keeping the input in place", (t) => {
  const s = studio(t); s.select();
  const input = s.root.byTag("input").find((el) => el.getAttribute("aria-label") === "Spoken line 1");
  input.value = "Hello"; input.oninput({ target: input });
  assert.ok(s.root.byTag("input").includes(input));
  const remove = s.root.byTag("button").find((el) => el.getAttribute("aria-label") === "Remove line 1");
  assert.ok(remove);
  remove.onclick();
  assert.equal(s.read().shots[0].spoken.length, 0);
});

test("editing an existing line preserves the button being clicked when the input loses focus", (t) => {
  const shot = { ...newShot(0, 10), id: "shot_a", text: "A woman walks.",
    spoken: [{ schema_version: 1, text: "First line", speaker_id: "", language: "English", delivery: "says" }] };
  const s = studio(t, { project: { shots: [shot], audio: [], lanes: [] } }); s.select();
  const input = s.root.byTag("input").find((el) => el.getAttribute("aria-label") === "Spoken line 1");
  const target = s.root.byClass("h3s-btn").find((el) => el.innerText.includes("Spoken line"));
  input.value = "Edited line"; input.oninput({ target: input });
  input.onchange?.({ target: input });
  assert.ok(s.root.byTag("button").includes(target), "focus transfer must not remove the click target");
  target.onclick();
  assert.equal(s.read().shots[0].spoken.length, 2);
  assert.equal(s.read().shots[0].spoken[0].text, "Edited line");
});

test("own dialogue distinguishes the named Narrator card from the anonymous narrator", () => {
  const S = { byId: new Map([["ctx_narr", { name: "Narrator" }]]), shots: [{ text: "", spoken: [
    { speaker_id: "ctx_narr", text: "My card line" }, { speaker_id: "", text: "My narrator line" }] }] };
  assert.equal(ownLines(S), "@Narrator says: My card line\nNarrator says: My narrator line");
});
