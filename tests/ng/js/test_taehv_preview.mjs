import assert from "node:assert/strict";
import {test} from "node:test";
import {installPreviewBrowser} from "./fake_preview_browser.mjs";

const product = (name) => new URL("../../../js/" + name, import.meta.url).href;
const {createFramePlayer, createPreviewPanel} = await import(product("minimax_preview_player.js"));
const {previewValues, PREVIEW_DEFAULTS, PREVIEW_FIELDS, configurePreviewType, migratePreviewInfo} = await import(product("minimax_preview_migrate.js"));
const old = ["latent2rgb (fast)", "node", 1024, 24, 12, 80, 1, 25, true, "true speed"];
const expected = {max_resolution:1024,preview_fps:12,jpeg_quality:80,every_n_steps:1,max_preview_overhead:25,suppress_default_preview:true};
const payload = (b, prefix="A", count=120, duration=5, fps=24, sequence="shot_a", run="run_a") => ({node_id:"7",run_id:run,sequence_id:sequence,frames:b.frames(prefix,count),duration,fps,source_fps:24,step:1,total_steps:20,ms:10,decoder:"TAEHV"});
const fixture = () => { const b=installPreviewBrowser(), image=document.createElement("img"), statuses=[];
  const player=createFramePlayer({image,onStatus:(text)=>statuses.push(text)});return {b,image,player,statuses,label:()=>b.label(image.src)}; };

test("legacy, misplaced playback and pre-playback positional values preserve their meanings",async()=>{
  assert.deepEqual(previewValues({widgets_values:old}),expected);
  assert.deepEqual(previewValues({widgets_values:old.slice(0,9)}),expected);
  assert.deepEqual(previewValues({widgets_values:[...old.slice(0,5),"true speed",...old.slice(5,9)]}),expected);
  assert.deepEqual(previewValues({widgets_values:["vae (quality)",...old.slice(1)]}),expected);
});

test("named settings win, current false/zero values survive and removed enabled is discarded",async()=>{
  assert.deepEqual(previewValues({widgets_values:old,widgets_values_named:{max_resolution:512,preview_fps:6,jpeg_quality:95}}),{...expected,max_resolution:512,preview_fps:6,jpeg_quality:95});
  const current={...PREVIEW_DEFAULTS,max_preview_overhead:0,suppress_default_preview:false};
  assert.deepEqual(previewValues({widgets_values:PREVIEW_FIELDS.map((name)=>current[name])}),current);
  assert.deepEqual(previewValues({widgets_values:[false,...PREVIEW_FIELDS.map((name)=>current[name])]}),current);
  assert.deepEqual(previewValues({}),PREVIEW_DEFAULTS);
});

function connectedNode(linkKind="object") {
  const names=["model","vae","decode","preview_target","max_resolution","preview_frames","preview_fps","webp_quality","every_n_steps","max_preview_overhead","suppress_default_preview","playback"];
  const links={1111:{id:1111,origin_id:1,origin_slot:0,target_id:15,target_slot:0},1112:{id:1112,origin_id:2,origin_slot:0,target_id:15,target_slot:1},1165:{id:1165,origin_id:3,origin_slot:0,target_id:15,target_slot:6},1166:{id:1166,origin_id:4,origin_slot:0,target_id:15,target_slot:7}};
  const origins=Object.values(links).map((link)=>({id:link.origin_id,outputs:[{links:[link.id]}]}));
  const graph={links:linkKind==="map"?new Map(Object.entries(links).map(([key,value])=>[Number(key),value])):links,getNodeById:(id)=>origins.find((n)=>n.id===Number(id))};
  const node={id:15,graph,inputs:["model","vae",...PREVIEW_FIELDS].map((name)=>({name,type:name==="model"?"MODEL":name==="vae"?"VAE":"FLOAT",link:null}))};
  const info={id:15,widgets_values:[...old],inputs:names.map((name,i)=>({name,link:({0:1111,1:1112,6:1165,7:1166})[i]??null,...(i>1?{widget:{name}}:{})}))};
  return {node,info,origins,links};
}

