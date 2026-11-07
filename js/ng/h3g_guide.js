// H3 Guide: the guide's chapters (js/guide, Markdown + pictures) read inside the graph. The node only shows them: it is
// virtual, so it never reaches the server when a workflow runs, and the chosen chapter is saved in its "chapter" widget.
import { followNodeWidth } from "./ng_widgets.js";
import { hideNative } from "./ng_editor_fields.js";

const { app } = window.comfyAPI.app;
const BASE = new URL("../guide/", import.meta.url);
const index = fetch(new URL("guide.json", BASE)).then((r) => r.json()).catch(() => ({ chapters: [] }));
const texts = new Map();

const CSS = `
.h3g{box-sizing:border-box;width:100%;height:100%;display:flex;flex-direction:column;gap:8px;color:#E6EAF2;font:14px/1.55 "IBM Plex Sans","Segoe UI",system-ui,sans-serif}
.h3g *{box-sizing:border-box}
.h3g-bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.h3g-bar select{flex:1 1 220px;min-height:32px;background:#0E1117;border:1px solid #2E3848;border-radius:8px;color:#E6EAF2;padding:0 8px;font:inherit}
.h3g-btn{min-height:32px;padding:0 12px;border-radius:8px;border:1px solid #344055;background:#1E2633;color:#E6EAF2;cursor:pointer;font:13px "IBM Plex Sans","Segoe UI",sans-serif}
.h3g-btn:hover{background:#273142}
.h3g-page{flex:1 1 auto;min-height:0;overflow:auto;background:#121720;border:1px solid #262E3B;border-radius:10px;padding:14px 18px;user-select:text}
.h3g-page h1{font-size:22px;margin:0 0 10px}.h3g-page h2{font-size:17px;margin:18px 0 6px;color:#CFE1FF}.h3g-page h3{font-size:15px;margin:14px 0 4px}
.h3g-page p{margin:6px 0}.h3g-page ul,.h3g-page ol{margin:6px 0;padding-left:22px}.h3g-page li{margin:3px 0}
.h3g-page code{background:#0B0E13;border:1px solid #262E3B;border-radius:5px;padding:0 4px;font:12.5px Consolas,monospace}
.h3g-page img{display:block;max-width:100%;margin:10px 0;border-radius:8px;border:1px solid #2E3848;cursor:zoom-in}
.h3g-page a{color:#8FC1FF}
.h3g-page blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid #E0A33E;background:#1E1A12;border-radius:0 8px 8px 0}
.h3g-page table{border-collapse:collapse;margin:8px 0}.h3g-page td,.h3g-page th{border:1px solid #2E3848;padding:4px 8px;text-align:left;vertical-align:top}
.h3g-page th{background:#1A2130}
.h3g-over{position:fixed;inset:0;z-index:10000;background:rgba(5,8,12,.82);display:flex;align-items:center;justify-content:center;padding:28px}
.h3g-over .h3g{width:min(1100px,96vw);height:92vh;background:#0B0E13;border:1px solid #2E3848;border-radius:14px;padding:14px}
.h3g-over img.h3g-big{max-width:96vw;max-height:94vh;border-radius:8px;cursor:zoom-out}
`;

function style() {
  if (document.getElementById("h3g-style")) return;
  const tag = document.createElement("style");
  tag.id = "h3g-style";
  tag.textContent = CSS;
  document.head.append(tag);
}

const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Inline Markdown: code, pictures, links, bold, italic. Text is escaped first, so a chapter can never inject HTML.
function inline(text, base) {
  const codes = [];
  let out = escape(text).replace(/`([^`]+)`/g, (_, code) => `\u0000${codes.push(code) - 1}\u0000`);
  out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => `<img alt="${alt}" src="${new URL(src, base)}">`)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
      const url = new URL(href, base);
      const safe = /^https?:$/.test(url.protocol) ? url.href : "#";
      return `<a href="${safe}" target="_blank" rel="noopener">${label}</a>`;
    })
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>");
  return out.replace(/\u0000(\d+)\u0000/g, (_, n) => `<code>${codes[Number(n)]}</code>`);
}

// Block Markdown as the chapters use it: headings, paragraphs, lists, quotes, tables and pictures on their own line.
export function render(markdown, base) {
  const html = [];
  let list = null, paragraph = [];
  const flush = () => {
    if (paragraph.length) html.push(`<p>${inline(paragraph.join(" "), base)}</p>`);
    paragraph = [];
  };
  const close = () => { if (list) { html.push(`</${list}>`); list = null; } };
  const lines = markdown.replace(/\r/g, "").split("\n");
  for (let n = 0; n < lines.length; n += 1) {
    const line = lines[n];
    const heading = /^(#{1,3})\s+(.*)$/.exec(line), item = /^\s*([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (!line.trim()) { flush(); close(); continue; }
    if (heading) { flush(); close(); html.push(`<h${heading[1].length}>${inline(heading[2], base)}</h${heading[1].length}>`); continue; }
    if (line.startsWith(">")) { flush(); close(); html.push(`<blockquote>${inline(line.replace(/^>\s?/, ""), base)}</blockquote>`); continue; }
    if (line.startsWith("|")) {
      flush(); close();
      const rows = [];
      for (; n < lines.length && lines[n].startsWith("|"); n += 1) rows.push(lines[n]);
      n -= 1;
      const cells = (row) => row.replace(/^\||\|$/g, "").split("|").map((cell) => inline(cell.trim(), base));
      const body = rows.filter((row) => !/^\|[\s:|-]+\|$/.test(row));
      html.push(`<table><tr>${cells(body[0]).map((c) => `<th>${c}</th>`).join("")}</tr>${body.slice(1)
        .map((row) => `<tr>${cells(row).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</table>`);
      continue;
    }
    if (item) {
      flush();
      const kind = /\d/.test(item[1]) ? "ol" : "ul";
      if (list !== kind) { close(); html.push(`<${kind}>`); list = kind; }
      // an item wrapped onto indented lines stays one item
      const text = [item[2]];
      for (; n + 1 < lines.length && /^\s+\S/.test(lines[n + 1]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[n + 1]); n += 1) text.push(lines[n + 1].trim());
      html.push(`<li>${inline(text.join(" "), base)}</li>`);
      continue;
    }
    close();
    paragraph.push(line.trim());
  }
  flush(); close();
  return html.join("\n");
}

