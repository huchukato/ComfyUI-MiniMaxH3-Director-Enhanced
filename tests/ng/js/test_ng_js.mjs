// Tests for the NG frontend modules that have logic: reading widgets and wires, and rendering a plan.
// Run: node tests/ng/js/test_ng_js.mjs   (also called by tests/ng/run_tests.py)
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "..", "..", "js", "ng");
const load = (name) => import(pathToFileURL(path.join(root, name)).href);

class FakeElement {
  constructor(tag) { this.tag = tag; this.children = []; this.className = ""; this.textContent = ""; this.style = {setProperty: () => {}}; this.title = ""; this.dataset = {}; this.attributes = {}; }
  setAttribute(key, value) { this.attributes[key] = value; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  text() { return [this.textContent, ...this.children.map((c) => c.text())].join(" ").trim(); }
  find(className) { return [this, ...this.children.flatMap((c) => c.all?.() ?? [])].filter((n) => n.className.split(" ").includes(className)); }
  all() { return [this, ...this.children.flatMap((c) => c.all())]; }
}
globalThis.document = { createElement: (tag) => new FakeElement(tag), dispatchEvent: () => {},
  getElementById: () => null, head: new FakeElement("head") };
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };

const { readContexts, readPayload, isContextNode } = await load("ng_read.js");
const { connectedProvider, contextProvider, restoredProviderValues } = await load("ng_read.js");
const { renderPlan } = await load("ng_view.js");
const { extraContextInputs,compactContextInputs } = await load("ng_connector_slots.js");
const { nativePrompt } = await load("ng_ai_request.js");
const { contextOptions, setOptions } = await load("ng_context_controls.js");

{
  const card = {widgets:[{name:"context_options",value:JSON.stringify({schema_version:1,anchor_s:20})},
    {name:"preserve",value:"high"}]};
  const saved = card.widgets[0].value;
  assert.equal(contextOptions(card).anchor_s,20,"an older card's stored keyframe time is read");
  assert.equal(card.widgets[0].value,saved,"reading defaults must not rewrite stored options");
  assert.deepEqual(contextOptions(card).preserve,{});
  setOptions(card,{anchor_s:0,preserve:{identity:"low"}});
  assert.equal(contextOptions(card).anchor_s,0,"zero is a valid first-frame guide time");
  assert.equal(contextOptions(card).preserve.identity,"low","explicit retention must survive default loading");
  assert.equal(contextOptions(card).video_audio,"ignore");
}

{
  const output={"1":{class_type:"CLIPLoader",inputs:{clip_name:"model.safetensors"}},
    "2":{class_type:"NGAIProvider",inputs:{source:"clip",clip:["1",0]}},
    "3":{class_type:"NGProjectRender",inputs:{sequence:["4",0]}}};
  const prompt=nativePrompt(output,"2","analyze",{media:"text",widgets:{text:"Rules"}});
  assert.deepEqual(Object.keys(prompt).sort(),["1","2","ng_ai_action"].sort(),"AI actions must not queue H3 rendering");
  assert.deepEqual(prompt.ng_ai_action.inputs.ai_provider,["2",0]);
  assert.throws(()=>nativePrompt(output,"missing","analyze",{}),/unavailable/);
}

assert.deepEqual(restoredProviderValues(["custom","http://localhost:1234","old-model","MY_KEY",true,false]),
  {source:"api",provider:"custom",base_url:"http://localhost:1234",model:"old-model",api_key_env:"MY_KEY",vision:true,audio:false,
    timeout_seconds:120,max_tokens:512,keep_alive:0},"The original six provider widgets must survive the added Source field");
assert.equal(restoredProviderValues(["api","custom","http://localhost:1234","new-model","",true,false,120,512,0]),null);