for (const kind of ["object","map"]) test(`legacy input slots preserve MODEL, VAE and FPS connections in a ${kind} graph`,async()=>{
  const f=connectedNode(kind),before=JSON.stringify(f.info);const {info,values}=migratePreviewInfo(f.node,f.info);
  assert.deepEqual(values,expected);assert.equal(JSON.stringify(f.info),before,"caller snapshot is not rewritten");
  assert.deepEqual(info.inputs.map((input)=>input.name),["model","vae",...PREVIEW_FIELDS]);
  assert.equal(info.inputs[0].link,1111);assert.equal(info.inputs[3].link,1165);assert.equal(f.links[1165].target_slot,3);
  assert.equal(info.inputs[4].name,"jpeg_quality");assert.equal(info.inputs[4].widget.name,"jpeg_quality");assert.equal(f.links[1166].target_slot,4);
  assert.equal(info.inputs[1].link,1112);assert.deepEqual(f.origins[1].outputs[0].links,[1112]);
  assert.equal(kind==="map"?f.node.graph.links.get(1112).target_slot:f.node.graph.links[1112].target_slot,1);
});

test("actual configure wrapper snapshots values before native configure mutation",async()=>{
  class NativeNode {constructor(){Object.assign(this,connectedNode().node);this.widgets=PREVIEW_FIELDS.map((name)=>({name,value:PREVIEW_DEFAULTS[name]}));}
    configure(info){this.received=info;this.inputs=info.inputs;info.widgets_values.fill("native mutation");this.widgets.forEach((w)=>w.value="wrong");this.onConfigure?.(info);return "native result";}}
  configurePreviewType(NativeNode,{input:{required:{}}});const node=new NativeNode(),info=connectedNode().info;
  assert.equal(node.configure(info),"native result");assert.deepEqual(Object.fromEntries(node.widgets.map((w)=>[w.name,w.value])),expected);
  assert.deepEqual(info.widgets_values,old);assert.equal(node.inputs[3].link,1165);
});

test("removed enabled port disconnects both ends while adding a plain required VAE port",()=>{
  const f=connectedNode("map"),enabled=1199;
  f.node.graph.links.delete(1112);f.origins[1].outputs[0].links=[];
  f.node.graph.links.set(enabled,{id:enabled,origin_id:2,origin_slot:0,target_id:15,target_slot:1});
  f.origins[1].outputs[0].links=[enabled];
  f.info.inputs=[f.info.inputs[0],{name:"enabled",type:"BOOLEAN",widget:{name:"enabled"},link:enabled},
    ...f.info.inputs.filter((input)=>PREVIEW_FIELDS.includes(input.name)||input.name==="webp_quality")];
  f.info.widgets_values=[false,...PREVIEW_FIELDS.map((name)=>expected[name])];
  const migrated=migratePreviewInfo(f.node,f.info);
  assert.deepEqual(migrated.values,expected);assert.ok(!migrated.info.inputs.some((input)=>input.name==="enabled"));
  assert.deepEqual(migrated.info.inputs[1],{name:"vae",type:"VAE",link:null});
  assert.deepEqual(f.origins[1].outputs[0].links,[]);assert.equal(f.node.graph.links.has(enabled),false);
  assert.equal(migrated.info.inputs[0].link,1111);assert.equal(migrated.info.inputs[3].link,1165);
  assert.equal(f.node.graph.links.get(1165).target_slot,3);
  assert.doesNotThrow(()=>JSON.parse(JSON.stringify(migrated.info)));
});

