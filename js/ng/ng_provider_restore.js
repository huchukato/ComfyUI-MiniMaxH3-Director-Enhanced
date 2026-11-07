// Restore native widget meanings when new AI settings are inserted before older local-model fields.
import {restoredProviderValues} from "./ng_read.js";

const SOURCE_FIELDS=["source","provider","base_url","model","api_key_env","vision","audio","timeout_seconds","max_tokens","keep_alive"];
const LOCAL_FIELDS=["local_model","local_type"];

export function providerSchemaDefaults(nodeData){
  const fields={...nodeData?.input?.required,...nodeData?.input?.optional};
  return Object.fromEntries(Object.entries(fields).filter(([,input])=>input[1]&&Object.hasOwn(input[1],"default"))
    .map(([name,input])=>[name,input[1].default]));
}

export function restoreProviderFields(node,restored){
  if(restored)for(const entry of node.widgets||[])if(Object.hasOwn(restored,entry.name))entry.value=restored[entry.name];
}

export function configureProviderType(nodeType,nodeData){
  const defaults=providerSchemaDefaults(nodeData),configure=nodeType.prototype.configure;
  nodeType.ng_provider_defaults=defaults;
  nodeType.prototype.configure=function(data,...args){
    // Current ComfyUI rewrites widgets_values during configure; read the original layout first.
    const restored=providerRestoreValues(data,defaults);
    const result=configure.call(this,data,...args);
    restoreProviderFields(this,restored);
    return result;
  };
}

export function providerRestoreValues(data,defaults){
  const saved=data?.widgets_values,named=data?.widgets_values_named;
  const legacy=restoredProviderValues(saved);
  const hasNames=named&&typeof named==="object"&&!Array.isArray(named);
  let positional=null;
  // A saved workflow holds the ten source fields, then two for the installed encoder. The old
  // layout put a "Local source" dropdown (server/disk) at index 10, so a file saved by that build
  // still has to open: its value is recognised and stepped over rather than read as a model name.
  // Both layouts are accepted: the old one carries the switch at index 10, the new one is two
  // values shorter. Keying on the switch alone would throw away everything a workflow saved by the
  // current build had set, which is why the plain length is a valid case too.
  if(Array.isArray(saved)&&["local","api","clip"].includes(saved[0])&&
     (saved.length<=10||(saved.length<=12||(saved.length<=14&&["server","disk",""].includes(saved[10]))))){
    const fields=[...SOURCE_FIELDS,...LOCAL_FIELDS];
    const tail=saved.slice(10);
    const values=["server","disk"].includes(tail[0])?[...saved.slice(0,10),...tail.slice(1)]:saved;
    positional=Object.fromEntries(fields.filter((_,index)=>index<values.length).map((name,index)=>[name,values[index]]));
  }
  if(!legacy&&!hasNames&&!positional)return null;
  // Use schema defaults: asynchronous nodeCreated can run after positional Configure already assigned old values.
  const restored={...defaults,...positional,...(hasNames?named:{}),...legacy};
  const oldBackend=hasNames?named.local_backend:saved?.[10];
  if(Object.hasOwn(defaults,"local_backend")&&["server","disk"].includes(oldBackend))restored.local_backend=oldBackend;
  if(restored.source==="local"&&oldBackend==="disk"&&!Object.hasOwn(defaults,"local_backend"))restored.source="clip";
  return restored;
}
