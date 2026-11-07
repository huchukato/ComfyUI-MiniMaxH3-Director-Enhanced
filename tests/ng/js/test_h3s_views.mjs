// Studio views on a minimal DOM: what they show for a given state and which actions the mouse triggers.
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const { timelineView } = await import("../../../js/ng/h3s_timeline.js");
const { sideView } = await import("../../../js/ng/h3s_side.js");
const { footerView } = await import("../../../js/ng/h3s_footer.js");
const { settingsView, manualPromptAlert } = await import("../../../js/ng/h3s_settings.js");
const { drawerView } = await import("../../../js/ng/h3s_prompts.js");
const { contentView, promptView, contentEntries } = await import("../../../js/ng/h3s_content.js");
const { issueLine } = await import("../../../js/ng/h3s_issues.js");

const shot = (id, start, end, text = id, media = []) => ({ id, start, end, text, media, spoken: [], locked_fields: [], draft: null });
const contexts = contentEntries([
  { media: "image", widgets: { context_id: "mage", name: "Mage", image: "mage.png", usage: "reference" } },
  { media: "video", widgets: { context_id: "move", name: "Move", video: "move.mp4", usage: "motion" } },
  { media: "audio", widgets: { context_id: "song", name: "Song", audio: "song.wav", usage: "music_style" } },
], (entry) => ({ image: "#6AA6F8", video: "#E6BE57", audio: "#B38CF5" }[entry.media]));
const plan = { width: 1344, height: 768, total_s: 20, total_frames: 480, mode: "ref2va", issues: [{ code: "shot_gap", text: "there is a gap.", ref: "shot 2" }],
  chunks: [{ index: 0, start_s: 0, end_s: 10, delivered_frames: 240, head_frames: 0, mode: "ref2va", prompt: "first prompt", refs: [{ kind: "picture", ctx_id: "mage" }], shots: [{ shot_id: "a" }] },
    { index: 1, start_s: 10, end_s: 20, delivered_frames: 240, head_frames: 22, mode: "ref2va", prompt: "second prompt", refs: [], shots: [{ shot_id: "a" }, { shot_id: "b" }] }] };

function state(extra = {}) {
  const values = { idea: "A walk.", project_seconds: 20, chunk_seconds: 0, width: 1344, height: 768, mode: "ref2va", turbo: false, steps: 20, seed: 1,
    sampler_name: "res_multistep", scheduler: "simple", turbo_lora_fl2va: "fl.safetensors", turbo_lora_ref2va: "none", resize_method: "crop",
    ref_image_size: "match", continuity: "video_audio", pin_frames: "22", style: "None", shift_video: 12, shift_audio: 3, ...extra.values };
  return { values, duration: values.project_seconds, options: { sampler_name: ["euler", "res_multistep"], scheduler: ["simple"],
    turbo_lora_fl2va: ["none", "fl.safetensors"], turbo_lora_ref2va: ["none", "ref.safetensors"] },
    contexts, byId: new Map(contexts.map((entry) => [entry.id, entry])), shots: [shot("a", 0, 8, "Walks in.", [{ schema_version: 1, context_id: "mage", role: "context" }]), shot("b", 8, 20)],
    audio: [{ schema_version: 1, id: "c1", context_id: "song", start: 4, end: 18, offset: 10, mode: "lock", lane: "l1" }], lanes: ["l1", "l2"],
    selected: null, ghosts: [], suggestions: {}, plan, ai: false, busy: "", promptOpen: false, sizeOpen: false, furtherOpen: false, selectedRange: null,
    lengths: new Map(), ...extra };
}
function recorder() {
  const calls = [];
  const actions = new Proxy({}, { get: (_t, name) => name === "shotLabel" ? (id) => ({ a: "Shot 1", b: "Shot 2" }[id] || "Shot")
    : name === "thumb" ? () => "" : name === "takeDragged" ? () => "song" : (...args) => { calls.push([name, ...args]); } });
  return { actions, calls };
}