for (const runtimeSlot of [false,true]) test(`native JSON cloning and reload handle ${runtimeSlot?"runtime slots":"wrapped widget getters"} with circular node ownership`,()=>{
  // Installed BaseWidget keeps an enumerable _node and prototype name/value getters.
  // Native Comfy configure JSON-copies its incoming input descriptors before onConfigure.
  class BooleanWidget {
    constructor(node,name,value){this._node=node;this._name=name;this._state={value};this.type="toggle";}
    get name(){return this._name;}get value(){return this._state.value;}set value(value){this._state.value=value;}
  }
  class ComfyNode {
    constructor(){
      const fixture=connectedNode("map");Object.assign(this,fixture.node);this.origins=fixture.origins;
      this.widgets=PREVIEW_FIELDS.map((name)=>new BooleanWidget(this,name,PREVIEW_DEFAULTS[name]));
      this.inputs=["model","vae",...PREVIEW_FIELDS].map((name)=>{
        const slot={name,type:name==="model"?"MODEL":name==="vae"?"VAE":"FLOAT",link:null};
        const widget=this.widgets.find((entry)=>entry.name===name);
        if(runtimeSlot)slot._node=this;
        if(widget)Object.defineProperty(slot,"widget",{enumerable:true,get:()=>widget});
        return slot;
      });
    }
    configure(info){
      this.received=info;
      // This is the real failure boundary: native cloneObject uses JSON serialization.
      this.inputs=JSON.parse(JSON.stringify(info.inputs));
      this.widgets.forEach((widget,index)=>widget.value=info.widgets_values[index]);
      return "native result";
    }
    serialize(){return {id:this.id,type:"MiniMaxH3PreviewOverrideCS",inputs:JSON.parse(JSON.stringify(this.inputs)),
      widgets_values:this.widgets.map((widget)=>widget.value),widgets_values_named:Object.fromEntries(this.widgets.map((widget)=>[widget.name,widget.value]))};}
  }
  configurePreviewType(ComfyNode,{input:{required:{}}});
  const node=new ComfyNode(),original=connectedNode().info;
  original.inputs=original.inputs.filter((input)=>input.name!=="max_preview_overhead");
  const before=JSON.stringify(original);
  assert.equal(node.configure(original),"native result");
  assert.equal(JSON.stringify(original),before,"migration does not modify the caller's saved descriptor");
  assert.deepEqual(Object.fromEntries(node.widgets.map((widget)=>[widget.name,widget.value])),expected);
  assert.equal(node.inputs[0].link,1111);assert.equal(node.inputs[3].link,1165);
  assert.equal(node.graph.links.get(1165).target_slot,3);assert.equal(node.inputs[1].link,1112);
  assert.deepEqual(node.origins[1].outputs[0].links,[1112]);assert.equal(node.inputs[6].widget.name,"max_preview_overhead");
  assert.ok(!Object.hasOwn(node.inputs[6],"_node"));assert.ok(!Object.hasOwn(node.inputs[6].widget,"_node"));
  // Save current settings and reload against fresh runtime slots, like opening the saved graph.
  node.widgets.find((widget)=>widget.name==="suppress_default_preview").value=false;
  node.widgets.find((widget)=>widget.name==="max_preview_overhead").value=0;
  const saved=JSON.parse(JSON.stringify(node.serialize())),links=JSON.parse(JSON.stringify([...node.graph.links]));
  const reloaded=new ComfyNode();reloaded.graph.links=new Map(links);
  assert.equal(reloaded.configure(saved),"native result");
  assert.deepEqual(Object.fromEntries(reloaded.widgets.map((widget)=>[widget.name,widget.value])),{...expected,suppress_default_preview:false,max_preview_overhead:0});
  assert.equal(reloaded.inputs[0].link,1111);assert.equal(reloaded.inputs[3].link,1165);
  assert.equal(reloaded.graph.links.get(1165).target_slot,3);
  assert.deepEqual(reloaded.serialize(),saved);
});

