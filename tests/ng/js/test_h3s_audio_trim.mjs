// Audio edge edits preserve placed-file timing and serialized Studio state.
import test from "node:test";
import assert from "node:assert/strict";
import * as model from "../../../js/ng/h3s_model.js";
import { installDom } from "./fake_dom.mjs";
import { timelineView } from "../../../js/ng/h3s_timeline.js";

const ranges = [{ index: 0, start_s: 0, end_s: 10 }, { index: 1, start_s: 10, end_s: 20 }];
const clip = (mode = "lock", extra = {}) => ({ schema_version: 1, id: "clip", context_id: "song", start: 4, end: 18,
  offset: 10, mode, lane: "l1", ...extra });
const drag = (c, side, delta, items = [c]) => model.dragTo(items, { id: c.id, mode: side, start: c.start, end: c.end }, delta, 20).items.find((v) => v.id === c.id);
const fileAt = (c, story) => {
  const part = model.clipParts(c, ranges).find((p) => p.story[0] <= story && story < p.story[1]);
  return part.file[0] + story - part.story[0];
};

for (const mode of ["lock", "copy"]) {
  test(`${mode}: left trim preserves file clock and serializes across render seam`, () => {
    const old = clip(mode), cut = drag(old, "left", 4);
    assert.equal(cut.offset, 14);
    for (const at of [8, 9.9, 10, 12, 17.9]) assert.equal(fileAt(cut, at), fileAt(old, at));
    const roundtrip = model.readProject(model.writeProject({ shots: [], audio: [cut], lanes: ["l1"] })).audio[0];
    assert.deepEqual(roundtrip, cut);
    assert.equal(fileAt(roundtrip, 12), 18);
  });

  test(`${mode}: expansion stops at start of file with no negative offset`, () => {
    const old = clip(mode, { offset: 1 });
    const expanded = drag(old, "left", -4);
    assert.equal(expanded.start, 3);
    assert.equal(expanded.offset, 0);
    assert.equal(expanded.end, old.end);
    assert.equal(fileAt(expanded, 12), fileAt(old, 12));
  });

  test(`${mode}: trim stops at neighbor and computes offset from actual movement`, () => {
    const old = clip(mode);
    const next = clip(mode, { id: "neighbor", start: 18, end: 20, offset: 0 });
    const cut = drag(old, "left", 50, [old, next]);
    assert.equal(cut.start, 17.5);
    assert.equal(cut.offset, 23.5);
    assert.equal(fileAt(cut, 17.9), fileAt(old, 17.9));
    assert.equal(drag(old, "right", -4).offset, old.offset);
    assert.equal(drag(old, "move", 2).offset, old.offset);
  });

  test(`${mode}: actual timeline pointer handler persists trimmed offset`, () => {
    installDom();
    const old = clip(mode);
    const S = { duration: 20, plan: { total_s: 20, total_frames: 480, chunks: [] }, shots: [], audio: [old],
      lanes: ["l1"], byId: new Map([["song", { name: "Song", color: "#abcdef" }]]), selected: null, ghosts: [], suggestions: {} };
    let saved;
    const actions = new Proxy({ setClips(value) { saved = value; } }, { get: (target, key) => target[key] || (() => {}) });
    const view = timelineView(S, actions);
    const block = view.byClass("h3s-clip")[0], grip = block.byClass("h3s-grip")[0];
    const event = { stopPropagation() {}, preventDefault() {}, currentTarget: grip, clientX: 200, pointerId: 1 };
    grip.onpointerdown(event);
    grip.onpointermove({ clientX: 400 });
    grip.onpointerup();
    assert.equal(saved[0].start, 8);
    assert.equal(saved[0].offset, 14);
    assert.equal(fileAt(saved[0], 12), 18);
  });
}

test("reference trim follows the file head and shot edges remain unchanged", () => {
  const old = clip("ref");
  assert.equal(drag(old, "left", 4).offset, old.offset + 4);
  assert.equal(drag(old, "left", -4).start, 0);
  assert.equal(drag(old, "left", -4).offset, old.offset - 4);
  const shot = { id: "s1", start: 4, end: 18, text: "A scene", spoken: [], media: [] };
  const cut = drag(shot, "left", 4);
  assert.equal(cut.start, 8);
  assert.equal(Object.hasOwn(cut, "offset"), false);
});
