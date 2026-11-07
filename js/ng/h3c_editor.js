// The Image card's editor (the brush icon): a window over the graph, opened only when needed (user 2026-10-19).
//   Mask      - paint (brush, eraser) or find with SAM 3.1 what a picture of the Director's Pictures output may change;
//               saved as the card's edit mask (white = change). The rest of the picture stays as it is.
//   Structure - Canny, Pose or Depth of this picture, as a new card: in Pictures a pose or layout guide that is not drawn
//               (H3's ControlNet does not steer a single frame; the guide given as a reference does, measured 2026-10-19).
//   Sheet     - a character sheet of this figure made by H3 itself (front, sides, back, face), no Qwen needed.
import { h, icon } from "./h3s_dom.js";
import { mediaURL } from "./h3c_media.js";
import { values, applyValues } from "./ng_widgets.js";
import { contextOptions, setOptions } from "./ng_context_controls.js";
import { downstreamNodes } from "./ng_graph.js";
import { modelState, resolveModel, missingText } from "./ng_models.js";
import { connectedH3, maskGraph, runPictureJob, sheetGraph, structureGraph, FOLDER } from "./h3c_editor_jobs.js";

const STRUCTURES = [["pose", "Pose", "pose", "The pose of the figure in this picture."],
  ["canny", "Edges (Canny)", "composition", "The outlines and layout of this picture."],
  ["depth", "Depth", "composition", "The depth and layout of this picture."]];

async function uploadMaskPicture(api, canvas) {
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  const data = new FormData();
  data.append("image", blob, `mask_${Date.now()}.png`); data.append("type", "input"); data.append("subfolder", FOLDER);
  const response = await api.fetchApi("/upload/image", { method: "POST", body: data });
  if (!response.ok) throw new Error("Saving the mask failed.");
  const saved = await response.json();
  return [saved.subfolder, saved.name].filter(Boolean).join("/");
}

const loadImage = (url) => new Promise((resolve, reject) => {
  const picture = new Image(); picture.crossOrigin = "anonymous";
  picture.onload = () => resolve(picture); picture.onerror = () => reject(new Error("The picture could not be loaded.")); picture.src = url;
});

// A new Image card beside this one, connected to the same Context Connector when it has a free picture input.
function addCard(card, source, content, name, description) {
  const graph = card.graph, LG = window.LiteGraph || window.comfyAPI?.litegraph?.LiteGraph;
  const created = LG.createNode("NGContextImage");
  created.pos = [card.pos[0] + card.size[0] + 40, card.pos[1]];
  graph.add(created);
  applyValues(created, { image: source, name, content, content_roles: JSON.stringify([content]), usage: "reference",
    usage_roles: JSON.stringify(["reference"]), description });
  const connector = downstreamNodes(card).find((entry) => entry.comfyClass === "NGContextConnector");
  const slot = connector?.inputs?.findIndex((input) => input.name.startsWith("context_image.") && input.link == null) ?? -1;
  if (slot >= 0) created.connect(0, connector, slot);
  graph.change?.();
  return slot >= 0;
}