test("24 FPS clock presents every source frame and keeps a five-second duration",async()=>{
  const f=fixture();assert.ok(await f.player.update(payload(f.b)));const shown=new Set([f.label()]);
  for(let t=1000/60;t<5000;t+=1000/60){f.b.tick(t);shown.add(f.label());}
  assert.equal(shown.size,120,"all 24 unique source frames per second are displayed");
  f.b.tick(5000);assert.equal(f.label(),"A0");assert.ok(f.player.state.actualFPS>=23&&f.player.state.actualFPS<=25);
  f.player.dispose();assert.equal(f.b.raf.size,0);assert.equal(f.b.urls.size,0);
});

test("same-sample replacement preserves phase, remaps a resized buffer, rejects a late sample",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",50,5,10));f.b.advance(2000);
  await f.player.update(payload(f.b,"B",50,5,10));assert.equal(f.label(),"B20");
  await f.player.update(payload(f.b,"C",100,5,10));assert.equal(f.label(),"C40");
  await f.player.update(payload(f.b,"D",50,5,10,"shot_b"));assert.equal(f.label(),"D0");
  assert.equal(await f.player.update(payload(f.b,"late",50,5,10)),false);assert.equal(f.label(),"D0");f.player.dispose();
});

test("low frame count retains timeline duration and a delayed callback catches up",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",10,5,24));f.b.advance(1250);assert.equal(f.label(),"A2");
  f.b.tick(3750);assert.equal(f.label(),"A7");f.b.tick(5000);assert.equal(f.label(),"A0");f.player.dispose();
});

test("6 FPS cap and absolute clock avoid a burst after a late browser callback",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",30,5,6));const start=f.b.draws.length;
  f.b.tick(100);assert.equal(f.b.draws.length,start);f.b.tick(180);assert.equal(f.label(),"A1");
  const draws=f.b.draws.length;f.b.tick(2100);assert.equal(f.label(),"A12");assert.equal(f.b.draws.length,draws+1);
  f.player.dispose();
});

test("pause, seek and same-sample update preserve paused time; replay resumes there",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",120,5,24));f.b.advance(1500);f.player.pause();
  const cadence=f.player.state.actualFPS;assert.ok(cadence>=23&&cadence<=25);
  assert.equal(f.b.raf.size,0);f.b.tick(23000);f.player.seek(2.5);assert.equal(f.label(),"A60");
  await f.player.update(payload(f.b,"B",120,5,24));assert.equal(f.label(),"B60");assert.equal(f.player.state.paused,true);
  assert.equal(f.player.state.actualFPS,cadence,"paused scrubbing and updates must not include idle seconds in displayed FPS");
  f.player.play();f.b.advance(23500);assert.equal(f.label(),"B72");f.player.dispose();
});

test("empty/malformed/status payloads preserve buffer; reset rejects old execution",async()=>{
  const f=fixture();await f.player.update(payload(f.b));const first=f.image.src;
  assert.equal(await f.player.update({...payload(f.b),frames:[],status:"Decoding TAEHV…"}),false);assert.equal(f.image.src,first);
  assert.equal(await f.player.update({...payload(f.b),duration:NaN}),false);assert.equal(f.image.src,first);
  await f.player.update({error:"Decoder missing",node_id:"7"});assert.equal(f.player.state.paused,true);assert.equal(f.image.src,first);
  f.player.reset();assert.equal(f.b.urls.size,0);assert.equal(await f.player.update(payload(f.b)),false);
  assert.ok(await f.player.update(payload(f.b,"new",1,1,24,"shot_a","run_b")));assert.equal(f.b.raf.size,0);f.player.dispose();
});

test("real panel buttons and range input control the actual player",async()=>{
  const b=installPreviewBrowser(),panel=createPreviewPanel();await panel.player.update(payload(b));
  assert.equal(panel.button.textContent,"Pause");panel.button.onclick();assert.equal(panel.player.state.paused,true);
  panel.scrub.value="2.5";panel.scrub.oninput();assert.equal(b.label(panel.img.src),"A60");assert.match(panel.time.textContent,/2\.50 \/ 5\.00s/);
  panel.button.onclick();assert.equal(panel.player.state.paused,false);panel.player.dispose();
});