{
  const inputs=[{name:"clip",link:7},{name:"context_image.image_0",link:1},{name:"context_image.image_1",link:null},
    {name:"context_image.image_2",link:null},{name:"context_video.video_0",link:null},
    {name:"context_text.text_0",link:null},{name:"context_text.text_1",link:2},{name:"context_text.text_2",link:null},
    {name:"context_text.text_3",link:null}];
  const connected=inputs.filter((input)=>input.link!=null);
  assert.deepEqual(extraContextInputs(inputs),[8,3],"one empty tail per group; keep a gap before a connected slot");
  const node={inputs,removeInput:(index)=>inputs.splice(index,1),addInput:(name,type)=>inputs.push({name,type,link:null})};compactContextInputs(node);
  assert.deepEqual(inputs.filter((input)=>input.link!=null),connected,"compaction must preserve every native/model/context connection");
  assert.deepEqual(extraContextInputs(inputs),[],"repeated configure/connection notifications are idempotent");
  assert.ok(inputs.some((input)=>input.name==="context_audio.audio_0"),"a missing optional group must still have one accessible port");
  inputs.push({name:"context_video.video_1",link:3});compactContextInputs(node);
  assert.ok(inputs.some((input)=>input.name==="context_video.video_2"),"a connected final slot must leave a next input within the schema limit");
  inputs.find((input)=>input.name==="context_video.video_2").link=4;compactContextInputs(node);
  assert.ok(inputs.some((input)=>input.name==="context_video.video_3"),"three references may still need a continuation card");
  for(const media of ["image","video","audio"]){
    const connected=Array.from({length:15},(_,i)=>({name:`context_${media}.${media}_${i}`,link:100+i}));
    const restored={inputs:connected,removeInput:(index)=>connected.splice(index,1),
      addInput:(name,type)=>connected.push({name,type,link:null})};
    compactContextInputs(restored);
    assert.equal(connected.filter((input)=>input.name.startsWith(`context_${media}.`)).length,15,"the Context cap remains finite");
  }
}

function node(comfyClass, widgets = {}, inputs = [], graph = null) {
  return { comfyClass, widgets: Object.entries(widgets).map(([name, value]) => ({ name, value })), inputs, graph };
}

{
  const {nativeAIFingerprint}=await load("ng_widgets.js");
  const encoder=node("CLIPLoader",{clip_name:"qwen.safetensors"});encoder.id=31;
  const loader=node("NGAIProvider",{source:"clip",vision:true,audio:false,max_tokens:256,timeout_seconds:120},[{name:"clip",link:15}]);loader.id=30;
  const graph={links:{15:{origin_id:31},16:{origin_id:30}},getNodeById:(id)=>({30:loader,31:encoder}[id])};loader.graph=graph;
  const context=node("NGContextText",{},[{name:"ai_provider",link:16}],graph);
  assert.equal(connectedProvider(context).model,"qwen.safetensors");
  assert.equal(connectedProvider(context).loader_node_id,"30");
  const tested=nativeAIFingerprint(loader);encoder.widgets[0].value="other.safetensors";
  assert.notEqual(nativeAIFingerprint(loader),tested,"changing the connected model invalidates its tested badge");
  loader.inputs[0].link=null;assert.equal(connectedProvider(context),null,"the CLIP source needs a connection or an installed encoder");
  // An installed encoder is the same native path, so it needs no switch of its own: with no Load
  // CLIP connected it is simply what the card uses.
  loader.widgets=node("NGAIProvider",{source:"clip",local_model:"disk.safetensors",local_type:"stable_diffusion"}).widgets;
  assert.equal(connectedProvider(context).model,"disk.safetensors");
  assert.equal(connectedProvider(context).source,"clip");
  // A connected encoder still wins over a leftover model name, so the two cannot disagree. The
  // encoder was renamed above on purpose, which also shows the name is read from the connection
  // and not from the widget that is still holding the old encoder.
  loader.inputs[0].link=15;
  assert.equal(connectedProvider(context).model,"other.safetensors");
}

