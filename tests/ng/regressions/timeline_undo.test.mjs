import test from "node:test";
import assert from "node:assert/strict";
import { studio } from "./studio_fixture.mjs";
import { newShot, newClip } from "../../../js/ng/h3s_model.js";

const toolbar = (f, action) => f.root.byTag("button").find((el) => el.getAttribute("aria-label") === `${action} timeline edit`);

test("timeline Undo/Redo restores a removed shot with all media and dialogue intact", (t) => {
  const shot = { ...newShot(0, 10), id: "shot_a", text: "Walk", media: [{ schema_version: 1, context_id: "figure", role: "keyframe", at_s: 4 }],
    spoken: [{ schema_version: 1, text: "Hello", speaker_id: "figure", voice: "a woman", language: "English", delivery: "says" }], locked_fields: ["text"] };
  const f = studio(t, { project: { shots: [shot], audio: [], lanes: [], control: [] } }); f.select();
  const before = f.read();
  f.root.byTag("button").find((el) => el.getAttribute("aria-label") === "Delete shot").onclick();
  assert.equal(f.read().shots.length, 0);
  assert.ok(toolbar(f, "Undo"), "Undo is reachable without keyboard shortcuts");
  toolbar(f, "Undo").onclick();
  assert.deepEqual(f.read(), before);
  toolbar(f, "Redo").onclick();
  assert.equal(f.read().shots.length, 0);
});

test("keyboard moves and removes only the selected control clip, with complete undo", (t) => {
  const control = { ...newClip("pose", "control", 4, 7), id: "control", offset: 1.25 }; delete control.mode;
  const shot = { ...newShot(0, 10), id: "shot_a" };
  const audio = { ...newClip("sound_a", "lane", 1, 9), offset: 2.5 };
  const f = studio(t, { audio: true, project: { shots: [shot], audio: [audio], lanes: ["lane"], control: [control] } });
  const block = f.root.byClass("h3s-clip")[1];
  block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 450, pointerId: 1 }); block.onpointerup();
  const key = (name, extra = {}) => f.root.onkeydown({ key: name, target: { closest: () => null }, preventDefault() {}, stopPropagation() {}, ...extra });
  key("ArrowRight", { shiftKey: true });
  assert.deepEqual([f.read().control[0].start, f.read().control[0].end, f.read().control[0].offset], [5, 8, 1.25]);
  assert.deepEqual(f.read().audio, [audio]);
  key("z", { ctrlKey: true });
  assert.deepEqual(f.read().control, [control]);
  key("y", { ctrlKey: true });
  assert.equal(f.read().control[0].start, 5);
  key("Delete"); assert.equal(f.read().control.length, 0);
  toolbar(f, "Undo").onclick(); assert.equal(f.read().control[0].start, 5);
});

test("text inputs keep native undo and arrow behavior", (t) => {
  const f = studio(t); f.select(); f.edit("Changed text.");
  let prevented = false;
  f.root.onkeydown({ key: "z", ctrlKey: true, target: { closest: () => ({ tagName: "TEXTAREA" }) },
    preventDefault() { prevented = true; }, stopPropagation() {} });
  assert.equal(prevented, false);
  assert.equal(f.read().shots[0].text, "Changed text.");
});

test("capture and bubble handlers apply a shortcut once and stop graph shortcuts", (t) => {
  const f = studio(t);
  f.root.button("Shot").onclick(); f.root.button("Shot").onclick();
  assert.equal(f.read().shots.length, 3);
  const event = { key: "z", ctrlKey: true, defaultPrevented: false, target: { closest: () => null },
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
  f.root.fire("keydown", event); f.root.onkeydown(event);
  assert.equal(f.read().shots.length, 2, "one key must undo only one edit");
  assert.equal(event.stopped, true);
  assert.equal(toolbar(f, "Redo").disabled, false);
});

test("button actions and Undo retain focus in the Studio for the next shortcut", (t) => {
  const f = studio(t);
  const add = f.root.button("Shot"); document.activeElement = add; add.onclick();
  assert.ok(f.root.all().includes(document.activeElement), "adding a clip/shot must not leave focus on the page body");
  const undo = toolbar(f, "Undo"); document.activeElement = undo; undo.onclick();
  assert.ok(f.root.all().includes(document.activeElement), "Undo must leave the next Ctrl+Y inside the Studio");
});

test("external graph changes clear local history instead of overwriting new work", (t) => {
  const f = studio(t); f.select(); f.edit("Local text.");
  const widget = f.node.widgets.find((entry) => entry.name === "shots");
  const document = JSON.parse(widget.value); document.shots[0].text = "New external work.";
  widget.value = JSON.stringify(document); f.handle.refresh();
  assert.equal(toolbar(f, "Undo").disabled, true);
  toolbar(f, "Undo").onclick();
  assert.equal(f.read().shots[0].text, "New external work.");
});

test("timeline Undo restores the clips and project duration cut by a duration edit", (t) => {
  const f = studio(t);
  const before = f.read();
  const duration = f.root.byTag("input").find((el) => el.value === 10 && el.getAttribute("list") === "h3s-durations");
  assert.ok(duration);
  duration.onchange({ target: { value: "5" } });
  assert.equal(f.node.widgets.find((w) => w.name === "project_seconds").value, 5);
  toolbar(f, "Undo").onclick();
  assert.equal(f.node.widgets.find((w) => w.name === "project_seconds").value, 10);
  assert.deepEqual(f.read(), before);
});