async function chapterText(chapter) {
  if (!texts.has(chapter.file)) texts.set(chapter.file, fetch(new URL(chapter.file, BASE)).then((r) => (r.ok ? r.text() : `# ${chapter.title}\n\nThis chapter could not be loaded.`)));
  return texts.get(chapter.file);
}

function zoom(src) {
  const over = document.createElement("div");
  over.className = "h3g-over";
  const big = document.createElement("img");
  big.className = "h3g-big";
  big.src = src;
  over.append(big);
  over.onclick = () => over.remove();
  document.body.append(over);
}

// One guide view: chapter list, back / next, the page. Used in the node and in the large window.
function view(widget, onLarge) {
  const root = document.createElement("div");
  root.className = "h3g";
  const select = document.createElement("select"), back = document.createElement("button"), next = document.createElement("button");
  const page = document.createElement("div");
  page.className = "h3g-page";
  back.className = next.className = "h3g-btn";
  back.textContent = "‹ Back"; next.textContent = "Next ›";
  const bar = document.createElement("div");
  bar.className = "h3g-bar";
  bar.append(select, back, next);
  if (onLarge) {
    const large = document.createElement("button");
    large.className = "h3g-btn";
    large.textContent = "Open large";
    large.onclick = onLarge;
    bar.append(large);
  }
  root.append(bar, page);
  page.addEventListener("click", (event) => { if (event.target.tagName === "IMG") zoom(event.target.src); });
  // the page scrolls itself; the canvas must not take the wheel or a drag that selects text
  for (const name of ["wheel", "pointerdown"]) page.addEventListener(name, (event) => event.stopPropagation());
  const show = async () => {
    const { chapters } = await index;
    if (!select.options.length) select.append(...chapters.map((c) => new Option(c.title, c.id)));
    const at = Math.max(0, chapters.findIndex((c) => c.id === widget.value));
    select.value = chapters[at]?.id ?? "";
    back.disabled = at === 0; next.disabled = at >= chapters.length - 1;
    const chapter = chapters[at];
    if (chapter) { page.innerHTML = render(await chapterText(chapter), new URL(chapter.file, BASE)); page.scrollTop = 0; }
  };
  const go = async (step) => {
    const { chapters } = await index;
    const at = chapters.findIndex((c) => c.id === widget.value) + step;
    if (chapters[at]) { widget.value = chapters[at].id; widget.callback?.(widget.value); show(); }
  };
  select.onchange = () => { widget.value = select.value; widget.callback?.(widget.value); show(); };
  back.onclick = () => go(-1);
  next.onclick = () => go(1);
  root.show = show;
  return root;
}

function attach(node) {
  style();
  const chapter = node.widgets?.find((w) => w.name === "chapter");
  if (!chapter) return;
  hideNative(node, ["chapter"]);
  const inner = view(chapter, () => {
    const over = document.createElement("div");
    over.className = "h3g-over";
    const large = view(chapter, null);
    const close = document.createElement("button");
    close.className = "h3g-btn";
    close.textContent = "Close";
    close.onclick = () => { over.remove(); inner.show(); };
    large.querySelector(".h3g-bar").append(close);
    over.append(large);
    over.onclick = (event) => { if (event.target === over) close.onclick(); };
    document.body.append(over);
    large.show();
  });
  // The page scrolls inside a fixed height that follows the node: with ComfyUI's Vue nodes the widget otherwise took the
  // whole chapter's height (a node 11,000 px tall, user 2026-10-25).
  // (the Vue node gives its widgets flex: 1 with an automatic minimum height, which outweighs a plain height)
  const fit = () => { inner.style.flex = "none"; inner.style.height = Math.max(300, (node.size?.[1] ?? 900) - 70) + "px"; };
  followNodeWidth(node.addDOMWidget("h3_guide", "h3_guide", inner, { serialize: false, hideOnZoom: false,
    getMinHeight: () => 300 }));
  const configure = node.onConfigure, resized = node.onResize;
  node.onConfigure = function (...args) { const out = configure?.apply(this, args); fit(); inner.show(); return out; };
  node.onResize = function (...args) { const out = resized?.apply(this, args); fit(); return out; };
  if ((node.size?.[0] ?? 0) < 620) node.size = [620, 760];
  fit();
  inner.show();
}

app.registerExtension({
  name: "mmxd.ng.guide",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "NGGuide") return;
    nodeType.prototype.isVirtualNode = true;      // never part of a queued prompt
  },
  nodeCreated(node) {
    if (node.comfyClass === "NGGuide") attach(node);
  },
});