// --- reading -----------------------------------------------------------------
{
  const alice = node("NGContextImage", { name: "Alice", content: "character" });
  const voice = node("NGContextAudio", { name: "Voice", speaker: "Alice" });
  const other = node("KSampler", { seed: 1 });
  const nodes = { 1: alice, 2: voice, 3: other };
  const links = { 10: { origin_id: 1 }, 11: { origin_id: 2 }, 12: { origin_id: 3 } };
  const graph = { links, getNodeById: (id) => nodes[id] };
  const director = node("NGDirector", { idea: "x", project_seconds: 30 },
    [{ name: "prepend_text", link: null }, { name: "contexts.context_0", link: 10 }, { name: "contexts.context_1", link: 11 },
     { name: "contexts.context_2", link: 12 }, { name: "contexts.context_3", link: null }], graph);

  assert.equal(isContextNode(alice), true);
  assert.equal(isContextNode(other), false);
  const contexts = readContexts(director);
  assert.deepEqual(contexts.map((c) => c.media), ["image", "audio"], "only NG context nodes count, in socket order");
  assert.equal(contexts[0].widgets.name, "Alice");
  assert.deepEqual(readPayload(director).director, { idea: "x", project_seconds: 30 });
}

// --- rendering ---------------------------------------------------------------
{
  const image=node("NGContextImage",{name:"Alice"});image.outputs=[{links:[3]}];
  const provider=node("NGAIProvider",{provider:"custom",base_url:"http://localhost:1234",model:"local",vision:true,audio:false,api_key_env:"",timeout_seconds:45,max_tokens:1024,keep_alive:60});
  provider.widgets.push({name:"ng_product",value:"presentation only"});
  const connector=node("NGContextConnector",{},[{name:"context_image.image_0",link:3},{name:"ai_provider",link:4}]);
  const director=node("NGH3Director",{idea:"Alice walks."},[{name:"context",link:5}]);
  const graph={links:{3:{origin_id:1,target_id:2},4:{origin_id:3,target_id:2},5:{origin_id:2,target_id:4}},getNodeById:(id)=>({1:image,2:connector,3:provider,4:director}[id])};
  [image,provider,connector,director].forEach((entry)=>entry.graph=graph);
  assert.equal(isContextNode(connector),false,"the connector is not a media ContextItem");
  assert.equal(readContexts(director)[0].widgets.name,"Alice","Director reads contexts through Connector");
  assert.equal(connectedProvider(director).model,"local");
  assert.equal("ng_product" in connectedProvider(director),false,"DOM widgets must never enter provider configuration");
  assert.equal(connectedProvider(director).timeout_seconds,45,"Request tuning must reach the provider transport");
  assert.equal(connectedProvider(director).max_tokens,1024);
  assert.equal(connectedProvider(director).keep_alive,60);
  assert.equal(contextProvider(image).model,"local","Context AI can inherit the connected Connector provider");
  connector.inputs[1].link=null;
  assert.equal(connectedProvider(director),null,"disconnect disables AI");
  assert.equal(contextProvider(image),null);
}

// --- rendering ---------------------------------------------------------------
{
  const root = new FakeElement("div");
  renderPlan(root, null);
  assert.match(root.text(), /planning/);

  renderPlan(root, { ok: false, error: "project_seconds: must be at least 0.1" });
  assert.match(root.text(), /must be at least 0.1/);
  assert.equal(root.find("ng-error").length, 1);

  const chunk = (index, start, end, head) => ({ index, start_s: start, end_s: end, delivered_frames: Math.round((end - start) * 24), sampled_frames: 260,
    head_frames: head, mode: "ref2va", prompt: `prompt ${index}`, refs: [{ kind: "picture", name: "Alice" }, { kind: "audio", name: "Alice voice" }] });
  const data = { ok: true, total_s: 20, total_frames: 480, mode: "ref2va", chunks: [chunk(0, 0, 10, 0), chunk(1, 10, 20, 22)],
    issues: [{ text: "late", ref: "shot 2" }, { text: "global", ref: "" }] };
  renderPlan(root, data);
  const text = root.text();
  assert.match(text, /2 chunks/);
  assert.match(text, /20\.00 s \(480 frames\)/);
  assert.match(text, /shot 2: late/);
  assert.match(text, /global/);
  assert.equal(root.find("ng-seg").length, 2, "one timeline segment per chunk");
  assert.match(text, /chunk 2 +10\.00 s - 20\.00 s/);
  assert.match(text, /sampled 260, head 22/);
  assert.match(text, /prompt 1/);
  assert.match(text, /picture: Alice +· +audio: Alice voice/);

  renderPlan(root, { ...data, chunks: [chunk(0, 0, 8, 0)], issues: [] });
  assert.match(root.text(), /1 chunk\b/);
  assert.doesNotMatch(root.text(), /Notes/);
}

