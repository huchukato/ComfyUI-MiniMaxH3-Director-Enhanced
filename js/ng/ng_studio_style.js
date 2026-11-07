// Visual layout from the NG specification: quiet surfaces, compact sections and progressive disclosure.
const CSS = `
.ng-studio { --ng-accent:#73aaa8; --ng-surface:#24282e; --ng-line:#3b424b; box-sizing:border-box; width:100%; height:100%;
  overflow:auto; color:#e4e8ed; background:#202329; border:1px solid var(--ng-line); border-radius:10px; padding:14px;
  font:13px/1.45 Inter,system-ui,sans-serif; }
.ng-studio *, .ng-studio-context * { box-sizing:border-box; }
.ng-studio .ng-header, .ng-studio-context .ng-header { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.ng-studio .ng-header strong { font-size:16px; font-weight:650; letter-spacing:.02em; }
.ng-studio .ng-header { position:sticky; top:-14px; z-index:3; background:#202329; padding:8px 0; flex-wrap:wrap; }
.ng-studio .ng-header .ng-button { font-size:12px; padding:6px 8px; }
.ng-studio .ng-status { color:#a7b4c3; font-size:11px; }
.ng-section { margin:12px 0; padding-top:10px; border-top:1px solid var(--ng-line,#3b424b); }
.ng-section-title { font-size:11px; font-weight:650; letter-spacing:.09em; text-transform:uppercase; margin:0 0 9px; color:#adbac7; }
.ng-field { display:flex; flex-direction:column; gap:4px; margin:7px 0; flex:1; min-width:0; }
.ng-field-label { font-size:11px; color:#aeb8c5; }
.ng-studio input, .ng-studio select, .ng-studio textarea, .ng-studio-context input, .ng-studio-context select, .ng-studio-context textarea {
  width:100%; font:inherit; color:#e5e9ee; background:#181d23; border:1px solid #3a424d; border-radius:6px; padding:7px 8px; min-width:0; }
.ng-studio textarea, .ng-studio-context textarea { resize:vertical; min-height:72px; }
.ng-studio input:focus, .ng-studio textarea:focus, .ng-studio-context input:focus { outline:1px solid var(--ng-accent,#73aaa8); }
.ng-studio .ng-row, .ng-studio-context .ng-row { display:flex; gap:10px; }
.ng-actions { display:flex; gap:7px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.ng-button { font:inherit; border:1px solid #52656c; border-radius:6px; padding:7px 11px; color:#ebf5f4; background:#3a555b; cursor:pointer; }
.ng-secondary { background:#293039; border-color:#444e5b; color:#c6d0da; }
.ng-studio button:disabled, .ng-studio-context button:disabled { opacity:.45; cursor:default; }
.ng-muted { color:#a5b0bd; font-size:12px; margin:5px 0; }
.ng-context-list { display:flex; flex-wrap:wrap; gap:6px; }
.ng-context-chip { display:inline-flex; gap:6px; align-items:center; border:1px solid #46515e; border-radius:6px; padding:5px 8px; background:#282e36; font-size:12px; }
.ng-context-chip::before { content:""; width:7px; height:7px; background:var(--context-color,#73aaa8); border-radius:50%; }
.ng-shot-cards { display:flex; gap:9px; overflow:auto; padding-bottom:4px; }
.ng-shot-card { flex:0 0 220px; padding:10px; background:#292f37; border:1px solid #414b57; border-radius:8px; }
.ng-shot-header { display:flex; align-items:center; justify-content:space-between; color:#b9c6d2; font-size:11px; }
.ng-icon-button { border:0; background:transparent; color:#abb9c6; font:18px system-ui; cursor:pointer; }
.ng-shot-times { display:flex; gap:8px; margin:7px 0; }
.ng-shot-times input { font-size:11px; padding:4px; }
.ng-shot-card textarea { min-height:82px; font-size:12px; }
.ng-track-label { font-size:10px; font-weight:500; color:#9caebe; margin:10px 0 4px; }
.ng-story-timeline { position:relative; height:32px; background:#151b22; border-radius:5px; overflow:hidden; }
.ng-story-block { position:absolute; height:100%; min-width:8px; background:#46666c; border:1px solid #78a09f; border-radius:4px;
  padding:5px 10px; font-size:11px; cursor:grab; touch-action:none; }
.ng-time-handle { position:absolute; top:0; bottom:0; width:7px; cursor:ew-resize; }
.ng-time-start { left:0; } .ng-time-end { right:0; }
.ng-generation-track { position:relative; height:22px; background:#151b22; border-radius:5px; overflow:hidden; }
.ng-chunk-block { position:absolute; height:100%; text-align:center; padding:2px; background:#344151; border:1px solid #26354a; border-radius:3px; color:#c0ccdc; font-size:10px; }
.ng-studio .ng-story-block[aria-selected=true],.ng-studio .ng-chunk-block[aria-selected=true] { box-shadow:inset 0 0 0 2px #b8e1ff; }
.ng-studio .ng-requested-end { position:absolute; top:0; bottom:0; border-left:2px dashed #ffd483; transform:translateX(-2px); z-index:2; pointer-events:none; }
.ng-studio .ng-timeline-duration { font-size:11px; color:#b5c9dd; }
.ng-studio .ng-shot-order { display:flex; gap:3px; }
.ng-studio details, .ng-studio-context details { border-top:1px solid #3b424b; padding-top:7px; margin-top:9px; }
.ng-studio summary, .ng-studio-context summary { cursor:pointer; color:#becbd7; font-size:12px; }
.ng-studio .ng-plan-summary { background:#2b353e; border-radius:6px; padding:8px 10px; font-size:12px; margin:8px 0; }
.ng-studio .ng-warning { color:#e0bd80; font-size:11px; margin:5px 0; white-space:pre-wrap; }
.ng-studio .ng-error, .ng-studio-context .ng-error { color:#ed9d98; white-space:pre-wrap; }
.ng-studio pre { font:11px/1.5 monospace; white-space:pre-wrap; color:#c3d2df; }
.ng-studio-context { --ng-accent:#73aaa8; box-sizing:border-box; width:100%; height:100%; overflow:auto; background:#20252c;
  color:#e4e8ed; border:1px solid #444e5b; border-radius:9px; padding:11px; font:12px/1.45 Inter,system-ui,sans-serif; }
.ng-studio-context .ng-context-title { font-weight:600; font-size:14px; }
.ng-studio-context .ng-context-caption { color:#adb9c7; font-size:11px; margin-top:5px; }
.ng-studio-context .ng-thumbnail { display:block; max-width:100%; max-height:145px; margin:8px auto; border-radius:6px; }
.ng-studio-context .ng-waveform { width:100%; height:42px; }
.ng-studio-context .ng-media-preview { max-height:180px; overflow:auto; }
.ng-studio-context .ng-tools { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
.ng-studio-context .ng-tools input, .ng-studio-context .ng-tools select { flex:1; min-width:100px; }
.ng-studio-context button { font:inherit; color:#dbe5ee; background:#303f4a; border:1px solid #4a5a67; border-radius:5px; padding:5px 8px; cursor:pointer; }
.ng-studio-context .ng-suggestion { white-space:pre-wrap; border-left:2px solid #a88abd; padding:7px; margin:7px 0; }
.ng-studio-context .ng-status { font-size:11px; color:#c4bd9f; white-space:pre-wrap; }
.ng-studio-context label input[type=checkbox] { width:auto; }
.ng-studio, .ng-studio-context { --ng-accent:#29b9ff; --ng-line:#284260; color:#e5f0ff; background:linear-gradient(145deg,#0c1829,#121829);
  border:1px solid var(--ng-accent); border-radius:13px; padding:16px; font:14px/1.45 Inter,system-ui,sans-serif;
  box-shadow:inset 0 0 18px #142d462e; }
.ng-studio .ng-header, .ng-studio-context .ng-header { background:linear-gradient(100deg,#122b43,#201b38); padding:13px; border:1px solid #345277; border-radius:11px; }
.ng-studio .ng-header strong, .ng-studio-context .ng-context-title { font-size:23px; letter-spacing:.025em; color:#f0f5ff; }
.ng-studio-context .ng-context-name { font-size:16px; color:#91b8ee; margin:3px 0; }
.ng-studio-context[data-expanded=false] { padding:10px; }
.ng-studio-context[data-expanded=false] .ng-header { padding:8px; gap:6px; }
.ng-studio-context[data-expanded=false] .ng-context-title { font-size:14px; letter-spacing:0; }
.ng-studio-context[data-expanded=false] .ng-context-name { font-size:13px; }
.ng-studio-context[data-expanded=false] .ng-ai-badge { font-size:10px; padding:3px 5px; }
.ng-studio-context[data-expanded=false] button { font-size:11px; padding:4px 6px; }
.ng-ai-badge { border:1px solid #c99735; color:#f6d26e; background:#40321355; border-radius:12px; padding:6px 10px; font-size:12px; white-space:nowrap; }
.ng-section { border:1px solid var(--ng-line,#284260); border-radius:10px; padding:12px; margin:10px 0; background:linear-gradient(120deg,#10243b80,#0b162480); }
.ng-section-title { color:#99d4ff; font-size:13px; letter-spacing:.03em; }
.ng-studio input,.ng-studio textarea,.ng-studio select,.ng-studio-context input,.ng-studio-context textarea,.ng-studio-context select { background:#0a1627; border-color:#2a4c71; border-radius:8px; }
.ng-studio button,.ng-studio-context button { color:#d9e9ff; background:linear-gradient(140deg,#183859,#10243e); border:1px solid #315d87; border-radius:7px; cursor:pointer; padding:7px 11px; }
.ng-studio .ng-button { background:linear-gradient(110deg,#ff992d,#ec397e); color:#fff; border-color:#ffaf6d; font-weight:600; }
.ng-context-top { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(190px,1fr); gap:12px; align-items:start; }
.ng-context-bottom { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.ng-option-row { display:flex; align-items:center; gap:10px; padding:7px 3px; color:#d5e6ff; }
.ng-option-row input[type=checkbox],.ng-option-row input[type=radio] { width:19px; height:19px; accent-color:#048eff; margin:0; }
.ng-preserve-row { display:flex; justify-content:space-between; align-items:center; gap:9px; padding:6px 0; }
.ng-segments { display:flex; }
.ng-segments button { padding:5px 9px; font-size:12px; border-radius:0; }
.ng-segments button:first-child { border-radius:7px 0 0 7px; } .ng-segments button:last-child { border-radius:0 7px 7px 0; }
.ng-media-editor { border:1px solid #254768; border-radius:10px; padding:8px; margin-top:10px; overflow:hidden; }
.ng-source-preview { display:block; width:100%; max-height:300px; object-fit:contain; border-radius:8px; }
img.ng-source-preview { cursor:zoom-in; }
.ng-image-dialog { background:#0b1321; border:1px solid #50a7ff; padding:8px; max-width:90vw; max-height:90vh; }
.ng-image-dialog img { max-width:85vw; max-height:85vh; }
.ng-wave-container { position:relative; width:100%; height:106px; overflow:hidden; border:1px solid #294e7b; background:#10162b; }
.ng-wave-container { overflow-x:auto; } .ng-wave-track { position:relative; height:100px; min-width:100%; }
.ng-studio-context .ng-waveform { display:block; width:100%; height:100px; }
.ng-wave-selection { position:absolute; top:0; bottom:0; background:#278cff30; border:1px solid #6094ff; pointer-events:none; }
.ng-wave-handle { position:absolute; top:0; bottom:0; width:10px; background:#6195ff80; cursor:ew-resize; pointer-events:auto; touch-action:none; }
/* .ng-text-highlight / .ng-text-token / .ng-reference-unknown stay in this shared sheet on purpose:
   ng_studio.js, ng_story_editor.js and ng_references.js render references in the Director and in the
   shot editor too, so they are not owned by the Text context card. */
.ng-text-highlight { white-space:pre-wrap; font:12px/1.5 ui-monospace,monospace; max-height:100px; overflow:auto; }
.ng-text-token { color:#6ccbff; }
.ng-reference-unknown { color:#ffc273; text-decoration:underline wavy; }
.ng-connector-groups { display:grid; gap:7px; }
.ng-connector-group { display:flex; justify-content:space-between; gap:12px; border:1px solid #2b5369; padding:9px; border-radius:8px; }
.ng-connector-group strong { color:#76e3d7; }
.ng-context-chip { display:flex; flex-direction:column; align-items:flex-start; min-width:120px; width:145px; padding:8px; background:#132339; border-color:var(--context-color,#37627f); }
.ng-context-chip::before { display:none; }
.ng-context-chip img,.ng-context-chip video { width:100%; height:75px; object-fit:cover; border-radius:5px; margin-top:5px; }
.ng-context-chip small { font-size:10px; color:#9ab4d0; }
.ng-context-chip audio { width:130px; height:27px; margin-top:7px; }
.ng-shot-card { background:#12263c; border-color:#29638e; width:235px; flex-basis:235px; }
.ng-shot-thumbnail { width:100%; height:70px; object-fit:cover; border-radius:5px; margin:7px 0; }
.ng-studio .ng-shot-media-marks { display:flex; flex-wrap:wrap; gap:4px; margin:7px 0; }
.ng-studio .ng-shot-media-mark { display:inline-flex; align-items:center; gap:4px; border:1px solid currentColor; border-radius:4px; padding:2px 4px; font-size:10px; }
.ng-studio .ng-shot-media-icon { width:13px; height:13px; }
.ng-studio .ng-shot-gallery { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px; }
.ng-studio .ng-shot-preview { min-width:0; margin:0; }
.ng-studio .ng-shot-preview .ng-shot-thumbnail { height:64px; object-fit:contain; margin:0; background:#101a2c; }
.ng-studio .ng-shot-preview figcaption,.ng-studio .ng-shot-preview-status { display:block; font-size:9px; line-height:1.3; color:#a5b0bd; overflow-wrap:anywhere; }
.ng-story-block { background:linear-gradient(#106cc2,#214e87); border-color:#40b4ff; }
.ng-audio-track { display:flex; gap:10px; align-items:center; padding:5px 0; font-size:11px; }
.ng-audio-track span { width:100px; } .ng-audio-track audio { flex:1; height:28px; min-width:0; }
.ng-generation-cards { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.ng-generation-card { flex:1; min-width:140px; padding:11px; border:1px solid #285174; border-radius:9px; background:#10263b; }
.ng-generation-card strong { display:block; font-size:14px; } .ng-generation-card small { color:#8fabca; }
.ng-subtitle { display:block; margin:-6px 0 4px; color:#9aa6bb; font-size:12px; }
.ng-source-cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
.ng-source-card { display:flex; align-items:center; gap:9px; text-align:left; cursor:pointer;
  padding:10px; border:1px solid #38455c; border-radius:9px; background:#141d2e; color:#d6dceb; }
.ng-source-card:hover { border-color:#5d6f92; background:#18243a; }
.ng-source-card[aria-pressed=true] { border-color:#a77cff; background:#241a44; box-shadow:inset 0 0 0 1px #a77cff; }
.ng-source-icon { font-size:19px; line-height:1; }
.ng-source-text { display:flex; flex-direction:column; min-width:0; }
.ng-source-text strong { font-size:13px; font-weight:650; }
.ng-source-text small { color:#93a1ba; font-size:11px; white-space:normal; }
.ng-ai-badge { border:1px solid #6a5aa8; border-radius:6px; padding:4px 9px; color:#cbb6ff; background:#231a44; font-size:11px; }
.ng-studio-context details summary { cursor:pointer; padding:8px 10px; border:1px solid #38455c; border-radius:8px;
  background:#141d2e; color:#c3b0f5; font-size:12px; list-style:none; }
.ng-studio-context details[open] summary { margin-bottom:8px; border-color:#5b4a91; }
.ng-studio-context .ng-row .ng-field { margin:4px 0; }
.ng-studio-context input[type=checkbox] { width:16px; height:16px; accent-color:#a77cff; }
/* A capability is one line: caption left, box right. Stacked it opened a gap the size of the field. */
.ng-studio-context .ng-field:has(input[type=checkbox]) { flex-direction:row; align-items:center; justify-content:space-between;
  gap:8px; padding:7px 9px; border:1px solid #2f3c54; border-radius:7px; background:#141d2e; }
.ng-studio-context .ng-field:has(input[type=checkbox]) .ng-field-label { flex:1; }
/* LiteGraph lays the DOM widget out after the panel is built, so a percentage width measured
   during the first computeSize is 0 and the measured height is nonsense. Pin a floor that stays
   below the node's real widget width, or the panel grows a horizontal scrollbar. */
/* LiteGraph hands a DOM widget the space the node gained, but the panel inside still has to grow
   into it. The root is a flex column so the body takes exactly the height left under the sticky
   header, and the last panel absorbs the slack: a taller node shows more panel, not a dead gap. */
.ng-studio-context:has(.ng-panel-body) { display:flex; flex-direction:column; }
.ng-panel-body { width:100%; min-width:300px; flex:1 1 auto; display:flex; flex-direction:column; }
/* Two stacked hint lines in one section need a gap, or the sentences run together. */
.ng-section > .ng-muted { display:block; margin:4px 0; }
.ng-studio [hidden],.ng-studio-context [hidden] { display:none !important; }
.ng-source-cards { grid-template-columns:repeat(4,minmax(0,1fr)); }
.ng-studio-context[data-expanded=true] { font-size:13px; padding:12px; }
.ng-studio-context[data-expanded=true] .ng-header { padding:10px; }
.ng-studio-context[data-expanded=true] .ng-context-title { font-size:20px; }
.ng-context-details .ng-section { padding:10px; margin:6px 0; }
.ng-context-details .ng-section-title { font-size:12px; margin-bottom:6px; }
.ng-context-details .ng-option-row { padding:4px 2px; }
.ng-context-details .ng-preserve-row { padding:4px 0; }
.ng-context-footer { display:grid; grid-template-columns:1fr 1fr; gap:10px; align-items:start; }
.ng-studio-context[data-media=audio] .ng-context-top { display:block; }
/* The text card's top row also switches to display:block; that rule moved into ng_context_text_style.js,
   where the Text card keeps the rest of its own layout. */
.ng-studio-context[data-media=audio] .ng-context-bottom { grid-template-columns:1fr 1fr 1.25fr; gap:10px; }
.ng-studio-context[data-media=audio] .ng-context-footer { grid-template-columns:1fr 1.25fr 1.25fr; }
.ng-studio-context[data-media=audio] .ng-waveform { height:82px; }
.ng-studio-context[data-media=audio] .ng-wave-container { height:88px; }
.ng-studio-context[data-media=audio] .ng-wave-track { height:82px; }
.ng-studio-context[data-media=audio] .ng-source-preview { height:40px; }
.ng-studio-context[data-media=audio] .ng-context-bottom .ng-field:has(input[type=range]) { display:grid; grid-template-columns:1fr auto; gap:2px; margin:6px 0; }
.ng-studio-context[data-media=audio] .ng-context-bottom .ng-field:has(input[type=range]) input { grid-column:1/-1; grid-row:2; height:20px; padding:0; margin:0; }
.ng-studio-context[data-media=audio] .ng-context-bottom .ng-field:has(input[type=range]) .ng-muted { grid-column:2; grid-row:1; margin:0; }
.ng-context-details .ng-field { margin:4px 0; gap:3px; }
.ng-context-details input,.ng-context-details select { padding:5px 7px; }
.ng-wave-ruler { display:flex; justify-content:space-between; color:#9cacc8; font-size:10px; padding:2px 0; }
/* The Text card's own layout moved into ng_context_text_style.js. It is the only node with a text
   workspace, so its rules cannot reach the image, video, audio or product cards that share this sheet. */
.ng-context-footer .ng-tools { gap:5px; }
.ng-context-footer .ng-tools input,.ng-context-footer .ng-tools select { flex-basis:100%; }
.ng-studio { font-size:13px; padding:12px; container-type:inline-size; }
.ng-studio .ng-sampling-settings { flex-wrap:wrap; }
.ng-studio .ng-sampling-settings > .ng-field { flex:1 1 130px; }
@container (max-width:740px) { .ng-studio .ng-creation-grid { grid-template-columns:minmax(0,1fr); } }
.ng-studio .ng-header strong { font-size:21px; }
.ng-studio .ng-section { padding:10px; margin:7px 0; }
.ng-creation-grid { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,1fr); gap:10px; }
.ng-creation-grid .ng-row { flex-wrap:wrap; }
.ng-creation-grid .ng-row > * { flex:1 1 100px; }
.ng-studio .ng-context-chip { min-width:100px; width:125px; padding:6px; }
.ng-studio .ng-context-chip img,.ng-studio .ng-context-chip video { height:48px; }
.ng-studio .ng-plan-summary { font-size:11px; padding:3px; margin:3px; background:transparent; }
.ng-studio .ng-generation-card { padding:8px; min-width:130px; }
.ng-studio .ng-generation-cards { gap:7px; }
.ng-studio .ng-shot-card textarea { min-height:66px; }
.ng-studio .ng-shot-card { padding:8px; }
.ng-studio .ng-shot-thumbnail { height:48px; }
.ng-studio .ng-shot-card[aria-selected=true] { border-color:#89ccff; box-shadow:inset 0 0 0 1px #89ccff; }
.ng-timeline-ruler { display:flex; justify-content:space-between; font-size:10px; color:#a2b4cc; }
.ng-audio-lane { position:relative; flex:1; height:24px; background:#101a2b; border-radius:4px; overflow:hidden; }
.ng-audio-lane .ng-audio-region { display:block; height:100%; min-width:0; font-size:10px; padding:4px 8px; width:auto; color:#10182a; }
.ng-audio-track > audio { flex:0 1 180px; }
.ng-studio .ng-tools { display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
.ng-studio .ng-tools select { width:auto; }
.ng-studio > details.ng-generation-details > .ng-field { display:inline-flex; width:calc(33.333% - 10px); margin-right:8px; }
.ng-product-node .ng-header { padding:8px; gap:6px; }
 /* The accent frame around the whole panel is dropped for the product nodes: the four sections are
    ordered and titled, so a frame around them costs a border and padding without adding meaning.
    Only the product nodes are affected - the context cards keep theirs. */
 .ng-product-node { border-color:#2a3240; border-radius:9px; padding:6px; box-shadow:none; }
 .ng-product-node .ng-header { background:none; border:0; border-radius:0; padding:8px 6px; }
.ng-product-node .ng-header .ng-context-title { font-size:16px; letter-spacing:0; }
.ng-product-node .ng-ai-badge { font-size:10px; padding:3px 5px; }
.ng-studio-context .ng-suggestion:empty { display:none; }
  .ng-field-picker { display:flex; flex-direction:column; gap:4px; margin:7px 0; padding:7px; border-left:2px solid #a88abd; }
  .ng-field-row { display:flex; align-items:flex-start; gap:6px; font-size:12px; cursor:pointer; }
  .ng-field-row span { white-space:pre-wrap; word-break:break-word; }
  .ng-direction-tools .ng-assistbar { display:flex; gap:5px; margin:6px 0; }
  .ng-direction-tools .ng-assistbar button[aria-pressed=true] { background:#2f4a63; border-color:#7fb2dd; color:#eaf4ff; }
  .ng-studio .ng-direction-field { display:flex; gap:7px; align-items:center; margin-top:8px; }
  .ng-studio .ng-direction-field input { width:auto; }
  .ng-studio .ng-direction-preview { white-space:pre-wrap; overflow-wrap:anywhere; max-height:180px; overflow:auto; }
/* Product nodes: the AI Loader's branded header, icon tiles and framed sections. Kept separate from
   the studio rules above so the context cards keep the compact density they were tuned for. */
.ng-icon { display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; }
.ng-icon svg { width:100%; height:100%; display:block; }
.ng-product-node .ng-brand { display:flex; align-items:center; gap:10px; min-width:0; }
.ng-brand-mark { width:34px; height:34px; padding:6px; border-radius:10px; color:#e7dcff;
  background:linear-gradient(145deg,#7a4ff0,#4a2bb0); border:1px solid #8f6cff;
  box-shadow:0 2px 10px #0006, inset 0 1px 0 #ffffff33; }
.ng-brand-text { display:flex; flex-direction:column; min-width:0; }
.ng-brand-title { font-size:19px; font-weight:700; letter-spacing:.01em; line-height:1.15; white-space:nowrap; }
.ng-brand-lead { color:#f2f5fb; }
.ng-brand-accent { background:linear-gradient(92deg,#b98cff,#8f6cff); -webkit-background-clip:text; background-clip:text; color:transparent; }
.ng-brand-sub { font-size:11.5px; color:#9fb0c8; letter-spacing:.02em; }
.ng-brand-menu { border:0; background:transparent; color:#8fa0b8; font-size:19px; line-height:1; cursor:pointer;
  padding:2px 5px; border-radius:6px; }
.ng-brand-menu:hover { color:#e6edf7; background:#ffffff14; }
/* The badge carries its state in the colour, so the panel reads at a glance without reading words. */
.ng-product-node .ng-status { display:inline-flex; align-items:center; gap:6px; margin-left:auto; }
.ng-status-mark { width:14px; height:14px; }
.ng-status[data-tone=idle] { border-color:#4d5768; color:#a7b3c4; background:#2a3140; }
.ng-status[data-tone=warn] { border-color:#c99735; color:#f6d26e; background:#40321388; }
.ng-status[data-tone=ready] { border-color:#3f9c74; color:#7fe3b4; background:#12332699; }
/* Section heading: icon, caption and a help marker that carries the explanation as its tooltip. */
.ng-section-head { display:flex; align-items:center; gap:8px; margin:0 0 9px; }
.ng-section-icon { width:16px; height:16px; color:#7fb2ff; }
/* The help marker follows its caption; the reference reads "1. SOURCE (?)" as one phrase. */
.ng-section-head .ng-section-title { margin:0; line-height:18px; }
.ng-section-help { width:17px; height:17px; flex:0 0 17px; display:flex; align-items:center; justify-content:center;
  border-radius:50%; cursor:pointer; border:1px solid #4d5a6e; background:#1d2431; color:#9fb0c8;
  font:600 11px/1 system-ui; padding:0; margin:0; min-height:0; }
.ng-section-help:hover { border-color:#7fb2ff; color:#cfe4ff; }
/* A field tile draws a box around label and input, with the icon in the caption row. */
.ng-field-tile { gap:5px; margin:0; padding:9px 10px; border:1px solid #2f3d52; border-radius:9px;
  background:#16202f; }
.ng-field-tile:focus-within { border-color:#6f9fe0; box-shadow:0 0 0 1px #6f9fe055; }
.ng-field-head { display:flex; align-items:center; gap:7px; }
.ng-field-icon { width:15px; height:15px; color:#7fb2ff; }
.ng-field-tile .ng-field-label { font-size:11.5px; color:#b7c6da; }
/* Checkbox tiles keep the caption and the box on one line, because a stacked box reads as empty. */
.ng-field-tile:has(input[type=checkbox]) { flex-direction:row; align-items:center; gap:9px; }
.ng-field-tile:has(input[type=checkbox]) .ng-field-head { flex:1; }
.ng-field-tile input[type=checkbox] { width:16px; height:16px; flex:0 0 16px; accent-color:#8f6cff; }
/* Advanced reads as its own framed row with a chevron, the same shape the reference uses. */
.ng-advanced { margin:10px 0; padding:0 11px; border:1px solid #2f3d52; border-radius:10px; background:#16202f; }
/* The framed details rules above would put a second box and a chevron inside this row, and the row
   already is the box, so the summary keeps only the flex layout. */
.ng-studio-context .ng-advanced > .ng-advanced-head { display:flex; align-items:center; gap:8px; cursor:pointer;
  padding:9px 0; margin:0; border:0; background:transparent; list-style:none; }
.ng-advanced-head::-webkit-details-marker { display:none; }
.ng-advanced-icon { width:16px; height:16px; color:#c39cff; }
.ng-advanced-title { font-size:12px; font-weight:700; letter-spacing:.08em; color:#c8a4ff; }
.ng-advanced-note { font-size:12px; color:#9fb0c8; }
.ng-advanced-chevron { width:15px; height:15px; margin-left:auto; color:#8fa0b8; transition:transform .15s; }
.ng-advanced[open] .ng-advanced-chevron { transform:rotate(90deg); }
.ng-advanced > .ng-field-tile { margin:0 0 8px; }
/* Source cards: taller tiles, so the title and its hint each keep one line. */
.ng-product-node .ng-source-cards { gap:9px; }
.ng-product-node .ng-source-card { flex-direction:column; align-items:flex-start; gap:7px; padding:11px 12px;
  border-radius:11px; background:#141d2e; }
.ng-product-node .ng-source-icon { width:22px; height:22px; color:#8fb6ef; }
.ng-product-node .ng-source-card[aria-pressed=true] .ng-source-icon { color:#d9c4ff; }
.ng-product-node .ng-source-text strong { font-size:13.5px; }
.ng-product-node .ng-source-text small { font-size:11px; }
.ng-product-node .ng-section { padding:12px; margin:9px 0; }
.ng-product-node .ng-section-title { font-size:12px; letter-spacing:.05em; color:#9dc6f5; }
/* The overflow button collapses the two hint sentences; fit() re-measures the node around it. */
.ng-product-node[data-hints=off] .ng-panel-body > .ng-section > .ng-muted { display:none; }
/* The field-level "?" repeats the section marker on the tiles that need one. It stays hidden until
   the registry has something to say, so a field the chosen provider does not have carries no "?". */
.ng-field-help { width:15px; height:15px; flex:0 0 15px; margin-left:auto; display:flex; align-items:center;
  justify-content:center; border-radius:50%; cursor:pointer; border:1px solid #4d5a6e; background:#1d2431;
  color:#9fb0c8; font:600 10px/1 system-ui; padding:0; min-height:0; }
.ng-field-help:hover { border-color:#7fb2ff; color:#cfe4ff; }
/* The panel's only buttons live inside a tile, so they have to look unlike the inputs above them. */
.ng-field-actions { display:flex; gap:7px; margin-top:7px; }
.ng-action { display:inline-flex; align-items:center; gap:5px; padding:5px 10px; cursor:pointer;
  border:1px solid #3a4a61; border-radius:7px; background:#1b2534; color:#c3d2e4; font:500 11.5px/1 system-ui; }
.ng-action:hover:not(:disabled) { border-color:#6f9fe0; color:#eaf2ff; }
.ng-action:disabled { opacity:.5; cursor:default; }
.ng-action-primary { border-color:#4a6fa5; background:#1d2c44; color:#dceaff; }
.ng-action-icon { width:13px; height:13px; }
/* A status line under a field. Amber means something is still missing, green means the provider
   answered, grey is simply the current state - and never a claim the request did not prove. */
.ng-field-status { display:block; font-size:11px; line-height:1.45; color:#8e9db2; margin:6px 0 0; }
.ng-field-status[data-state=ok] { color:#8fd6a4; }
.ng-field-status[data-state=warn] { color:#e8b661; }
.ng-secret { width:100%; }
.ng-secret-stored { border-color:#3f6b4d; }
/* A capability is a fact, so its tile carries a sentence and no control. It keeps the shape of the
   fields around it so the row height does not jump when the provider changes underneath it. */
.ng-field-fact { background:#161b22; border:1px solid #333c47; }
.ng-fact-text { font-size:12px; color:#cfd8e3; padding:7px 8px; line-height:1.4; }
/* The wire name goes under the field only where it differs from the label. Ollama nests its sampling
   knobs under "options" and calls the token limit num_predict, so a user reading their own request
   log would otherwise not find the control they just set. */
.ng-wire-name { font-size:10.5px; color:#7f8ea3; font-family:ui-monospace,Consolas,monospace; margin-top:3px; }
.ng-shot-binding { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto; gap:6px; align-items:center; margin:6px 0; }
.ng-shot-binding span { overflow-wrap:anywhere; }
.ng-shot-bindings select,.ng-spoken-line input { width:100%; min-width:0; box-sizing:border-box; }
.ng-shot-dialogue,.ng-shot-protection { margin-top:8px; }
.ng-spoken-line { margin:8px 0; padding:8px; border:1px solid #344457; border-radius:6px; }
.ng-lock-field { display:flex; gap:6px; align-items:center; margin:4px 0; }
.ng-lock-field input { width:auto; }
/* The AI Loader in the Context cards' look (user 2026-10-19: "it does not look like our nodes yet; it was built first"):
   the cards' colours, boxes, captions, fields and buttons (h3c_style.js), its height its content, no inner scrollbar. */
.ng-product-node.ng-ai { background:transparent; border:0; border-radius:0; box-shadow:none; padding:2px 2px 6px; overflow:visible;
  color:#E6EAF2; font:13px/1.4 "IBM Plex Sans","Segoe UI",system-ui,sans-serif; }
.ng-product-node.ng-ai .ng-header { background:none; border:0; padding:2px 2px 8px; }
.ng-product-node.ng-ai .ng-brand-mark { width:26px; height:26px; padding:4px; border-radius:8px; background:#1F1A33; border:1px solid #4B3F78;
  box-shadow:none; color:#D6C8FF; }
.ng-product-node.ng-ai .ng-brand-title { font-size:15px; font-weight:650; }
.ng-product-node.ng-ai .ng-brand-accent { background:none; color:#D6C8FF; -webkit-text-fill-color:#D6C8FF; }
.ng-product-node.ng-ai .ng-brand-sub { font-size:12px; color:#9AA4B5; }
.ng-product-node.ng-ai .ng-ai-badge { border-radius:999px; padding:2px 10px; font-size:12px; }
.ng-product-node.ng-ai .ng-section { border:1px solid #262E3B; border-radius:10px; background:#161B24; padding:10px 12px; margin:0 0 10px; }
.ng-product-node.ng-ai .ng-section-head { margin:0 0 8px; }
.ng-product-node.ng-ai .ng-section-title { font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:#9AA4B5; }
.ng-product-node.ng-ai .ng-section-icon, .ng-product-node.ng-ai .ng-field-icon { color:#7F8A9C; width:14px; height:14px; }
.ng-product-node.ng-ai .ng-section-help, .ng-product-node.ng-ai .ng-field-help { border-color:#344055; background:#1E2633; color:#9AA4B5; }
.ng-product-node.ng-ai .ng-muted, .ng-product-node.ng-ai .ng-field-status { font-size:12px; color:#8E98AA; }
.ng-product-node.ng-ai .ng-field-tile { padding:0; border:0; background:transparent; box-shadow:none; gap:4px; }
.ng-product-node.ng-ai .ng-field-tile:focus-within { box-shadow:none; }
.ng-product-node.ng-ai .ng-field-tile .ng-field-label { font-size:12px; color:#9AA4B5; }
.ng-product-node.ng-ai .ng-field-tile:has(input[type=checkbox]) { padding:4px 0; }
.ng-product-node.ng-ai input:not([type=checkbox]):not([type=range]), .ng-product-node.ng-ai select {
  background:#0E1117; border:1px solid #2E3848; border-radius:8px; min-height:30px; padding:0 8px; color:#E6EAF2; }
.ng-product-node.ng-ai input:focus, .ng-product-node.ng-ai select:focus { outline:2px solid #8FC1FF; outline-offset:1px; }
.ng-product-node.ng-ai input[type=checkbox] { accent-color:#3D7BF0; }
.ng-product-node.ng-ai .ng-action { min-height:30px; padding:0 10px; border-radius:8px; border:1px solid #344055; background:#1E2633;
  color:#E6EAF2; font-size:12px; }
.ng-product-node.ng-ai .ng-action:hover:not(:disabled) { background:#273142; border-color:#46546C; }
.ng-product-node.ng-ai .ng-action-primary { border-color:#4B3F78; background:#1F1A33; color:#D6C8FF; }
.ng-product-node.ng-ai .ng-source-card { border:1px solid #2E3848; border-radius:8px; background:#0E1117; color:#E6EAF2; padding:9px 10px; }
.ng-product-node.ng-ai .ng-source-card:hover { background:#1C2330; border-color:#46546C; }
.ng-product-node.ng-ai .ng-source-card[aria-pressed=true] { border-color:#3D7BF0; background:#16233D; box-shadow:none; }
.ng-product-node.ng-ai .ng-source-icon, .ng-product-node.ng-ai .ng-source-card[aria-pressed=true] .ng-source-icon { color:#8FC1FF; }
.ng-product-node.ng-ai .ng-source-text small { color:#9AA4B5; }
.ng-product-node.ng-ai .ng-advanced { border:1px solid #262E3B; border-radius:10px; background:#161B24; padding:0 12px; margin:0; }
.ng-product-node.ng-ai .ng-advanced-title { font-size:11px; font-weight:600; letter-spacing:.06em; color:#9AA4B5; }
.ng-product-node.ng-ai .ng-advanced-icon { color:#7F8A9C; }
.ng-product-node.ng-ai .ng-field-fact { border:1px solid #262E3B; background:#0E1117; border-radius:8px; }
`;

export function ensureStudioStyle() {
  if (document.getElementById("ng-studio-style")) return;
  const style = document.createElement("style"); style.id = "ng-studio-style"; style.textContent = CSS; document.head.append(style);
}
