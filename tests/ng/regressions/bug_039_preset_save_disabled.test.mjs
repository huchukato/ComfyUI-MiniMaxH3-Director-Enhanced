// BUG-039: Preset 'Save' button remains disabled after typing a preset name.
//
// In all Context cards (Image, Video, Audio, Text), the preset row initializes the
// Save button with: disabled: !S.presetName.trim()
// When opening a card with no preset selected, S.presetName is "" and the button is disabled.
// When the user types a new preset name into the input field, name.oninput calls
// actions.presetName(value), which only assigns S.presetName = value.
// It never updates saveBtn.disabled nor triggers a render. As a result, the Save button
// in the DOM remains permanently disabled, preventing the user from saving the typed preset.
import assert from "node:assert/strict";
import test from "node:test";
import { installDom } from "../js/fake_dom.mjs";
import { presetRow } from "../../../js/ng/h3c_parts.js";

installDom();

test("BUG-039: typing a preset name into the Preset field must enable the Save button", () => {
  const S = {
    presetName: "",
    presets: [],
    accent: "#6c8cff",
  };

  const actions = {
    presetName(value) { S.presetName = value; },
    savePreset() {},
    loadPreset() {},
    autoColor() {},
    set() {},
  };

  const row = presetRow(S, actions);
  const nameInput = row.byTag("input").find((el) => el.getAttribute("aria-label") === "Preset name");
  const saveBtn = row.button("Save");

  assert.equal(saveBtn.disabled, true, "Save button should initially be disabled when preset name is empty");

  // User types a preset name into the input field
  nameInput.value = "Hero Close-up";
  nameInput.oninput({ target: nameInput });

  // After typing a valid name, the Save button in the DOM must be enabled
  assert.equal(saveBtn.disabled, false, "Save button must be enabled after typing a valid preset name");
});

test("control: Save button is enabled when card opens with an existing preset name", () => {
  const S = {
    presetName: "Existing Preset",
    presets: ["Existing Preset"],
    accent: "#6c8cff",
  };

  const actions = {
    presetName(value) { S.presetName = value; },
    savePreset() {},
    loadPreset() {},
    autoColor() {},
    set() {},
  };

  const row = presetRow(S, actions);
  const saveBtn = row.button("Save");

  assert.equal(saveBtn.disabled, false, "Save button must be enabled when a preset name is present");
});
