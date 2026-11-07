import test from "node:test";
import assert from "node:assert/strict";
import { studio } from "./studio_fixture.mjs";

test("a plan redraw preserves an uncommitted duration and commits it on blur", (t) => {
  const f = studio(t);
  const duration = () => f.root.byTag("input").find((el) => el.getAttribute("aria-label") === "Duration in seconds");
  const field = duration();
  field.value = "5"; document.activeElement = field;
  f.handle.refresh();
  const restored = duration();
  assert.equal(restored.value, "5", "a response must not overwrite the number being typed");
  assert.equal(f.node.widgets.find((w) => w.name === "project_seconds").value, 10, "the draft is not committed until blur");
  restored.isConnected = true;
  restored.onblur({ target: restored });
  assert.equal(f.node.widgets.find((w) => w.name === "project_seconds").value, 5);
  assert.equal(f.read().shots[0].end, 5);
});

test("a plan redraw keeps the focused text element and its browser editing history", (t) => {
  const f = studio(t); f.select(); f.edit("Words being edited.");
  const field = f.root.byTag("textarea").find((el) => el.value === "Words being edited.");
  const parent = field.parentNode;
  document.activeElement = field;
  f.handle.refresh();
  assert.ok(f.root.byTag("textarea").find((el) => el.value === "Words being edited.") === field,
    "the browser undo stack belongs to the same DOM input");
  assert.ok(field.parentNode === parent, "the input's containing branch must never be detached");
});

test("implicit text inputs such as Look keep their native editing element", (t) => {
  const f = studio(t);
  const field = f.root.byTag("input").find((el) => el.getAttribute("id") === "h3s-look");
  field.value = "Keep the violet costume."; field.oninput({ target: field }); document.activeElement = field;
  const parent = field.parentNode;
  f.handle.refresh();
  assert.ok(f.root.byTag("input").find((el) => el.getAttribute("id") === "h3s-look") === field);
  assert.ok(field.parentNode === parent);
});
