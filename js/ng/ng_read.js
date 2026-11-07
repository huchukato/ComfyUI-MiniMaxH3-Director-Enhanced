import {contextId} from "./ng_widgets.js";
// Reads what the Director and its context nodes currently say, straight from their widgets, for the live plan panel.

const CONTEXT_PREFIX = "NGContext";

// The provider fields the panel owns and the request needs. Kept as one list because a field that
// is missing here is a setting the user can change and the request never sees - the quietest kind
// of broken. The two native branches below are built separately: they have no provider to talk to.
const PROVIDER_FIELDS = ["provider", "base_url", "model", "api_key_env", "vision", "audio",
                         "timeout_seconds", "max_tokens", "keep_alive", "temperature", "top_p",
                         "top_k", "min_p", "frequency_penalty", "presence_penalty",
                         "seed", "fixed_seed"];

// An older workflow saved six provider values; a new one saves the rest as well. Reading by name
// rather than by position means a workflow stays readable when a field is added, and adding one
// does not shift the meaning of every value behind it.
export function restoredProviderValues(saved) {
  if (!Array.isArray(saved) || saved.length < 6 || !saved[0] || ["local", "api", "clip"].includes(saved[0])) return null;
  const names = ["provider", "base_url", "model", "api_key_env", "vision", "audio"];
  const found = Object.fromEntries(names.map((name, index) => [name, saved[index]]));
  return { source: found.provider === "custom" ? "api" : "local", timeout_seconds: 120,
           max_tokens: 512, keep_alive: 0, ...found };
}

function widgetValues(node) {
  const values = {};
  for (const widget of node.widgets || []) {
    if (widget.name) values[widget.name] = widget.value;
  }
  return values;
}

function mediaOf(node) {
  const type = node.comfyClass || node.type || "";
  return ["NGContextImage", "NGContextVideo", "NGContextAudio", "NGContextText"].includes(type)
    ? type.slice(CONTEXT_PREFIX.length).toLowerCase() : null;
}

export function isContextNode(node) {
  return mediaOf(node) !== null;
}

export function upstreamNode(graph, input) {
  if (!input || input.link == null) return null;
  const link = graph.links?.[input.link] ?? graph.getLink?.(input.link);
  return link ? graph.getNodeById(link.origin_id) : null;
}

// The context nodes wired into the Director's autogrow inputs, in socket order.
// The Context nodes behind a Director (through its Connector) or a Connector, in input order.
export function contextNodes(director) {
  if (director.comfyClass === "NGH3Director") {
    const connector = upstreamNode(director.graph, director.inputs?.find((input) => input.name === "context"));
    return connector?.comfyClass === "NGContextConnector" ? contextNodes(connector) : [];
  }
  const found = [];
  for (const input of director.inputs || []) {
    if (!input.name.startsWith("contexts.") && !/^context_(image|video|audio|text)\./.test(input.name)) continue;
    const source = upstreamNode(director.graph, input);
    const media = source && mediaOf(source);
    if (media) found.push({ media, node: source });
  }
  return found;
}

export function readContexts(director) {
  return contextNodes(director).map(({ media, node }) => ({ media, widgets: widgetValues(node) }));
}

export function connectedProvider(node) {
  const direct = upstreamNode(node.graph, node.inputs?.find((input) => input.name === "ai_provider"));
  if (direct?.comfyClass === "NGAIProvider") {
    const config=widgetValues(direct);
    if(config.source==="clip") {
      // A connected encoder wins; an installed one is the fallback. Both reach Generate Text by
      // the same route, so there is no switch to read and no fourth card that could fall out of
      // step with this one.
      const encoder=upstreamNode(direct.graph,direct.inputs?.find((input)=>input.name==="clip"));
      if(!encoder&&!config.local_model)return null;
      const model=encoder?(widgetValues(encoder).clip_name||"Connected CLIP"):config.local_model;
      return {source:"clip",loader_node_id:String(direct.id),model,local_type:config.local_type,
        vision:config.vision,audio:config.audio,max_tokens:config.max_tokens,timeout_seconds:config.timeout_seconds};
    }
    const provider = { schema_version: 2 };
    for (const key of PROVIDER_FIELDS)
      if (config[key] !== undefined) provider[key] = config[key];
    return provider;
  }
  // The Director and the Storyboard take the AI provider of the Context Connector on their "context" input.
  if (node.comfyClass === "NGH3Director" || node.comfyClass === "NGStoryboard") {
    const connector = upstreamNode(node.graph, node.inputs?.find((input) => input.name === "context"));
    return connector ? connectedProvider(connector) : null;
  }
  return null;
}

export function contextProvider(node) {
  const direct=connectedProvider(node);if(direct)return direct;
  const providers=[];
  for(const id of node.outputs?.[0]?.links||[]) {
    const link=node.graph?.links?.[id], target=link&&node.graph.getNodeById(link.target_id);
    if(target?.comfyClass==="NGContextConnector") {
      const provider=connectedProvider(target);if(provider)providers.push(provider);
    }
  }
  const unique=[...new Map(providers.map((provider)=>[JSON.stringify(provider),provider])).values()];
  return unique.length===1?unique[0]:null;
}

export function relatedContexts(node) {
  const found=new Map();
  for(const id of node.outputs?.[0]?.links||[]) {
    const link=node.graph?.links?.[id],target=link&&node.graph.getNodeById(link.target_id);
    if(target?.comfyClass!=="NGContextConnector")continue;
    // Keyed like the plan keys them: cards with an empty Context ID no longer collapse into one (BUG-054).
    for(const entry of readContexts(target))found.set(contextId(entry.widgets,entry.media),entry);
  }
  return [...found.values()];
}

export function readPayload(director) {
  return { director: widgetValues(director), contexts: readContexts(director) };
}