export function openPictureEditor(card, api, done) {
  const source = values(card).image;
  if (!source) return done("Choose a picture first.", true);
  const E = { tab: "mask", size: 40, erase: false, busy: "", note: "", result: null, kind: "pose", find: "" };
  const view = h("canvas", { class: "h3e-view" }), mask = document.createElement("canvas"), tint = document.createElement("canvas");
  let picture = null, scale = 1, painting = false, last = null;
  const overlay = h("div", { class: "h3e-back", onclick: (event) => { if (event.target === overlay) close(); } });
  const panel = h("div", { class: "h3e" });
  overlay.append(panel);
  // keys typed in the editor stay there (ComfyUI deletes a selected node on Delete); Escape closes it
  overlay.addEventListener("keydown", (event) => event.stopPropagation());
  const keys = (event) => { if (event.key === "Escape") close(); };
  document.addEventListener("keydown", keys, true);
  document.body.append(overlay);
  function close() { document.removeEventListener("keydown", keys, true); overlay.remove(); done(""); }
  const say = (text) => { E.note = text; render(); };

  function draw() {
    if (!picture) return;
    const ctx = view.getContext("2d");
    ctx.globalCompositeOperation = "source-over"; ctx.drawImage(picture, 0, 0, view.width, view.height);
    const t = tint.getContext("2d");
    t.globalCompositeOperation = "source-over"; t.drawImage(mask, 0, 0, tint.width, tint.height);
    t.globalCompositeOperation = "multiply"; t.fillStyle = "#ff3030"; t.fillRect(0, 0, tint.width, tint.height);
    ctx.globalAlpha = 0.6; ctx.globalCompositeOperation = "screen"; ctx.drawImage(tint, 0, 0); ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
  function paint(event) {
    const box = view.getBoundingClientRect(), x = (event.clientX - box.left) / box.width * mask.width, y = (event.clientY - box.top) / box.height * mask.height;
    const m = mask.getContext("2d");
    // a line from the last point, so a fast stroke is no row of dots
    m.strokeStyle = E.erase ? "#000" : "#fff"; m.lineWidth = E.size / scale; m.lineCap = m.lineJoin = "round";
    m.beginPath(); m.moveTo(...(last || [x, y])); m.lineTo(x, y); m.stroke();
    last = [x, y];
    draw();
  }
  view.onpointerdown = (event) => { if (E.tab !== "mask") return; painting = true; last = null; view.setPointerCapture(event.pointerId); paint(event); };
  view.onpointermove = (event) => { if (painting) paint(event); };
  view.onpointerup = () => { painting = false; last = null; };
  function addMaskPicture(other) {
    const m = mask.getContext("2d");
    m.globalCompositeOperation = "lighten"; m.drawImage(other, 0, 0, mask.width, mask.height); m.globalCompositeOperation = "source-over";
    draw();
  }
  function grow(pixels) {
    const copy = document.createElement("canvas"); copy.width = mask.width; copy.height = mask.height;
    copy.getContext("2d").drawImage(mask, 0, 0);
    const m = mask.getContext("2d"); m.globalCompositeOperation = "lighten";
    for (let a = 0; a < 16; a += 1) m.drawImage(copy, Math.cos(a * Math.PI / 8) * pixels, Math.sin(a * Math.PI / 8) * pixels);
    m.globalCompositeOperation = "source-over"; draw();
  }
  async function job(label, run) {
    if (E.busy) return;
    E.busy = label; say("");
    try { await run(); } catch (error) { say(error.message); } finally { E.busy = ""; render(); }
  }

  const tabs = () => h("div", { class: "h3e-tabs" }, [["mask", "Mask"], ["structure", "Structure"], ["sheet", "Sheet"]].map(([key, text]) =>
    h("button", { class: E.tab === key ? "h3c-btn on" : "h3c-btn", onclick: () => { E.tab = key; E.result = null; render(); } }, text)));
  function maskTools() {
    const find = h("input", { class: "h3c-in", value: E.find, placeholder: "What to change, e.g. mug, person, sky", "aria-label": "Find with SAM 3.1",
      oninput: (event) => { E.find = event.target.value; } });
    return [h("div", { class: "h3c-row" },
      h("button", { class: E.erase ? "h3c-btn" : "h3c-btn on", onclick: () => { E.erase = false; render(); } }, "Brush"),
      h("button", { class: E.erase ? "h3c-btn on" : "h3c-btn", onclick: () => { E.erase = true; render(); } }, "Eraser"),
      h("label", { class: "h3c-lbl" }, "Size", h("input", { type: "range", min: 4, max: 200, value: E.size, oninput: (event) => { E.size = Number(event.target.value); } })),
      h("button", { class: "h3c-btn", title: "Make the white area 12 px larger", onclick: () => grow(12) }, "Grow"),
      h("button", { class: "h3c-btn", onclick: () => { const m = mask.getContext("2d"); m.fillStyle = "#000"; m.fillRect(0, 0, mask.width, mask.height); draw(); } }, "Clear")),
    h("div", { class: "h3c-row" }, find, h("button", { class: "h3c-btn ai", disabled: Boolean(E.busy), onclick: () => job("sam", async () => {
      if (!find.value.trim()) throw new Error("Write what to find, e.g. mug.");
      const state = await modelState(api, ["sam3"]), file = resolveModel(state, "sam3", card.properties.ng_models?.sam3);
      if (!file) throw new Error(missingText(state.sam3));
      const name = await runPictureJob(api, maskGraph(source, find.value.trim(), file, globalThis.crypto.randomUUID()), "mask");
      addMaskPicture(await loadImage(mediaURL(name, api))); say("Found. Paint or erase to correct it, then Save.");
    }) }, E.busy === "sam" ? "Finding …" : "Find (SAM 3.1)")),
    h("span", { class: "h3c-hint" }, "Red is what may change in the Director's Pictures output (a First frame picture on a shot). Everything else stays exactly as it is."),
    h("div", { class: "h3c-row" }, h("button", { class: "h3c-btn ai", disabled: Boolean(E.busy), onclick: () => job("save", async () => {
      const file = await uploadMaskPicture(api, mask); setOptions(card, { edit_mask: file }); close();
    }) }, "Save mask"), contextOptions(card).edit_mask ? h("button", { class: "h3c-btn", onclick: () => { setOptions(card, { edit_mask: "" }); close(); } }, "Remove mask") : null)];
  }
  function resultTools(kind, content, name, description) {
    if (!E.result) return [];
    return [h("img", { class: "h3e-result", src: mediaURL(E.result, api) }), h("div", { class: "h3c-row" },
      h("button", { class: "h3c-btn ai", onclick: () => { const linked = addCard(card, E.result, content, name, description);
        say(linked ? "Added as a new card and connected." : "Added as a new card; connect it to the Context Connector."); } }, "Add as new card"),
      kind === "sheet" ? h("button", { class: "h3c-btn", onclick: () => { applyValues(card, { image: E.result }); card.graph?.change?.(); close(); } }, "Use as this card's picture") : null)];
  }
  function structureTools() {
    const own = values(card).name || "Picture", chosen = STRUCTURES.find(([key]) => key === E.kind);
    return [h("div", { class: "h3c-row" }, STRUCTURES.map(([key, text]) => h("button", { class: E.kind === key ? "h3c-btn on" : "h3c-btn",
      onclick: () => { E.kind = key; E.result = null; render(); } }, text)),
    h("button", { class: "h3c-btn ai", disabled: Boolean(E.busy), onclick: () => job("structure", async () => {
      const purposes = E.kind === "pose" ? ["pose_detector", "pose"] : E.kind === "depth" ? ["moge"] : [];
      const state = purposes.length ? await modelState(api, purposes) : {}, files = purposes.map((p) => resolveModel(state, p, card.properties.ng_models?.[p]));
      const lacking = purposes.filter((_, n) => !files[n]).map((p) => missingText(state[p]));
      if (lacking.length) throw new Error(lacking.join(" "));
      const setup = E.kind === "pose" ? { detector: files[0], pose: files[1] } : { depth: files[0] };
      E.result = await runPictureJob(api, structureGraph(E.kind, source, setup, globalThis.crypto.randomUUID()), E.kind); say("");
    }) }, E.busy === "structure" ? "Making …" : "Make")),
    h("span", { class: "h3c-hint" }, "As a card on a shot of the Pictures output it guides the new picture (pose or layout); it is never drawn itself."),
    ...resultTools(E.kind, chosen[2], `${own} ${chosen[1].split(" ")[0].toLowerCase()}`, chosen[3])];
  }
  function sheetTools() {
    const own = values(card).name || "Figure", place = E.sheetKind === "place";
    return [h("div", { class: "h3c-row" }, [["figure", "Figure"], ["place", "Place"]].map(([key, text]) => h("button", {
      class: (E.sheetKind || "figure") === key ? "h3c-btn on" : "h3c-btn", onclick: () => { E.sheetKind = key; E.result = null; render(); } }, text))),
    h("span", { class: "h3c-hint" }, place ? "H3 turns once in this place, frozen and empty, and keeps six views all around. About 9 minutes "
      + "with the ref2v turbo LoRA." : "H3 circles this figure once and keeps six views: front, left, back, right, three-quarter and the face. "
      + "About 4 minutes with the ref2v turbo LoRA; uses the H3 models of the Context Connector."),
    h("button", { class: "h3c-btn ai", disabled: Boolean(E.busy), onclick: () => job("sheet", async () => {
      const files = connectedH3(card);
      E.result = await runPictureJob(api, await sheetGraph(api, source, files, globalThis.crypto.randomUUID(), place ? "place" : "figure"), "sheet", 3600);
      say("");
    }) }, E.busy === "sheet" ? "Making the sheet …" : place ? "Make place sheet" : "Make character sheet"),
    ...(place ? resultTools("sheet", "location", `${own} views`, `Views all around ${own}, the same place from six sides.`)
      : resultTools("sheet", "character", `${own} sheet`, `Character sheet of ${own}: front, sides, back and face.`))];
  }
  function render() {
    const tools = E.tab === "mask" ? maskTools() : E.tab === "structure" ? structureTools() : sheetTools();
    panel.replaceChildren(h("div", { class: "h3c-row" }, h("span", { class: "h3c-cap" }, `Edit ${values(card).name || "picture"}`), h("span", { class: "h3c-grow" }),
      h("button", { class: "h3c-btn", "aria-label": "Close", onclick: close }, icon("close", 14))), tabs(),
    h("div", { class: "h3e-body" }, h("div", { class: "h3e-stage", style: { cursor: E.tab === "mask" ? "crosshair" : "default" } }, view),
      h("div", { class: "h3e-tools" }, ...tools, E.note ? h("span", { class: "h3c-hint", style: { color: "#F2C14E" } }, E.note) : null)));
  }
  render();
  loadImage(mediaURL(source, api)).then(async (loaded) => {
    picture = loaded;
    scale = Math.min(1, 860 / picture.width, 640 / picture.height);
    view.width = tint.width = Math.round(picture.width * scale); view.height = tint.height = Math.round(picture.height * scale);
    mask.width = picture.width; mask.height = picture.height;
    const m = mask.getContext("2d"); m.fillStyle = "#000"; m.fillRect(0, 0, mask.width, mask.height);
    const saved = contextOptions(card).edit_mask;
    if (saved) try { addMaskPicture(await loadImage(mediaURL(saved, api))); } catch { /* an old mask that is gone: start empty */ }
    draw();
  }).catch((error) => say(error.message));
}
