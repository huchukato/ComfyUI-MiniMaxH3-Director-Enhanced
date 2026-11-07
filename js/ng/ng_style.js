// One stylesheet for the NG nodes. Colours come from ComfyUI's own variables so it follows the theme.

const CSS = `
.ng-plan { box-sizing: border-box; width: 100%; font: 12px/1.45 var(--font-inter, system-ui, sans-serif); color: var(--input-text, #ddd);
  background: var(--comfy-input-bg, #222); border: 1px solid var(--border-color, #444); border-radius: 6px; padding: 8px; overflow: auto; }
.ng-plan h4 { margin: 0 0 4px; font-size: 12px; font-weight: 600; }
.ng-plan .ng-summary { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-bottom: 6px; }
.ng-plan .ng-pill { padding: 1px 8px; border-radius: 10px; background: var(--comfy-menu-bg, #353535); }
.ng-plan .ng-error { color: #ff7b72; white-space: pre-wrap; }
.ng-plan ul { margin: 0 0 6px; padding-left: 16px; }
.ng-plan li.ng-issue { color: #e3b341; }
.ng-plan details { margin: 2px 0; border-top: 1px solid var(--border-color, #444); padding-top: 2px; }
.ng-plan summary { cursor: pointer; }
.ng-plan .ng-dim { opacity: .65; }
.ng-plan pre { margin: 4px 0; white-space: pre-wrap; font: 11px/1.4 var(--font-mono, monospace); }
.ng-plan .ng-bar { display: flex; height: 8px; margin: 4px 0 8px; border-radius: 4px; overflow: hidden; background: var(--comfy-menu-bg, #353535); }
.ng-plan .ng-seg { height: 100%; border-right: 1px solid var(--comfy-input-bg, #222); }
.ng-card { box-sizing: border-box; width: 100%; padding: 8px; overflow: auto; font: 12px/1.4 system-ui; color: var(--input-text, #ddd); background: var(--comfy-input-bg, #222); border-radius: 6px; }
.ng-card .ng-tools { display: flex; gap: 5px; flex-wrap: wrap; margin: 6px 0; }
.ng-card button, .ng-card input, .ng-card select { font: inherit; color: inherit; background: var(--comfy-menu-bg, #353535); border: 1px solid var(--border-color, #555); border-radius: 4px; padding: 4px 6px; max-width: 100%; }
.ng-card button { cursor: pointer; }
.ng-card button:disabled { opacity: .5; cursor: default; }
.ng-card .ng-status { white-space: pre-wrap; }
.ng-card .ng-thumbnail { max-width: 100%; max-height: 110px; object-fit: contain; display: block; margin: auto; }
.ng-card .ng-waveform { width: 100%; height: 48px; }
.ng-card .ng-media-preview { white-space: pre-wrap; max-height: 130px; overflow: auto; }
.ng-card label { display: flex; gap: 6px; align-items: center; margin: 3px 0; }
.ng-card .ng-suggestion { white-space: pre-wrap; border-left: 2px solid #b294db; padding: 6px; margin: 4px 0; }
.ng-assistbar { display: flex; gap: 6px; margin-bottom: 6px; }
.ng-assistbar button { padding: 3px 8px; border-radius: 4px; cursor: pointer; }
.ng-assistbar button[aria-pressed=true] { background: #2f5d8c; color: white; }
`;

let injected = false;

export function ensureStyle() {
  if (injected) return;
  const tag = document.createElement("style");
  tag.textContent = CSS;
  document.head.appendChild(tag);
  injected = true;
}
