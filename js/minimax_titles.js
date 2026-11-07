// Drop the old " CS" suffix from nodes that were placed before the rename.
//
// LiteGraph serialises a node's title into the workflow, so a node created while the
// display name still ended in "CS" keeps showing it forever — renaming the node class
// does not reach back into saved graphs. This rewrites those stale titles on load, but
// only when the title is exactly the old default: a title the user typed themselves is
// theirs to keep.
//
// The same pass marks the original Director as Legacy: a node still carrying its plain default title is
// relabelled "(Legacy)", so a workflow built before the NG nodes existed shows what it is.

const { app } = window.comfyAPI.app;

const RENAMED = {
  MiniMaxH3DirectorCS: "MiniMax H3 Director",
  MiniMaxH3PreviewOverrideCS: "MiniMax H3 Preview Override",
  MiniMaxH3RetakeStitchCS: "MiniMax H3 Retake Stitch",
};

const LEGACY_LABEL = {
  MiniMaxH3DirectorCS: "MiniMax H3 Director (Legacy)",
};

function healTitle(node) {
  const current = RENAMED[node?.type];
  if (!current || !node.title) return;
  const target = LEGACY_LABEL[node.type] || current;
  const stale = [current, current + " CS", current + " -CS"];
  if (node.title !== target && stale.includes(node.title)) {
    node.title = target;
    node.setDirtyCanvas?.(true, true);
  }
}

app.registerExtension({
  name: "MiniMaxH3.TitleCleanup",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!RENAMED[nodeData.name]) return;
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const out = onConfigure?.apply(this, arguments);
      healTitle(this);
      return out;
    };
  },

  // also catch graphs that were already on screen when this loaded
  async setup() {
    setTimeout(() => (app.graph?._nodes || []).forEach(healTitle), 0);
  },

  async afterConfigureGraph() {
    (app.graph?._nodes || []).forEach(healTitle);
  },
});