// Timeline: shots, lanes, parts with their colours and the clip's mode.
{
  const { actions, calls } = recorder();
  const view = timelineView(state(), actions);
  assert.deepEqual(view.byClass("h3s-shot").map((node) => node.style.left), ["0%", "40%"]);
  assert.equal(view.byClass("h3s-clip")[0].innerText.includes("locked · 4–18 s"), true);
  const parts = view.byClass("h3s-part");
  assert.deepEqual(parts.map((node) => node.style.borderColor), ["#4FB8C4", "#E58A5C"], "each render part has its own colour");
  assert.equal(parts[0].title, "Part 1: 240 new frames");
  assert.equal(parts[1].title, "Part 2: 240 new frames, with 22 preceding frames for continuity");
  const external = timelineView(state({ plan: { ...plan, chunks: [{ ...plan.chunks[0], head_frames: 90, delivered_frames: 102 }] } }), actions);
  assert.equal(external.byClass("h3s-part")[0].title, "Part 1: 102 new frames, with 90 preceding frames for continuity");
  assert.ok(view.innerText.includes("Audio 2"), "an empty lane is shown");
  // Drag shot b over shot a: the drop reorders.
  const block = view.byClass("h3s-shot")[1];
  block.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: block, clientX: 500, pointerId: 1 });
  block.onpointermove({ clientX: 50 });
  block.onpointerup();
  const set = calls.find(([name]) => name === "setShots");
  assert.ok(set, "a drag writes the shots once, on release");
  assert.deepEqual(set[1].map((s) => [s.id, s.start, s.end]).sort((x, y) => x[1] - y[1]), [["b", 0, 12], ["a", 12, 20]]);
  assert.deepEqual(calls.filter(([name]) => ["beginPointer", "endPointer"].includes(name)).map(([name]) => name), ["beginPointer", "endPointer"]);
  // A click without moving selects.
  const fresh = recorder(), again = timelineView(state(), fresh.actions), first = again.byClass("h3s-shot")[0];
  first.onpointerdown({ stopPropagation() {}, preventDefault() {}, currentTarget: first, clientX: 100, pointerId: 1 });
  first.onpointerup();
  assert.deepEqual(fresh.calls.find(([name]) => name === "select"), ["select", "shot", "a"]);
}

// Lane source choices only offer media the track can execute.
{
  const guide = { id: "pose", name: "Pose guide", media: "video", usage: ["control"] };
  const S = state({ contexts: [...contexts, guide], control: [{ id: "guide_1", context_id: "pose", start: 0, end: 4, offset: 1 }] });
  const { actions, calls } = recorder(), view = timelineView(S, actions);
  const picker = view.byTag("select").find((el) => el.getAttribute("aria-label") === "Add control clip to Control");
  assert.deepEqual(picker.children.map((option) => option.value), ["", "pose"], "motion video cards are not control sources");
  picker.onchange({ target: { value: "pose" } });
  assert.deepEqual(calls.at(-1), ["newControl", 4, "pose"]);
}

// Ghost suggestions say what Accept does.
{
  const view = timelineView(state({ ghosts: [{ start: 0, end: 20, text: "One take." }] }), recorder().actions);
  assert.ok(view.byClass("h3s-banner")[0].innerText.includes("Accept replaces your 2 shots; audio lanes stay."));
  assert.ok(view.byClass("h3s-track")[0].classList.contains("ghosting"));
}

