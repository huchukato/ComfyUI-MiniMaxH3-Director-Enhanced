// Previews and the source range of the Image, Video and Audio cards. The <img>/<video>/<audio> elements live in
// S.els and survive redraws, so playback does not stop when a checkbox is ticked.
import { h } from "./h3s_dom.js";

export function mediaURL(source, api) {
  const path = String(source || "").replace(/ \[input\]$/, "").replaceAll("\\", "/"), split = path.lastIndexOf("/");
  return api.apiURL("/view?" + new URLSearchParams({ filename: path.slice(split + 1), subfolder: split < 0 ? "" : path.slice(0, split), type: "input" }));
}

const clock = (s) => { const m = Math.floor(s / 60), r = s - m * 60; return `${m}:${r < 10 ? "0" : ""}${r.toFixed(1)}`; };

// Dragging across a strip chooses the part of the file: press = one end, release = the other. Committed once, on release.
// A click without a drag moves the playhead there instead.
function rangeDrag(S, actions, total, onPreview, player) {
  return (event) => {
    if (!(total > 0)) return;
    const strip = event.currentTarget, box = strip.getBoundingClientRect(), at = (x) => Math.max(0, Math.min(total, (x - box.left) / box.width * total));
    const anchor = at(event.clientX);
    let range = [anchor, anchor];
    try { strip.setPointerCapture(event.pointerId); } catch {}
    actions.beginPointer();
    strip.onpointermove = (move) => { const t = at(move.clientX); range = [Math.min(anchor, t), Math.max(anchor, t)]; onPreview(range); };
    strip.onpointerup = strip.onpointercancel = strip.onlostpointercapture = () => {
      strip.onpointermove = strip.onpointerup = strip.onpointercancel = strip.onlostpointercapture = null;
      actions.endPointer();
      if (range[1] - range[0] < 0.1) { if (player) seek(S, player, anchor); return; }
      actions.setRange(Math.round(range[0] * 100) / 100, Math.round(range[1] * 100) / 100 >= total - 0.05 ? 0 : Math.round(range[1] * 100) / 100);
    };
  };
}

const clamp = (t, a, b) => Math.max(a, Math.min(b, t));
// Playback stays inside the chosen part, so a seek does too.
function seek(S, player, t) {
  const end = S.opts.end_s || player.duration || 0;
  player.currentTime = clamp(t, S.opts.start_s || 0, Math.max(S.opts.start_s || 0, end - 0.05));
}

// Where playback is: a line over the strip or waveform that follows the player (moveHeads) and can be dragged to look or
// listen from elsewhere (user 2026-10-19).
function playhead(S, total, player) {
  const head = h("div", { class: "h3c-head", title: "Playback position: drag to play from elsewhere" });
  head.style.left = `${clamp((player.currentTime || 0) / total, 0, 1) * 100}%`;
  head.onpointerdown = (event) => {
    event.stopPropagation(); event.preventDefault();
    const box = head.parentElement.getBoundingClientRect();
    try { head.setPointerCapture(event.pointerId); } catch {}
    head.onpointermove = (move) => { seek(S, player, (move.clientX - box.left) / box.width * total); moveHeads(head.parentElement, player); };
    head.onpointerup = head.onpointercancel = () => { head.onpointermove = head.onpointerup = head.onpointercancel = null; };
  };
  return head;
}

export function moveHeads(root, player) {
  const total = player.duration;
  if (!(total > 0)) return;
  for (const head of root.querySelectorAll?.(".h3c-head") || []) head.style.left = `${clamp(player.currentTime / total, 0, 1) * 100}%`;
}

function selection(range, total, extra = "") {
  const node = h("div", { class: `h3c-sel ${extra}` });
  node.style.left = `${range[0] / total * 100}%`; node.style.width = `${Math.max(0, range[1] - range[0]) / total * 100}%`;
  return node;
}

export function imageBlock(S) {
  const img = S.els.image;
  if (!S.values.image) return h("div", { class: "h3c-preview" }, h("span", { class: "h3c-hint" }, "Choose or upload a picture."));
  const size = img.naturalWidth ? ` · ${img.naturalWidth}×${img.naturalHeight}` : "";
  return h("div", { class: "h3c-preview" }, img, h("span", { class: "h3c-cornertag" }, `${S.values.image}${size}`));
}

export function videoBlock(S, actions) {
  const video = S.els.video, total = video.duration || 0;
  const end = S.opts.end_s || total, range = [S.opts.start_s || 0, end];
  const preview = h("div", { class: "h3c-preview" }, S.values.video ? video : h("span", { class: "h3c-hint" }, "Choose or upload a video."));
  if (!total) return h("div", { class: "h3c-grid" }, preview);
  const sel = selection(range, total);
  // the video's own sound under the range, when it has one (the strip stays plain without)
  const canvas = S.envelope ? h("canvas", { width: 720, height: 48 }) : null;
  if (canvas) drawWave(canvas, S.envelope, range);
  const strip = h("div", { class: S.envelope ? "h3c-strip sound" : "h3c-strip", title: "Drag to choose the part of the video this card stands for; click to move the playhead",
    onpointerdown: rangeDrag(S, actions, total, (r) => { if (canvas) drawWave(canvas, S.envelope, r); sel.style.left = `${r[0] / total * 100}%`; sel.style.width = `${(r[1] - r[0]) / total * 100}%`; }, video) },
  canvas, sel, playhead(S, total, video));
  return h("div", { class: "h3c-grid" }, preview,
    h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Part of the file to use", h("span", { class: "h3c-grow" }),
      h("span", { class: "h3c-lbl", style: { textTransform: "none", letterSpacing: 0 } }, `${clock(range[0])} – ${clock(range[1])} of ${clock(total)}`)),
      strip, h("span", { class: "h3c-hint" }, "Drag across the strip. Motion and camera references read this part; Continue uses its final frames and eases the picture join.")));
}

