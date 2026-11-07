/**
 * BUG-079: `followRenames` in `h3s_node.js` fails to update @Name references in `project.look`,
 * `project.part_prompts`, and `shot.spoken` dialogue lines, and fails completely when `project.shots` is empty.
 *
 * User Workflow:
 * 1. User builds a workflow with an H3 Director node and connects a Context card (e.g. Character card named "Alice", context_id: "ctx_1").
 * 2. In H3 Director Studio, the user defines:
 *    - A shared Look ("Look (every part)"): "Cinematic dark anime, following @Alice through the castle."
 *    - Custom render-part prompts ("Prompts per render part"): "Render part 1: @Alice enters the throne room."
 *    - Spoken dialogue lines in a shot: "Wait for @Alice!"
 * 3. The user renames the connected Context card from "Alice" to "Bob".
 * 4. The `ng-context-changed` event fires and invokes `followRenames(node)` on the Director node.
 *
 * Faulty State (Ist):
 * - `h3s_node.js:31-46` only checks and updates `now.idea` and `shot.text`:
 *     const idea = renameReferences(now.idea || "", previous, entries);
 *     ...
 *     const shots = project.shots.map((shot) => ({ ...shot, text: renameReferences(shot.text, previous, entries) }));
 *     if (shots.some((shot, index) => shot.text !== project.shots[index].text)) changes.shots = writeProject({ ...project, shots });
 * - `project.look` is never passed to `renameReferences` and retains stale `@Alice`.
 * - `project.part_prompts` is never passed to `renameReferences` and retains stale `@Alice`.
 * - `shot.spoken` (dialogue lines) is never passed to `renameReferences` and retains stale `@Alice`.
 * - If `project.shots` is empty (`project.shots.length === 0`), line 39 evaluates to false and skips JSON update entirely.
 * - If `shot.text` had no mentions, `shots.some(...)` is false, so `changes.shots` is not created at all.
 * - Even when `shot.text` DID change, `writeProject({ ...project, shots })` writes back the un-renamed `project.look` and `project.part_prompts`.
 * - Line 43 then updates `node.properties.ng_context_names` to `{ ctx_1: "Bob" }`, discarding the old name "Alice".
 *   Future renames can never fix the stale `@Alice` mentions because the old mapping is lost.
 * - During rendering (Ref2VA mode), `_tag_substitutor` in `legacy_bridge.py:112` looks for `@Bob`.
 *   Since `look` still contains `@Alice`, the replacement fails: `@ref1` is not injected into the prompt,
 *   the Subject slot is unreferenced, and the model renders a random person instead of the connected Subject.
 *
 * Expected (Soll):
 * - `followRenames` must rename @Name in `project.look`, `project.part_prompts`, and `shot.spoken`.
 * - Changes in `look`, `part_prompts`, or `spoken` must produce `changes.shots` even when `shot.text` is unchanged or `shots` is empty.
 *
 * Run: node --test tests/ng/regressions/bug_079_follow_renames_look_and_prompts.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readProject, writeProject, renamedDirector } from "../../../js/ng/h3s_model.js";
import { renameReferences } from "../../../js/ng/ng_references.js";

// The production logic itself (h3s_node.js followRenames calls renamedDirector); the test used to carry an older copy.
function executeFollowRenames(node, entries) {
  const previous = node.properties.ng_context_names || {};
  const changes = renamedDirector(node.values, (text) => renameReferences(text, previous, entries));
  node.properties.ng_context_names = Object.fromEntries(entries.filter((entry) => entry.widgets.context_id && entry.widgets.name)
    .map((entry) => [entry.widgets.context_id, entry.widgets.name]));
  if (Object.keys(changes).length) Object.assign(node.values, changes);
  return changes;
}

test("control: followRenames updates idea and shot.text when context is renamed", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [
      { id: "s1", start: 0, end: 4, text: "A wide shot of @Alice in the courtyard.", media: [], spoken: [], locked_fields: [], draft: null }
    ],
    audio: [],
    audio_lanes: []
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "Story starring @Alice.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  assert.equal(changes.idea, "Story starring @Bob.");
  assert.ok(changes.shots, "changes.shots should be produced");
  const parsed = readProject(node.values.shots);
  assert.equal(parsed.shots[0].text, "A wide shot of @Bob in the courtyard.");
});

test("BUG-079: followRenames must update @Name in project.look when shot descriptions have no mentions", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [
      { id: "s1", start: 0, end: 4, text: "A scenic shot of the forest.", media: [], spoken: [], locked_fields: [], draft: null }
    ],
    audio: [],
    audio_lanes: [],
    look: "Cinematic dark anime, following @Alice through the castle."
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "A fantasy story.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  // Ist (Bug): shots.some(...) is false because shots[0].text has no mention, so changes.shots is undefined.
  // node.properties.ng_context_names is overwritten with Bob, leaving look as @Alice forever.
  // Soll: changes.shots must be created with look updated to @Bob.
  assert.ok(changes.shots, "changes.shots must be produced when project.look contains a renamed @Name");
  const parsed = readProject(node.values.shots);
  assert.equal(
    parsed.look,
    "Cinematic dark anime, following @Bob through the castle.",
    "project.look must rename @Alice to @Bob"
  );
});

test("BUG-079: followRenames must update @Name in project.part_prompts (render part custom prompts)", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [
      { id: "s1", start: 0, end: 4, text: "A scenic shot of the forest.", media: [], spoken: [], locked_fields: [], draft: null }
    ],
    audio: [],
    audio_lanes: [],
    part_prompts: [
      { index: 0, key: "part_0_key", text: "Render part 1: @Alice enters the throne room.", by: "manual" }
    ]
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "A fantasy story.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  // Ist (Bug): part_prompts is never checked or renamed by followRenames.
  // Soll: changes.shots must be produced and part_prompts text updated to @Bob.
  assert.ok(changes.shots, "changes.shots must be produced when part_prompts contains a renamed @Name");
  const parsed = readProject(node.values.shots);
  assert.equal(
    parsed.partPrompts[0].text,
    "Render part 1: @Bob enters the throne room.",
    "part_prompts text must rename @Alice to @Bob"
  );
});

test("BUG-079: followRenames must update @Name in shot.spoken dialogue lines", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [
      {
        id: "s1",
        start: 0,
        end: 4,
        text: "Characters talk in the hall.",
        media: [],
        spoken: [
          { schema_version: 1, text: "Wait for @Alice over by the bridge!", speaker_id: "", voice: "a narrator", language: "English", delivery: "says" }
        ],
        locked_fields: [],
        draft: null
      }
    ],
    audio: [],
    audio_lanes: []
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "A fantasy story.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  // Ist (Bug): shot.spoken is never updated; spoken[0].text retains @Alice.
  // Soll: changes.shots must be produced and spoken[0].text updated to @Bob.
  assert.ok(changes.shots, "changes.shots must be produced when shot.spoken contains a renamed @Name");
  const parsed = readProject(node.values.shots);
  assert.equal(
    parsed.shots[0].spoken[0].text,
    "Wait for @Bob over by the bridge!",
    "spoken dialogue text must rename @Alice to @Bob"
  );
});

test("BUG-079: followRenames must update @Name in project.look when project.shots is empty", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [],
    audio: [
      { schema_version: 1, id: "c1", context_id: "sound_1", start: 0, end: 10, offset: 0, mode: "lock", lane: "l1" }
    ],
    audio_lanes: ["l1"],
    look: "Dark gothic hall, featuring @Alice in amber rim light."
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "A prompt-only project.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  // Ist (Bug): line 39 checks `project.shots.length`, which is 0, so the JSON branch is completely bypassed.
  // Soll: changes.shots must be produced and look updated to @Bob even when shots is empty.
  assert.ok(changes.shots, "changes.shots must be produced for prompt-only project with empty shots list");
  const parsed = readProject(node.values.shots);
  assert.equal(
    parsed.look,
    "Dark gothic hall, featuring @Bob in amber rim light.",
    "look in prompt-only project must rename @Alice to @Bob"
  );
});

test("BUG-079: writeProject must not preserve stale @Alice in look and part_prompts when shots are updated", () => {
  const rawProject = JSON.stringify({
    format: "h3-director-shots",
    schema_version: 1,
    shots: [
      { id: "s1", start: 0, end: 4, text: "A wide shot of @Alice in the courtyard.", media: [], spoken: [], locked_fields: [], draft: null }
    ],
    audio: [],
    audio_lanes: [],
    look: "Cinematic dark anime, following @Alice through the castle.",
    part_prompts: [
      { index: 0, key: "part_0_key", text: "Render part 1: @Alice enters the throne room.", by: "manual" }
    ]
  });

  const node = {
    properties: { ng_context_names: { ctx_1: "Alice" } },
    values: { idea: "A fantasy story.", shots: rawProject }
  };
  const entries = [{ widgets: { context_id: "ctx_1", name: "Bob" } }];

  const changes = executeFollowRenames(node, entries);

  // Ist (Bug): shots.some(...) is true because shots[0].text changed.
  // But writeProject({ ...project, shots }) writes back the untouched project.look and project.partPrompts!
  // Soll: parsed.look and parsed.partPrompts must both reflect @Bob.
  assert.ok(changes.shots, "changes.shots must be produced");
  const parsed = readProject(node.values.shots);
  assert.equal(parsed.shots[0].text, "A wide shot of @Bob in the courtyard.");
  assert.equal(
    parsed.look,
    "Cinematic dark anime, following @Bob through the castle.",
    "look must not remain @Alice when project is rewritten"
  );
  assert.equal(
    parsed.partPrompts[0].text,
    "Render part 1: @Bob enters the throne room.",
    "part_prompts must not remain @Alice when project is rewritten"
  );
});