// Side: mode, turbo LoRA per mode, shot panel, clip panel restricted in FL2VA.
{
  const { actions, calls } = recorder();
  let [mode, panel] = sideView(state({ values: { turbo: true, mode: "fl2va" } }), actions);
  assert.equal(mode.byTag("select").length, 0, "the page keeps only Mode and Turbo on/off; the LoRA is in Settings");
  assert.ok(mode.innerText.includes("Turbo on"));
  const gear = settingsView(state({ settingsOpen: true, values: { turbo: true, mode: "fl2va" } }), actions);
  assert.ok(gear.innerText.includes("Turbo LoRA first / last frame") && !gear.innerText.includes("Turbo LoRA references"),
    "First/last frame shows only its own turbo LoRA");
  assert.equal(settingsView(state({ settingsOpen: false }), actions), null);
  // Turbo without a LoRA says so on the page and opens Settings.
  const [noLora] = sideView(state({ values: { turbo: true, mode: "ref2va", turbo_lora_ref2va: "none" } }), actions);
  assert.ok(noLora.innerText.includes("Turbo needs a turbo LoRA."), noLora.innerText);
  noLora.button("Choose").onclick();
  assert.deepEqual(calls.at(-1), ["toggle", "settingsOpen"]);
  // A manual prompt is shown on the page and can be cleared there.
  assert.equal(manualPromptAlert(state(), actions), null);
  const alert = manualPromptAlert(state({ values: { prompt_override: "my own prompt" } }), actions);
  assert.ok(alert.innerText.includes("Manual prompt is on"));
  alert.button("Clear").onclick();
  assert.deepEqual(calls.at(-1), ["setWidget", "prompt_override", ""]);
  mode.button("References").onclick();
  assert.deepEqual(calls.at(-1), ["setWidget", "mode", "ref2va"]);
  // A video or sound reference is not used in FL2VA: the mode says so, not only the drawer (pictures are used since 2026-10-12).
  const ignored = { ...plan, issues: [{ code: "reference_disabled", text: "Is omitted by explicit fl2va mode.", ref: "Mage" }] };
  [mode] = sideView(state({ plan: ignored, values: { mode: "fl2va" } }), actions);
  assert.ok(mode.innerText.includes("Mage is a video or sound reference, which First / last frame mode does not use"), mode.innerText);
  [, panel] = sideView(state({ selected: { kind: "clip", id: "c1" }, values: { mode: "fl2va" } }), actions);
  assert.ok(panel.innerText.includes("Story 4–10 s → plays file 10–16 s"));
  assert.ok(panel.innerText.includes("H3 can only lock sound"));
  assert.equal(panel.byTag("select")[0].children.length, 1, "FL2VA offers only lock for a lane clip");
  [, panel] = sideView(state({ selected: { kind: "shot", id: "a" } }), actions);
  assert.ok(panel.innerText.includes("In: Render part 1, Render part 2"));
  assert.ok(panel.innerText.includes("Mage"));
  assert.equal(panel.button("AI: improve text").disabled, true, "no AI suggestion without a loader");
  // Effect: the official embeddings found on the server; none found and none chosen, no field
  const effectOf = (node) => node.byTag("select").find((one) => one.getAttribute("aria-label") === "Effect of this shot");
  assert.equal(effectOf(panel), undefined);
  let [, fx] = sideView({ ...state({ selected: { kind: "shot", id: "a" } }), effects: ["minimaxh3_bullet_time"] }, actions);
  assert.deepEqual(effectOf(fx).children.map((option) => option.innerText), ["None", "Bullet time"]);
  effectOf(fx).onchange({ target: { value: "minimaxh3_bullet_time" } });
  assert.deepEqual(calls.at(-1), ["setShot", "a", { effect: "minimaxh3_bullet_time" }]);
  effectOf(fx).onchange({ target: { value: "" } });
  assert.deepEqual(calls.at(-1), ["setShot", "a", { effect: undefined }]);
  // "Place like Shot N" (core/places.py): only a later shot offers it, and only earlier shots as its source.
  const placeOf = (node) => node.byTag("select").find((one) => one.getAttribute("aria-label") === "Place of this shot");
  assert.equal(placeOf(panel), undefined, "the first shot has no earlier place");
  [, panel] = sideView(state({ selected: { kind: "shot", id: "b" } }), actions);
  const place = placeOf(panel);
  assert.deepEqual(place.children.map((option) => option.innerText), ["Its own place", "Like Shot 1"]);
  place.onchange({ target: { value: "a" } });
  assert.deepEqual(calls.at(-1), ["setShot", "b", { place_from: "a" }]);
  assert.equal(panel.byTag("select").find((one) => one.getAttribute("aria-label") === "Place picture of this shot"), undefined,
    "no picture choice before a place is chosen");
  const placed = state({ selected: { kind: "shot", id: "b" } });
  placed.shots = placed.shots.map((one) => one.id === "b" ? { ...one, place_from: "a" } : one);
  [, panel] = sideView(placed, actions);
  const kind = panel.byTag("select").find((one) => one.getAttribute("aria-label") === "Place picture of this shot");
  assert.deepEqual(kind.children.map((option) => option.innerText), ["Without people", "As rendered (1 s in)", "From another view …"]);
  assert.equal(panel.byTag("input").some((one) => one.getAttribute("aria-label") === "Camera of the place picture"), false);
  kind.onchange({ target: { value: "view" } });
  assert.deepEqual(calls.at(-1), ["setShot", "b", { place_picture: "view" }]);
  kind.onchange({ target: { value: "clean" } });
  assert.deepEqual(calls.at(-1), ["setShot", "b", { place_picture: undefined }], "the default is not stored");
  placed.shots = placed.shots.map((one) => one.id === "b" ? { ...one, place_picture: "view", place_view: "from the door" } : one);
  [, panel] = sideView(placed, actions);
  const camera = panel.byTag("input").find((one) => one.getAttribute("aria-label") === "Camera of the place picture");
  assert.equal(camera.value, "from the door");
  camera.oninput({ target: { value: "from the bar" } });
  assert.deepEqual(calls.at(-1), ["setShot", "b", { place_view: "from the bar" }, false]);
  const gone = state({ selected: { kind: "shot", id: "b" } });
  gone.shots = gone.shots.map((one) => one.id === "b" ? { ...one, place_from: "deleted" } : one);
  [, panel] = sideView(gone, actions);
  assert.ok(panel.innerText.includes("That shot is gone"), panel.innerText);
}

