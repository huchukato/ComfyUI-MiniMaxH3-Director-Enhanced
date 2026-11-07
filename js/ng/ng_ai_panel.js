// Each AI source has a real execution path; native sources use ComfyUI's queue and loaders.
import { draggedByUser } from "./ng_layout.js";
import { element, values, applyValues, request, nativeAIFingerprint, clearedAddress } from "./ng_widgets.js";
import { control, hideNative, section, actionButton, secretControl } from "./ng_editor_fields.js";
import { icon } from "./ng_icons.js";
import { upstreamNode } from "./ng_read.js";
import { accepts, fieldHelp, wantsKey, wireName } from "./ng_ai_capabilities.js";

const { app } = window.comfyAPI.app;
// The api handle is two destructure levels deep: window.comfyAPI.api.api.fetchApi. Every other module
// here takes it the same way (ng_panel.js, ng_cards.js). Guessing one level less gives "fetchApi is
// not a function", which fails quietly enough to look like a provider list with one entry in it.
const { api: fetch } = window.comfyAPI.api;


// The provider list, the source cards and every address come from the server's registry
// (/ng/providers). They used to be written out here as well, which is how the two drifted apart.
// A field typed in twice is a field that will be wrong in one of the two places.
//
// Until the registry answers, an empty panel is worse than one with a clear default, so the first
// paint uses this minimal shape and refreshes once the route returns.
const FALLBACK = {
  sources: [
    { id: "local", title: "Local", hint: "Load LLM / AI Model", icon: "monitor",
      providers: ["ollama"], key: false, address: "", note: "Runs on your own machine." },
    { id: "api", title: "API", hint: "Online provider", icon: "globe",
      providers: [], key: true, address: "", note: "Needs an API key." },
    { id: "clip", title: "CLIP / Encoder", hint: "Text Encoder only", icon: "paperclip",
      providers: [], key: false, address: "", note: "Connect Load CLIP." },
  ],
  providers: [],
};

let REGISTRY = FALLBACK;
const BY_ID = {};
let loaded = false;

async function loadRegistry() {
  try {
    const response = await fetch.fetchApi("/ng/providers");
    const data = await response.json();
    if (!Array.isArray(data.sources) || !data.sources.length || !Array.isArray(data.providers)) {
      console.warn("[NG] /ng/providers answered an unexpected shape; keeping the fallback", data);
      return;
    }
    REGISTRY = data;
    for (const entry of data.providers) BY_ID[entry.id] = entry;
    loaded = true;
  } catch (error) {
    // The panel still works with the fallback, but the reason is written to the console. A silent
    // catch here hid a real failure for a whole session: the panel quietly showed one provider
    // and there was no way to tell that it was a fallback rather than the truth.
    console.warn("[NG] the provider registry could not be loaded; using the built-in fallback", error);
  }
}

export function SOURCES() { return REGISTRY.sources; }
export function providerEntry(id) { return BY_ID[id] || null; }
export function registryLoaded() { return loaded; }

export function sourceOf(node) {
  const config = values(node);
  const cards = SOURCES();
  const found = cards.find((entry) => entry.id === config.source);
  return found || cards.find((entry) => entry.providers.includes(config.provider)) || cards[0];
}

function sourceCard(entry, onPick) {
  const button = element("button", "ng-source-card");
  button.type = "button";
  button.dataset.source = entry.id;
  button.title = `${entry.title} — ${entry.hint}`;
  const badge = icon(entry.icon, "ng-source-icon");
  const text = element("span", "ng-source-text");
  text.append(element("strong", "", entry.title), element("small", "", entry.hint));
  button.append(badge, text);
  button.onclick = () => onPick(entry);
  return button;
}

// A tile with no input, for a fact rather than a setting. A disabled checkbox would still be a
// control, and a control that cannot be moved is the thing this replaces. The tile has the same
// shape as the fields around it so the grid does not change height when the provider does.
function capabilityControl(labelText, iconName = "eye") {
  const label = element("div", "ng-field ng-field-tile ng-field-fact");
  const head = element("span", "ng-field-head");
  head.append(icon(iconName, "ng-field-icon"), element("span", "ng-field-label", labelText));
  const text = element("span", "ng-fact-text", "");
  label.append(head, text);
  return {
    label,
    // The name is the provider this describes, so a change of provider is visible in the tile itself
    // and not only in the dropdown above.
    set(text_) { text.textContent = text_; },
  };
}

