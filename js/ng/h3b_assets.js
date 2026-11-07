// The Storyboard's own pictures made with Qwen Image 2.1: a figure from a character sheet in the pose and camera angle the
// user writes, on a transparent background, and an empty background in the panel's format. Each goes onto the panel and into
// the board's library, from which every panel can take it again (as can every picture already on a panel).
import { h, icon, field, select } from "./h3s_dom.js";
import { ASPECTS, newLayer, newId, srcUrl, figurePrompt, backgroundPrompt, makeSize, libraryItems } from "./h3b_model.js";
import { comboOptions, runJob, qwenSetup, qwenGraph } from "./h3b_queue.js";

const FORMATS = { portrait: [768, 1344], square: [1024, 1024], landscape: [1344, 768] };
const same = (a, b) => String(a || "").replace(/\\/g, "/") === String(b || "").replace(/\\/g, "/");

function natural(src) {
  return new Promise((resolve) => { const i = new Image(); i.onload = () => resolve([i.naturalWidth, i.naturalHeight]); i.onerror = () => resolve(null); i.src = srcUrl(src); });
}

export function boardAssets({ S, api, change, render, contexts, chosenModels }) {
  // Panel-relative size of a new layer: a figure as large as fits, a background covering the panel.
  async function place(src, name, kind) {
    const size = await natural(src);
    const [aw, ah] = ASPECTS[S.board.aspect], ratio = size ? size[0] / size[1] : 1;
    const background = kind === "background";
    change((board) => {
      const made = newLayer("image", { src, name, scale: background ? Math.max(1, (ah / aw) * ratio) : Math.min(0.6, 0.9 * (ah / aw) * ratio),
        y: background ? 0.5 : 0.55 });
      const layers = board.panels[S.selected].layers;
      if (background) layers.unshift(made); else layers.push(made);
      S.layer = made.id;
    });
  }

  async function make(kind) {
    const card = contexts().find((entry) => entry.widgets.name === S.makeCard);
    if (kind === "figure" && !card) { S.notice = { text: "Choose the character card to draw the figure from.", error: true }; render(); return; }
    if (kind === "background" && !String(S.makePlace || "").trim()) { S.notice = { text: "Describe the place first.", error: true }; render(); return; }
    S.busy = kind; S.notice = { text: `Qwen Image 2.1 is drawing the ${kind}…`, error: false }; render();
    try {
      const setup = await qwenSetup(api, chosenModels());
      let src, name;
      if (kind === "figure") {
        const file = String(card.widgets.image).replace(/ \[input\]$/, "");
        if (!(await comboOptions(api, "NGContextImage", "image")).some((n) => same(n, file))) throw new Error(`${file} is not in the input folder.`);
        name = `${card.widgets.name}: ${String(S.makePose || "standing").trim().slice(0, 40)}`;
        src = await runJob(api, qwenGraph(setup, { images: [file], prompt: figurePrompt(card.widgets.name, S.makePose), size: FORMATS[S.makeFormat || "portrait"],
          prefix: "figure" }), "s");
      } else {
        name = `Background: ${String(S.makePlace).trim().slice(0, 40)}`;
        src = await runJob(api, qwenGraph(setup, { prompt: backgroundPrompt(S.makePlace), size: makeSize(S.board.aspect), prefix: "background", opaque: true }), "s");
      }
      change((board) => { board.library = [...(board.library || []), { id: newId("a"), name, kind, src }]; }, { undoable: false });
      await place(src, name, kind);
      S.notice = { text: `The ${kind} is on panel ${S.selected + 1} and in this storyboard's pictures for every panel ("+ Picture").`, error: false };
    } catch (error) {
      S.notice = { text: `Qwen Image 2.1 failed: ${error.message}`, error: true };
    } finally { S.busy = ""; render(); }
  }

  // The two buttons and, when one is open, its form.
  function maker() {
    const cards = contexts().filter((entry) => entry.media === "image" && entry.widgets.image && entry.widgets.name
      && !/storyboard|first_frame|last_frame|keyframe/.test(`${entry.widgets.usage} ${entry.widgets.usage_roles || ""}`));
    if (!S.makeCard && cards.length) S.makeCard = cards[0].widgets.name;
    const toggle = (kind) => () => { S.make = S.make === kind ? null : kind; render(); };
    const input = (key, placeholder) => h("textarea", { class: "h3s-in", rows: 2, value: S[key] || "", placeholder, oninput: (e) => { S[key] = e.target.value; } });
    const form = S.make === "figure" ? h("div", { class: "h3b-picker" },
      cards.length ? field("Character card", select(cards.map((c) => [c.widgets.name, c.widgets.name]), S.makeCard, (v) => { S.makeCard = v; }))
        : h("span", { class: "h3s-warn" }, "Connect character cards (Context Image) to the Context Connector on H3 context."),
      field("Pose and camera angle", input("makePose", "e.g. standing in a three-quarter view from the left, raising her staff, looking over her shoulder")),
      h("div", { class: "h3s-row" },
        field("Format", select([["portrait", "Portrait 768 × 1344"], ["square", "Square 1024"], ["landscape", "Landscape 1344 × 768"]], S.makeFormat || "portrait",
          (v) => { S.makeFormat = v; })),
        h("button", { class: "h3s-btn ai", disabled: Boolean(S.busy) || !cards.length, onclick: () => make("figure") }, icon("spark", 14),
          S.busy === "figure" ? "Drawing…" : "Create figure (about 30 s)")))
      : S.make === "background" ? h("div", { class: "h3b-picker" },
        field("Place, light and mood", input("makePlace", "e.g. a candle-lit gothic hall at night with tall stone arches and a polished marble floor")),
        h("button", { class: "h3s-btn ai", disabled: Boolean(S.busy), onclick: () => make("background") }, icon("spark", 14),
          S.busy === "background" ? "Drawing…" : `Create background (${makeSize(S.board.aspect).join(" × ")}, about 20 s)`))
      : null;
    return [h("div", { class: "h3s-row" }, h("span", { class: "h3s-lbl" }, "Qwen Image 2.1:"),
      h("button", { class: S.make === "figure" ? "h3s-btn small ai" : "h3s-btn small", onclick: toggle("figure"),
        title: "A character card's figure in the pose you describe, without background" }, "+ Figure from a sheet"),
      h("button", { class: S.make === "background" ? "h3s-btn small ai" : "h3s-btn small", onclick: toggle("background"),
        title: "An empty background in the panel's format" }, "+ Background")), form];
  }

  // This storyboard's pictures in the "+ Picture" chooser: a click puts one on the selected panel.
  function shelf(onpick) {
    const items = libraryItems(S.board);
    if (!items.length) return null;
    return [h("div", { class: "h3s-lbl" }, "From this storyboard"),
      h("div", { class: "h3b-thumbs" }, items.map((item) => h("button", { class: "h3b-thumb", title: item.name, onclick: () => onpick(item) },
        h("img", { src: srcUrl(item.src), alt: "" }), h("span", {}, item.name || item.src.filename))))];
  }

  return { maker, shelf, place };
}
