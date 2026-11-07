// The Storyboard's own rules on top of the Studio's stylesheet (.h3s), all under .h3b.
const CSS = `
.h3b-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding:16px 20px 20px}
@container (max-width: 980px){.h3b-body{grid-template-columns:minmax(0,1fr)}}
.h3b-stacked .h3b-body{grid-template-columns:minmax(0,1fr)}
.h3b .h3s-card{display:flex;flex-direction:column;gap:12px;padding:14px;border:1px solid #222A37;border-radius:10px;background:#121620;min-width:0}
.h3b-sheet{width:100%;height:auto;border-radius:8px;cursor:pointer;background:#0B1222}
.h3b-stage{width:100%;height:auto;border-radius:6px;background:#141B2B;touch-action:none;cursor:grab}
.h3b-stage:active{cursor:grabbing}
.h3b-ai{display:flex;flex-direction:column;gap:8px;border-top:1px solid #222A37;padding-top:12px}
.h3b-picker{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid #2E3848;border-radius:8px;background:#0E1117}
.h3b-thumbs{display:flex;flex-wrap:wrap;gap:8px}
.h3b-thumb{display:flex;flex-direction:column;align-items:center;gap:4px;width:96px;padding:4px;border:1px solid #2E3848;border-radius:8px;background:#151B26;cursor:pointer}
.h3b-thumb:hover{border-color:#8FC1FF}
.h3b-thumb img{width:86px;height:64px;object-fit:contain;background:#0B0E14;border-radius:4px}
.h3b-thumb span{font-size:11px;max-width:86px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.h3b-names{display:flex;flex-direction:column;max-height:180px;overflow:auto;gap:2px}
.h3b-name{text-align:left;padding:4px 8px;border:0;border-radius:6px;background:transparent;cursor:pointer;font-size:12px}
.h3b-name:hover{background:#1E2633}
.h3b-layers{display:flex;flex-direction:column;gap:4px}
.h3b-layer{display:flex;align-items:center;gap:6px;padding:4px 6px;border:1px solid #222A37;border-radius:8px;cursor:pointer}
.h3b-layer.on{border-color:#8FC1FF;background:#16202E}
.h3b-kind{font-size:11px;color:#9AA4B5;width:52px}
.h3b-lname{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.h3b-props{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;align-items:end}
.h3b-props input[type=range]{width:100%}
.h3b input[type=color]{width:56px;height:36px;padding:0;border:1px solid #2E3848;border-radius:8px;background:#0E1117}
`;

export function ensureBoardStyle() {
  if (document.getElementById("h3b-style")) return;
  const style = document.createElement("style");
  style.id = "h3b-style";
  style.textContent = CSS;
  document.head.append(style);
}