let moduleId=0;
test("real extension routes preview panels, keeps native callbacks and cleans removed nodes",async()=>{
  const b=installPreviewBrowser();await import(product("minimax_preview.js")+`?audit=${moduleId++}`);const extension=b.extensions[0];
  class PreviewNode {constructor(){this.id=7;this.comfyClass="NGH3Preview";this.size=[200,100];this.widgets=PREVIEW_FIELDS.map((name)=>({name,value:PREVIEW_DEFAULTS[name]}));this.inputs=[{name:"model",link:null}];}
    onNodeCreated(){this.nativeCreated=true;} configure(info){this.inputs=info.inputs;this.onConfigure(info);return 42;}
    onConfigure(){this.nativeConfigured=true;} onRemoved(){return "removed";}computeSize(){return [340,420];}
    addDOMWidget(name,_type,root){this.root=root;const w={name};this.widgets.push(w);return w;}setDirtyCanvas(){}}
  await extension.beforeRegisterNodeDef(PreviewNode,{name:"NGH3Preview",input:{required:{}}});const node=new PreviewNode();node.onNodeCreated();b.app.graph._nodes.push(node);await extension.setup();
  assert.equal(node.nativeCreated,true);assert.equal(node.widgets.at(-1).serialize,false);
  assert.equal(node.configure({widgets_values:old,inputs:[{name:"model",link:null},{name:"vae",link:null}]}),42);assert.equal(node.nativeConfigured,true);assert.ok(node.size[1]>=520);
  await b.emit("minimax_h3_preview",{...payload(b),node_id:"70"});assert.equal(node._mmxPreview.player.state.urls.length,0);
  await b.emit("minimax_h3_preview",{...payload(b),node_id:"7.sample"});assert.equal(b.label(node._mmxPreview.img.src),"A0");
  await b.emit("execution_interrupted",{});assert.equal(b.raf.size,0);assert.equal(node._mmxPreview.player.state.paused,true);
  assert.equal(node.onRemoved(),"removed");assert.equal(b.urls.size,0);assert.equal(node._mmxPreview,null);
  for (const name of ["MiniMaxH3PreviewOverrideCS"]) {
    class OtherNode {constructor(){this.id=8;this.comfyClass=name;this.size=[200,100];this.widgets=[];}
      addDOMWidget(widgetName,_type,root){this.root=root;const w={name:widgetName};this.widgets.push(w);return w;}
      computeSize(){return [340,420];}setDirtyCanvas(){}}
    await extension.beforeRegisterNodeDef(OtherNode,{name});const other=new OtherNode();other.onNodeCreated();
    assert.ok(other._mmxPreview,`${name} owns a visible panel`);
    await b.emit("minimax_h3_preview",{...payload(b,"routed",24,1,24),node_id:"8.sample"});
    assert.equal(b.label(other._mmxPreview.img.src),"routed0");other.onRemoved();assert.equal(b.urls.size,0);
  }
  for (const name of ["NGDirectorStudio","NGH3Director","MiniMaxH3DirectorCS","NGRenderSequence","NGProjectRender"]) {
    class InternalNode {constructor(){this.id=9;}onNodeCreated(){this.nativeCreated=true;}
      addDOMWidget(){throw new Error("Only an external Preview node may install a live player");}}
    await extension.beforeRegisterNodeDef(InternalNode,{name});const internal=new InternalNode();internal.onNodeCreated();
    assert.equal(internal.nativeCreated,true);assert.equal(internal._mmxPreview,undefined,`${name} has no live panel`);
    await b.emit("minimax_h3_preview",{...payload(b,"ignored",24,1,24),node_id:"9.sample"});
    assert.equal(b.urls.size,0,"Director and internal render events never allocate images");assert.equal(b.raf.size,0);
  }
});

