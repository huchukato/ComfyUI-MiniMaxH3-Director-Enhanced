// BUG-040: Studio Mode card has no way to return to "Automatic" mode once fixed.
//
// In the Studio sidebar, modeCard presents two segmented buttons:
// "First / last frame" (fl2va) and "References" (ref2va).
// The hint text explains:
// "Automatic: ... depending on the Content. Click one side to fix it."
// When the user clicks one side (e.g. "First / last frame"), actions.setWidget("mode", "fl2va")
// fixes the mode. Because native widgets are hidden on the graph node, the Studio is the sole UI.
// However, clicking the already active segmented button does NOT toggle the selection back to "auto"
// (seg defines onclick: () => actions.setWidget("mode", value) unconditionally),
// and there is no "Auto" button or reset control.
// The user is permanently stuck in manual mode for that workflow and cannot revert to "auto".
import assert from "node:assert/strict";
import test from "node:test";
import { studio } from "./studio_fixture.mjs";

test("BUG-040: clicking the active mode segment in the Studio must toggle back to 'auto'", (t) => {
  const s = studio(t, { mode: "auto" });
  const getMode = () => s.node.widgets.find((w) => w.name === "mode").value;

  assert.equal(getMode(), "auto", "initial mode should be 'auto'");

  // User clicks "First / last frame" to fix the mode
  const [fl2vaBtn, ref2vaBtn] = s.root.byClass("h3s-seg").slice(2, 4);     // the Output switch (Video | Pictures) comes first
  fl2vaBtn.onclick();
  assert.equal(getMode(), "fl2va", "mode should be 'fl2va' after clicking First/last frame");

  // User clicks the active "First / last frame" button again to unfix and return to Automatic
  fl2vaBtn.onclick();
  assert.equal(getMode(), "auto", "clicking active mode segment must toggle back to 'auto'");
});

test("control: clicking the other mode segment switches between fl2va and ref2va", (t) => {
  const s = studio(t, { mode: "fl2va" });
  const getMode = () => s.node.widgets.find((w) => w.name === "mode").value;

  const [fl2vaBtn, ref2vaBtn] = s.root.byClass("h3s-seg").slice(2, 4);     // the Output switch (Video | Pictures) comes first
  assert.equal(getMode(), "fl2va");

  // Switching from fl2va to ref2va
  ref2vaBtn.onclick();
  assert.equal(getMode(), "ref2va");
});

test("control: the Output switch above the mode chooses video or pictures", (t) => {
  const s = studio(t, { mode: "auto" });
  const output = () => s.node.widgets.find((w) => w.name === "output")?.value;
  const [video, pictures] = s.root.byClass("h3s-seg");
  pictures.onclick();
  assert.equal(output(), "images");
  video.onclick();
  assert.equal(output(), "video");
});