// Edits from presets notify callbacks, and presentation mode survives a workflow reload without editing render inputs.
{
  const { applyValues, newContextId } = await load("ng_widgets.js");
  const withoutCrypto = Array.from({ length: 20 }, () => newContextId(null));
  assert.equal(new Set(withoutCrypto).size, 20, "IDs work even when a browser lacks crypto APIs");
  assert.ok(withoutCrypto.every((id) => /^ctx_[0-9a-f]{32}$/.test(id)));
  assert.match(newContextId({ getRandomValues: (bytes) => bytes.fill(12) }), /^ctx_[0-9a-f]{32}$/,
    "getRandomValues without randomUUID supports ordinary HTTP pages");
  let calls = 0;
  const changed = [];
  const card = { widgets: [{ name: "description", value: "old", callback: () => calls++ }, { name: "usage", value: "lock" }],
    onWidgetChanged: (name, value, old) => changed.push([name, value, old]) };
  applyValues(card, { description: "new", provider_key: "ignored" });
  assert.equal(card.widgets[0].value, "new");
  assert.equal(card.widgets[1].value, "lock");
  assert.equal(calls, 1);
  assert.deepEqual(changed, [["description", "new", "old"]], "ComfyUI hears the change and clears a missing-model mark");
}

// Exercise the real product extension's configure hook with both running backend schemas.
{
  let extension;
  globalThis.window = {comfyAPI: {app: {app: {registerExtension: (value) => {extension = value;}}}, api: {api: {}}}};
  await load("ng_product_nodes.js");
  function outputNode(shiftValue) {
    const output = node("NGDirectorOutput", {chunk_index: 0,
      ...(shiftValue === undefined ? {} : {apply_sigma_shift: shiftValue})});
    output.size = [440, 370];
    output.setSize = (size) => {output.size = size;};
    output.addDOMWidget = (name, type, element, options) => {
      const widget = {name, type, element, options}; output.widgets.push(widget); return widget;
    };
    extension.nodeCreated(output);
    return output;
  }
  const oldBackend = outputNode();
  assert.doesNotThrow(() => oldBackend.onConfigure({widgets_values: [0, ""]}),
    "New UI must load workflows while the running backend still lacks apply_sigma_shift");
  assert.equal(oldBackend.widgets.some((entry) => entry.name === "apply_sigma_shift"), false,
    "Never fabricate a setting the backend cannot execute");
  const current = outputNode(false);
  current.onConfigure({widgets_values: [0, false]});
  assert.equal(current.widgets.find((entry) => entry.name === "apply_sigma_shift").value, false,
    "An explicitly disabled shift must survive reload");
  current.onConfigure({widgets_values: [0, ""]});
  assert.equal(current.widgets.find((entry) => entry.name === "apply_sigma_shift").value, true,
    "Old saved DOM placeholders migrate to the backend's default shift");
  current.onConfigure({widgets_values: [0, true]});
  assert.equal(current.widgets.find((entry) => entry.name === "apply_sigma_shift").value, true);
}

console.log("ng js: all checks passed");

{
  const {renameReferences,referenceParts}=await load("ng_references.js");
  const entries=[{media:"image",widgets:{context_id:"ctx_a",name:"Alice Smith",color:"#12aabb"}}];
  assert.equal(renameReferences("@Alice walks; @Alicex stays.",{ctx_a:"Alice"},entries),"@Alice Smith walks; @Alicex stays.");
  assert.equal(renameReferences("@Alice walks.",{ctx_old:"Alice"},entries),"@Alice walks.","a different ID must not steal the old reference");
  const tokens=referenceParts("@Alice Smith talks to @Missing. @ctx_a",entries).filter((part)=>part.entry||part.unknown);
  assert.equal(tokens[0].entry.widgets.context_id,"ctx_a");assert.equal(tokens[1].unknown,true);assert.equal(tokens[2].entry.widgets.name,"Alice Smith");
  const {downstreamNodes,hasRenderPath,projectRenderIds}=await load("ng_graph.js");
  const director={id:1,outputs:[{links:[1]}]},output={id:2,comfyClass:"NGDirectorOutput",outputs:[{links:[2]}]},render={id:3,comfyClass:"NGProjectRender",outputs:[{links:[3]}]};
  const graph={links:{1:{target_id:2},2:{target_id:3},3:{target_id:1}},getNodeById:(id)=>({1:director,2:output,3:render}[id])};director.graph=graph;
  assert.deepEqual(downstreamNodes(director).map((entry)=>entry.id),[2,3],"cycles are bounded");assert.equal(hasRenderPath(director),true);
  assert.deepEqual(projectRenderIds(director),[1,2,3]);
}

