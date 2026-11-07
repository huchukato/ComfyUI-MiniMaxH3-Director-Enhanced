// Live JPEG playback belongs to the Preview nodes and to H3 Render Sequence, which previews its parts with the Context
// Connector's preview VAE.
import {createPreviewPanel} from "./minimax_preview_player.js";
import {configurePreviewType} from "./minimax_preview_migrate.js";

const {app} = window.comfyAPI.app;
const {api} = window.comfyAPI.api;
const PREVIEW_NODES = new Set(["MiniMaxH3PreviewOverrideCS", "NGH3Preview"]);
const panels = new Set();
const owns = (value, root) => value != null && (String(value) === String(root) || String(value).startsWith(String(root) + "."));

function installPanel(node) {
  if (node._mmxPreview) return;
  const panel = createPreviewPanel(); node._mmxPreview = panel;
  panels.add(node);
  const widget = node.addDOMWidget("minimax_preview_ui", "minimax_preview_ui", panel.root, {
    getValue: () => "", setValue: () => {}, getMinHeight: () => 240,
  });
  widget.serialize = false;
  widget.computeLayoutSize = () => ({minHeight: 240, maxHeight: Number.MAX_SAFE_INTEGER, minWidth: 0});
  node.imgs = null; node.imageIndex = null;
  const width = Math.max(node.size[0], 340), height = Math.max(node.size[1], 520, node.computeSize?.()[1] || 0);
  node.size[0] = width; node.size[1] = height; node.setSize?.([width, height]);
  node._widgetSlotsDirty = true; node.setDirtyCanvas?.(true, true);
  if (!PREVIEW_NODES.has(node.comfyClass) && !node._mmxPreviewCleanup) {
    node._mmxPreviewCleanup = true;
    const removed = node.onRemoved;
    node.onRemoved = function () {
      this._mmxPreview?.player.dispose(); this._mmxPreview = null; panels.delete(this);
      return removed?.apply(this, arguments);
    };
  }
}

app.registerExtension({
  name: "MiniMaxH3PreviewOverrideCS",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!PREVIEW_NODES.has(nodeData.name)) return;
    configurePreviewType(nodeType, nodeData);
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = created?.apply(this, arguments); installPanel(this); return result;
    };
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = configured?.apply(this, arguments);
      const minimum = Math.max(520, this.computeSize?.()[1] || 0);
      if (Number.isFinite(minimum) && this.size[1] < minimum) {
        this.size[1] = minimum; this._widgetSlotsDirty = true; this.setDirtyCanvas?.(true, true);
      }
      return result;
    };
    const removed = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      this._mmxPreview?.player.dispose(); this._mmxPreview = null; panels.delete(this);
      return removed?.apply(this, arguments);
    };
  },
  async setup() {
    api.addEventListener("minimax_h3_preview", async ({detail = {}}) => {
      // H3 Render Sequence previews each part itself; its player appears with the first preview event.
      const render = app.graph?.getNodeById?.(String(detail.node_id ?? "").split(".")[0]);
      if (render?.comfyClass === "NGProjectRender") installPanel(render);
      const updates = [];
      for (const node of panels) {
        if (!owns(detail.node_id, node.id)) continue;
        node.imgs = null; node.imageIndex = null;
        const update = node._mmxPreview?.player.update(detail);
        if (update) updates.push(update.then(() => node.setDirtyCanvas?.(true, false)));
      }
      await Promise.allSettled(updates);
    });
    api.addEventListener("execution_start", () => {
      for (const node of panels) node._mmxPreview?.player.reset();
    });
    for (const name of ["execution_error", "execution_interrupted", "execution_success"]) {
      api.addEventListener(name, () => {
        const text = name === "execution_success" ? "Render finished" : name === "execution_interrupted" ? "Render interrupted" : "Render failed";
        for (const node of panels) node._mmxPreview?.player.stop(text, {discardPending: name !== "execution_success"});
      });
    }
  },
});