test("H3 Render Sequence gets its player with the first preview of its own parts",async()=>{
  const b=installPreviewBrowser();await import(product("minimax_preview.js")+`?audit=${moduleId++}`);const extension=b.extensions[0];
  class RenderNode {constructor(id){this.id=id;this.comfyClass="NGProjectRender";this.size=[300,120];this.widgets=[];this.imgs=["still"];this.imageIndex=0;}
    addDOMWidget(name,_type,root){this.root=root;const w={name};this.widgets.push(w);return w;}computeSize(){return [340,420];}setDirtyCanvas(){}}
  const render=new RenderNode(12),other=new RenderNode(13);b.app.graph._nodes.push(render,other);
  b.app.graph.getNodeById=(id)=>b.app.graph._nodes.find((n)=>String(n.id)===String(id));await extension.setup();
  assert.equal(render._mmxPreview,undefined,"no player before a preview arrives");
  await b.emit("minimax_h3_preview",{...payload(b,"part",24,1,24),node_id:"12"});
  assert.ok(render._mmxPreview,"the Render Sequence shows the player");assert.equal(b.label(render._mmxPreview.img.src),"part0");
  assert.equal(render.imgs,null,"native single-frame preview image is cleared");
  assert.deepEqual(render.widgets.at(-1).computeLayoutSize(),{minHeight:240,maxHeight:Number.MAX_SAFE_INTEGER,minWidth:0});
  assert.equal(other._mmxPreview,undefined,"another Render Sequence stays as it is");assert.ok(render.size[1]>=520);
  render.onRemoved();assert.equal(render._mmxPreview,null);assert.equal(b.urls.size,0);
});

function deferredImages() {
  const Original=globalThis.Image,pending=[];let concurrent=0,maxConcurrent=0;
  globalThis.Image=class extends Original {decode(){concurrent++;maxConcurrent=Math.max(concurrent,maxConcurrent);
    return new Promise((resolve,reject)=>{const entry={image:this,settled:false,resolve(){if(!entry.settled){entry.settled=true;concurrent--;resolve();}},reject(){if(!entry.settled){entry.settled=true;concurrent--;reject(new Error("bad JPEG"));}}};pending.push(entry);});}};
  const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
  const drain=async(predicate=()=>true)=>{for(let i=0;i<500;i++){const entries=pending.filter((p)=>!p.settled&&predicate(p));if(!entries.length){await flush();if(!pending.some((p)=>!p.settled&&predicate(p)))return;}for(const p of entries)p.resolve();await flush();}throw new Error("Decode queue did not settle");};
  return {pending,drain,flush,get maxConcurrent(){return maxConcurrent;}};
}

test("decode is bounded to four images and the complete buffer swaps atomically",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",24,1,24));f.b.advance(400);const old=f.image.src;
  const control=deferredImages(),next=f.player.update(payload(f.b,"B",24,1,24));
  assert.equal(control.pending.length,4);assert.equal(f.image.src,old);
  control.pending[0].resolve();await control.flush();assert.equal(f.image.src,old,"one decoded JPEG is not a new buffer");
  f.player.pause();f.player.seek(.5);await control.drain();assert.equal(await next,true);
  assert.equal(f.label(),"B12");assert.equal(f.player.state.paused,true);assert.equal(f.player.state.images.length,24);
  assert.equal(control.maxConcurrent,4);assert.equal(f.b.urls.size,24);f.player.dispose();assert.equal(f.b.urls.size,0);
});

test("a newer pending callback wins; a stale decode cannot restore an older buffer",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",24,1,24));f.b.advance(400);
  const control=deferredImages(),stale=f.player.update(payload(f.b,"B",24,1,24));
  const latest=f.player.update(payload(f.b,"C",24,1,24));assert.equal(f.b.urls.size,48,"old active and latest pending only");
  await control.drain((entry)=>entry.image.src==="");assert.equal(await stale,false);assert.equal(f.label(),"A9");
  f.b.advance(500);await control.drain();assert.equal(await latest,true);assert.equal(f.label(),"C12");
  assert.equal(f.b.urls.size,24);f.player.dispose();
});

