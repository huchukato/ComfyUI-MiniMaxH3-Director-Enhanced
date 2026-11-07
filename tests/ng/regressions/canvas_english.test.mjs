// BUG-026: canvasInfo() returns German text in native resolution range.
// The Studio UI must be strictly in English (USR-004).
import assert from "node:assert/strict";
import test from "node:test";
import { canvasInfo } from "../../../js/ng/h3s_canvas.js";

test("control: auto size returns English description", () => {
  const [info] = canvasInfo(0, 0);
  assert.match(info, /^H3 takes the size/);
});

test("control: above native returns English description", () => {
  const [info, tone] = canvasInfo(1920, 1088);
  assert.equal(tone, "warn");
  assert.match(info, /^Above H3 native/);
});

test("control: fast size returns English description", () => {
  const [info] = canvasInfo(480, 736);
  assert.match(info, /^Fast size/);
});

test("BUG-026: native range canvas info must be in English", () => {
  const [info] = canvasInfo(1344, 768);
  // Must NOT contain German words like "Bereich", "Kanten", "Vielfache"
  assert.ok(!info.includes("Bereich"), `Expected English, got: ${info}`);
  assert.ok(!info.includes("Kanten"), `Expected English, got: ${info}`);
  assert.ok(!info.includes("Vielfache"), `Expected English, got: ${info}`);
  assert.match(info, /native range/i, `Expected English phrasing, got: ${info}`);
});
