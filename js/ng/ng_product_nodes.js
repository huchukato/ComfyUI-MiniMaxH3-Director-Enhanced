// Product nodes outside the Director: AI Loader, Context Connector, Director Output, Render Sequence.
import { element, values, followNodeWidth } from "./ng_widgets.js";
import { control, hideNative, section } from "./ng_editor_fields.js";
import { ensureStudioStyle } from "./ng_studio_style.js";
import { connectedProvider, readContexts } from "./ng_read.js";
import { providerRestoreValues, configureProviderType, restoreProviderFields } from "./ng_provider_restore.js";
import { attachProgress } from "./ng_studio_progress.js";
import { compactContextInputs } from "./ng_connector_slots.js";
import { icon } from "./ng_icons.js";
import { pushOnGrowth } from "./ng_layout.js";
import { buildPanel } from "./ng_ai_panel.js";

const { app } = window.comfyAPI.app, { api } = window.comfyAPI.api;

function shell(node, title, accent, size, brand) {
  ensureStudioStyle(); node.properties ||= {}; node.color = "#162b45"; node.bgcolor = "#101a2c";
  const root = element("div", "ng-studio-context ng-product-node"); root.style.setProperty("--ng-accent", accent);
  const header = element("div", "ng-header");
  // A branded node shows a logo tile, a two-tone title and a subtitle; the plain ones keep the old
  // single strong, so the other product nodes do not grow a header they never asked for.
  if (brand) {
    const badge = element("div", "ng-brand");
    badge.append(icon(brand.icon, "ng-brand-mark"));
    const text = element("div", "ng-brand-text");
    const heading = element("strong", "ng-brand-title");
    const [lead, ...rest] = title.split(" ");
    heading.append(element("span", "ng-brand-lead", [lead, ...rest.slice(0, -1)].join(" ")));
    heading.append(element("span", "ng-brand-accent", rest[rest.length - 1] || ""));
    text.append(heading, element("small", "ng-brand-sub", brand.subtitle));
    badge.append(text);
    header.append(badge);
    // No overflow menu: its only job was to hide two hint sentences, and every field now carries
    // its own explanation. A button in the header that changes the layout is a surprise.
  } else header.append(element("strong", "ng-context-title", title));
  root.append(header);
  const widget = followNodeWidth(node.addDOMWidget("ng_product", "ng_product", root, { serialize: false, hideOnZoom: false }));
  widget.computeSize=undefined;
  // Only the minimum width is fixed; the height comes from the panel, which measures its own
  // content. The panel sizes itself through computeLayoutSize, so fall back to the passed minimum
  // here instead of asking for a computeSize that a DOM panel no longer defines.
  const configured = node.onConfigure; node.onConfigure = function (...args) { const result = configured?.apply(this, args);
    node.setSize([Math.max(size[0], node.size[0]), Math.max(size[1], node.size[1])]); return result; };
  return { root, header, widget };
}