// Each part says what its prompt is made from; a shot chip selects the shot, a shot without text is flagged.
{
  const { sourcesRow } = await import("../../../js/ng/h3s_prompts.js");
  const { actions, calls } = recorder();
  const row = sourcesRow(state(), actions, { sources: [{ kind: "shot", id: "a", label: "Shot 1", text: "(no text)" },
    { kind: "rule", id: "r", label: "Style rule", text: "Anime CGI." }, { kind: "manual", id: "", label: "Manual prompt", text: "x" }] });
  assert.ok(row.innerText.includes("no text") && row.innerText.includes("Style rule"), row.innerText);
  row.find((node) => node.tagName === "BUTTON")[0].onclick();
  assert.equal(calls.at(-1)[0], "select");
  assert.equal(sourcesRow(state(), actions, { sources: [] }), null);
}

// The summary follows custom sampling settings and does not guess the upstream model graph.
{
  const [mode] = sideView(state({ values: { turbo: false, steps: 7 } }), recorder().actions);
  assert.ok(mode.innerText.includes("7 steps"), "the mode summary must show the actual sampler settings");
  assert.ok(!mode.innerText.includes("full model"), "an upstream LoRA may be connected even with the internal Turbo switch off");
}

// Every spoken line of a shot has its own editor and remove button.
{
  const { actions, calls } = recorder();
  const two = [{ schema_version: 1, text: "Hello.", speaker_id: "mage", language: "German" }, { schema_version: 1, text: "Hi.", speaker_id: "", language: "English" }];
  const base = state({ selected: { kind: "shot", id: "a" } });
  base.shots = base.shots.map((shot) => (shot.id === "a" ? { ...shot, spoken: two } : shot));
  const [, panel] = sideView(base, actions);
  const inputs = panel.byTag("input").filter((node) => node.attributes["aria-label"]?.startsWith("Spoken line"));
  assert.deepEqual(inputs.map((node) => node.value), ["Hello.", "Hi."]);
  inputs[1].oninput({ target: { value: "Hi there." } });
  assert.deepEqual(calls.at(-1), ["setSpoken", "a", 1, { text: "Hi there." }, false]);
  // A song needs "sings": the delivery is chosen per line (it was fixed to "says").
  const delivery = panel.find((node) => node.attributes["aria-label"] === "Delivery of line 2")[0];
  assert.equal(delivery.value, "says");
  delivery.onchange({ target: { value: "sings" } });
  assert.deepEqual(calls.at(-1), ["setSpoken", "a", 1, { delivery: "sings" }]);
  panel.find((node) => node.attributes["aria-label"] === "Remove line 1")[0].onclick();
  assert.deepEqual(calls.at(-1), ["removeSpoken", "a", 0]);
  panel.button("Spoken line").onclick();
  assert.deepEqual(calls.at(-1), ["addSpoken", "a"]);
  const [, empty] = sideView(state({ selected: { kind: "shot", id: "b" } }), actions);
  assert.equal(empty.button("Spoken line"), undefined, "without dialogue there is one empty editor and no add button");
}

