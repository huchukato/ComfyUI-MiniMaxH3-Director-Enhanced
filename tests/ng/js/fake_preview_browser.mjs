// Independent deterministic browser fixture. Only product modules may be loaded by tests.
import { Buffer } from "node:buffer";

export function installPreviewBrowser() {
  let now = 0, nextHandle = 1;
  const raf = new Map(), timers = new Map(), extensions = [], listeners = new Map();
  const urls = new Map(), revoked = [], draws = [];
  class Element {
    constructor(tag) {
      this.tagName = tag.toUpperCase(); this.children = []; this.style = {setProperty(name,value){this[name]=value;}}; this.dataset = {};
      this.attributes = {}; this.className = ""; this.hidden = false; this.textContent = "";
      this.width = this.naturalWidth = 512; this.height = this.naturalHeight = 256;
      this.complete = true; this._src = ""; this.listeners = new Map();
    }
    set src(value) { this._src = String(value); this.attributes.src = this._src; if (!this._preloading) draws.push({now,src:this._src,element:this}); }
    get src() { return this._src; }
    append(...nodes) { for (const node of nodes) { node.parentNode = this; this.children.push(node); } }
    appendChild(node) { this.append(node); return node; }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    setAttribute(name, value) { this.attributes[name] = String(value); if (name === "src") this.src = value; }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; if (name === "src") this._src = ""; }
    remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((n)=>n!==this); }
    addEventListener(name, listener) { const a=this.listeners.get(name)||[]; a.push(listener); this.listeners.set(name,a); }
    removeEventListener(name, listener) { this.listeners.set(name,(this.listeners.get(name)||[]).filter((fn)=>fn!==listener)); }
    decode() { return Promise.resolve(); }
    getContext() { return {drawImage:(image)=>draws.push({now,src:image.src,element:this}),clearRect(){},fillRect(){}}; }
  }
  class FakeBlob { constructor(parts, options={}) { this.parts=parts; this.type=options.type||""; } }
  const app = {graph:{_nodes:[]},registerExtension(extension){extensions.push(extension);}};
  const api = {
    addEventListener(name,fn){const a=listeners.get(name)||[];a.push(fn);listeners.set(name,a);},
    removeEventListener(name,fn){listeners.set(name,(listeners.get(name)||[]).filter((listener)=>listener!==fn));},
  };
  globalThis.document = {createElement:(tag)=>new Element(tag),head:new Element("head"),body:new Element("body"),getElementById(){return null;}};
  globalThis.window = {comfyAPI:{app:{app},api:{api}}};
  globalThis.Image = class extends Element {constructor(){super("img");this._preloading=true;}};
  globalThis.Blob = FakeBlob;
  globalThis.atob = (data)=>Buffer.from(data,"base64").toString("binary");
  globalThis.btoa = (data)=>Buffer.from(data,"binary").toString("base64");
  Object.defineProperty(globalThis,"performance",{configurable:true,value:{now:()=>now}});
  globalThis.requestAnimationFrame = (fn)=>{const id=nextHandle++;raf.set(id,fn);return id;};
  globalThis.cancelAnimationFrame = (id)=>raf.delete(id);
  const timer = (fn,ms,repeat)=>{const id=nextHandle++;timers.set(id,{fn,ms,repeat,at:now+Number(ms)});return id;};
  globalThis.setTimeout = (fn,ms=0)=>timer(fn,ms,false);
  globalThis.setInterval = (fn,ms)=>timer(fn,ms,true);
  globalThis.clearTimeout = globalThis.clearInterval = (id)=>timers.delete(id);
  URL.createObjectURL = (blob)=>{const url=`blob:fixture-${nextHandle++}`;urls.set(url,blob);return url;};
  URL.revokeObjectURL = (url)=>{revoked.push(url);urls.delete(url);};
  function tick(ms) {
    if(ms<now)throw new Error("The clock is monotonic");
    now=ms;
    for(const [id,t] of [...timers])if(t.at<=now){if(t.repeat)t.at=now+t.ms;else timers.delete(id);t.fn();}
    const batch=[...raf];raf.clear();for(const [,fn]of batch)fn(now);
  }
  function label(src) {
    const blob=urls.get(src);
    if(blob) {
      const chunks=blob.parts.map((part)=>typeof part==="string"?Buffer.from(part):ArrayBuffer.isView(part)?Buffer.from(part.buffer,part.byteOffset,part.byteLength):Buffer.from(part));
      return Buffer.concat(chunks).toString();
    }
    return src.startsWith("data:")?Buffer.from(src.split(",",2)[1],"base64").toString():src;
  }
  return {app,api,extensions,raf,timers,urls,revoked,draws,Element,tick,label,
    get now(){return now;},
    emit(name,detail){return Promise.all((listeners.get(name)||[]).map((fn)=>fn({detail})));},
    images(root=document.body){return [root,...root.children.flatMap((child)=>this.images(child))].filter((n)=>n.tagName==="IMG");},
    frames(prefix,count){return Array.from({length:count},(_,i)=>Buffer.from(`${prefix}${i}`).toString("base64"));},
    advance(ms,step=1000/60){for(let t=now+step;t<ms;t+=step)tick(t);tick(ms);},
  };
}
