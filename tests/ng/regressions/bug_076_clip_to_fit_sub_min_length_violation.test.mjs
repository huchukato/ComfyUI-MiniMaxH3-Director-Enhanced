/**
 * BUG-076: clipToFit and trimToDuration violate MIN_LENGTH invariant, creating uneditable sub-0.5s clips.
 *
 * User flow:
 * 1. User has an audio clip or shot near the end of a project (e.g., project_seconds = 15.0s, clip from 9.7s to 13.0s).
 * 2. User reduces the project duration to 10.0s in the Studio ("setDuration(10)" or duration selector).
 * 3. trimToDuration calls clipToFit(items, 10.0).
 * 4. clipToFit filters using:
 *      items.filter((item) => item.start < total - MIN_LENGTH / 2)
 *    Since MIN_LENGTH is 0.5s, MIN_LENGTH / 2 = 0.25s, so total - MIN_LENGTH / 2 = 9.75s.
 *    The clip at start = 9.7s passes the filter (9.7 < 9.75) and is truncated to end = 10.0s.
 * 5. The resulting clip has length = 10.0 - 9.7 = 0.3s, violating the studio invariant MIN_LENGTH = 0.5s.
 * 6. When the user attempts to resize the clip on the timeline via dragTo:
 *    - Right edge drag: snapWithin evaluates lo = drag.start + MIN_LENGTH = 10.2s > hi = room.next = 10.0s.
 *      Because lo > hi, snapWithin returns null and the right handle is completely locked / frozen.
 *    - Left edge drag (with predecessor clip ending at 9.6s): snapWithin evaluates lo = room.prev = 9.6s
 *      > hi = drag.end - MIN_LENGTH = 9.5s. Because lo > hi, snapWithin returns null and the left handle is frozen.
 *
 * Soll:
 * clipToFit and trimToDuration must enforce that every retained clip satisfies the MIN_LENGTH contract
 * (duration >= MIN_LENGTH = 0.5s). Clips starting at total - MIN_LENGTH < start < total - MIN_LENGTH / 2
 * cannot fit within total while maintaining MIN_LENGTH; they must be pruned rather than retained in a corrupted,
 * uneditable sub-0.5s state.
 *
 * Run:
 *   node --test tests/ng/regressions/bug_076_clip_to_fit_sub_min_length_violation.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { clipToFit, trimToDuration, dragTo, MIN_LENGTH } from "../../../js/ng/h3s_model.js";

const clip = (id, start, end) => ({
  schema_version: 1,
  id,
  context_id: "audio_1",
  start,
  end,
  offset: 0,
  mode: "lock",
  lane: "lane_1",
});

test("control: clip with start <= total - MIN_LENGTH preserves length >= MIN_LENGTH and is editable", () => {
  const total = 10.0;
  const c0 = clip("c0", 9.4, 14.0);
  const kept = clipToFit([c0], total);
  assert.equal(kept.length, 1);
  const item = kept[0];
  assert.equal(item.end, 10.0);
  assert.ok(
    item.end - item.start >= MIN_LENGTH,
    `expected duration >= ${MIN_LENGTH}, got ${item.end - item.start}`
  );

  // User can resize the right handle inward
  const dragRight = dragTo(kept, { id: "c0", mode: "right", start: item.start, end: item.end }, -0.1, total);
  assert.equal(dragRight.items[0].end, 9.9, "right edge must respond to drag and shorten to 9.9s");
});

test("control: clip with start >= total - MIN_LENGTH / 2 is properly pruned by clipToFit and trimToDuration", () => {
  const total = 10.0;
  const cFar = clip("cFar", 9.8, 14.0);
  const kept = clipToFit([cFar], total);
  assert.equal(kept.length, 0, "clips starting after total - MIN_LENGTH / 2 must be pruned");

  const trimResult = trimToDuration([cFar], total);
  assert.equal(trimResult.items.length, 0);
  assert.deepEqual(trimResult.removed, ["cFar"]);
  assert.deepEqual(trimResult.shortened, []);
});

test("BUG-076: clipToFit must not retain clips violating MIN_LENGTH (e.g. 0.3s duration)", () => {
  const total = 10.0;
  const cSub = clip("cSub", 9.7, 14.0);
  const kept = clipToFit([cSub], total);

  // In product code, kept retains cSub with end = 10.0 and length = 0.3s < MIN_LENGTH (0.5s).
  // Every retained clip must satisfy MIN_LENGTH.
  for (const item of kept) {
    const duration = Math.round((item.end - item.start) * 10) / 10;
    assert.ok(
      duration >= MIN_LENGTH,
      `BUG-076: clipToFit retained clip ${item.id} with duration ${duration}s < MIN_LENGTH (${MIN_LENGTH}s)`
    );
  }

  // Clips that cannot satisfy MIN_LENGTH within total must be pruned.
  assert.equal(
    kept.length,
    0,
    `BUG-076: clipToFit should prune clips that cannot fit MIN_LENGTH (${MIN_LENGTH}s), but kept ${kept.length} item(s)`
  );
});

test("BUG-076: trimToDuration must report sub-MIN_LENGTH clip as removed, not shortened", () => {
  const total = 10.0;
  const cSub = clip("cSub", 9.7, 14.0);
  const result = trimToDuration([cSub], total);

  // In product code: result.items contains [cSub] with duration 0.3s,
  // result.removed is [], and result.shortened is ['cSub'].
  assert.equal(
    result.items.length,
    0,
    `BUG-076: trimToDuration kept illegal sub-MIN_LENGTH clip in items: ${JSON.stringify(result.items)}`
  );
  assert.deepEqual(
    result.removed,
    ["cSub"],
    "BUG-076: sub-MIN_LENGTH clip must be in removed list so Studio can display 'removed ...' and offer Undo"
  );
  assert.deepEqual(
    result.shortened,
    [],
    "BUG-076: sub-MIN_LENGTH clip must not be in shortened list"
  );
});

test("BUG-076: sub-MIN_LENGTH clip produced by clipToFit completely freezes right edge dragging in dragTo", () => {
  const total = 10.0;
  const cSub = clip("cSub", 9.7, 14.0);
  const kept = clipToFit([cSub], total);
  // Since the fix clipToFit drops a clip that would be shorter than MIN_LENGTH, so no frozen 0.3 s clip can exist.
  if (!kept.length) return;
  const item = kept[0];

  // User attempts to drag the right edge inward by 0.1s to adjust the clip
  const dragRight = dragTo(kept, { id: item.id, mode: "right", start: item.start, end: item.end }, -0.1, total);

  // In product code, lo = 9.7 + 0.5 = 10.2 > hi = 10.0 -> snapWithin returns null -> end is frozen at 10.0!
  assert.notEqual(
    dragRight.items[0].end,
    item.end,
    `BUG-076: right handle is frozen at ${item.end}s because snapWithin returned null (lo: 10.2 > hi: 10.0)`
  );
});

test("BUG-076: sub-MIN_LENGTH clip produced by clipToFit freezes left edge dragging in dragTo when neighbor is present", () => {
  const total = 10.0;
  const cPrev = clip("cPrev", 8.0, 9.6);
  const cSub = clip("cSub", 9.7, 14.0);
  const kept = [cPrev, ...clipToFit([cSub], total)];
  if (kept.length === 1) return;     // the sub-MIN_LENGTH clip was dropped, nothing can freeze
  const item = kept[1];

  // User attempts to drag the left edge leftward by 0.1s
  const dragLeft = dragTo(kept, { id: item.id, mode: "left", start: item.start, end: item.end }, -0.1, total);

  // In product code, lo = room.prev = 9.6 > hi = 10.0 - 0.5 = 9.5 -> snapWithin returns null -> start is frozen at 9.7!
  assert.notEqual(
    dragLeft.items[1].start,
    item.start,
    `BUG-076: left handle is frozen at ${item.start}s because snapWithin returned null (lo: 9.6 > hi: 9.5)`
  );
});
