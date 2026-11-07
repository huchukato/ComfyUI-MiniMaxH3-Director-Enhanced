import assert from "node:assert/strict";
import { timeView, zoomView, fitRange, tickTimes } from "../../../js/ng/h3s_time.js";

assert.deepEqual(timeView(), { zoom: 1, scroll: 0 });
assert.deepEqual(timeView({ zoom: Infinity, scroll: NaN }), { zoom: 1, scroll: 0 });
assert.deepEqual(timeView({ zoom: 99, scroll: -2 }), { zoom: 32, scroll: 0 });

// Zoom keeps the middle of the visible interval, except when the project edge constrains it.
let view = zoomView({ zoom: 2, scroll: 0.5 }, 4);
assert.equal(view.zoom, 4);
assert.equal(view.scroll, 0.5);
view = zoomView({ zoom: 4, scroll: 1 }, 8);
assert.ok(Math.abs(view.scroll * (1 - 1 / 8) + 0.5 / 8 - 0.875) < 1e-9);
assert.deepEqual(zoomView(view, 1), { zoom: 1, scroll: 0 });

view = fitRange([50, 52], 120);
assert.equal(view.zoom, 32, "short clips remain bounded at the maximum zoom");
const left = view.scroll * (1 - 1 / view.zoom) * 120;
assert.ok(left <= 50 && left + 120 / view.zoom >= 52);
assert.deepEqual(fitRange([0, 120], 120), { zoom: 1, scroll: 0 });
assert.deepEqual(fitRange(null, 120), { zoom: 1, scroll: 0 });
assert.deepEqual(tickTimes(20, 1), [0, 5, 10, 15, 20]);
assert.ok(tickTimes(120, 16).includes(51), "seconds remain readable when zoomed into a long project");
assert.ok(tickTimes(600, 32).length <= 601, "avoid a tick for every frame of a long project");
console.log("Timeline zoom, selection fit and ruler passed.");

const { installDom } = await import("./fake_dom.mjs");
installDom();
const { timelineNavigation, rememberTimeline, restoreTimeline } = await import("../../../js/ng/h3s_navigation.js");
const S = { duration: 120, selectedRange: [50, 52], node: { properties: {} } };
let changes = 0;
const actions = { setTimeline(next) { changes++; rememberTimeline(S, next); } };
let tools = timelineNavigation(S, actions);
tools.byTag("button").find((el) => el.getAttribute("aria-label") === "Zoom in timeline").onclick();
assert.equal(S.timeline.zoom, 2);
tools = timelineNavigation(S, actions);
tools.button("Fit selection").onclick();
assert.equal(S.timeline.zoom, 32);
assert.deepEqual(S.node.properties.ng_timeline, S.timeline, "workflow properties preserve view separately from the shot document");
const saved = JSON.parse(JSON.stringify(S.node.properties));
assert.deepEqual(timeView(saved.ng_timeline), S.timeline);
const viewport = { scrollWidth: 3200, clientWidth: 1000, scrollLeft: 0 };
restoreTimeline({ querySelector: () => viewport }, S);
assert.equal(viewport.scrollLeft, S.timeline.scroll * 2200, "plan refresh restores horizontal position without another edit");
assert.equal(changes, 2);
tools = timelineNavigation({ ...S, selectedRange: null }, actions);
assert.equal(tools.button("Fit selection").disabled, true);
tools.button("Fit project").onclick();
assert.deepEqual(S.timeline, { zoom: 1, scroll: 0 });
console.log("Timeline toolbar, workflow view state and scroll restoration passed.");

const { nextClipStart } = await import("../../../js/ng/h3s_model.js");
assert.equal(nextClipStart([], 10), 0);
assert.equal(nextClipStart([{ start: 0.5, end: 4 }], 10), 4, "click insertion continues after existing material");
assert.equal(nextClipStart([{ start: 2, end: 10 }], 10), 0, "can still use an earlier gap when the end is full");
assert.equal(nextClipStart([{ start: 0, end: 3 }, { start: 4, end: 10 }], 10), 3);
assert.equal(nextClipStart([{ start: 0, end: 10 }], 10), null, "never creates an overlapping clip");
assert.equal(nextClipStart([{ start: 0.2, end: 10 }], 10), null, "a gap shorter than the minimum is not an insertion point");
console.log("Timeline click insertion points passed.");