// Footer and drawer.
{
  const { actions, calls: gearCalls } = recorder();
  const base = state();
  const footer = footerView(state({ values: { width: 0, height: 0 } }), actions);
  assert.equal(footer.byTag("select").find((node) => node.value === "auto")?.value, "auto");
  assert.ok(footer.innerText.includes("1344×768 from picture"));
  // the gear warns of a sampler pair that spoils H3 pictures (M16: res_multistep + beta overexposed)
  const bad = settingsView({ ...base, values: { ...base.values, scheduler: "beta" }, settingsOpen: true }, actions);
  assert.ok(bad.innerText.includes("overexposes"), bad.innerText);
  assert.ok(!settingsView({ ...base, settingsOpen: true }, actions).innerText.includes("overexposes"));
  // Spectrum: a switch only when its pack is installed
  assert.ok(!settingsView({ ...base, settingsOpen: true }, actions).innerText.includes("Spectrum"));
  globalThis.LiteGraph = { registered_node_types: { SpectrumApplyMiniMaxH3: {} } };
  const spec = settingsView({ ...base, settingsOpen: true }, actions);
  assert.ok(spec.innerText.includes("Spectrum off"), spec.innerText);
  spec.button("Spectrum off").onclick();
  assert.deepEqual(gearCalls.at(-1), ["setWidget", "spectrum", true]);
  delete globalThis.LiteGraph;
  // Turbo: the steps of the parts' own LoRA profile, not the widget's 4 (Ref2VA parts here: ref.safetensors -> 6)
  assert.ok(footerView(base, actions).innerText.includes("Ref2VA · 20 steps"));
  const turbo = footerView({ ...base, values: { ...base.values, turbo: true, steps: 4, turbo_lora_ref2va: "ref.safetensors" },
    turboProfiles: { ref: { steps: 6, sampler_name: "res_multistep", scheduler: "simple" } } }, actions);
  assert.ok(turbo.innerText.includes("Turbo · 6 steps"), turbo.innerText);
  const drawer = drawerView(state({ promptOpen: true }), actions);
  assert.ok(drawer.innerText.includes("first prompt") && drawer.innerText.includes("second prompt"));
  assert.ok(drawer.innerText.includes("Images 1/9 · Video 0/3 · Audio 0/3"));
  assert.ok(drawer.innerText.includes("Gap between shots (shot 2): there is a gap."));
  assert.equal(issueLine({ code: "new_code", text: "x" }), "Note: x");
  // Each part: write it with the AI, edit it, reset it; an own prompt of an older plan is flagged.
  const { actions: parts, calls: asked } = recorder();
  const own = { ...plan, chunks: [{ ...plan.chunks[0], prompt_key: "k0", prompt_source: "ai" }, { ...plan.chunks[1], prompt_key: "k1", prompt_source: "compiled" }] };
  const view = drawerView(state({ promptOpen: true, ai: true, plan: own, partPrompts: [{ index: 0, key: "k0", text: "mine", by: "ai" }, { index: 1, key: "old", text: "x", by: "user" }] }), parts);
  assert.ok(view.innerText.includes("AI-written") && view.innerText.includes("own prompt outdated"), view.innerText);
  view.button("Write all parts with AI").onclick();
  assert.deepEqual(asked.at(-1), ["writeAllParts"]);
  view.find((node) => node.tagName === "BUTTON" && node.innerText.endsWith("Write with AI"))[1].onclick();
  assert.deepEqual(asked.at(-1), ["writePart", 1]);
  view.button("Edit").onclick();
  assert.deepEqual(asked.at(-1), ["editPart", 0, "first prompt"]);
  view.button("Reset").onclick();
  assert.deepEqual(asked.at(-1), ["resetPart", 0]);
  const refused = drawerView(state({ promptOpen: true, plan: own, partDrafts: { 1: { key: "k1", text: "", problems: ["the cut times differ"] } } }), parts);
  assert.ok(refused.innerText.includes("was not used: the cut times differ"));
  assert.equal(refused.button("Accept"), undefined, "a refused version cannot be accepted");
  const kept = drawerView(state({ promptOpen: true, plan: own, partDrafts: { 1: { key: "k1", text: "second prompt", problems: [], unchanged: true } } }), parts);
  assert.ok(kept.innerText.includes("The AI kept the compiled prompt as it is"), "a copy is not passed off as a rewrite");
  // Any duration, and a music video's length in one click (a 27 s song had no matching entry in the old list).
  const { actions: act, calls } = recorder();
  const withSong = footerView(state({ lengths: new Map([["song", 27.0106]]) }), act);
  const seconds = withSong.byTag("input").find((node) => node.attributes["aria-label"] === "Duration in seconds");
  seconds.onchange({ target: { value: "27.34" } });
  assert.deepEqual(calls.at(-1), ["setDuration", 27.3]);
  withSong.button("= ").onclick();
  assert.deepEqual(calls.at(-1), ["setDuration", 27]);
  assert.ok(withSong.button("= ").title.includes("(27.0 s)") || withSong.button("= ").title.includes("27"), withSong.button("= ").title);
  assert.equal(footerView(state({ values: { project_seconds: 27 }, lengths: new Map([["song", 27.0106]]) }), act).button("= "), undefined, "no button when it already fits");
}

