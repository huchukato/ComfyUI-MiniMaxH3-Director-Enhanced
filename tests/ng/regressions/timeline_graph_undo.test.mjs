import test from "node:test";
import assert from "node:assert/strict";
import { bindTimelineKeys } from "../../../js/ng/h3s_keys.js";

function fixture() {
  const listeners = new Set();
  const root = { addEventListener(type, fn, capture) { assert.equal(type, "keydown"); assert.equal(capture, true); listeners.add(fn); },
    removeEventListener(type, fn, capture) { assert.equal(type, "keydown"); assert.equal(capture, true); listeners.delete(fn); } };
  class Tracker {
    calls = [];
    undoRedo(...args) { this.calls.push(args); return Promise.resolve("graph result"); }
  }
  return { root, Tracker, dispatch(event) { for (const fn of listeners) fn(event); } };
}

test("Studio consumes the exact event before ComfyUI's deferred graph undo runs", async () => {
  const f = fixture(), tracker = new f.Tracker();
  bindTimelineKeys(f.root, (event) => event.studio, f.Tracker);
  const event = { key: "z", ctrlKey: true, studio: true };
  // Matches ChangeTracker.init: window capture has already queued this callback.
  const deferredGraphUndo = () => tracker.undoRedo(event);
  f.dispatch(event);
  assert.equal(await deferredGraphUndo(), true);
  assert.equal(tracker.calls.length, 0, "the graph must not reconstruct the Studio node");
  const other = { key: "z", ctrlKey: true };
  assert.equal(await tracker.undoRedo(other, "extra"), "graph result");
  assert.deepEqual(tracker.calls, [[other, "extra"]]);
});

test("native text undo and other graph events pass through unchanged", async () => {
  const f = fixture(), tracker = new f.Tracker();
  bindTimelineKeys(f.root, () => false, f.Tracker);
  const event = { key: "z", ctrlKey: true, target: "textarea" };
  f.dispatch(event);
  assert.equal(await tracker.undoRedo(event), "graph result");
  assert.equal(tracker.calls[0][0], event);
});

test("multiple Studios share one guard and disposal removes only their listener", async () => {
  const f = fixture(), tracker = new f.Tracker();
  const dispose = bindTimelineKeys(f.root, () => true, f.Tracker);
  const wrapped = f.Tracker.prototype.undoRedo;
  const disposeOther = bindTimelineKeys(f.root, () => false, f.Tracker);
  assert.equal(f.Tracker.prototype.undoRedo, wrapped);
  const handled = {}; f.dispatch(handled); dispose();
  assert.equal(await tracker.undoRedo(handled), true, "a pending callback stays guarded after closing");
  const later = {}; f.dispatch(later);
  assert.equal(await tracker.undoRedo(later), "graph result");
  disposeOther();
});