{
  const {autoColor,contextColor}=await load("ng_identity.js");
  const {compiledParts}=await load("ng_references.js");
  const first=autoColor("image","ctx_a",[]),second=autoColor("image","ctx_b",[first]);
  assert.notEqual(first,second,"same-media contexts need distinguishable automatic colors");
  assert.equal(autoColor("image","ctx_a",[]),first,"identity makes the default color stable");
  assert.equal(contextColor({media:"audio",widgets:{color:"#123abc"}}),"#123abc");
  const image={media:"image",widgets:{context_id:"ctx_a",name:"Alice",color:first}};
  const audio={media:"audio",widgets:{context_id:"ctx_voice",name:"Voice",color:"#123abc"}};
  const parts=compiledParts("<Picture 1> <Subject 1> <Audio 1> <Video 1>",
    [{kind:"picture",ctx_id:"ctx_a"},{kind:"audio",ctx_id:"ctx_voice"}],[image,audio]).filter((part)=>part.text.startsWith("<"));
  assert.equal(parts[0].entry,image);assert.equal(parts[1].entry,image);assert.equal(parts[2].entry,audio);
  assert.equal(parts[3].entry,undefined,"a missing video must never borrow a picture's color");
}

{
  const { readStory, writeStory, moveShot } = await load("ng_story_model.js");
  const text = "0-8: @Alice enters.\n@Alice says: Hello.\n0:08-0:22.5: She finds a robot.";
  const parsed = readStory(text);
  assert.equal(parsed.error, "");
  assert.equal(parsed.shots.length, 2);
  assert.equal(parsed.shots[1].end, 22.5);
  assert.deepEqual(readStory(writeStory(parsed.shots)).shots, parsed.shots, "timing and multiline dialogue survive editing");
  assert.match(readStory("unrecognized shot without times").error, /retained/);
  const shot = { start: 8, end: 12, text: "Action" };
  assert.deepEqual(moveShot(shot, -100, "move", 20), { start: 0, end: 4, text: "Action" });
  assert.deepEqual(moveShot(shot, 100, "move", 20), { start: 16, end: 20, text: "Action" });
  assert.ok(moveShot(shot, 100, "start", 20).start < 12);
  assert.ok(moveShot(shot, -100, "end", 20).end > 8);
}