// Content cards and prompt.
{
  const { actions, calls } = recorder();
  const view = contentView(state({ selected: { kind: "shot", id: "a" }, values: { mode: "fl2va" } }), actions);
  const cards = view.byClass("h3s-ctx");
  assert.equal(cards.length, 4, "Text-Shot plus three Context cards");
  assert.ok(cards[1].classList.contains("on"), "Mage is in the selected shot");
  assert.ok(cards[2].classList.contains("off"), "a video is unused in FL2VA");
  for (const usage of ["continue", "control"]) {
    const supported = contentEntries([{ media: "video", widgets: { context_id: "source", name: "Source", video: "source.mp4", usage } }], () => "#E6BE57");
    const card = contentView(state({ contexts: supported, values: { mode: "fl2va" } }), actions).byClass("h3s-ctx")[1];
    assert.equal(card.classList.contains("off"), false, `${usage} works in FL2VA`);
    assert.equal(card.title.includes("Not used"), false);
    card.onclick();
    assert.deepEqual(calls.at(-1), ["toggleBinding", "source"]);
  }
  cards[3].onclick();
  assert.deepEqual(calls.at(-1), ["toggleBinding", "song"]);
  const prompt = promptView(state({ ai: false }), actions);
  assert.equal(prompt.button("AI: split into shots").disabled, true, "no AI without a loader");
  assert.equal(prompt.button("Make H3 prompt").disabled, true, "Make H3 prompt needs a loader too");
  assert.match(prompt.innerText, /Connect an H3 AI Loader/);
}

