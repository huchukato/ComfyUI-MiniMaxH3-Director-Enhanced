// The H3 Storyboard's jobs outside the drawing: Cut out (ComfyUI's Remove Background) and Redraw (Qwen Image 2.1), both queued
// like any job, and the Director side: the sheet and frame panels as Context cards, the panels as the Director's shots.
// boardJobs takes the editor's state and functions (h3b_editor.js).
import { ASPECTS, newLayer, newId, panelTimes, fmtSeconds, pictureSize, loadName, srcUrl, redrawPrompt, mergeDirectorShots, syncFromDirector } from "./h3b_model.js";
import { drawPicture } from "./h3b_draw.js";
import { SUBFOLDER, comboOptions, canvasOf, runJob, qwenSetup, qwenGraph } from "./h3b_queue.js";
import { missingText, modelState, resolveModel } from "./ng_models.js";
import { isContextNode, upstreamNode } from "./ng_read.js";
import { applyValues, ownIdentity, values } from "./ng_widgets.js";

export function boardJobs({ S, node, app, api, pictures, change, render, flash, renderFiles, upload, connector, contexts }) {
  // ComfyUI's Remove Background on the picture: a new PNG with the figure on a transparent background, in output/h3-storyboard.
  async function cutOut(item) {
    const state = await modelState(api, ["background_removal"]);
    const model = resolveModel(state, "background_removal", node.properties.ng_models?.background_removal);
    if (!model) { flash(missingText(state.background_removal), true); return; }
    const prompt = {
      "1": { class_type: "LoadImage", inputs: { image: loadName(item.src) } },
      "2": { class_type: "LoadBackgroundRemovalModel", inputs: { bg_removal_name: model } },
      "3": { class_type: "RemoveBackground", inputs: { bg_removal_model: ["2", 0], image: ["1", 0] } },
      // JoinImageWithAlpha keeps where its mask is 0 (LoadImage's convention), so the foreground mask is inverted first.
      "4": { class_type: "InvertMask", inputs: { mask: ["3", 0] } },
      "5": { class_type: "JoinImageWithAlpha", inputs: { image: ["1", 0], alpha: ["4", 0] } },
      "6": { class_type: "SaveImage", inputs: { images: ["5", 0], filename_prefix: `${SUBFOLDER}/cutout` } },
    };
    S.busy = "cutout"; render();
    try {
      const src = await runJob(api, prompt, "6", 300);
      change((board) => {
        const target = board.panels.flatMap((p) => p.layers).find((l) => l.id === item.id);
        if (target) { target.src = src; target.name = `${item.name || "Picture"} (cut out)`; }
      });
      S.notice = { text: "Cut out. Undo brings the picture with its background back.", error: false };
    } catch (error) {
      S.notice = { text: `Cut out failed: ${error.message}`, error: true };
    } finally { S.busy = ""; render(); }
  }

  // --- Context cards for the Director: the sheet and panels used as first/last frames ----------------------------------
  const same = (a, b) => String(a || "").replace(/\\/g, "/") === String(b || "").replace(/\\/g, "/");
  function cardOf(file) {
    return app.graph._nodes.find((n) => n.comfyClass === "NGContextImage" && same(n.widgets?.find((w) => w.name === "image")?.value, file)) || null;
  }
  // A card with this file, made and connected to the Context Connector unless one exists; returns [card, connected].
  function ensureCard(file, { name, usage, description }, offset = 0) {
    const found = cardOf(file);
    if (found) return [found, true];
    const card = window.LiteGraph.createNode("NGContextImage");
    card.pos = [node.pos[0] + node.size[0] + 40, node.pos[1] + offset];
    app.graph.add(card);
    const set = (key, value) => { const w = card.widgets?.find((x) => x.name === key); if (w) { w.value = value; w.callback?.(value); } };
    // The card's file list was read when ComfyUI loaded, and on Windows it spells folders with "\": the file goes in with
    // the list's spelling, else the frontend flags the card as missing and the server refuses the value as not in the list.
    const listed = card.widgets?.find((x) => x.name === "image")?.options?.values || [];
    const spelled = listed.find((v) => same(v, file)) || (listed.some((v) => v.includes("\\")) ? file.replace(/\//g, "\\") : file);
    if (!listed.includes(spelled)) listed.push(spelled);
    const others = app.graph._nodes.filter((n) => n !== card && isContextNode(n)).map(values);
    set("image", spelled); set("name", ownIdentity({ name }, others).name || name); set("description", description);
    set("content", "composition"); set("usage", usage);
    set("content_roles", JSON.stringify(["composition"])); set("usage_roles", JSON.stringify([usage]));
    if (!card.widgets?.find((x) => x.name === "context_id")?.value) set("context_id", newId("ctx_sb_"));
    const target = connector(), slot = target?.inputs?.findIndex((input) => input.name.startsWith("context_image.") && input.link == null);
    if (target && slot >= 0) card.connect(0, target, slot);
    app.graph.setDirtyCanvas(true, true);
    return [card, Boolean(target && slot >= 0)];
  }
  const cardId = (card) => String(card.widgets?.find((w) => w.name === "context_id")?.value || "");

  async function useInDirector() {
    S.busy = "card"; render();
    try {
      const files = JSON.parse(await renderFiles());
      const [, connected] = ensureCard(files.sheet, { name: "Storyboard", usage: "storyboard",
        description: `Storyboard of ${S.board.panels.length} panels with times and captions.` });
      S.notice = { text: connected ? "The sheet's Context card is connected to the Context Connector. Send to Director puts it on the shots."
        : "A Context card with the sheet was added next to this node; connect it to the Context Connector.", error: false };
    } catch (error) {
      S.notice = { text: `Could not add the card: ${error.message}`, error: true };
    } finally { S.busy = ""; render(); }
  }

  // The Director that shares this node's Context Connector (or the only one in the graph).
  function director() {
    const directors = app.graph._nodes.filter((n) => n.comfyClass === "NGH3Director");
    const source = connector();
    return directors.find((d) => source && upstreamNode(d.graph, d.inputs?.find((i) => i.name === "context")) === source)
      || (directors.length === 1 ? directors[0] : null);
  }
  function sheetCardId() {
    const suffix = `${S.board.id}_${node.id}_sheet.png`;
    const last = S.lastFiles ? (() => { try { return JSON.parse(S.lastFiles).sheet; } catch { return ""; } })() : "";
    const found = (last && cardOf(last)) || app.graph._nodes.find((n) => n.comfyClass === "NGContextImage"
      && String(n.widgets?.find((w) => w.name === "image")?.value || "").replace(/\\/g, "/").endsWith(suffix));
    return found ? cardId(found) : "";
  }
  function pullFromDirector() {
    const target = director();
    if (!target) { flash("No H3 Director found: connect both nodes to the same Context Connector.", true); return; }
    const raw = String(target.widgets?.find((w) => w.name === "shots")?.value || "").trim();
    let project = {};
    try { project = raw.startsWith("{") ? JSON.parse(raw) : {}; } catch { project = {}; }
    const sbId = sheetCardId(), probe = syncFromDirector(structuredClone(S.board), project.shots || [], sbId);
    if (!probe.matched) { flash("No matching shots found in the Director yet. Send the panels to the Director first.", true); return; }
    if (!probe.updated) { flash(`All ${probe.matched} panel(s) are already in sync with the Director.`); return; }
    change((board) => { syncFromDirector(board, project.shots || [], sbId); });
    S.notice = { text: `Synced ${probe.updated} of ${probe.matched} panel(s) from the Director (times and shot texts). Undo restores the previous values.`, error: false };
    render();
  }
  // Stage 4: the panels become (or update/append) the Director's shots, with the sheet's card on every shot and a panel's own
  // picture as the first/last frame of its shot where the panel says so. The Director's sound lanes, Look, spoken lines and
  // other storyboard scenes stay.
  async function sendToDirector() {
    const target = director();
    if (!target) { flash("No H3 Director found: connect both nodes to the same Context Connector.", true); return; }
    const vals = Object.fromEntries((target.widgets || []).map((w) => [w.name, w.value]));
    let project = {};
    try { project = String(vals.shots || "").trim().startsWith("{") ? JSON.parse(vals.shots) : {}; } catch { project = {}; }
    const existing = Array.isArray(project.shots) ? project.shots : [];
    const hasSb = existing.some((s) => (s.media || []).some((m) => m.role === "storyboard") || String(s.id || "").startsWith("sb-"));
    const nonJson = !existing.length && Boolean(String(vals.shots || "").trim());
    if ((nonJson || (existing.length && !hasSb))
      && !window.confirm(`Replace the Director's ${existing.length || 1} shot${existing.length === 1 || nonJson ? "" : "s"} with the ${S.board.panels.length} panels? Its sound lanes stay.`)) return;
    S.busy = "send"; render();
    try {
      const files = JSON.parse(await renderFiles());
      const [sheetCard] = ensureCard(files.sheet, { name: "Storyboard", usage: "storyboard",
        description: `Storyboard of ${S.board.panels.length} panels with times and captions.` });
      const frames = {}, lastFrames = {};
      S.board.panels.forEach((item, index) => {
        if (!item.first_frame && !item.last_frame) return;
        const [card] = ensureCard(files.panels[index], { name: `Panel ${index + 1}`, usage: item.first_frame ? "first_frame" : "last_frame",
          description: item.caption || `Panel ${index + 1} of the storyboard.` }, 260 * (index + 1));
        if (item.first_frame) frames[index] = cardId(card);
        if (item.last_frame) lastFrames[index] = cardId(card);
      });
      const shots = mergeDirectorShots(existing, S.board, { storyboard: cardId(sheetCard), frames, lastFrames }, { replaceAll: !hasSb });
      const total = shots.length ? shots[shots.length - 1].end : panelTimes(S.board).at(-1)[1];
      const doc = { format: "h3-director-shots", schema_version: 1, ...project, shots };
      const changes = { shots: JSON.stringify(doc), project_seconds: total };
      if (!String(vals.idea || "").trim() && S.board.idea.trim()) changes.idea = S.board.idea;
      applyValues(target, changes);
      target.graph?.change?.();
      S.notice = { text: `The Director has ${shots.length === S.board.panels.length ? `the ${shots.length} panels as shots` : `${S.board.panels.length} panels (${shots.length} total shots)`} (${fmtSeconds(changes.project_seconds)} s), the storyboard on every shot`
        + `${Object.keys(frames).length ? `, ${Object.keys(frames).length} first frame(s)` : ""}`
        + `${Object.keys(lastFrames).length ? `, ${Object.keys(lastFrames).length} last frame(s)` : ""}.`, error: false };
    } catch (error) {
      S.notice = { text: `Could not send the panels: ${error.message}`, error: true };
    } finally { S.busy = ""; render(); }
  }

  // --- Stage 3: redraw a panel with Qwen Image 2.1 -------------------------------------------------------------------------
  // The collage (every visible layer but an earlier redraw) is image 1 and sets composition and size; the Context cards of
  // the characters the panel names are the references. Queued like any job; the result is a new layer over the collage, and
  // every redraw takes a new seed, so asking again gives another version.
  // A card whose file is not in the input folder would stop the whole job, so only cards with a file there count.
  function references(index, present) {
    const item = S.board.panels[index], text = `${item.title} ${item.caption} ${item.shot}`.toLowerCase();
    const cards = contexts().filter((entry) => entry.media === "image" && entry.widgets.image && entry.widgets.name
      && present.some((name) => same(name, String(entry.widgets.image).replace(/ \[input\]$/, "")))
      && !/storyboard|first_frame|last_frame|keyframe/.test(`${entry.widgets.usage} ${entry.widgets.usage_roles || ""}`));
    const named = cards.filter((entry) => text.includes(entry.widgets.name.toLowerCase()));
    return (named.length ? named : cards).slice(0, 4);
  }
  async function redraw(index) {
    const item = S.board.panels[index];
    if (!item.layers.some((l) => !l.hidden && !l.redrawn)) return `panel ${index + 1} has nothing to redraw yet (place pictures on it first)`;
    const [setup, present] = await Promise.all([qwenSetup(api, node.properties.ng_models || {}), comboOptions(api, "NGContextImage", "image")]);
    await pictures.ready(S.board);
    const [w, h] = pictureSize(S.board.aspect), collage = canvasOf(w, h);
    drawPicture(collage.getContext("2d"), { ...item, layers: item.layers.filter((l) => !l.redrawn) }, { x: 0, y: 0, w, h }, pictures);
    const collageName = await upload(collage, `${S.board.id}_${node.id}_collage${index + 1}.png`);
    const refs = references(index, present);
    const prompt = redrawPrompt(S.board, index, refs.map((r) => ({ name: r.widgets.name, description: r.widgets.description || "" })));
    const src = await runJob(api, qwenGraph(setup, { images: [collageName, ...refs.map((r) => String(r.widgets.image).replace(/ \[input\]$/, ""))],
      prompt, prefix: "redraw", opaque: true }), "s");
    const img = await new Promise((resolve) => { const i = new Image(); i.onload = () => resolve(i); i.onerror = () => resolve(null); i.src = srcUrl(src); });
    const [aw, ah] = ASPECTS[S.board.aspect];
    const scale = img ? Math.max(1, (ah / aw) * (img.naturalWidth / img.naturalHeight)) : 1;
    change((board) => {
      const layers = board.panels[index].layers;
      const old = layers.findIndex((l) => l.redrawn);
      const made = newLayer("image", { src, name: "Redrawn (Qwen Image 2.1)", scale, redrawn: true });
      if (old >= 0) layers.splice(old, 1, made); else layers.push(made);
      if (index === S.selected) S.layer = made.id;
    });
    return true;
  }
  async function redrawPanels(indexes) {
    S.busy = "redraw"; S.notice = null; render();
    let done = 0;
    const skipped = [];
    try {
      for (const [number, index] of indexes.entries()) {
        S.notice = { text: `Redrawing panel ${index + 1} with Qwen Image 2.1 (${number + 1} of ${indexes.length})…`, error: false }; render();
        const result = await redraw(index);
        if (result === true) done += 1; else skipped.push(result);
      }
      S.notice = { text: `Redrawn: ${done} of ${indexes.length} panel${indexes.length === 1 ? "" : "s"}${skipped.length ? `; ${skipped.join("; ")}` : ""}.`
        + (done ? " The collage stays below the new layer; Hide it or Undo to go back." : ""), error: Boolean(skipped.length) };
    } catch (error) {
      S.notice = { text: `Redraw failed: ${error.message}`, error: true };
    } finally { S.busy = ""; render(); }
  }

  return { cutOut, useInDirector, pullFromDirector, sendToDirector, redrawPanels };
}