{
  const { belongsToNode, attachProgress } = await load("ng_studio_progress.js");
  assert.equal(belongsToNode("5.0.1.sample",5),true);
  assert.equal(belongsToNode("50.0.1.sample",5),false,"progress must not spill into another Director");
  const handlers=new Map();
  const api={addEventListener:(name,fn)=>handlers.set(name,fn),removeEventListener:(name)=>handlers.delete(name)};
  const status={textContent:""};
  const progress=attachProgress({id:5},api,status);
  assert.equal(handlers.has("minimax_h3_preview"),false,"Director progress never subscribes to video buffers");
  assert.equal(handlers.has("b_preview_with_metadata"),false,"Director progress never subscribes to native pictures");
  handlers.get("executing")({detail:"5"});
  assert.equal(status.textContent,"Rendering…");
  handlers.get("progress_text")({detail:{nodeId:"5.0.1.start",text:"Iteration 1 / 2"}});
  handlers.get("progress")({detail:{node:"5.0.1.sample",value:4,max:8}});
  assert.equal(status.textContent,"Iteration 1 / 2 · 50%");
  progress.planning("new plan");
  assert.equal(status.textContent,"Iteration 1 / 2 · 50%","editing a plan must not replace render progress");
  handlers.get("executing")({detail:"16"});
  assert.equal(status.textContent,"Iteration 1 / 2 · 50%","executing a different node is not completion");
  handlers.get("execution_interrupted")({detail:{node_id:"5"}});
  assert.equal(status.textContent,"Render interrupted");
  handlers.get("executing")({detail:"5"});
  handlers.get("executing")({detail:null});
  assert.equal(status.textContent,"Render finished · see Save Video");
  progress.dispose();assert.equal(handlers.size,0,"listeners are removed with the node");
}
{
  const { MODES, canAutoDirect, offeredFields, applyChanges, reasonLine, summarizeBatch } = await load("ng_assist.js");
  assert.deepEqual(MODES,["manual","assist","auto"]);
  assert.equal(canAutoDirect("auto",true),true);
  assert.equal(canAutoDirect("manual",true),false,"Manual must never start a scene proposal");
  assert.equal(canAutoDirect("assist",true),false);
  assert.equal(canAutoDirect("auto",false),false,"no loader, no proposal");
  assert.equal(canAutoDirect("auto",true,true),false,"a running request must not start another");

  const full={description:"A woman in a red coat.",content:"character",usage:"reference",why:"  she fills the frame.  "};
  assert.deepEqual(offeredFields(full),{description:"A woman in a red coat.",content:"character",usage:"reference"});
  assert.deepEqual(offeredFields({description:"A woman.",content:"",usage:"   "}),{description:"A woman."},
    "an empty field is never offered, so Apply cannot blank what the user typed");
  assert.deepEqual(offeredFields(null),{});

  assert.deepEqual(applyChanges(full,["description"]),{description:"A woman in a red coat."},
    "only ticked fields are written");
  assert.deepEqual(applyChanges(full,["content","usage"]),{content:"character",content_roles:'["character"]',
    usage:"reference",usage_roles:'["reference"]'});
  assert.deepEqual(applyChanges(full,["why","color"]),{},"why is a reason, not a widget");
  assert.deepEqual(applyChanges({description:"x"},[]),{});

  assert.equal(reasonLine(full),"Why: she fills the frame.");
  assert.equal(reasonLine({why:"  "}),"");
  assert.equal(reasonLine({}),"");

  const batch=summarizeBatch({results:[{ok:true},{ok:false,error:"Enable audio"}],skipped:["Empty: text is empty"]});
  assert.equal(batch.part,"1 analyzed · 1 failed");
  assert.deepEqual(batch.failed,["Enable audio"]);
  assert.deepEqual(batch.skipped,["Empty: text is empty"]);
  assert.equal(summarizeBatch({results:[],skipped:[]}).part,"Nothing analyzed");
  assert.equal(summarizeBatch(null).part,"Nothing analyzed","a malformed answer must not throw in the panel");
}
{
  const { isSubject, subjectChoices, voiceAssignment, SUBJECT_ROLES } = await load("ng_subjects.js");
  assert.deepEqual(SUBJECT_ROLES,["character","face","animal"]);
  const alice={media:"image",widgets:{context_id:"ctx_a",name:"Alice",image:"a.png",content_roles:'["character"]'}};
  const coat={media:"image",widgets:{context_id:"ctx_c",name:"Coat",image:"c.png",content_roles:'["outfit"]'}};
  const empty={media:"image",widgets:{context_id:"ctx_e",name:"Empty",image:"",content_roles:'["character"]'}};
  const unlabelled={media:"image",widgets:{context_id:"ctx_u",name:"Mystery",image:"u.png"}};
  assert.equal(isSubject(alice),true);
  assert.equal(isSubject(coat),false,"an outfit is an asset, not a figure that can speak");
  assert.equal(isSubject(empty),false,"a figure without a file cannot be drawn from");
  assert.equal(isSubject(unlabelled),true,"no content label yet: still offer it, the user decides");
  assert.equal(isSubject({media:"audio",widgets:{context_id:"x",name:"Voice",audio:"v.wav"}}),false);
  assert.equal(isSubject(null),false);

  assert.deepEqual(subjectChoices([alice,coat,empty]),[{id:"ctx_a",name:"Alice"}]);
  assert.deepEqual(subjectChoices([unlabelled]),[{id:"ctx_u",name:"Mystery"}],
    "an item without content_roles falls back to the single content widget");
  assert.deepEqual(subjectChoices([alice,{media:"image",widgets:{context_id:"ctx_a",name:"Alice again",image:"a.png"}}]),
    [{id:"ctx_a",name:"Alice"}],"the same figure must not appear twice");
  // A stored speaker that is no longer connected stays visible, so the value cannot vanish from the workflow.
  assert.deepEqual(subjectChoices([alice],"ctx_gone"),[{id:"ctx_a",name:"Alice"},{id:"ctx_gone",name:"ctx_gone (not connected)"}]);
  assert.deepEqual(subjectChoices([], "ctx_gone"),[{id:"ctx_gone",name:"ctx_gone (not connected)"}]);
  assert.deepEqual(subjectChoices(null),[]);
  // A card with an empty Context ID is offered under the id the plan gives it (context_build.card_id), BUG-051.
  assert.deepEqual(subjectChoices([{media:"image",widgets:{name:"No id",image:"x.png"}}]),[{id:"image_no_id",name:"No id"}]);

  const voices=[alice,
    {media:"audio",widgets:{context_id:"v1",name:"Take 1",audio:"1.wav",speaker:"ctx_a"}},
    {media:"audio",widgets:{context_id:"v2",name:"Take 2",audio:"2.wav",speaker:"ctx_a"}}];
  const flag=voiceAssignment(voices);
  assert.equal(flag("ctx_a","v1"),"Another take also names this figure; the first one fills the voice slot.");
  assert.equal(flag("ctx_a","v2"),"Another take also names this figure; the first one fills the voice slot.");
  assert.equal(flag("",  "v1"),"","no speaker chosen, nothing to warn about");
  assert.equal(flag("ctx_z","v1"),"","a speaker nobody else claims needs no note");
  assert.equal(voiceAssignment([{media:"audio",widgets:{context_id:"only",speaker:"ctx_a"}}])("ctx_a","only"),"");
}