export function buildPanel(node, root, header, widget) {
  // root is height:100%, so measuring it would feed the widget height back into itself and grow
  // without bound. Measure an auto-height wrapper instead.
  const body = element("div", "ng-panel-body");
  // The badge keeps its text for assistive tech and for the existing "Tested ..." updates; the
  // glyph next to it is decoration, so it changes state without touching the label.
  const status = element("span", "ng-ai-badge ng-status");
  const statusMark = icon("sparkle", "ng-status-mark");
  const statusText = element("span", "ng-status-text", "Not configured");
  status.append(statusMark, statusText);
  const setStatus = (text, tone) => { statusText.textContent = text; status.dataset.tone = tone || "idle"; };
  setStatus("Not configured", "idle");
  header.append(status);
  root.append(body);

  const sourceSection = section("1. Source", "", { icon: "link",
    help: "Where the AI runs. It only runs when you press an AI button (Analyze, Make H3 prompt, AI: split into shots, Write with AI)." });
  const cards = element("div", "ng-source-cards");
  const address = element("small", "ng-muted");
  const note = element("small", "ng-muted");
  sourceSection.append(cards, address, note);
  body.append(sourceSection);

  const identity = section("2. Provider / Model", "", { icon: "grid",
    help: "Which server answers and which model it serves." });
  const identityRow = element("div", "ng-row");
  const providerField = control(node, "provider", "Provider", { tile: true, icon: "globe" });
  const modelField = control(node, "model", "Model", { tile: true, icon: "file" });
  identityRow.append(providerField.label, modelField.label);
  // Asking a provider which models it serves costs a network call and needs a key, so it happens
  // only when the button is pressed - never while the panel is being drawn, and never on connect.
  const modelActions = element("div", "ng-field-actions");
  const modelList = element("datalist");
  modelList.id = `ng-models-${node.id ?? 0}`;
  modelField.field.setAttribute("list", modelList.id);
  const modelStatus = element("small", "ng-field-status");
  const loadModelsButton = actionButton("Load models", () => refreshModels(),
    { icon: "refresh", title: "Ask the provider which models it serves" });
  modelActions.append(loadModelsButton);
  modelField.label.append(modelActions, modelStatus, modelList);
  // The key never becomes a widget. A widget is written into every saved and exported workflow, so
  // the field posts to /ng/keys instead and the secret stays in ComfyUI's user folder.
  const keyTile = secretControl("API key", { icon: "key" });
  const providerNote = element("small", "ng-field-status");
  identity.append(identityRow, keyTile.label, providerNote);
  body.append(identity);

  // "Installed text encoder" and its loader type belong to the CLIP / Encoder card, not to a source
  // of their own: an installed encoder and a connected Load CLIP node reach Generate Text by the
  // same route. They appear only while no Load CLIP node is connected, so the panel never offers two
  // ways at once without saying which one is in use. There is no "Local source" switch any more -
  // what is actually present decides, which is why this section follows the card and not the header.
  const encoderSection = section("Encoder", "", { icon: "paperclip",
    help: "Used when no Load CLIP node is connected. It loads only during an explicit AI action." });
  const diskField = control(node, "local_model", "Installed text encoder", { tile: true, icon: "box" });
  const typeField = control(node, "local_type", "Encoder loader type", { tile: true, icon: "cpu" });
  const encoderRow = element("div", "ng-row");
  encoderRow.append(diskField.label, typeField.label);
  encoderSection.append(encoderRow);
  body.append(encoderSection);

  // What this provider reads is stated on the tile below, not offered as a switch - a capability is a
  // fact about the provider, and a switch that can only fail at request time is a promise the panel
  // cannot keep. Timeout and Max tokens are the two ordinary choices here.
  const settings = section("3. Settings", "", { icon: "gear",
    help: "What this provider can read is a fact, not a choice. Timeout and Max tokens bound one request." });
  // The statement sits where the two switches used to be, so the eye lands in the same place, and it
  // names what produced it. It only appears on the CLIP / Encoder card - on the HTTP cards the
  // registry answers this, and repeating it as a sentence the user cannot act on helps nobody.
  const capabilityRow = element("div", "ng-row");
  const capabilityTile = capabilityControl("Can read");
  capabilityRow.append(capabilityTile.label);
  // The two switches survive for CLIP / Encoder and only there. They are not a capability there
  // either: nothing knows what the connected model accepts, so these are the user's own statement and
  // are labelled as such. provider_payload() and _capability_error() both honour them for that card.
  const vision = control(node, "vision", "Vision \u00b7 reads images", { boolean: true, tile: true, icon: "eye" });
  const audio = control(node, "audio", "Audio \u00b7 reads sound", { boolean: true, tile: true, icon: "audio" });
  capabilityRow.append(vision.label, audio.label);
  const tuningRow = element("div", "ng-row");
  const timeout = control(node, "timeout_seconds", "Timeout \u00b7 seconds", { number: true, tile: true, icon: "clock" });
  const tokens = control(node, "max_tokens", "Max tokens", { number: true, tile: true, icon: "hash" });
  tuningRow.append(timeout.label, tokens.label);
  const seed = control(node, "seed", "Seed", { number: true, tile: true, icon: "hash" });
  const fixed = control(node, "fixed_seed", "Fixed seed", { boolean: true, tile: true, icon: "check" });
  const seedRow = element("div", "ng-row");
  // Seed and its switch belong to Settings, not to Advanced: they are ordinary choices. The
  // switch is what makes the number mean anything, so the two sit side by side.
  seedRow.append(seed.label, fixed.label);
  settings.append(capabilityRow, tuningRow, seedRow);
  body.append(settings);

  const advanced = element("details", "ng-advanced");
  const advancedHead = element("summary", "ng-advanced-head");
  advancedHead.append(icon("sliders", "ng-advanced-icon"),
    element("span", "ng-advanced-title", "ADVANCED"), element("span", "ng-advanced-note", "(optional)"),
    icon("chevron", "ng-advanced-chevron"));
  advanced.append(advancedHead);
  const urlField = control(node, "base_url", "Server / API base URL", { tile: true, icon: "globe" });
  const keepAlive = control(node, "keep_alive", "Keep model loaded \u00b7 seconds", { number: true, tile: true, icon: "clock" });
  const keyField = control(node, "api_key_env", "API key environment variable", { tile: true, icon: "key" });
  advanced.append(urlField.label, keepAlive.label, keyField.label);

  // The sampling fields live in Advanced and are shown from the registry, not from a list typed
  // here. A field the chosen provider does not accept is hidden rather than disabled: a greyed
  // control asks the user a question the panel cannot answer.
  const SAMPLING = [["temperature", "Temperature", 0.01], ["top_p", "Top P", 0.01],
                    ["top_k", "Top K", 1], ["min_p", "Min P", 0.01],
                    ["frequency_penalty", "Frequency penalty", 0.1],
                    ["presence_penalty", "Presence penalty", 0.1]];
  const samplingRow = element("div", "ng-row");
  const samplingFields = SAMPLING.map(([name, label, step]) => {
    const field = control(node, name, label, { number: true, tile: true, icon: "sliders", step });
    return [name, field];
  });
  samplingRow.append(...samplingFields.map(([, field]) => field.label));
  advanced.append(samplingRow);
  advanced.append(element("small", "ng-muted",
    "Connecting sends nothing. The AI only runs when you press one of its buttons."));
  body.append(advanced);

  // vision and audio are synced here rather than through the shared list: they belong to the CLIP
  // card alone, and a field that is synced but never appended to a section is one the user cannot
  // find - the silent-disappearance bug this panel has hit before.
  const fields = [providerField, modelField, timeout, tokens, seed, fixed, urlField,
                  keepAlive, keyField, ...samplingFields.map(([, field]) => field), diskField, typeField];
  // The fields the registry can explain. The provider and model tiles get their text separately,
  // because for those the interesting sentence is about the provider rather than about a setting.
  const HELPED = [timeout, tokens, seed, fixed, keepAlive, ...samplingFields.map(([, field]) => field)];
  const providerWidget = node.widgets?.find((entry) => entry.name === "provider");

  // The panel never receives a key back, not even partially, so every statement here is about
  // whether a key exists - never about what it is.
  let keyStates = {};
  // Which provider the current model list belongs to. A list is an answer from one server; carrying
  // it over to the next provider would offer model names that server has never heard of.
  let modelFor = null;

  async function readKeyStates() {
    try {
      const data = await request(fetch, "/ng/keys");
      keyStates = data.keys || {};
    } catch (error) {
      console.warn("[NG] stored keys could not be read", error);
      keyStates = {};
    }
    sync();
  }

  function applyKeyState() {
    const config = values(node);
    const entry = providerEntry(config.provider);
    // A provider that authenticates with nothing has no key to store, so the tile is not offered.
    if (!entry || entry.auth === "none") { keyTile.label.hidden = true; return; }
    keyTile.label.hidden = false;
    const stored = keyStates[config.provider];
    keyTile.setState(stored ? "stored" : "empty", stored
      ? `Stored in ComfyUI's user folder${stored.env ? ` · from ${stored.env}` : ""}`
      : "No key stored yet.");
  }

  async function saveKey() {
    const config = values(node);
    const secret = keyTile.field.value.trim();
    if (!secret) { keyTile.setState("warn", "Type the key first, then save it."); return; }
    try {
      await request(fetch, "/ng/keys", { provider: config.provider, key: secret, key_env: config.api_key_env || "" });
      // Emptied straight away: the panel must not hold on to a secret it can never show again.
      keyTile.clear();
      await readKeyStates();
      keyTile.setState("stored", "Saved. It stays on this machine and never enters a workflow.");
    } catch (error) {
      keyTile.setState("warn", error.message);
    }
  }

  async function clearKey() {
    const config = values(node);
    try {
      await request(fetch, "/ng/keys", { provider: config.provider, key: "" });
      await readKeyStates();
      keyTile.setState("empty", "Key removed from this machine.");
    } catch (error) {
      keyTile.setState("warn", error.message);
    }
  }
  keyTile.actions.append(
    actionButton("Save", saveKey, { className: "ng-action-primary", title: "Store the key for this provider" }),
    actionButton("Clear", clearKey, { title: "Remove the stored key for this provider" }));

  // Three answers, kept apart on purpose: "no models" is a failure, "466 models" is a success, and
  // "the key is untested" is neither. OpenRouter serves /v1/models to anyone, so a green tick after a
  // successful listing would claim something the request never proved.
  function modelReport(names, data) {
    if (!names.length) { modelStatus.dataset.state = "warn"; return data.reason || "The provider returned no models."; }
    const key = data.key_checked === true ? "key accepted" : data.key_checked === false ? "key untested" : "key not checked";
    modelStatus.dataset.state = data.key_checked === false ? "warn" : "ok";
    const typed = values(node).model;
    // A name the user typed by hand survives a listing that does not contain it. The list is a
    // suggestion, not a whitelist: a provider may serve a model it never advertises.
    return `${names.length} models · ${key}` + (typed && !names.includes(typed) ? ` · "${typed}" not listed` : "");
  }

  async function refreshModels() {
    const config = values(node);
    loadModelsButton.disabled = true;
    modelStatus.dataset.state = "";
    modelStatus.textContent = "Asking the provider…";
    try {
      const data = await request(fetch, "/ng/models",
        { provider: config.provider, base_url: config.base_url || "", key_env: config.api_key_env || "" });
      const names = Array.isArray(data.models) ? data.models : [];
      modelList.replaceChildren(...names.map((name) => { const option = element("option"); option.value = name; return option; }));
      modelStatus.textContent = modelReport(names, data);
    } catch (error) {
      modelStatus.dataset.state = "warn";
      modelStatus.textContent = error.message;
    } finally {
      loadModelsButton.disabled = false;
    }
  }

  // The dropdown must only offer what this source really supports, so a wrong provider cannot be
// picked and then fail at request time.
  function applyProviderChoices(providers) {
    if (!providerWidget) return;
    providerWidget.options = providerWidget.options || {};
    providerWidget.options.values = providers;
    if (!providers.includes(providerWidget.value) && providers.length) {
      providerWidget.value = providers[0];
      providerWidget.callback?.(providerWidget.value);
    }
    const select = providerField.field;
    if (select.tagName !== "SELECT") return;
    select.replaceChildren();
    for (const value of providers) {
      const option = element("option", "", value);
      option.value = value;
      select.append(option);
    }
    providerField.sync();
  }

  function sync() {
    const current = sourceOf(node);
    for (const entry of cards.children) entry.setAttribute("aria-pressed", String(entry.dataset.source === current.id));
    address.textContent = current.address;
    note.textContent = current.note;
    const config = values(node), native=current.id==="clip";
    identity.hidden = current.id==="clip";
    // With a Load CLIP node connected the installed encoder would never be read, so it is hidden
    // rather than shown as a second option that does nothing.
    const encoder=upstreamNode(node.graph,node.inputs?.find((input)=>input.name==="clip"));
    const showEncoder=native&&!encoder;
    encoderSection.hidden=!showEncoder;
    diskField.label.hidden=!showEncoder;
    typeField.label.hidden=!showEncoder||!config.local_model;
    identityRow.hidden=native;timeout.label.hidden=false;
    urlField.label.hidden=keepAlive.label.hidden=native;
    if(!native)applyProviderChoices(current.providers);
    const entry = providerEntry(config.provider);
    // Reuse the registry's own addresses, so the field shows the server that actually answers
    // instead of a blank box. A provider with no address of its own keeps the typed one.
    const hint = entry ? { url: entry.base_url || "", model: entry.sample_model || "" } : { url: "", model: "" };
    if (urlField.field.tagName === "INPUT") urlField.field.placeholder = hint.url;
    if (modelField.field.tagName === "INPUT") modelField.field.placeholder = hint.model;
    if (modelFor !== config.provider) {
      modelFor = config.provider;
      modelList.replaceChildren();
      modelStatus.textContent = "";
      modelStatus.dataset.state = "";
    }
    // A local server needs no key, so the row would only be one more thing to wonder about.
    keyField.label.hidden = native||!wantsKey(entry);
    applyKeyState();
    fields.forEach((field) => field.sync());
    vision.sync();
    audio.sync();
    // What the provider can read is stated, not offered. The two checkboxes stay on the CLIP card
    // only, because there the model is whatever the user connected and the registry knows nothing
    // about it - there they are a promise the user makes, which is the honest shape for an unknown
    // model. The stored provider id is deliberately NOT consulted on that card: it still holds
    // whichever HTTP provider was chosen before the switch, and reporting that one's abilities here
    // would describe a model that is not the one the request goes to.
    // The two switches are shown on the CLIP / Encoder card and nowhere else. On an HTTP card they
    // would be a second opinion about a fact the registry already states, and ticking one could only
    // disagree with the provider and be refused at request time.
    vision.label.hidden = audio.label.hidden = !native;
    capabilityTile.label.hidden = !native;
    capabilityTile.set(native
      ? "Set by the connected model · " +
        (vision.field.checked ? "image yes" : "image no") + " · " +
        (audio.field.checked ? "audio yes" : "audio no")
      : "");
    // The "?" texts come from the registry, so every field explains itself for the provider that is
    // actually chosen: Claude offers no seed and no top_p, and a provider may override the sentence
    // where the generic one would describe a control it does not have.
    for (const field of HELPED) field.setHelp(fieldHelp(entry, field.name));
    // The wire name goes under the field where it differs from the label. Ollama sends Max tokens
    // as num_predict and nests everything under "options", so a user reading their own request log
    // would otherwise not find the field they just set.
    const wireNote = (field, name) => {
      const wire = wireName(entry, name);
      let note = field.label.querySelector(".ng-wire-name");
      if (!entry || wire === name) { note?.remove(); return; }
      if (!note) { note = element("small", "ng-wire-name"); field.label.append(note); }
      note.textContent = `sent as ${wire}`;
    };
    for (const [name, field] of samplingFields) wireNote(field, name);
    wireNote(tokens, "max_tokens");
    wireNote(timeout, "timeout_seconds");
    providerField.setHelp(entry ? `${entry.label} · ${entry.verified_note}` : "");
    providerNote.dataset.state = entry && !entry.verified ? "warn" : "";
    providerNote.textContent = entry
      ? `${entry.label} · ${entry.verified ? "verified against a live server" : "not verified against a live server"}`
      : "";
    // Sampling fields follow the registry: a provider that does not accept one never shows it.
    // The panel is only the display; what actually goes out is decided by provider_payload().
    // While the registry is still loading the answer is "unknown", and unknown must not hide
    // anything: a field that turns out to be unsupported is a smaller problem than one the user
    // cannot find at all. That is why an absent entry means "show everything", not "show nothing".
    for (const [name, field] of samplingFields) field.label.hidden = native || !accepts(entry, name);
    seed.label.hidden = fixed.label.hidden = native || !accepts(entry, "seed");
    keepAlive.label.hidden = native || !accepts(entry, "keep_alive");
    samplingRow.hidden = samplingFields.every(([, field]) => field.label.hidden);
    // Each state gets a tone so the badge colour matches what it says: amber means it still needs
    // something from the user, green means a provider answered, slate means nothing has been set.
    if (current.id==="clip") {
      // One card, two ways in. The badge names which one is actually in use, because the panel
      // only offers the installed encoder when no Load CLIP node is connected.
      if (encoder) setStatus("CLIP connected \u00b7 not tested", "ready");
      else if (config.local_model) setStatus(config.local_model+" \u00b7 loads on action", "ready");
      else setStatus("Connect Load CLIP, or choose an encoder", "idle");
    }
    else if (!config.model) setStatus("Not configured", "idle");
    else if (config.provider === "custom" && !config.base_url) setStatus("Address needed", "warn");
    else setStatus("Configured \u00b7 not tested", "ready");
    const test=node.properties.ng_ai_test;
    if(native&&test?.fingerprint===nativeAIFingerprint(node))setStatus(`Tested · ${test.action} / ${test.media}`,"ready");
    node.setDirtyCanvas?.(true, true);
  }

  // The cards are rebuilt whenever the registry arrives, because a card drawn from the fallback has
  // the wrong provider list. Replacing them in place keeps the node's height from jumping twice.
  function paintCards() {
    cards.replaceChildren();
    for (const entry of SOURCES()) {
      cards.append(sourceCard(entry, (picked) => {
        // The CLIP card has no provider, so it must not overwrite a previously chosen one; a stale address is dropped.
        applyValues(node, { source: picked.id, ...(picked.providers[0] ? { provider: picked.providers[0] } : {}), ...clearedAddress(values(node).base_url) });
        sync();
        fit(true);
        app.graph?.change();
      }));
    }
    sync();
  }

  paintCards();
  // Which providers hold a key is read once when the panel opens, so the tile can say so before the
  // user types anything. It answers only "is there one", never what it is.
  readKeyStates();
  if (!registryLoaded()) {
    loadRegistry().then(() => { if (registryLoaded()) { paintCards(); fit(true); } });
  }

  hideNative(node, ["source", "provider", "base_url", "model", "api_key_env", "vision", "audio",
                     "timeout_seconds", "max_tokens", "keep_alive", "temperature", "top_p", "top_k",
                     "min_p", "frequency_penalty", "presence_penalty", "seed", "fixed_seed",
                     "local_model", "local_type"]);

  // Below this width the three source tiles and the provider / model pair no longer fit: at 210 the Model field was cut
  // off with a scrollbar under it (GUI test 2026-10-19). The Context cards and the Director snap back to theirs the same way.
  const MIN_HEIGHT = 240, MIN_WIDTH = 440;
  function panelHeight() {
    const content=Array.from(body.children).filter((child)=>!child.hidden).reduce((height,child)=>{
      const style=getComputedStyle(child);
      return height+child.offsetHeight+(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0);
    },0);
    return Math.max(MIN_HEIGHT,Math.ceil(content+header.offsetHeight)+32);
  }
  // The Loader is as tall as its panel, like the Context cards: nothing in it can use more height, and a taller node only
  // showed an empty area under the panel (user 2026-10-19: "wrong sizes, height and width").
  widget.computeSize = undefined;
  widget.computeLayoutSize = () => ({ minHeight: panelHeight(), maxHeight: panelHeight(), minWidth: MIN_WIDTH - 20 });
  // Grow when the content needs room, but only shrink when the panel itself changed shape. Shrinking
  // unconditionally would fight the user's drag and snap the node back while they resize it.
  function fit(allowShrink = false) {
    const width = Math.max(node.size[0], MIN_WIDTH), wanted = panelHeight();
    if (width !== node.size[0] || wanted > node.size[1] || (allowShrink && wanted < node.size[1] - 2)) node.setSize([width, Math.max(wanted, allowShrink ? 0 : node.size[1])]);
    node.setDirtyCanvas?.(true, true);
  }
  advanced.addEventListener("toggle", () => fit(true));
  // After a drag the node goes back to the panel's height; during it, it follows the pointer.
  let settling = 0;
  const resized = node.onResize; node.onResize = function (...args) { const result = resized?.apply(this, args);
    clearTimeout(settling); settling = setTimeout(() => fit(true), draggedByUser(node) ? 200 : 0); return result; };
  const observer=new ResizeObserver(() => fit());observer.observe(body);
  const changed=node.onConnectionsChange;node.onConnectionsChange=function(...args){const result=changed?.apply(this,args);queueMicrotask(sync);return result;};
  const tested=()=>sync();document.addEventListener("ng-ai-tested",tested);
  sync();
  fit(true);
  return { sync, fit, dispose(){observer.disconnect();document.removeEventListener("ng-ai-tested",tested);} };
}
