// Native AI actions queue only the AI loader's upstream graph, independently of H3 rendering.
import { request,nativeAIFingerprint } from "./ng_widgets.js";

export function nativePrompt(output, loaderId, action, payload) {
  const prompt={}, seen=new Set();
  function visit(id) {
    id=String(id);if(seen.has(id))return;seen.add(id);
    const entry=output[id];if(!entry)throw new Error("The AI loader connection is unavailable; reconnect Load CLIP.");
    prompt[id]=entry;
    for(const value of Object.values(entry.inputs||{}))
      if(Array.isArray(value)&&value.length===2&&typeof value[0]==="string"&&Number.isInteger(value[1]))visit(value[0]);
  }
  visit(loaderId);
  let id="ng_ai_action";while(id in output)id+="_";
  prompt[id]={class_type:"NGAIRequest",inputs:{ai_provider:[String(loaderId),0],action,request_json:JSON.stringify(payload)}};
  return prompt;
}

async function cancelPrompt(api,id) {
  if(!id)return;
  const options={method:"POST",headers:{"Content-Type":"application/json"}};
  await api.fetchApi("/queue",{...options,body:JSON.stringify({delete:[id]})});
  await api.fetchApi("/interrupt",{...options,body:JSON.stringify({prompt_id:id})});
}

async function nativeAction(app,api,action,payload,signal) {
  const graph=await app.graphToPrompt();
  if(signal?.aborted)throw new Error("AI action cancelled.");
  const prompt=nativePrompt(graph.output,payload.provider.loader_node_id,action,payload);
  const queued=await api.queuePrompt(0,{output:prompt,workflow:graph.workflow});
  const id=queued.prompt_id;
  if(!id)throw new Error("ComfyUI did not accept the AI job.");
  const deadline=Date.now()+(payload.provider.timeout_seconds||120)*1000;
  return new Promise((resolve,reject)=>{
    let timer=null,done=false;
    function finish(error,suggestion) {
      if(done)return;done=true;clearTimeout(timer);
      signal?.removeEventListener("abort",abort);
      for(const name of ["execution_error","execution_interrupted","executed"])api.removeEventListener(name,receive);
      if(error)reject(error);else resolve({ok:true,suggestion});
    }
    async function abort(){try{await cancelPrompt(api,id);finish(new Error("AI action cancelled."));}catch(error){finish(error);}}
    function receive(event) {
      const data=event.detail;if(data?.prompt_id!==id)return;
      if(data.output?.ng_suggestion)finish(null,data.output.ng_suggestion[0]);
      else if(event.type==="execution_error")finish(new Error(data.exception_message||"The connected CLIP could not generate a valid AI suggestion."));
      else if(event.type==="execution_interrupted")finish(new Error("AI action interrupted."));
    }
    async function poll() {
      if(done)return;
      try {
        if(Date.now()>deadline){await cancelPrompt(api,id);finish(new Error("AI timed out; increase Timeout or choose a smaller model."));return;}
        const response=await api.fetchApi("/history/"+encodeURIComponent(id)),history=(await response.json())[id];
        if(history){
          const result=Object.values(history.outputs||{}).find((entry)=>entry.ng_suggestion);
          if(result){finish(null,result.ng_suggestion[0]);return;}
          const failure=(history.status?.messages||[]).find(([type])=>["execution_error","execution_interrupted"].includes(type));
          if(failure){finish(new Error(failure[1].exception_message||"AI action interrupted."));return;}
          if(history.status?.completed){finish(new Error("The AI job finished without a suggestion."));return;}
        }
      }catch(error){finish(error);return;}
      if(!done)timer=setTimeout(poll,1000);
    }
    for(const name of ["execution_error","execution_interrupted","executed"])api.addEventListener(name,receive);
    signal?.addEventListener("abort",abort,{once:true});
    if(signal?.aborted)abort();else poll();
  });
}

// Each action names its own endpoint; only Analyze falls back to /ng/analyze, so a misrouted action cannot hand back a
// field suggestion where shots or a prompt were expected.
const ENDPOINTS = { direct: "/ng/direct", write: "/ng/write_part", build: "/ng/build_plan", storyboard: "/ng/storyboard_texts" };

export async function aiAction(app,api,action,payload,signal) {
  if(payload.provider.source==="clip") {
    const loader=app.graph.getNodeById(payload.provider.loader_node_id),before=loader&&nativeAIFingerprint(loader);
    const result=await nativeAction(app,api,action,payload,signal);
    if(loader&&before===nativeAIFingerprint(loader)) {
      loader.properties.ng_ai_test={fingerprint:before,action,media:payload.media||"project"};
      document.dispatchEvent(new CustomEvent("ng-ai-tested",{detail:{node_id:loader.id}}));
    }
    return result;
  }
  return request(api,ENDPOINTS[action]||"/ng/analyze",payload,signal);
}