// Make H3 prompt: a picture is enough, the direction brings its speech, and the button starts the build.
{
  const { changeQuick, readQuick } = await import("../../../js/ng/h3s_quick.js");
  const calls = [];
  const actions = new Proxy({}, { get: (_, name) => (...args) => calls.push([name, ...args]) });
  const quick = { direction: "music_video", speech: "none", language: "English" };
  const prompt = promptView(state({ ai: true, quick, values: { idea: "", project_seconds: 20 } }), actions);
  // What goes into the plan is in the i next to the options, not as a line of text on the page.
  const about = prompt.find((node) => node.classList?.contains("h3s-tip")).map((node) => node.title ?? node.attributes?.title).join(" | ");
  assert.match(about, /1 picture, no Prompt \(optional with pictures\) and 20 s, then writes every render part's H3 prompt\..*Nobody speaks\./);
  prompt.button("Make H3 prompt").onclick();
  assert.deepEqual(calls.at(-1), ["buildPrompt"]);
  assert.equal(changeQuick(quick, "direction", "song").speech, "singing", "a song sings");
  assert.equal(changeQuick({ ...quick, speech: "singing" }, "direction", "story").speech, "none", "and stops singing after");
  assert.equal(changeQuick({ ...quick, speech: "dialogue" }, "direction", "story").speech, "dialogue", "a chosen dialogue stays");
  assert.deepEqual(readQuick({ properties: { ng_quick: { direction: "x", speech: "dialogue" } } }),
    { direction: "auto", speech: "dialogue", language: "English" });
  const none = promptView(state({ ai: true, quick, values: { idea: "", project_seconds: 20 }, contexts: [] }), actions);
  assert.equal(none.button("Make H3 prompt").disabled, true, "nothing to build from without a picture or a Prompt");
}

// BUG-003: with an empty Context ID field the Studio uses the id the Python side builds (tests/ng/test_context_ids.py).
{
  const { contextId } = await import("../../../js/ng/h3s_content.js");
  assert.equal(contextId({ context_id: "ctx_1", name: "Mage" }, "image"), "ctx_1");
  assert.equal(contextId({ context_id: "", name: "Mage Två" }, "image"), "image_mage_tv");
  assert.equal(contextId({ context_id: "", name: "", image: "people/My Pic.png [input]" }, "image"), "image_my_pic");
  assert.equal(contextId({ context_id: "", name: "", text: "  Hello, world of H3 and more text here" }, "text"), "text_hello_world_of_h3_and");
  assert.equal(contextId({ context_id: "", name: "", audio: "" }, "audio"), "audio_audio");
}

// FL2VA supports appearance pictures, but not voice-reference audio.
{
  const [, panel] = sideView(state({ selected: { kind: "shot", id: "a" }, values: { mode: "fl2va" } }), recorder().actions);
  assert.ok(panel.innerText.includes("First / last frame mode does not use voice references"));
  assert.ok(panel.innerText.includes("Reference pictures still guide appearance"));
  assert.ok(!panel.innerText.includes("has no character references"));
  const [, refs] = sideView(state({ selected: { kind: "shot", id: "a" } }), recorder().actions);
  assert.ok(!refs.innerText.includes("does not use voice references"));
}

// A related outfit is not a speaker; the Studio follows the Audio card's figure choices.
{
  const entries = contentEntries([
    { media: "image", widgets: { context_id: "mage", name: "Mage", image: "mage.png", usage: "reference", content: "character" } },
    { media: "image", widgets: { context_id: "outfit", name: "Outfit", image: "outfit.png", usage: "reference", content: "outfit", subject_ids: '["mage"]' } },
    { media: "image", widgets: { context_id: "place", name: "Place", image: "place.png", usage: "reference", content: "environment" } },
    { media: "image", widgets: { context_id: "empty", name: "Empty", image: "", usage: "reference", content: "character" } },
    { media: "image", widgets: { context_id: "anchor", name: "Anchor", image: "anchor.png", usage: "first_frame", content: "character" } },
  ], () => "#123456");
  const S = state({ contexts: entries, selected: { kind: "shot", id: "a" } });
  const speaker = () => sideView(S, recorder().actions)[1].byTag("select").find((el) => el.getAttribute("aria-label") === "Speaker of line 1");
  assert.deepEqual(speaker().children.map((option) => option.value), ["", "mage"]);
  S.shots[0].spoken = [{ text: "Hello.", speaker_id: "missing", language: "English", delivery: "says" }];
  const orphan = speaker();
  assert.equal(orphan.value, "missing", "a saved unavailable speaker must remain visible until explicitly repaired");
  assert.ok(orphan.children.some((option) => option.value === "missing" && option.innerText.includes("not connected")));
}

// BUG-008: the strip after the project end is marked as the frame grid's extra.
{
  const view = timelineView(state({ values: { project_seconds: 10 }, plan: { ...plan, total_s: 10.125 } }), recorder().actions);
  assert.ok(view.byClass("h3s-beyond").length > 0);
  assert.ok(!timelineView(state(), recorder().actions).byClass("h3s-beyond").length, "no strip when plan and project end agree");
}

// Older NG workflows put an empty trailing value on the first widget added later; it falls back to its default.
{
  globalThis.window = { comfyAPI: { app: { app: { registerExtension() {} } }, api: { api: {} } } };
  const { repairLaterWidgets } = await import("../../../js/ng/h3s_node.js");
  const widget = (name, value, values) => ({ name, value, options: values ? { values } : {} });
  const node = { widgets: [widget("turbo", ""), widget("turbo_lora_fl2va", "gone.safetensors", ["none", "fl.safetensors"]),
    widget("turbo_lora_ref2va", 1.5, ["none"]), widget("resize_method", "pad", ["crop", "pad"]), widget("seed", "")] };
  repairLaterWidgets(node);
  assert.deepEqual(node.widgets.map((w) => w.value), [false, "gone.safetensors", "none", "pad", ""],
    "only the later widgets are repaired; a LoRA that is not installed keeps its name for the download offer");
  // A workflow saved before "resume": its prompt_override text stays with prompt_override, resume is on.
  const { repairInsertedWidgets } = await import("../../../js/ng/h3s_node.js");
  const fresh = () => ({ widgets: [widget("ref_image_size", "?"), widget("resume", "?"), widget("resume_delete_done", "?"),
    widget("prompt_override", "?"), widget("h3_director", undefined)] });
  const older = fresh();
  repairInsertedWidgets(older, ["max", "my override", ""]);
  assert.deepEqual(older.widgets.map((w) => w.value), ["max", true, true, "my override", ""]);
  // Saved with resume but before resume_delete_done: resume keeps its value, the new box is on.
  const middle = fresh();
  repairInsertedWidgets(middle, ["max", false, "my override", ""]);
  assert.deepEqual(middle.widgets.map((w) => w.value), ["max", false, true, "my override", ""]);
  const current = { widgets: [widget("resume", false), widget("resume_delete_done", false), widget("prompt_override", "x")] };
  repairInsertedWidgets(current, [false, false, "x"]);
  assert.deepEqual(current.widgets.map((w) => w.value), [false, false, "x"], "a list of the current length is left alone");
  const named = { resume: false, resume_delete_done: true, control_strength: .5, control_start: .2, control_end: .9 };
  const modern = { widgets: [...Object.keys(named).map((name) => widget(name, "?")), { name: "h3_director", serialize: false }] };
  repairInsertedWidgets(modern, Object.values(named), named);
  assert.deepEqual(modern.widgets.slice(0, 5).map((w) => w.value), Object.values(named),
    "a nonserialized DOM widget must not rotate settings that have saved names");
  // Saved while "resume" was required (before prompt_override): the two come back swapped and are put right.
  const swapped = { widgets: [widget("prompt_override", true), widget("resume", "my override")] };
  repairLaterWidgets(swapped);
  assert.deepEqual(swapped.widgets.map((w) => w.value), ["my override", true]);
  const lost = { widgets: [widget("prompt_override", false), widget("resume", true)] };
  repairLaterWidgets(lost);
  assert.deepEqual(lost.widgets.map((w) => w.value), ["", true], "a switch value is never Prompt override text");
  // Frontend 1.55 makes the text box hold "true" (2026-10-18: every part's prompt was "true", the AI's texts were refused).
  const texted = { widgets: [widget("prompt_override", "true"), widget("resume", true)] };
  repairLaterWidgets(texted);
  assert.deepEqual(texted.widgets.map((w) => w.value), ["", true], "the text true is the misplaced switch, not a prompt");
  const kept = { widgets: [widget("prompt_override", "true love at dawn"), widget("resume", true)] };
  repairLaterWidgets(kept);
  assert.equal(kept.widgets[0].value, "true love at dawn", "a real override text stays");
}

// The Studio speaks English: no German text is left in its modules (comments included, to keep them consistent).
{
  const { readdirSync, readFileSync } = await import("node:fs");
  const dir = new URL("../../../js/ng/", import.meta.url);
  for (const name of readdirSync(dir).filter((file) => file.startsWith("h3s_"))) {
    const text = readFileSync(new URL(name, dir), "utf8");
    assert.doesNotMatch(text, /[äöüÄÖÜß]|\b(Teil|Tonspur|Shots aus|Übernehmen|Verwerfen|Hinweis|Zurück|und|nicht|oder|der|die|das|ist|mit|von|wird|sind|kein|keine|eine|einen)\b/, `${name} still has German text`);
  }
}

console.log("h3s views ok");
