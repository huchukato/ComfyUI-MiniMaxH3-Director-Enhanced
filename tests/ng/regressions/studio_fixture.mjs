// No HTTP/provider/GPU calls: only the ComfyUI graph shape and a deferred /ng/direct response.
import { installDom } from "../js/fake_dom.mjs";
import { newShot, writeProject, readProject } from "../../../js/ng/h3s_model.js";
import { openStudio } from "../../../js/ng/h3s_studio.js";

export function fixture({ mode = "ref2va", locks = [], audio = false, project: initial = null } = {}) {
  const shot = { ...newShot(0, 10), id: "shot_a", text: "Original shot.", locked_fields: locks };
  const initialProject = initial || { shots: [shot], audio: [], lanes: [] };
  const settings = { idea: "Original idea.", project_seconds: 10, chunk_seconds: 10, shots: writeProject(initialProject),
    mode, width: 1344, height: 768, steps: 20, cfg: 1, seed: 1, sampler_name: "euler", scheduler: "simple", turbo: false,
    turbo_lora_fl2va: "none", turbo_lora_ref2va: "none", resize_method: "crop", ref_image_size: "match", soundscape: "", music: "", output: "video" };
  const widgets = (data) => Object.entries(data).map(([name, value]) => ({ name, value, options: { values: [value] } }));
  const node = { id: 1, comfyClass: "NGH3Director", properties: {}, widgets: widgets(settings), inputs: [{ name: "context", link: 1 }], outputs: [] };
  const connector = { id: 2, comfyClass: "NGContextConnector", widgets: [], inputs: [{ name: "ai_provider", link: 2 }], outputs: [] };
  const provider = { id: 3, comfyClass: "NGAIProvider", widgets: widgets({ source: "local", provider: "ollama", model: "fixture", base_url: "http://fixture.invalid", timeout_seconds: 120 }), inputs: [] };
  const sound = { id: 4, comfyClass: "NGContextAudio", widgets: widgets({ context_id: "sound_a", name: "Music", audio: "fixture.wav", usage: "reference" }), inputs: [] };
  const graph = { links: { 1: { origin_id: 2 }, 2: { origin_id: 3 }, 3: { origin_id: 4 } },
    getNodeById: (id) => [node, connector, provider, sound].find((entry) => entry.id === Number(id)), change() {} };
  for (const entry of [node, connector, provider, sound]) entry.graph = graph;
  if (audio) connector.inputs.push({ name: "contexts.0", link: 3 });
  let respond;
  const pending = new Promise((resolve) => { respond = resolve; });
  const requests = [];
  const api = { addEventListener() {}, removeEventListener() {}, async fetchApi(path, options) {
    requests.push({ path, payload: options?.body && JSON.parse(options.body) });
    if (path === "/ng/direct") return pending;
    return { json: async () => ({ ok: false, error: "No live plan in offline regression fixture." }) };
  } };
  const S = { node, values: { ...settings }, ...initialProject, suggestions: {}, ghosts: [], busy: "", notice: null };
  return { S, node, provider, sound, api, app: {}, requests,
    reply: (suggestion) => respond({ json: async () => ({ ok: true, suggestion }) }),
    setWidget(name, value) { node.widgets.find((widget) => widget.name === name).value = value; S.values[name] = value; } };
}

export function installStudioDom() {
  installDom();
  const prototype = Object.getPrototypeOf(document.body);
  prototype.querySelectorAll = function (selector) {
    const tags = selector.split(",").map((tag) => tag.trim().toUpperCase());
    return this.find((node) => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : tags.includes(node.tagName));
  };
  prototype.querySelector = function (selector) { return this.querySelectorAll(selector)[0] || null; };
  prototype.focus = function () { document.activeElement = this; };
  prototype.remove = function () { document.body.children = document.body.children.filter((child) => child !== this); };
  globalThis.window = {};
}

export const patch = (text = "AI proposal.") => ({ format: "h3-director-draft", schema_version: 1,
  patches: [{ shot_id: "shot_a", fields: { text } }] });

export function studio(t, options) {
  installStudioDom();
  const f = fixture(options), handle = openStudio(f.node, f.app, f.api);
  t.after(() => handle.close());
  const root = document.body.byClass("h3s")[0];
  const read = () => readProject(f.node.widgets.find((widget) => widget.name === "shots").value);
  const select = () => {
    const block = root.byClass("h3s-shot")[0];
    block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 100, pointerId: 1 });
    block.onpointerup();
  };
  const edit = (text) => {
    const input = root.byTag("textarea").find((field) => field.value === read().shots[0].text);
    if (!input) throw new Error("The selected shot has no text editor.");
    input.value = text; input.oninput({ target: input });
  };
  const acceptIfAvailable = () => { const button = root.button("Accept"); if (button && !button.disabled) button.onclick(); };
  return { ...f, root, read, select, edit, acceptIfAvailable, handle };
}