test("JPEG failure preserves the active buffer and releases failed URLs and images",async()=>{
  const f=fixture();await f.player.update(payload(f.b,"A",24,1,24));const old=f.image.src;
  const control=deferredImages(),next=f.player.update(payload(f.b,"bad",12,1,24));
  control.pending[0].reject();await control.drain();assert.equal(await next,false);assert.equal(f.image.src,old);
  assert.equal(f.b.urls.size,24);assert.match(f.statuses.at(-1),/could not be read/);
  assert.ok(control.pending.every((p)=>p.image.src===""));f.player.dispose();
});

for (const action of ["reset","dispose","stop"]) test(`${action} prevents a late decode and immediately releases pending resources`,async()=>{
  const f=fixture(),control=deferredImages(),pending=f.player.update(payload(f.b,"late",12,1,24));
  f.player[action]();assert.equal(f.b.urls.size,0);assert.equal(f.b.raf.size,0);
  await control.drain();assert.equal(await pending,false);assert.equal(f.player.state.urls.length,0);assert.equal(f.image.src,"");
  assert.ok(control.pending.every((p)=>p.image.src===""));f.player.dispose();
});

test("successful execution may complete its final JPEG decode without resuming playback",async()=>{
  const f=fixture(),control=deferredImages(),pending=f.player.update(payload(f.b,"last",24,1,24));
  f.player.stop("Render finished",{discardPending:false});await control.drain();assert.equal(await pending,true);
  assert.equal(f.label(),"last0");assert.equal(f.player.state.paused,true);assert.equal(f.b.raf.size,0);
  f.player.play();assert.equal(f.b.raf.size,1);f.player.dispose();
});

test("requested FPS is read separately from effective buffered FPS",async()=>{
  const f=fixture();await f.player.update({...payload(f.b,"A",120,5,12),requested_fps:24});
  assert.equal(f.player.state.requestedFPS,24);f.b.advance(1000);assert.equal(f.label(),"A24");f.player.dispose();
});

test("Director progress handles downstream text only and never registers video events",async()=>{
  const b=installPreviewBrowser(),status={textContent:""},names=[];
  const {attachProgress}=await import(product("ng/ng_studio_progress.js"));
  const add=b.api.addEventListener;b.api.addEventListener=(name,listener)=>{names.push(name);add(name,listener);};
  const progress=attachProgress({id:7},b.api,status,()=>[7,9]);
  assert.ok(!names.includes("minimax_h3_preview"));assert.ok(!names.includes("b_preview_with_metadata"));
  await b.emit("minimax_h3_preview",{...payload(b,"ours",24,1,24),node_id:"9.sample"});
  await b.emit("b_preview_with_metadata",{nodeId:"9.sample",blob:new Blob(["still"])});
  assert.equal(b.urls.size,0);assert.equal(b.raf.size,0);
  await b.emit("progress",{node:"70.sample",value:1,max:2});assert.equal(status.textContent,"");
  await b.emit("progress_text",{nodeId:"9.start",text:"Iteration 1 / 2"});
  await b.emit("progress",{node:"9.sample",value:1,max:2});assert.equal(status.textContent,"Iteration 1 / 2 · 50%");
  progress.planning("Edited plan");assert.equal(status.textContent,"Iteration 1 / 2 · 50%");
  await b.emit("executing","9.sample");await b.emit("executing",null);
  assert.match(status.textContent,/finished/);
  progress.dispose();assert.equal(b.urls.size,0);assert.equal(b.raf.size,0);
  const done=status.textContent;await b.emit("progress",{node:"9.sample",value:2,max:2});assert.equal(status.textContent,done);
});

