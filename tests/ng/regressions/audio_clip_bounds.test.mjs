// BUG-004: eine Audiokarte, die an einen Shot gebunden UND auf eine Tonspur gezogen ist,
// darf nicht stillschweigend eine der beiden Zuordnungen verschlucken.
// BUG-014: ein Tonclip, dessen Offset hinter dem Dateiende liegt, muss im Plan benannt werden.
import assert from "node:assert/strict";
import test from "node:test";
import { readProject, writeProject, newShot } from "../../../js/ng/h3s_model.js";

const shot = (media) => ({ ...newShot(0, 6), id: "s1", text: "A", media });
const binding = (contextId, role) => ({ schema_version: 1, context_id: contextId, role });
const clip = (over) => ({ schema_version: 1, id: "c1", context_id: "a1", start: 0, end: 4,
  offset: 0, mode: "lock", lane: "l1", ...over });

function document(shotMedia, audio) {
  return writeProject({ shots: [shot(shotMedia)], audio, lanes: audio.length ? ["l1"] : [] });
}

test("control: ein Tonclip im gültigen Bereich bleibt unauffällig", () => {
  const read = readProject(document([], [clip({ offset: 2 })]));
  assert.equal(read.error, "");
  assert.equal(read.skipped.length, 0);
  assert.equal(read.audio[0].offset, 2);
});

test("BUG-014: ein Offset hinter dem Dateiende bleibt sichtbar; der Plan benennt ihn", () => {
  // Nur der Plan kennt die Dateilänge: er meldet audio_clip_past_file ("plays nothing", tests/ng/test_audio_clips.py).
  // Das Studio verwirft den Clip nicht still, sonst könnte man ihn nicht korrigieren.
  const read = readProject(document([], [clip({ offset: 9999 })]));
  assert.equal(read.audio.length, 1, "the clip stays in the Studio so the user can fix its offset");
  assert.equal(read.audio[0].offset, 9999);
});

test("BUG-014: eine doppelte Clip-ID wird gemeldet und nur einmal verwendet", () => {
  const read = readProject(document([], [clip(), clip({ start: 6, end: 10 })]));
  assert.equal(read.audio.length, 1);
  assert.equal(read.skipped.length, 1, "the repeated id must be named instead of quietly dropped");
});

test("BUG-004: Shot-Bindung und Tonspur-Clip derselben Karte werden beide sichtbar gehalten", () => {
  const read = readProject(document([binding("a1", "copy")], [clip({ mode: "lock" })]));
  const kept = read.shots[0].media.map((entry) => entry.context_id);
  assert.deepEqual(kept, ["a1"], "the shot binding must survive while the clip exists");
  // Der Konflikt selbst wird sichtbar gemeldet, damit die Oberfläche ihn erklären kann.
  assert.ok(read.conflicts && read.conflicts.length,
    "binding and lane clip on the same card must be reported as a conflict");
});