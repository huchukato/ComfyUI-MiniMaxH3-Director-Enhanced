// Stable context accents travel with the serialized color widget; native port colors stay native.
export const PALETTES={
  image:["#6ec8ef","#81a9ef","#8fdcdd","#a1bcec","#669dd0","#a3d3ec","#739dbf","#86b8d5","#b1cbe3"],
  video:["#e8b274","#ecc18b","#d59a69","#d8c277","#e5a08d"],
  audio:["#b38fe3","#d095ce","#a6a1e6","#ceafe8","#ba91be"],
  text:["#7acdbb","#96d3ab","#83b9b2","#abd3c7","#64bcae"]
};

export function autoColor(media,id,used=[]) {
  const palette=PALETTES[media]||PALETTES.text;
  let hash=0;for(const character of String(id))hash=(Math.imul(hash,31)+character.charCodeAt(0))>>>0;
  const start=hash%palette.length;
  return Array.from({length:palette.length},(_,index)=>palette[(start+index)%palette.length]).find((color)=>!used.includes(color))||palette[start];
}

export function contextColor(entry) {
  return /^#[0-9a-f]{6}$/i.test(entry.widgets.color)?entry.widgets.color:autoColor(entry.media,entry.widgets.context_id||entry.widgets.name);
}