test("real Director Studio DOM has no live image/player while render text remains",async(t)=>{
  const {installStudioDom,fixture}=await import(new URL("../regressions/studio_fixture.mjs",import.meta.url).href);
  const {openStudio}=await import(product("ng/h3s_studio.js"));installStudioDom();const f=fixture();
  const handlers=new Map(),names=[];
  f.api.addEventListener=(name,fn)=>{names.push(name);handlers.set(name,fn);};f.api.removeEventListener=(name)=>handlers.delete(name);
  const sampler={id:5,comfyClass:"KSampler",outputs:[]},get=f.node.graph.getNodeById;
  f.node.graph.getNodeById=(id)=>Number(id)===5?sampler:get(id);
  f.node.outputs=[{links:[90]}];f.node.graph.links[90]={origin_id:f.node.id,target_id:5};
  const handle=openStudio(f.node,f.app,f.api);t.after(()=>handle.close());
  assert.equal(handle.root.byClass("mmx-preview").length,0);assert.equal(handle.root.byClass("h3s-live").length,0);
  assert.equal(handle.root.byClass("mmx-preview-play").length,0);assert.equal(handle.root.byTag("img").length,0);
  assert.equal(f.node._mmxPreview,undefined);assert.ok(!names.includes("minimax_h3_preview"));assert.ok(!names.includes("b_preview_with_metadata"));
  handlers.get("progress_text")({detail:{nodeId:"5.start",text:"Iteration 1 / 2"}});
  handlers.get("progress")({detail:{node:"5.sample",value:1,max:2}});
  assert.ok(handle.root.byClass("h3s-lbl").some((el)=>el.textContent==="Iteration 1 / 2 · 50%"));
  handlers.get("execution_interrupted")({detail:{node_id:"5"}});
  assert.ok(handle.root.byClass("h3s-lbl").some((el)=>el.textContent==="Render interrupted"));
  handle.close();assert.equal(handlers.size,0);
});

test("real project render panel has no live image/player while render text remains",async()=>{
  const b=installPreviewBrowser(),names=[];
  const add=b.api.addEventListener;b.api.addEventListener=(name,listener)=>{names.push(name);add(name,listener);};
  await import(product("ng/ng_product_nodes.js")+`?audit=${moduleId++}`);
  const extension=b.extensions.find((entry)=>entry.name==="mmxd.ng.product_nodes");assert.ok(extension);
  const node={id:9,comfyClass:"NGProjectRender",size:[480,245],properties:{},widgets:[],
    addDOMWidget(name,_type,root){this.root=root;const widget={name};this.widgets.push(widget);return widget;},
    setSize(size){this.size=size;}};
  extension.nodeCreated(node);
  const elements=(root)=>[root,...root.children.flatMap(elements)],tree=elements(node.root);
  assert.equal(b.images(node.root).length,0);assert.ok(!tree.some((el)=>/mmx-preview|ng-live-preview/.test(el.className)));
  assert.equal(node._mmxPreview,undefined);assert.ok(!names.includes("minimax_h3_preview"));assert.ok(!names.includes("b_preview_with_metadata"));
  await b.emit("minimax_h3_preview",{...payload(b,"ignored",24,1,24),node_id:"9.sample"});
  await b.emit("b_preview_with_metadata",{nodeId:"9.sample",blob:new Blob(["still"])});
  assert.equal(b.urls.size,0);assert.equal(b.raf.size,0);
  const status=tree.find((el)=>el.className==="ng-ai-badge");assert.equal(status.textContent,"Awaiting sequence");
  await b.emit("progress_text",{nodeId:"9.start",text:"Iteration 1 / 3"});
  await b.emit("progress",{node:"9.sample",value:1,max:4});assert.equal(status.textContent,"Iteration 1 / 3 · 25%");
  await b.emit("execution_interrupted",{node_id:"9"});assert.equal(status.textContent,"Render interrupted");
  node.onRemoved();await b.emit("progress",{node:"9.sample",value:4,max:4});assert.equal(status.textContent,"Render interrupted");
});
