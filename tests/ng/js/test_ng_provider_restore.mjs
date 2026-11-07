import assert from "node:assert/strict";
import {providerRestoreValues,providerSchemaDefaults,configureProviderType} from "../../../js/ng/ng_provider_restore.js";
const defaults={source:"local",provider:"ollama",temperature:.3,top_p:.9,top_k:40,min_p:0,local_model:"",local_type:"stable_diffusion"};
// A file saved before the "Local source" dropdown was removed: the switch sits at index 10 and the
// two encoder fields follow it. Reading must skip the switch, not take it for a model name.
const old=["clip","ollama","","","",true,false,120,512,0,"server","private-model.safetensors","stable_diffusion",""];
const restored=providerRestoreValues({widgets_values:old},defaults);
assert.equal(restored.source,"clip");assert.equal(restored.temperature,.3);assert.equal(restored.top_p,.9);
assert.equal(restored.top_k,40);assert.equal(restored.local_model,"private-model.safetensors");
assert.equal(restored.local_type,"stable_diffusion");
assert.equal(restored.local_backend,undefined,"the removed switch is not restored as a value");
// A file saved by the current build has no switch, so index 10 is the encoder itself.
const withoutSwitch=["clip","ollama","","","",true,false,120,512,0,"private-model.safetensors","stable_diffusion"];
const current0=providerRestoreValues({widgets_values:withoutSwitch},defaults);
assert.equal(current0.local_model,"private-model.safetensors");
assert.equal(current0.local_type,"stable_diffusion");
assert.equal(current0.temperature,.3);
const named={source:"clip",provider:"ollama",temperature:.7,top_k:15};
const current=providerRestoreValues({widgets_values:old,widgets_values_named:named},defaults);
assert.equal(current.temperature,.7);assert.equal(current.top_k,15);assert.equal(current.source,"clip");
const six=providerRestoreValues({widgets_values:["custom","http://localhost:1234","old-model","ENV_KEY",true,false]},defaults);
assert.equal(six.source,"api");assert.equal(six.base_url,"http://localhost:1234");assert.equal(six.model,"old-model");
assert.equal(six.temperature,.3);
const early=providerRestoreValues({widgets_values:old.slice(0,10).concat("")},defaults);
assert.equal(early.source,"clip");assert.equal(early.temperature,.3);
assert.equal(providerRestoreValues({widgets_values:old.slice(0,10).concat([.8,.95,20,0,0,0,1,false,"server","","stable_diffusion",""])},defaults),null,
  "a current positional workflow keeps native assignment including edited sampling settings");
assert.equal(providerRestoreValues({},defaults),null);
const schema=providerSchemaDefaults({input:{required:{temperature:["FLOAT",{default:.3}],top_p:["FLOAT",{default:.9}],
  top_k:["INT",{default:40}],min_p:["FLOAT",{default:0}]},optional:{local_model:[[""],{default:""}]}}});
const late=providerRestoreValues({widgets_values:old},{temperature:"server",top_p:"",top_k:"stable_diffusion",...schema});
assert.equal(late.temperature,.3);assert.equal(late.top_p,.9);assert.equal(late.top_k,40);assert.equal(late.min_p,0);
assert.deepEqual(providerSchemaDefaults({}),{});
class NativeNode{
  constructor(){this.widgets=[{name:"source",value:"local"},{name:"temperature",value:.3},{name:"top_k",value:40}];}
  configure(data){data.widgets_values.push(...Array(8).fill(""));this.widgets[1].value="server";this.widgets[2].value="stable_diffusion";return "native result";}
}
configureProviderType(NativeNode,{input:{required:{source:["STRING",{default:"local"}],temperature:["FLOAT",{default:.3}],top_k:["INT",{default:40}]}}});
const native=new NativeNode();assert.equal(native.configure({widgets_values:[...old]}),"native result");
assert.equal(native.widgets[0].value,"clip");assert.equal(native.widgets[1].value,.3);assert.equal(native.widgets[2].value,40);
const oldDisk=["local",...old.slice(1)];oldDisk[10]="disk";
const olderDefaults={...defaults,local_backend:"server"};
assert.equal(providerRestoreValues({widgets_values:oldDisk},olderDefaults).source,"local","an older running backend keeps its disk switch");
assert.equal(providerRestoreValues({widgets_values:oldDisk},olderDefaults).local_backend,"disk");
const modernDefaults={...defaults};delete modernDefaults.local_backend;
assert.equal(providerRestoreValues({widgets_values:oldDisk},modernDefaults).source,"clip","a current backend migrates the old disk selection");
assert.equal(providerRestoreValues({widgets_values:oldDisk,widgets_values_named:{source:"local",local_backend:"disk",local_model:"disk.safetensors"}},modernDefaults).source,"clip");
console.log("ng provider restore: six-field, source-based, named and current native workflows passed");
