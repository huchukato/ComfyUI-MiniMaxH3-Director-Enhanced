// The H3 Guide's Markdown: headings, lists, tables, pictures relative to the chapter, and nothing a chapter could inject.
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
globalThis.fetch = async () => ({ ok: false, json: async () => ({ chapters: [] }), text: async () => "" });
globalThis.window = { comfyAPI: { app: { app: { registerExtension() {} } } } };
const { render } = await import("../../../js/ng/h3g_guide.js");

const base = new URL("https://example.test/extensions/pack/guide/en/chapter.md");
const html = render([
  "# Title", "", "Some **bold** and *italic* and `code`.", "", "- one", "- two", "", "1. first", "2. second", "",
  "| A | B |", "|---|---|", "| x | y |", "", "> Note", "", "![Picture](../images/a.jpg)", "",
  "[site](https://huggingface.co/x) [bad](javascript:alert(1)) <script>alert(1)</script>",
].join("\n"), base);
assert.match(html, /<h1>Title<\/h1>/);
assert.match(html, /<b>bold<\/b> and <i>italic<\/i> and <code>code<\/code>/);
assert.match(html, /<ul>\n<li>one<\/li>\n<li>two<\/li>\n<\/ul>/);
assert.match(html, /<ol>\n<li>first<\/li>/);
assert.match(html, /<table><tr><th>A<\/th><th>B<\/th><\/tr><tr><td>x<\/td><td>y<\/td><\/tr><\/table>/);
assert.match(html, /<blockquote>Note<\/blockquote>/);
assert.match(html, /src="https:\/\/example\.test\/extensions\/pack\/guide\/images\/a\.jpg"/, "pictures resolve next to the chapter");
assert.match(html, /href="https:\/\/huggingface\.co\/x"/);
assert.match(html, /<a href="#"[^>]*>bad<\/a>/, "only http(s) links");
assert.ok(!html.includes("<script>"), "HTML in a chapter is shown as text");
assert.match(render("- a *long\n  item* goes on\n- next", base), /<li>a <i>long item<\/i> goes on<\/li>\n<li>next<\/li>/, "a wrapped item stays one item");
console.log("h3 guide: ok");
