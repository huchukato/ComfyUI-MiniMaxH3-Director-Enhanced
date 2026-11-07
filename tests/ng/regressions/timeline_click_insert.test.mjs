import test from "node:test";
import assert from "node:assert/strict";
import { studio } from "./studio_fixture.mjs";

const picker = (f) => f.root.byTag("select").find((el) => el.getAttribute("aria-label") === "Add audio clip to Audio 1");

test("audio lane source picker creates clips in free room and disables when full", (t) => {
  const f = studio(t, { audio: true });
  f.root.button("Audio lane").onclick();
  let source = picker(f);
  assert.equal(source.disabled, false);
  source.onchange({ target: { value: "sound_a" } });
  assert.deepEqual(f.read().audio.map((c) => [c.start, c.end, c.offset, c.mode]), [[0, 8, 0, "ref"]]);
  picker(f).onchange({ target: { value: "sound_a" } });
  assert.deepEqual(f.read().audio.map((c) => [c.start, c.end]), [[0, 8], [8, 10]]);
  assert.equal(picker(f).disabled, true);
  const event = { key: "z", ctrlKey: true, target: { closest: (selector) => selector === "select" ? {} : null },
    preventDefault() {}, stopPropagation() {} };
  f.root.onkeydown(event);
  assert.equal(f.read().audio.length, 1, "Undo still works after choosing a source in the dropdown");
});

test("FL2VA click insertion uses its supported audio lock mode", (t) => {
  const f = studio(t, { audio: true, mode: "fl2va" });
  f.root.button("Audio lane").onclick(); picker(f).onchange({ target: { value: "sound_a" } });
  assert.equal(f.read().audio[0].mode, "lock");
});

for (const [usage, mode] of [["lock", "lock"], ["copy", "copy"], ["music_style", "ref"]]) {
  test(`Ref2VA new clip starts with the card's ${usage} sound usage`, (t) => {
    const f = studio(t, { audio: true });
    f.sound.widgets.find((w) => w.name === "usage").value = usage;
    f.handle.refresh(); f.root.button("Audio lane").onclick();
    picker(f).onchange({ target: { value: "sound_a" } });
    assert.equal(f.read().audio[0].mode, mode);
  });
}

test("source picker explains missing audio cards instead of accepting image/video sources", (t) => {
  const f = studio(t);
  f.root.button("Audio lane").onclick();
  assert.equal(picker(f).disabled, true);
  assert.ok(picker(f).title.includes("Audio"));
});
