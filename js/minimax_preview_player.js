// A browser clock plays the latest JPEG buffer over the shot's actual duration.
// No queue of old denoising steps and no animation restart when a buffer is replaced.
const positive = (value, fallback) => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : fallback;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function frameUrl(encoded) {
  const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], {type: "image/jpeg"}));
}

export function createFramePlayer({image, onStatus = () => {}, onTime = () => {}, onPlayback = () => {}} = {}) {
  const state = {key: null, urls: [], images: [], duration: 0, requestedFPS: 24, actualFPS: 0, index: -1,
    paused: true, stopped: false, time: 0, epoch: 0, schedule: 0, window: 0, changes: 0, handle: null, disposed: false};
  const retired = new Set(), buffers = new Set();
  let revision = 0, pendingKey = null, active = null;
  const retire = (key = state.key) => {
    if (key != null) retired.add(key);
    if (retired.size > 64) retired.delete(retired.values().next().value);
  };
  const cancel = () => { if (state.handle != null) cancelAnimationFrame(state.handle); state.handle = null; };
  const release = (buffer) => {
    if (!buffer || buffer.released) return;
    buffer.released = true;
    buffer.urls.forEach((url) => URL.revokeObjectURL(url));
    buffer.images.forEach((image) => { image.src = ""; });
    buffers.delete(buffer);
  };
  const currentTime = (now) => state.paused ? state.time : ((now - state.epoch) / 1000 % state.duration + state.duration) % state.duration;
  const notify = () => onTime(state.time, state.duration, state.actualFPS, state.requestedFPS, state.index);

  function draw(now, force = false) {
    if (!state.urls.length) return;
    state.time = currentTime(now);
    const index = Math.min(state.urls.length - 1, Math.floor(state.time / state.duration * state.urls.length + 1e-7));
    if (force || index !== state.index) {
      if (!state.paused && state.index >= 0 && index !== state.index) state.changes++;
      state.index = index; image.src = state.urls[index]; image.hidden = false; image.style.display = "block";
    }
    const elapsed = now - state.window;
    if (!state.paused && elapsed >= 1000) { state.actualFPS = state.changes * 1000 / elapsed; state.changes = 0; state.window = now; }
    notify();
  }

  function tick(now) {
    state.handle = null;
    if (state.disposed || state.paused || state.urls.length < 2) return;
    const interval = 1000 / state.requestedFPS, elapsed = now - state.schedule;
    if (elapsed + 1e-6 >= interval) {
      state.schedule += Math.max(1, Math.floor((elapsed + 1e-6) / interval)) * interval;
      draw(now);
    }
    state.handle = requestAnimationFrame(tick);
  }

  const animate = () => {
    cancel();
    if (!state.paused && state.urls.length > 1 && !state.disposed) state.handle = requestAnimationFrame(tick);
    onPlayback(!state.paused, state.urls.length > 0);
  };

  async function prepare(encoded, serial) {
    const buffer = {urls: [], images: [], released: false}; buffers.add(buffer);
    try {
      for (const frame of encoded) buffer.urls.push(frameUrl(frame));
      let cursor = 0;
      const worker = async () => {
        while (cursor < buffer.urls.length && serial === revision && !state.disposed) {
          const index = cursor++, image = new Image(); buffer.images[index] = image;
          if (typeof image.decode === "function") { image.src = buffer.urls[index]; await image.decode(); }
          else await new Promise((resolve, reject) => {
            image.onload = resolve; image.onerror = () => reject(new Error("JPEG decode failed")); image.src = buffer.urls[index];
          });
        }
      };
      const results = await Promise.allSettled(Array.from({length: Math.min(4, encoded.length)}, worker));
      const failure = results.find((result) => result.status === "rejected");
      if (failure) throw failure.reason;
      if (serial !== revision || state.disposed) { release(buffer); return null; }
      return buffer;
    } catch (error) { release(buffer); throw error; }
  }

  async function update(detail = {}) {
    if (state.disposed) return false;
    const key = `${detail.run_id ?? ""}\0${detail.sequence_id ?? detail.node_id ?? ""}`;
    if (retired.has(key)) return false;
    if (!Array.isArray(detail.frames) || !detail.frames.length) {
      const text = detail.error || detail.message || detail.status;
      if (text) onStatus(String(text), detail);
      if (detail.error) stop(String(detail.error));
      return false;
    }
    const duration = positive(detail.duration, null), fps = positive(detail.requested_fps ?? detail.fps, null);
    if (!duration || !fps || !detail.frames.every((frame) => typeof frame === "string" && frame.length > 0)) return false;
    if (key !== state.key && state.key != null) retire();
    if (pendingKey !== key) retire(pendingKey);
    pendingKey = key;
    const serial = ++revision;
    for (const buffer of [...buffers]) if (buffer !== active) release(buffer);
    let buffer;
    try { buffer = await prepare(detail.frames, serial); }
    catch (error) {
      if (serial === revision && !state.disposed) onStatus(`Preview images could not be read: ${error.message}`, detail);
      return false;
    }
    if (!buffer) return false;
    const now = performance.now(), same = key === state.key && state.urls.length > 0;
    const phase = same ? currentTime(now) / state.duration : 0;
    if (!same) {
      const wasPaused = state.stopped || state.urls.length > 0 && state.paused;
      state.key = key; state.paused = wasPaused; state.actualFPS = 0; state.changes = 0;
      state.window = now; state.schedule = now;
    }
    const old = active; active = buffer;
    state.urls = buffer.urls; state.images = buffer.images; state.duration = duration; state.requestedFPS = clamp(fps, 1, 24);
    state.time = phase * duration; state.epoch = now - state.time * 1000;
    draw(now, true); release(old); animate();
    onStatus(`step ${detail.step ?? "?"}/${detail.total_steps ?? "?"} · ${buffer.urls.length} frames`, detail);
    return true;
  }

  function pause() {
    if (!state.paused && state.urls.length) state.time = currentTime(performance.now());
    state.paused = true; cancel(); notify(); onPlayback(false, state.urls.length > 0);
  }
  function play() {
    if (state.disposed || !state.urls.length || !state.paused) return;
    const now = performance.now(); state.stopped = false; state.epoch = now - state.time * 1000; state.schedule = now;
    state.window = now; state.changes = 0; state.actualFPS = 0; state.paused = false; animate();
  }
  function seek(seconds) {
    if (!state.urls.length || !Number.isFinite(Number(seconds))) return;
    const now = performance.now(); state.time = clamp(Number(seconds), 0, Math.max(0, state.duration - 1e-9));
    state.epoch = now - state.time * 1000; state.schedule = now;
    draw(now, true);
  }
  function stop(message, {discardPending = true} = {}) {
    pause(); state.stopped = true;
    if (discardPending) {
      retire(pendingKey); pendingKey = null; revision++;
      for (const buffer of [...buffers]) if (buffer !== active) release(buffer);
    }
    if (message) onStatus(message, {});
  }
  function reset(message = "Waiting for sampler…") {
    retire(); retire(pendingKey); pendingKey = null; revision++;
    cancel(); for (const buffer of [...buffers]) release(buffer); active = null;
    state.key = null; state.urls = []; state.images = []; state.duration = 0;
    state.index = -1; state.time = 0; state.actualFPS = 0; state.changes = 0; state.paused = true; state.stopped = false;
    image.removeAttribute?.("src"); image.hidden = true; image.style.display = "none";
    notify(); onPlayback(false, false); onStatus(message, {});
  }
  function dispose() { reset(""); state.disposed = true; }
  return {update, pause, play, seek, stop, reset, dispose, get state() {return state;}};
}

