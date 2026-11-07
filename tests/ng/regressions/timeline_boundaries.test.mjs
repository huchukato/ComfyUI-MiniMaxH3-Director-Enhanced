// Imported shot times may be off the Studio's 0.1 s grid. Editing must still respect neighbours.
import assert from "node:assert/strict";
import test from "node:test";
import { readProject, placeAt, dragTo } from "../../../js/ng/h3s_model.js";

const imported = () => readProject("0-6.04: First shot.\n6.55-10: Second shot.").shots;

test("BUG-010: a new shot fits entirely inside an imported off-grid gap, or is refused", () => {
  const shots = imported();
  assert.equal(shots[0].end, 6.04);
  assert.equal(shots[1].start, 6.55);
  const placed = placeAt(shots, 6.5, 10, 4);
  if (placed) {
    assert.ok(placed.start >= 6.04, `start ${placed.start} crosses the previous shot`);
    assert.ok(placed.end <= 6.55, `end ${placed.end} crosses the next shot`);
    assert.ok(placed.end - placed.start >= 0.5 - 1e-9, "minimum duration is preserved");
  }
});

for (const mode of ["left", "right"]) {
  test(`BUG-010: dragging the ${mode} edge cannot cross an imported neighbour`, () => {
    const shots = imported(), original = shots[mode === "left" ? 1 : 0];
    const { items } = dragTo(shots, { ...original, mode }, mode === "left" ? -1 : 1, 10);
    const [first, second] = items;
    assert.ok(first.end <= second.start, `overlap: first ends at ${first.end}, second starts at ${second.start}`);
  });
}

test("control: dragging an edge on ordinary grid-aligned shots respects the neighbour", () => {
  const shots = [{ id: "a", start: 0, end: 6 }, { id: "b", start: 6.5, end: 10 }];
  const { items } = dragTo(shots, { ...shots[0], mode: "right" }, 1, 10);
  assert.equal(items[0].end, 6.5);
});

test("BUG-010: snapping an imported edge preserves the minimum shot duration", () => {
  const shots = readProject("6.04-6.55: A short imported shot.").shots;
  const { items } = dragTo(shots, { ...shots[0], mode: "left" }, 1, 10);
  assert.ok(items[0].end - items[0].start >= 0.5 - 1e-9,
    `minimum duration lost: ${items[0].start}-${items[0].end}`);
});

for (const mode of ["left", "right"]) {
  test(`BUG-010: an impossible minimum-duration constraint cannot corrupt a short imported ${mode} edge`, () => {
    const shots = readProject("0-0.2: First brief shot.\n0.2-0.4: Second brief shot.").shots;
    assert.equal(shots.length, 2, "short legacy shots remain readable");
    const original = shots[mode === "left" ? 1 : 0];
    const { items } = dragTo(shots, { ...original, mode }, mode === "left" ? 0.1 : -0.1, 1);
    assert.ok(items[0].end <= items[1].start, "an impossible 0.5 s minimum must refuse the edit, not overlap another shot");
    assert.ok(items.every((shot) => shot.start >= 0 && shot.end > shot.start), "all original shots remain valid");
  });
}
