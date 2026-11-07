import assert from "node:assert/strict";
import { cardContentHeight } from "../../../js/ng/h3c_measure.js";
import { installDom } from "./fake_dom.mjs";

globalThis.getComputedStyle = () => ({ paddingBottom: "6px" });
const root = (allocated, bottom, scale = 1) => ({
  offsetHeight: allocated,
  getBoundingClientRect: () => ({ top: 100, height: allocated * scale }),
  lastElementChild: { getBoundingClientRect: () => ({ bottom: 100 + bottom * scale }) },
});
assert.equal(cardContentHeight(root(1000, 1300)), 1314, "an expanded preview outside the old widget grows the card");
assert.equal(cardContentHeight(root(1400, 900)), 914, "closing the preview shrinks despite unused allocated space");
assert.equal(cardContentHeight(root(1314, 1300)), 1314, "the allocated result does not cause another growth cycle");
assert.equal(cardContentHeight(root(1000, 1300, .45)), 1314, "canvas zoom does not change the natural card size");
assert.equal(cardContentHeight(root(0, 0)), 0, "offscreen Comfy widgets do not collapse the saved node");
installDom();
const { controlBox } = await import("../../../js/ng/h3c_control.js");
let resized = 0;
const original = document.createElement("video");
const view = controlBox({ usage: "control", values: { video: "canny.mp4" }, opts: { control_original: "source.mp4", control_result: "canny.mp4" },
  els: { original }, api: { apiURL: (path) => path } }, { resize: () => resized++ });
view.byTag("details")[0].ontoggle();
assert.equal(resized, 1, "the fixed-height Comfy DOM widget also measures when its child details expands");
console.log("card measurement ok");
