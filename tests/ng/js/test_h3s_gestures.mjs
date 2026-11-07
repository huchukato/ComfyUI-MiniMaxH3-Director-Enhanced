import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";
import { timelineView } from "../../../js/ng/h3s_timeline.js";
import { dragTo } from "../../../js/ng/h3s_model.js";

const control = { schema_version: 1, id: "control", context_id: "pose", lane: "control", start: 4, end: 8, offset: 2 };
let moved = dragTo([control], { id: "control", mode: "left", start: 4, end: 8 }, 1, 20).items[0];
assert.deepEqual([moved.start, moved.end, moved.offset], [5, 8, 3], "left trimming a control video keeps the source clock");
moved = dragTo([control], { id: "control", mode: "left", start: 4, end: 8 }, -4, 20).items[0];
assert.deepEqual([moved.start, moved.offset], [2, 0], "cannot extend before the control file begins");

installDom();
const calls = [], S = { duration: 20, shots: [{ id: "s", start: 0, end: 8, text: "Walk", media: [] }],
  audio: [], lanes: [], control: [], ghosts: [], suggestions: {}, byId: new Map(), selected: null };
const actions = new Proxy({}, { get: (_target, name) => name === "shotLabel" ? () => "Shot 1" : (...args) => calls.push([name, ...args]) });
let view = timelineView(S, actions), block = view.byClass("h3s-shot")[0];
block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 100, pointerId: 1 });
block.onpointermove({ clientX: 300 });
block.onpointercancel();
assert.ok(!calls.some(([name]) => name === "setShots"), "a cancelled drag must never save the preview position");
assert.equal(block.style.left, "0%", "cancel restores the visible preview too");
assert.equal(calls.filter(([name]) => name === "endPointer").length, 1);

calls.length = 0;
view = timelineView(S, actions); block = view.byClass("h3s-shot")[0];
block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 100, pointerId: 1 });
block.onpointermove({ clientX: 300 });
block.onlostpointercapture();
assert.ok(!calls.some(([name]) => name === "setShots"), "losing capture aborts instead of committing an accidental move");
console.log("Timeline cancel and control source trim passed.");