function provider(node) {
  const defaults={...values(node),...node.constructor.ng_provider_defaults};
  const { root, header, widget } = shell(node, "H3 AI LOADER", "#a77cff", [660, 300],
    { icon: "box", subtitle: "Load LLM / AI Model" });
  // the Context cards' look and width (ng_studio_style.js, .ng-ai); it was placed at 270 wide before
  root.classList.add("ng-ai");
  node.setSize([660, node.size?.[1] || 300]);
  const panel = buildPanel(node, root, header, widget);
  const removed=node.onRemoved;node.onRemoved=function(...args){panel.dispose();return removed?.apply(this,args);};
  const configured = node.onConfigure; node.onConfigure = function (...args) { const result = configured?.apply(this, args);
    const restored=providerRestoreValues(args[0],defaults);
    restoreProviderFields(node,restored);
    queueMicrotask(() => { panel.sync(); panel.fit(true); }); return result; };
  for (const entry of node.widgets || []) { if (entry === widget) continue; const previous = entry.callback;
    entry.callback = function (...args) { const result = previous?.apply(this, args); panel.sync();
      document.dispatchEvent(new CustomEvent("ng-context-changed")); return result; }; }
}
function connector(node) {
  const {root,header,widget}=shell(node,"↔ H3 CONTEXT CONNECTOR","#57dfb8",[560,380]),status=element("span","ng-ai-badge");header.append(status);
  root.append(element("small","ng-muted","Models, reusable Contexts and optional AI → H3 Director. Connect the last empty context port to add another."));
  function sync(){
    compactContextInputs(node);
    const has=(name)=>(node.inputs||[]).some((input)=>input.name===name&&input.link!=null);
    const ready=["clip","vae","audio_vae"].every(has)&&(has("model_fl2va")||has("model_ref2va"));
    status.textContent=ready?(connectedProvider(node)?"Connected · AI available":"Connected · manual"):"Connect models";
    for(const input of node.inputs||[]){const match=/^context_(\w+)\.\w+_(\d+)$/.exec(input.name);if(match)input.label=`context ${match[1]} ${Number(match[2])+1}`;}
  }
  const connected=node.onConnectionsChange;node.onConnectionsChange=function(...args){const result=connected?.apply(this,args);queueMicrotask(sync);return result;};
  const configured=node.onConfigure;node.onConfigure=function(...args){const result=configured?.apply(this,args);queueMicrotask(sync);return result;};
  document.addEventListener("ng-context-changed",sync);
  const removed=node.onRemoved;node.onRemoved=function(...args){document.removeEventListener("ng-context-changed",sync);return removed?.apply(this,args);};
  widget.computeLayoutSize=()=>({minHeight:95,maxHeight:150,minWidth:0});node.setSize([560,380]);sync();
}
function output(node) {
  const {root,widget}=shell(node,"➜ H3 DIRECTOR OUTPUT","#e981ed",[440,335]);
  root.append(element("p","ng-muted","Director.chunks → Start Loop. Connect its list_item and current_iteration_value here. Native outputs → your sampler; seed → RandomNoise. Sequence → H3 Render Sequence for the simple path."));
  const advanced=element("details");advanced.append(element("summary","","Chunk and model settings"));
  const field=control(node,"chunk_index","Single chunk index · ignored when loop_chunk is connected",{number:true});
  const shift=control(node,"apply_sigma_shift","Apply Director sigma shifts · disable for an externally shifted model",{boolean:true});
  advanced.append(field.label,shift.label);root.append(advanced);
  hideNative(node,["chunk_index","apply_sigma_shift"]);widget.computeLayoutSize=()=>({minHeight:140,maxHeight:270,minWidth:0});node.setSize([440,370]);
  const configured=node.onConfigure;node.onConfigure=function(...args){const result=configured?.apply(this,args);
    // Older saved nodes have a trailing empty DOM-widget value where the new checkbox sits.
    const saved=args[0]?.widgets_values;
    // JS can refresh before the Python server restarts: the older schema has no checkbox.
    const shiftWidget=node.widgets?.find((entry)=>entry.name==="apply_sigma_shift");
    if(shiftWidget&&Array.isArray(saved)&&typeof saved[1]!=="boolean")shiftWidget.value=true;
    field.sync();shift.sync();return result;};
}
function render(node) {
  const {root,header,widget}=shell(node,"▶ H3 RENDER SEQUENCE","#5ba9ff",[480,245]),status=element("span","ng-ai-badge","Awaiting sequence");
  header.append(status);root.append(element("p","ng-muted","Native loop · sampler · continuity · final collect"));
  const progress=attachProgress(node,api,status);widget.computeLayoutSize=()=>({minHeight:110,maxHeight:130,minWidth:0});node.setSize([480,245]);
  const removed=node.onRemoved;node.onRemoved=function(...args){progress.dispose();return removed?.apply(this,args);};
}
app.registerExtension({name:"mmxd.ng.product_nodes",beforeRegisterNodeDef(nodeType,nodeData){
  if(nodeData.name==="NGAIProvider")configureProviderType(nodeType,nodeData);
},nodeCreated(node){
  ({NGAIProvider:provider,NGContextConnector:connector,NGDirectorOutput:output,NGProjectRender:render})[node.comfyClass]?.(node);
  if(["NGAIProvider","NGContextConnector","NGDirectorOutput","NGProjectRender"].includes(node.comfyClass)){
    pushOnGrowth(node);
    const changed=node.onConnectionsChange;node.onConnectionsChange=function(...args){const result=changed?.apply(this,args);
      document.dispatchEvent(new CustomEvent("ng-context-changed"));return result;};
  }
}});
