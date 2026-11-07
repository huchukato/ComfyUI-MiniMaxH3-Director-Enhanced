// Preserve connected native Autogrow slots; discard redundant empty tails restored by older workflows.
export function extraContextInputs(inputs) {
  const groups=new Map(), remove=[];
  inputs.forEach((input,index)=>{
    const match=/^context_(text|image|video|audio)\.\w+_(\d+)$/.exec(input.name);
    if(!match)return;
    const entries=groups.get(match[1])||[];entries.push({input,index,ordinal:Number(match[2])});groups.set(match[1],entries);
  });
  for(const entries of groups.values()){
    const last=Math.max(-1,...entries.filter((entry)=>entry.input.link!=null).map((entry)=>entry.ordinal));
    const emptyTail=entries.filter((entry)=>entry.input.link==null&&entry.ordinal>last).sort((a,b)=>a.ordinal-b.ordinal);
    remove.push(...emptyTail.slice(1).map((entry)=>entry.index));
  }
  return remove.sort((a,b)=>b-a);
}

export function compactContextInputs(node) {
  for(const index of extraContextInputs(node.inputs||[]))node.removeInput(index);
  // Slot removal can make the native layout restore drop an empty tail. Keep an accessible next port within the schema limit.
  for(const media of ["text","image","video","audio"]){
    const prefix=`context_${media}.${media}_`,group=(node.inputs||[]).filter((input)=>input.name.startsWith(prefix));
    const last=Math.max(-1,...group.filter((input)=>input.link!=null).map((input)=>Number(input.name.slice(prefix.length))));
    if(last+1<15&&!group.some((input)=>input.link==null&&Number(input.name.slice(prefix.length))>last))
      node.addInput(prefix+(last+1),"NG_CONTEXT");
  }
}
