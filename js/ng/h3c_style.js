// The Context cards' own stylesheet. Every rule is under .h3c, so nothing here reaches the Studio or other nodes.
const CSS = `
.h3c{box-sizing:border-box;width:100%;display:flex;flex-direction:column;gap:10px;padding:2px 2px 6px;color:#E6EAF2;font:13px/1.4 "IBM Plex Sans","Segoe UI",system-ui,sans-serif;user-select:none}
.h3c *{box-sizing:border-box}
.h3c input,.h3c textarea,.h3c pre{user-select:text}
.h3c button,.h3c select,.h3c input,.h3c textarea{font:inherit;color:#E6EAF2}
.h3c-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.h3c-grid{display:grid;gap:10px;min-width:0}
.h3c-grow{flex:1 1 auto}
.h3c-box{border:1px solid #262E3B;border-radius:10px;background:#161B24;padding:10px 12px;display:flex;flex-direction:column;gap:6px;min-width:0}
.h3c-cap{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#9AA4B5;min-height:22px}
.h3c-lbl{font-size:12px;color:#9AA4B5}
.h3c-hint{font-size:12px;color:#8E98AA;line-height:1.45}
.h3c-warn{color:#F2B98A}
.h3c-btn{min-height:30px;padding:0 10px;border-radius:8px;border:1px solid #344055;background:#1E2633;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;white-space:nowrap;font-size:12px}
.h3c-btn:hover{background:#273142;border-color:#46546C}
.h3c-btn:disabled{opacity:.45;cursor:not-allowed}
.h3c-btn.ai{border-color:#4B3F78;background:#1F1A33;color:#D6C8FF}
.h3c-btn.ai:hover:not(:disabled){background:#2A2346}
.h3c-in{background:#0E1117;border:1px solid #2E3848;border-radius:8px;min-height:30px;padding:0 8px;min-width:0}
.h3c-in:focus{outline:2px solid #8FC1FF;outline-offset:1px}
textarea.h3c-in{padding:8px 10px;line-height:1.45;resize:vertical;width:100%}
.h3c-chk{display:flex;align-items:center;gap:8px;min-height:26px;cursor:pointer;border:0;background:transparent;padding:0 4px;text-align:left;border-radius:6px;width:100%}
.h3c-chk:hover{background:#1C2330}
.h3c-box-i{width:16px;height:16px;border-radius:4px;border:1.5px solid #4A5871;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;font-size:11px;line-height:1}
.h3c-box-i.on{background:#3D7BF0;border-color:#3D7BF0;color:#fff}
.h3c-radio{display:flex;align-items:center;gap:8px;min-height:28px;cursor:pointer;border:1px solid transparent;background:transparent;padding:0 8px;text-align:left;border-radius:8px;width:100%}
.h3c-radio:hover{background:#1C2330}
.h3c-radio.on{border-color:#3D7BF0;background:#16233D}
.h3c-rd{width:14px;height:14px;border-radius:50%;border:1.5px solid #4A5871;flex:0 0 auto;position:relative}
.h3c-radio.on .h3c-rd{border-color:#8FC1FF}
.h3c-radio.on .h3c-rd::after{content:"";position:absolute;inset:3px;border-radius:50%;background:#8FC1FF}
.h3c-segs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border:1px solid #2E3848;border-radius:8px;overflow:hidden}
.h3c-segs button{border:0;background:#0E1117;min-height:26px;cursor:pointer;font-size:12px;color:#9AA4B5}
.h3c-segs button+button{border-left:1px solid #2E3848}
.h3c-segs button.on{background:#3D7BF0;color:#fff}
.h3c-badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 10px;font-size:12px;border:1px solid #3A475D;color:#9AA4B5;white-space:nowrap}
.h3c-badge.done{border-color:#6B5A1E;color:#F2D27A}
.h3c-preview{position:relative;border-radius:10px;overflow:hidden;background:#0E1117;border:1px solid #262E3B;display:flex;align-items:center;justify-content:center;min-height:calc(180px + var(--h3c-grow,0px))}
.h3c-preview img,.h3c-preview video{display:block;width:100%;height:calc(260px + var(--h3c-grow,0px));object-fit:contain}
.h3c-cornertag{position:absolute;left:8px;bottom:8px;font-size:12px;background:rgba(0,0,0,.6);padding:2px 8px;border-radius:6px}
.h3c-wave{position:relative;height:calc(72px + var(--h3c-grow,0px));border-radius:8px;background:#0E1117;border:1px solid #262E3B;overflow:hidden;cursor:crosshair;touch-action:none}
.h3c-wave canvas{position:absolute;inset:0;width:100%;height:100%}
.h3c-sel{position:absolute;top:0;bottom:0;background:rgba(143,193,255,.14);border-left:2px solid #8FC1FF;border-right:2px solid #8FC1FF;pointer-events:none}
.h3c-strip{position:relative;height:28px;border-radius:8px;background:repeating-linear-gradient(90deg,#1A2130 0 18px,#141922 18px 36px);border:1px solid #262E3B;cursor:crosshair;touch-action:none}
.h3c-strip .h3c-sel{background:rgba(230,190,87,.2);border-color:#E6BE57}
.h3c-strip.sound{height:48px;background:#0E1117}
.h3c-strip canvas{position:absolute;inset:0;width:100%;height:100%}
.h3c-head{position:absolute;top:-4px;bottom:-4px;width:14px;margin-left:-7px;cursor:ew-resize;touch-action:none;z-index:2}
.h3c-head::after{content:"";position:absolute;left:6px;top:0;bottom:0;width:2px;background:#F5F7FA;box-shadow:0 0 0 1px rgba(0,0,0,.55)}
.h3c-head::before{content:"";position:absolute;left:2px;top:0;width:10px;height:8px;border-radius:2px;background:#F5F7FA}
.h3c-ins{min-height:28px;border-radius:8px;border:1px solid;background:transparent;cursor:pointer;font-size:12px;display:flex;align-items:center;gap:8px;padding:0 10px;text-align:left}
.h3c-ins:hover{filter:brightness(1.25)}
.h3c-use{display:flex;align-items:center;gap:6px;font-size:12px;color:#B4BDCC;border-top:1px solid #262E3B;padding-top:8px;flex-wrap:wrap}
.h3c-pill{border:1px solid #3A475D;border-radius:999px;padding:1px 8px;font-size:11px;color:#C9D1DE}
.h3c-suggest{border-color:#4B3F78;background:#1B1730}
.h3c-swatch{width:22px;height:22px;border-radius:6px;border:1px solid #2E3848;flex:0 0 auto;padding:0;cursor:pointer}
.h3c-editor{font-family:"IBM Plex Mono",Consolas,monospace;font-size:13px;height:calc(190px + var(--h3c-grow,0px));min-height:120px}
.h3c-btn.on{border-color:#3D7BF0;background:#16233D;color:#CFE0FF}
.h3e-back{position:fixed;inset:0;z-index:10000;background:rgba(5,8,14,.72);display:flex;align-items:center;justify-content:center}
.h3e{background:#10151E;border:1px solid #2E3848;border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:10px;color:#E6EAF2;
  font:13px/1.4 "IBM Plex Sans","Segoe UI",system-ui,sans-serif;max-width:min(1320px,96vw);max-height:94vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.h3e-tabs{display:flex;gap:6px}
.h3e-body{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}
.h3e-stage{flex:0 0 auto;border-radius:10px;overflow:hidden;background:#0B0F16;line-height:0}
.h3e-view{display:block;touch-action:none}
.h3e-tools{flex:1 1 320px;display:flex;flex-direction:column;gap:10px;min-width:300px;max-width:420px}
.h3e-tools input[type=range]{width:120px}
.h3e-result{max-width:100%;max-height:300px;object-fit:contain;border-radius:8px;background:#0B0F16}
`;

export function ensureCardStyle() {
  if (document.getElementById("h3c-style")) return;
  const style = document.createElement("style");
  style.id = "h3c-style";
  style.textContent = CSS;
  document.head.append(style);
}
