/**
 * BUG-066: trimming the left edge of a placed (lock / copy) audio clip slides the sound against the picture.
 *
 * User flow (Studio, Mode First/Last frame -> new clips are "lock"): drop a song on an audio lane at 4-18 s with "From second in file" = 10,
 * then drag the clip's left edge from 4 s to 8 s ("trim it at its edges", docs/NG.md). Trimming should cut away the first four seconds
 * and leave the rest where it was: at story second 8 the clip played file second 14 before the trim and must still play it.
 *
 * Ist: dragTo returns only the new start/end; `offset` stays 10, so after the trim story second 8 plays file second 10: the audio
 * is four seconds earlier than before, for every render part (clipParts is what the compiler/preview uses).
 *
 * Run: node --test tests/ng/regressions/bug_066_clip_left_trim_slides_audio.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { dragTo, clipParts } from "../../../js/ng/h3s_model.js";

const chunks = [{ index: 0, start_s: 0, end_s: 10 }, { index: 1, start_s: 10, end_s: 20 }];
const clip = (mode) => ({ schema_version: 1, id: "c1", context_id: "song", start: 4, end: 18, offset: 10, mode, lane: "l1" });

// File second played at story second `t`, as the plan slices it.
function fileAt(c, t) {
  const part = clipParts(c, chunks).find((p) => p.story[0] <= t && t < p.story[1]);
  return part ? part.file[0] + (t - part.story[0]) : null;
}

function trim(c, side, seconds) {
  const drag = { id: c.id, mode: side, start: c.start, end: c.end, reorder: false };
  return dragTo([c], drag, seconds, 20).items[0];
}

for (const mode of ["lock", "copy"]) {
  test(`control (${mode}): trimming the right edge keeps the sound where it was`, () => {
    const c = clip(mode), cut = trim(c, "right", -4);
    assert.equal(cut.end, 14);
    assert.equal(fileAt(cut, 8), fileAt(c, 8));
  });

  test(`BUG-066 (${mode}): trimming the left edge keeps the remaining sound where it was`, () => {
    const c = clip(mode), cut = trim(c, "left", 4);
    assert.equal(cut.start, 8);
    assert.equal(fileAt(cut, 12), fileAt(c, 12), `story 12 s played file ${fileAt(c, 12)} s before the trim and ${fileAt(cut, 12)} s after`);
  });
}