export function installPreviewStyle() {
  if (document.getElementById("minimax-h3-preview-style")) return;
  const link = document.createElement("link"); link.id = "minimax-h3-preview-style"; link.rel = "stylesheet";
  link.href = new URL("./minimax_preview.css", import.meta.url).href;
  document.head.append(link);
}

export function createPreviewPanel({compact = false} = {}) {
  installPreviewStyle();
  const element = (tag, className, text = "") => { const el = document.createElement(tag); el.className = className; el.textContent = text; return el; };
  const root = element("div", `mmx-preview${compact ? " mmx-preview-compact" : ""}`);
  const stage = element("div", "mmx-preview-stage"), img = element("img", "mmx-preview-image");
  img.alt = "MiniMax H3 denoising preview"; img.hidden = true;
  const idle = element("span", "mmx-preview-idle", "Waiting for sampler…"); stage.append(img, idle);
  const controls = element("div", "mmx-preview-controls"), button = element("button", "mmx-preview-play", "Play");
  button.type = "button"; button.disabled = true;
  const scrub = element("input", "mmx-preview-scrub"); scrub.type = "range"; scrub.min = "0"; scrub.max = "0";
  scrub.step = ".001"; scrub.value = "0"; scrub.disabled = true; scrub.setAttribute("aria-label", "Preview position");
  const time = element("span", "mmx-preview-time", "0.00 / 0.00s"); controls.append(button, scrub, time);
  const status = element("div", "mmx-preview-status"), left = element("span", "mmx-preview-step", "Idle");
  const right = element("span", "mmx-preview-cost"), rates = element("div", "mmx-preview-rates", "TAEHV");
  status.append(left, right); root.append(stage, controls, status, rates);
  let shape = "";
  const player = createFramePlayer({image: img,
    onTime(seconds, duration, actual, requested) {
      scrub.max = String(duration); scrub.value = String(seconds); time.textContent = `${seconds.toFixed(2)} / ${duration.toFixed(2)}s`;
      rates.textContent = `TAEHV · target ${requested.toFixed(0)} FPS · shown ${actual.toFixed(1)} FPS`;
    },
    onPlayback(playing, available) { button.textContent = playing ? "Pause" : "Play"; button.disabled = !available; scrub.disabled = !available; },
    onStatus(text, detail) {
      left.textContent = text; idle.hidden = player.state.urls.length > 0;
      if (positive(detail.width, 0) && positive(detail.height, 0)) shape = `${detail.width}×${detail.height}`;
      const ms = Number(detail.ms), cost = Number.isFinite(ms) ? `update ${ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms.toFixed(0) + "ms"}` : "";
      right.textContent = [shape, cost].filter(Boolean).join(" · ");
    },
  });
  button.onclick = () => player.state.paused ? player.play() : player.pause();
  scrub.oninput = () => player.seek(Number(scrub.value));
  return {root, img, idle, left, right, rates, button, scrub, time, player};
}
