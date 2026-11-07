// Browser test (user 2026-10-19: "do the nodes fit when placed, when made wider or taller, is there a minimum size?").
// Run in a ComfyUI page with this pack loaded (it replaces the open workflow with an empty one): paste into the console or a
// browser tool, then `await nodeSizeTests()`. Returns one row per node and check; every `ok` must be true.
//
// Rules: the Context cards, the Storyboard and the H3 Director are as tall as their content and keep a minimum width; the AI
// Loader keeps a minimum width and height and may be taller. Visible content must end inside the node (nothing cut off), and
// a wider node must widen its content. Measured 2026-10-19 on 8210 by dragging corners with the mouse as well. Found and
// fixed then: the AI Loader had no minimum width (at 210 its Model field was cut off), and the Director, the Storyboard and
// the Audio / Text cards stayed taller than their content after a drag (690-1100 empty units; ng_layout.refitAfterResize).
// The page must be visible: a hidden tab runs no animation frames, so nothing re-fits and every DOM widget measures 0.
async function nodeSizeTests() {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const MIN = { NGContextImage: 660, NGContextVideo: 660, NGContextAudio: 700, NGContextText: 780, NGStoryboard: 760, NGH3Director: 900,
    NGAIProvider: 440 };
  const FIT = new Set(["NGContextImage", "NGContextVideo", "NGContextAudio", "NGContextText", "NGStoryboard", "NGH3Director"]);
  await app.loadGraphData({ last_node_id: 0, last_link_id: 0, nodes: [], links: [], groups: [], version: 0.4 }, true, true, "node-size-test");
  const rows = [], check = (type, name, ok, detail) => rows.push({ type, name, ok: Boolean(ok), detail });
  // the node's own panel: the largest DOM widget that is shown (ComfyUI keeps hidden native text boxes as DOM widgets too)
  const element = (node) => node.widgets?.map((widget) => widget.element).filter((el) => el && getComputedStyle(el).display !== "none")
    .sort((a, b) => b.offsetHeight - a.offsetHeight)[0];
  const show = (node) => { app.canvas.ds.scale = 0.5; app.canvas.ds.offset = [40 - node.pos[0], 60 - node.pos[1]]; app.canvas.setDirty(true, true); };
  const settle = async (node) => { show(node); for (let i = 0; i < 10; i++) { await wait(250); app.canvas.draw(true, true); } };
  // how far the lowest / rightmost visible content reaches past the node's edge, in graph units (> 2 = cut off)
  const overhang = (node) => {
    const el = element(node), box = app.canvas.canvas.getBoundingClientRect(), s = app.canvas.ds.scale, o = app.canvas.ds.offset;
    const kids = el ? [...el.querySelectorAll("*")].filter((c) => c.checkVisibility?.() !== false).map((c) => c.getBoundingClientRect())
      .filter((b) => b.width && b.height) : [];
    if (!kids.length) return [0, 0];
    return [(Math.max(...kids.map((b) => b.bottom)) - (box.top + (node.pos[1] + node.size[1] + o[1]) * s)) / s,
      (Math.max(...kids.map((b) => b.right)) - (box.left + (node.pos[0] + node.size[0] + o[0]) * s)) / s].map(Math.round);
  };
  let x = 0;
  for (const type of Object.keys(MIN)) {
    const node = LiteGraph.createNode(type);
    node.pos = [x, 0];
    app.graph.add(node);
    x += 2200;
    await settle(node);
    const [w, h] = node.size;
    check(type, "placed: minimum width", w >= MIN[type], `${Math.round(w)} >= ${MIN[type]}`);
    check(type, "placed: nothing cut off", overhang(node).every((v) => v <= 2), `overhang ${overhang(node)}`);
    node.setSize([w + 500, h]); await settle(node);
    const el = element(node);
    check(type, "wider: stays wide", Math.abs(node.size[0] - (w + 500)) < 2, `${Math.round(node.size[0])} (asked ${Math.round(w + 500)})`);
    check(type, "wider: content follows", el && el.offsetWidth >= node.size[0] - 60, `content ${el?.offsetWidth} in ${Math.round(node.size[0])}`);
    const tall = node.size[1] + 400;
    node.setSize([node.size[0], tall]); await settle(node);
    check(type, FIT.has(type) ? "taller: back to its content" : "taller: may be taller",
      FIT.has(type) ? node.size[1] < tall - 100 : node.size[1] >= tall - 2, `${Math.round(node.size[1])} (asked ${Math.round(tall)})`);
    if (type === "NGAIProvider") {
      // the Loader re-checks its size in onResize, which a drag calls too; the cards re-check when their content resizes
      node.setSize([210, node.size[1]]); await settle(node);
      check(type, "narrower: back to the minimum", node.size[0] >= MIN[type] - 1, `${Math.round(node.size[0])}`);
    }
    node.setSize([Math.max(node.size[0], MIN[type]), 150]); await settle(node);
    check(type, "shorter: nothing cut off", overhang(node).every((v) => v <= 2), `${Math.round(node.size[1])} high, overhang ${overhang(node)}`);
  }
  return rows;
}
