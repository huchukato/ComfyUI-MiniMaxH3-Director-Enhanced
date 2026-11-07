/**
 * BUG-044: The "+ Spoken line" add button and the delete button do not appear after typing
 * the first dialogue line in the Director Studio shot panel.
 *
 * In js/ng/h3s_side.js:
 * When a shot has no dialogue yet (shot.spoken.length === 0), spokenLines() renders a single
 * empty text input with placeholder "Line that is spoken".
 * The delete button (close icon) is omitted, and the "+ Spoken line" button at the bottom of the
 * spoken section is conditioned on `shot.spoken.length ? h("button", ..., "Spoken line") : null`.
 *
 * When the user types into the input, oninput calls:
 * `actions.setSpoken(shot.id, index, { text: ... }, false)` with rerender = false
 * to avoid stealing keyboard focus on each keystroke.
 *
 * However, there is no onblur or onchange handler on the input, and setSpoken never triggers
 * a rerender upon completing the input. As a result, even after entering a line of dialogue,
 * the DOM is never updated:
 * 1. The "+ Spoken line" button remains absent (null) from the panel. The user cannot add a second line.
 * 2. The remove button for the line remains unrendered.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { studio, fixture } from "./studio_fixture.mjs";
import { newShot } from "../../../js/ng/h3s_model.js";

test("BUG-044: typing a dialogue line in a shot with no previous dialogue must make the '+ Spoken line' button available", (t) => {
  const s = studio(t);
  s.select();

  // Initially shot has no spoken lines
  assert.equal(s.read().shots[0].spoken.length, 0);

  // Find the dialogue input
  const input = s.root.byTag("input").find((el) => el.getAttribute("aria-label") === "Spoken line 1");
  assert.ok(input, "Dialogue input must be present in the side panel");

  // Initial state: '+ Spoken line' button is not in DOM
  const addBtnBefore = s.root.byClass("h3s-btn").find((btn) => btn.innerText.includes("Spoken line"));
  assert.equal(addBtnBefore, undefined, "Before typing, '+ Spoken line' button is not rendered");

  // User types dialogue into the line
  input.value = "Welcome to the grand premiere!";
  input.oninput({ target: input });

  // Simulate user leaving the field (blur / change)
  if (input.onchange) input.onchange({ target: input });
  if (input.onblur) input.onblur({ target: input });

  // The shot in the data model now has dialogue
  assert.equal(s.read().shots[0].spoken.length, 1);
  assert.equal(s.read().shots[0].spoken[0].text, "Welcome to the grand premiere!");

  // The UI MUST now provide the '+ Spoken line' button so the user can add another dialogue line
  const addBtnAfter = s.root.byClass("h3s-btn").find((btn) => btn.innerText.includes("Spoken line"));
  assert.ok(addBtnAfter, "After entering dialogue, the '+ Spoken line' button must appear in the side panel");
});

test("control: a shot that already contains dialogue renders the '+ Spoken line' button", (t) => {
  const initial = {
    shots: [
      {
        ...newShot(0, 10),
        id: "shot_a",
        text: "Opening shot.",
        spoken: [{ schema_version: 1, text: "Existing dialogue line.", speaker_id: "", language: "English" }],
      },
    ],
    audio: [],
    lanes: [],
  };

  const s = studio(t, { project: initial });
  s.select();

  const addBtn = s.root.byClass("h3s-btn").find((btn) => btn.innerText.includes("Spoken line"));
  assert.ok(addBtn, "'+ Spoken line' button is present when dialogue already exists");

  // Clicking it adds a second line
  addBtn.onclick();
  assert.equal(s.read().shots[0].spoken.length, 2, "Clicking '+ Spoken line' adds another dialogue line");
});
