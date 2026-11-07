// Stable IDs retain the relationship when a visible context name is changed.
import { contextColor } from "./ng_identity.js";
import { caseFold } from "./ng_casefold.js";
const escape=(value)=>value.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
const namePattern=(names)=>[...new Set([...names,...[...names].map(caseFold)])].sort((a,b)=>b.length-a.length).map(escape);
function hasSoundtrack(entry){try{return JSON.parse(entry?.widgets.context_options||"{}").video_audio==="reference";}catch{return false;}}

export function renameReferences(text,previous,entries) {
  const current=new Map(entries.map((entry)=>[entry.widgets.context_id,entry.widgets.name]));
  const replacements=new Map(Object.entries(previous||{}).filter(([id,name])=>name&&current.get(id)&&name!==current.get(id))
    .map(([id,name])=>[caseFold(name),current.get(id)]));
  if(!replacements.size)return text;
  const names=Object.entries(previous||{}).filter(([,name])=>name&&replacements.has(caseFold(name))).map(([,name])=>name);
  const pattern=new RegExp(`@(${namePattern(names).join("|")})(?![\\p{L}\\p{N}_])`,"giu");
  return text.replace(pattern,(match,name)=>replacements.has(caseFold(name))?"@"+replacements.get(caseFold(name)):match);
}

// Names are remembered as soon as a Context is seen, not only after a first change: a rename needs the old name.
export function knownNames(previous,entries) {
  const names={...(previous||{})};
  for(const entry of entries)if(entry.widgets.context_id&&entry.widgets.name&&!(entry.widgets.context_id in names))names[entry.widgets.context_id]=entry.widgets.name;
  return names;
}

// A Text card keeps its note and its built prompt; a rename reaches the shown text and both kept versions.
export function followNoteRenames(properties,text,entries) {
  const previous=properties.ng_context_names||{};
  for(const key of ["ng_text_note","ng_text_ai"])if(typeof properties[key]==="string")properties[key]=renameReferences(properties[key],previous,entries);
  properties.ng_context_names=Object.fromEntries(entries.filter((entry)=>entry.widgets.context_id&&entry.widgets.name).map((entry)=>[entry.widgets.context_id,entry.widgets.name]));
  return renameReferences(text,previous,entries);
}

export function referenceParts(text,entries) {
  const names=new Map();
  const originals=[];
  for(const entry of entries) for(const name of [entry.widgets.name,entry.widgets.context_id]) if(name){names.set(caseFold(name),entry);originals.push(name);}
  const known=namePattern(originals);
  const pattern=new RegExp(`@(${[...known,"[\\p{L}\\p{N}_-]+"].join("|")})(?![\\p{L}\\p{N}_])`,"giu");
  const result=[];let cursor=0;
  for(const match of text.matchAll(pattern)) {
    result.push({text:text.slice(cursor,match.index)});
    result.push({text:match[0],entry:names.get(caseFold(match[1])),unknown:!names.has(caseFold(match[1]))});
    cursor=match.index+match[0].length;
  }
  result.push({text:text.slice(cursor)});return result;
}

export function renderReferences(root,text,entries,element) {
  root.replaceChildren();
  for(const part of referenceParts(text,entries)) {
    const span=element("span",part.unknown?"ng-reference-unknown":part.entry?"ng-text-token":"",part.text);
    if(part.entry){span.title=`${part.entry.widgets.name} · ${part.entry.widgets.context_id}`;
      span.style.color=contextColor(part.entry);}
    if(part.unknown)span.title="Connect a context with this name or ID.";
    root.append(span);
  }
}

export function compiledParts(text,refs,entries,promptLabels) {
  const byId=new Map(entries.map((entry)=>[entry.widgets.context_id,entry]));
  const counters={picture:0,video:0,audio:0},labels=new Map();
  if(promptLabels)for(const [label,id] of Object.entries(promptLabels))labels.set(label,byId.get(id));
  else {
    // A still-running older Python backend supplies refs without compiler display metadata.
    for(const ref of (refs||[]).filter(ref=>ref.kind==="picture")){
      const number=++counters.picture;labels.set(`<Picture ${number}>`,byId.get(ref.ctx_id));labels.set(`<Subject ${number}>`,byId.get(ref.ctx_id));
    }
    for(const ref of (refs||[]).filter(ref=>ref.kind==="video")){
      const entry=byId.get(ref.ctx_id);labels.set(`<Video ${++counters.video}>`,entry);
      if(hasSoundtrack(entry))labels.set(`<Audio ${++counters.audio}>`,entry);
    }
    for(const ref of (refs||[]).filter(ref=>ref.kind==="audio"))labels.set(`<Audio ${++counters.audio}>`,byId.get(ref.ctx_id));
  }
  const result=[];let cursor=0;
  for(const match of text.matchAll(/<(Picture|Video|Audio|Subject) (\d+)>/g)) {
    result.push({text:text.slice(cursor,match.index)});
    const entry=labels.get(match[0]);
    result.push({text:match[0],entry});cursor=match.index+match[0].length;
  }
  result.push({text:text.slice(cursor)});return result;
}

export function renderCompiled(root,chunk,entries,view,element) {
  root.replaceChildren();
  if(view==="plain"){root.textContent=chunk.prompt;return;}
  for(const part of compiledParts(chunk.prompt,chunk.refs,entries,chunk.prompt_labels)) {
    const span=element("span",part.entry?"ng-text-token":"",part.text);
    if(part.entry){span.style.color=view==="syntax"?"#99d4ff":contextColor(part.entry);
      span.title=`${part.entry.widgets.name} · ${part.entry.widgets.context_id} · ${part.entry.widgets.usage}`;}
    root.append(span);
  }
}