export function videoSoundBox(S, actions) {
  const send = S.opts.video_audio === "reference";
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Its own sound"),
    h("div", { class: "h3c-segs", style: { gridTemplateColumns: "repeat(2,minmax(0,1fr))" } },
      h("button", { class: send ? "" : "on", onclick: () => actions.setOptions({ video_audio: "ignore" }) }, "Ignore"),
      h("button", { class: send ? "on" : "", onclick: () => actions.setOptions({ video_audio: "reference" }) }, "Send along")),
    h("span", { class: "h3c-hint" }, send ? "Continue carries its final sound with the frames in FL2VA and Ref2VA. Reference usage pairs the video and sound in Auto or Ref2VA." : "Only the picture is used."));
}

function drawWave(canvas, envelope, range) {
  const ctx = canvas.getContext?.("2d");
  if (!ctx || !envelope) return;
  const w = canvas.width, hh = canvas.height, peaks = envelope.peaks, total = envelope.duration_s;
  ctx.clearRect(0, 0, w, hh);
  peaks.forEach((peak, index) => {
    const t = (index + 0.5) / peaks.length * total;
    ctx.fillStyle = t >= range[0] && t <= range[1] ? "#8FC1FF" : "#5B4A86";
    ctx.fillRect(index / peaks.length * w, hh / 2 - peak * (hh / 2 - 2), Math.max(1, w / peaks.length - 1), Math.max(1, peak * (hh - 4)));
  });
}

export function audioBlock(S, actions) {
  const audio = S.els.audio, envelope = S.envelope;
  if (!S.values.audio) return h("div", { class: "h3c-box" }, h("span", { class: "h3c-hint" }, "Choose or upload a sound file."));
  const total = envelope?.duration_s || 0, range = [S.opts.start_s || 0, S.opts.end_s || total];
  const canvas = h("canvas", { width: 720, height: 72 });
  drawWave(canvas, envelope, range);
  const sel = total ? selection(range, total) : null;
  const wave = h("div", { class: "h3c-wave", title: "Drag to choose the part of the file this card stands for; click to move the playhead",
    onpointerdown: rangeDrag(S, actions, total, (r) => { drawWave(canvas, envelope, r); sel.style.left = `${r[0] / total * 100}%`; sel.style.width = `${(r[1] - r[0]) / total * 100}%`; }, audio) },
    canvas, sel, total ? playhead(S, total, audio) : null);
  const info = envelope ? `${clock(total)} · ${(envelope.sample_rate / 1000).toFixed(1)} kHz · ${envelope.channels === 2 ? "stereo" : `${envelope.channels} ch`}` : S.waveError || "Reading the waveform …";
  return h("div", { class: "h3c-box" },
    h("div", { class: "h3c-row" }, h("button", { class: "h3c-btn", style: { width: "32px", padding: 0, borderRadius: "50%" }, "aria-label": audio.paused ? "Play selection" : "Pause",
      onclick: () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()) }, audio.paused ? "▶" : "❚❚"),
    h("span", { class: "h3c-lbl" }, info), h("span", { class: "h3c-grow" }),
    total ? h("span", { class: "h3c-lbl" }, `Selected: ${clock(range[0])} – ${clock(range[1])} (${(range[1] - range[0]).toFixed(1)} s)`) : null),
    wave, h("span", { class: "h3c-hint" }, "On an audio lane the Studio places this part and can start later in the file."));
}

export function listenBox(S, actions) {
  const settings = S.listen;
  const slider = (key, label, max, unit) => h("div", { style: { display: "grid", gridTemplateColumns: "84px 1fr 44px", gap: "8px", alignItems: "center" } },
    h("span", { class: "h3c-lbl" }, label),
    h("input", { type: "range", min: "0", max: String(max), step: "0.05", value: String(settings[key]), "aria-label": label,
      oninput: (event) => actions.setListen(key, Number(event.target.value)) }), h("span", { class: "h3c-lbl" }, `${settings[key]}${unit}`));
  return h("div", { class: "h3c-box" }, h("div", { class: "h3c-cap" }, "Listen here (playback only)"),
    slider("volume", "Volume", 1, ""), slider("fade_in", "Fade in", 5, " s"), slider("fade_out", "Fade out", 5, " s"));
}

// Playback stays inside the chosen part, with the listening fades; generation never sees these settings. The playhead
// follows every frame while it plays (timeupdate alone comes four times a second).
export function wirePlayback(S, redraw, audio, moved) {
  const follow = () => { moved(); if (!audio.paused) requestAnimationFrame(follow); };
  audio.onplay = () => { const start = S.opts.start_s || 0, end = S.opts.end_s || audio.duration; if (audio.currentTime < start || audio.currentTime >= end) audio.currentTime = start; redraw(); requestAnimationFrame(follow); };
  audio.onpause = () => redraw();
  audio.onseeked = () => moved();
  audio.ontimeupdate = () => {
    const start = S.opts.start_s || 0, end = S.opts.end_s || audio.duration, settings = S.listen;
    if (audio.currentTime >= end) { audio.pause(); audio.currentTime = start; return; }
    const fadeIn = settings.fade_in ? Math.min(1, Math.max(0, (audio.currentTime - start) / settings.fade_in)) : 1;
    // While a new file loads the browser reports timeupdate before it knows the duration (NaN).
    const fadeOut = settings.fade_out && Number.isFinite(end) ? Math.min(1, Math.max(0, (end - audio.currentTime) / settings.fade_out)) : 1;
    audio.volume = Math.max(0, Math.min(1, settings.volume * Math.min(fadeIn, fadeOut)));
  };
}