{
  const {accepts,fieldHelp,isNative,mediaHint,wantsKey,wireName}=await load("ng_ai_capabilities.js");
  const ollama={id:"ollama",auth:"none",fields:["max_tokens","seed","top_k"],
    wire:{max_tokens:"num_predict",seed:"options.seed",top_k:"options.top_k"},
    help:{max_tokens:"Upper bound."},media:{image:{ok:true,hint:""},audio:{ok:false,hint:"No audio here."}}};

  // The sampling matrix decides what is shown. A field Claude does not have must not appear at all.
  assert.equal(accepts(ollama,"top_k"),true);
  assert.equal(accepts({fields:["max_tokens"]},"top_k"),false,"Claude has no top_k");
  // Unknown is not "supports nothing": hiding every field while the registry loads makes them unfindable.
  assert.equal(accepts(null,"top_k"),true,"an absent entry must show the field, not hide it");
  assert.equal(accepts({},"top_k"),true);

  // The way out is named, not only the fault. This is what the context card shows in place of an
  // error, so an empty hint leaves the user with nothing to do about it.
  assert.equal(mediaHint(ollama,"audio"),"No audio here.");
  assert.equal(mediaHint(ollama,"image"),"");
  assert.equal(mediaHint(null,"audio"),"");

  // The wire name differs only where it really does, so the note appears on Ollama and nowhere else.
  assert.equal(wireName(ollama,"max_tokens"),"num_predict");
  assert.equal(wireName(ollama,"keep_alive"),"keep_alive","an unnamed field is sent under its own name");
  assert.equal(wireName(null,"max_tokens"),"max_tokens");

  assert.equal(fieldHelp(ollama,"max_tokens"),"Upper bound.");
  assert.equal(fieldHelp(ollama,"top_k"),"","a field with no text carries no ? marker");

  assert.equal(wantsKey(ollama),false,"a local server needs no key");
  assert.equal(wantsKey({auth:"bearer"}),true);
  assert.equal(wantsKey(null),false);
  assert.equal(isNative("clip"),true);
  assert.equal(isNative("local"),false);
}
