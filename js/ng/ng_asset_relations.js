import {element,values,applyValues,contextId} from "./ng_widgets.js";
import {section} from "./ng_editor_fields.js";
import {relatedContexts} from "./ng_read.js";

export function assetSubjects(entry){
  try {const value=JSON.parse(entry?.widgets?.subject_ids||"[]");return Array.isArray(value)?value.filter(id=>typeof id==="string"):[];}
  catch{return [];}
}

export function referenceSubject(entry){
  const widgets=entry?.widgets||{};
  if(entry?.media!=="image"||!String(widgets.source||widgets.image||"").trim()||assetSubjects(entry).length)return false;
  try {const usages=widgets.usage_roles?JSON.parse(widgets.usage_roles):[widgets.usage||"reference"];return usages.includes("reference");}
  catch{return false;}
}

export function assetChoices(entries,current=[],selfId=""){
  const choices=new Map();
  // An empty Context ID field gets the id the plan gives it (BUG-051), so a figure card without one is offered too.
  for(const entry of entries||[]){const id=contextId(entry.widgets,entry.media);
    if(referenceSubject(entry)&&id!==selfId)choices.set(id,{id,name:entry.widgets.name||"Subject"});}
  for(const id of current)if(!choices.has(id))choices.set(id,{id,name:id+" (not connected or not a Subject)"});
  return [...choices.values()];
}

export function relationNames(entry,entries){
  const names=new Map(entries.map(item=>[contextId(item.widgets,item.media),item.widgets.name||contextId(item.widgets,item.media)]));
  return assetSubjects(entry).map(id=>names.get(id)||id).join(" + ");
}

export function restoreAssetWidget(node){
  const field=node.widgets?.find(widget=>widget.name==="subject_ids");
  // Before this field existed, an upload/DOM placeholder occupied this saved array position.
  if(field&&(field.value==null||["image","video","audio"].includes(field.value)))field.value="";
}

export function assetPanel(node){
  if(!node.widgets?.some(widget=>widget.name==="subject_ids"))return null;
  const root=section("Subject assignment"),list=element("div"),note=element("small","ng-muted");root.append(list,note);
  let fingerprint="";
  return {root,sync(){
    const now=values(node),current=assetSubjects({widgets:now}),entries=relatedContexts(node);
    const choices=assetChoices(entries,current,now.context_id),next=JSON.stringify([current,choices]);
    note.textContent=current.length?"This reference belongs to the selected Subjects.":"Independent reference · select a Subject to link this asset.";
    if(next===fingerprint)return;fingerprint=next;list.replaceChildren();
    for(const choice of choices){
      const row=element("label","ng-option-row"),input=element("input");input.type="checkbox";
      input.setAttribute("aria-label","Assign asset to "+choice.name);input.checked=current.includes(choice.id);
      input.onchange=()=>{const ids=assetSubjects({widgets:values(node)});
        applyValues(node,{subject_ids:JSON.stringify(input.checked?[...new Set([...ids,choice.id])]:ids.filter(id=>id!==choice.id))});node.graph?.change();};
      row.append(input,element("span","",choice.name));list.append(row);
    }
  }};
}
