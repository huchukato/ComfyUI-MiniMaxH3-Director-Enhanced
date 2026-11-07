/**
 * BUG-078: Left trim of "ref" audio clip fails to advance offset, sliding reference audio window and cutting file tail instead of head.
 *
 * User flow (Studio, Mode References -> sound reference clips have mode: "ref"):
 * A sound reference clip is placed on an audio lane spanning 4-18 s on the timeline with "From second in file" = 10 s.
 * The clip represents a 14-second audio reference window [10..24] from the audio file.
 * The user drags the left handle of the clip on the timeline from 4 s to 8 s to cut 4 seconds off the beginning of the clip.
 *
 * Expected:
 * - Trimming 4 seconds from the beginning of the clip on the timeline cuts the first 4 seconds of the audio reference.
 * - The clip's `offset` advances from 10 s to 14 s (`source.offset + start - drag.start`).
 * - The reference window in `clipParts` becomes [14..24] (duration 10 s, covering the remaining 10 seconds of the original window).
 * - Dragging the left edge cannot be pulled earlier than `drag.start - source.offset` (cannot pull before second 0 of the audio file).
 *
 * Ist:
 * - In `dragTo` (h3s_model.js:139), `placedAudio` only checks `["lock", "copy"]`, ignoring `mode: "ref"`.
 * - For `ref` clips, line 159 evaluates `offset = {}`, so `clip.offset` remains 10 s.
 * - In `clipParts` (h3s_model.js:184) and backend `legacy_bridge.py:149`, the reference audio window becomes [10..20].
 * - The first 4 seconds [10..14] are NOT trimmed; instead, seconds 20..24 are trimmed from the TAIL of the audio file,
 *   and the reference audio window shifts 4 seconds forward relative to the user's intended timeline trimming!
 * - Furthermore, line 154 does not clamp `earliest` to `drag.start - source.offset`, allowing the left handle
 *   to be pulled into negative file times.
 *
 * Run: node --test tests/ng/regressions/bug_078_ref_clip_left_trim_slides_audio.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { dragTo, clipParts } from "../../../js/ng/h3s_model.js";

const chunks = [{ index: 0, start_s: 0, end_s: 20 }];
const clipRef = (offset = 10) => ({
  schema_version: 1,
  id: "c_ref",
  context_id: "sound_ref",
  start: 4,
  end: 18,
  offset,
  mode: "ref",
  lane: "l1",
});

function trim(c, side, seconds) {
  const drag = { id: c.id, mode: side, start: c.start, end: c.end, reorder: false };
  return dragTo([c], drag, seconds, 20).items[0];
}

test("control: right-edge trim of ref clip keeps file start offset and shortens tail", () => {
  const c = clipRef(10);
  const cut = trim(c, "right", -4);
  assert.equal(cut.start, 4, "clip start should remain 4 s");
  assert.equal(cut.end, 14, "clip end should be trimmed to 14 s");
  assert.equal(cut.offset, 10, "offset must remain 10 s");

  const parts = clipParts(cut, chunks);
  assert.equal(parts.length, 1);
  assert.deepEqual(parts[0].file, [10, 20], "file window should be trimmed at tail from [10, 24] to [10, 20]");
});

test("BUG-078: left-edge trim of ref clip must advance offset by trimmed duration", () => {
  const c = clipRef(10);
  const cut = trim(c, "left", 4);
  assert.equal(cut.start, 8, "clip start should move from 4 s to 8 s");
  assert.equal(cut.end, 18, "clip end should remain 18 s");
  // Defect: placedAudio excludes "ref", so cut.offset remains 10 instead of advancing to 14
  assert.equal(
    cut.offset,
    14,
    `Trimming 4 s off left edge must advance offset from 10 to 14, but got ${cut.offset}`
  );
});

test("BUG-078: clipParts on left-trimmed ref clip must reflect trimmed file head", () => {
  const c = clipRef(10);
  const cut = trim(c, "left", 4);
  const parts = clipParts(cut, chunks);
  assert.equal(parts.length, 1);
  // Defect: cut.offset stays 10, so clipParts produces [10, 20] instead of [14, 24]
  assert.deepEqual(
    parts[0].file,
    [14, 24],
    `Left trim of 4 s should yield file window [14, 24], but got [${parts[0].file.join(", ")}]`
  );
});

test("BUG-078: left handle drag of ref clip cannot pull earlier than source.offset allows", () => {
  const c = clipRef(2);
  // source.offset is 2, start is 4. Dragging left by -4 would attempt start = 0 (file offset -2).
  const cut = trim(c, "left", -4);
  // Defect: placedAudio excludes "ref", so earliest is room.prev (0) instead of Math.max(0, 4 - 2) = 2
  assert.equal(
    cut.start,
    2,
    `Dragging left cannot pull earlier than drag.start - source.offset (2 s), but got ${cut.start}`
  );
  assert.equal(
    cut.offset,
    0,
    `Offset should be clamped to 0 s, but got ${cut.offset}`
  );
});
