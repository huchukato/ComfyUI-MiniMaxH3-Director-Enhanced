// Timeline: picture track with shots, free audio lanes and the render parts the plan produced.
// During a mouse drag only the dragged block is moved; the project is written once, on release.
import { h, icon, tip } from "./h3s_dom.js";
import { dragTo, reorder, sorted, span, fmt, partColor, r1, isKeyframe, keyframeAt, nextClipStart } from "./h3s_model.js";
import { timeView, tickTimes } from "./h3s_time.js";
import { timelineNavigation, rememberTimeline } from "./h3s_navigation.js";

const MODE_SHORT = { lock: "locked", copy: "copy", ref: "reference" };
const DEFAULT_HINT = "";
const HOW = "Drag = move/reorder · edges = trim · ←/→ = move selected (Shift: 1 s) · Delete = remove · 0.1 s grid. "
  + "Audio runs independently of shots. Control clips affect whole render parts: uncovered edges hold their nearest control frame.";

export function timelineView(S, actions) {
  const axis = Math.max(S.duration, S.plan?.total_s || 0);
  const view = timeView(S.timeline), ticks = tickTimes(axis, view.zoom);
  const pct = (seconds) => `${seconds / axis * 100}%`;
  const info = h("span", { class: "h3s-lbl" }, DEFAULT_HINT);
  const beyond = () => axis - S.duration > 0.01 ? h("span", { class: "h3s-beyond", style: { left: pct(S.duration), width: pct(axis - S.duration) },
    title: `After the project end (${fmt(S.duration)}): H3 renders in fixed frame steps and delivers ${fmt(axis)}. Shots and audio end at ${fmt(S.duration)}.` }) : null;
  const grid = () => [...ticks.map((t) => h("span", { class: "h3s-grid", style: { left: pct(t) } })), beyond()].filter(Boolean);
  const lane = (name, track) => h("div", { class: "h3s-lane" }, name, track);

  function secondsAt(event, track) {
    const box = track.getBoundingClientRect();
    return Math.max(0, Math.min(S.duration, r1((event.clientX - box.left) / box.width * axis)));
  }

  // kind "shot" or "clip"; items are the shots or the clips of one lane.
  function grab(event, kind, item, mode, items, track, block) {
    event.stopPropagation(); event.preventDefault();
    block.focus?.({ preventScroll: true });
    const drag = { id: item.id, mode, start: item.start, end: item.end, reorder: kind === "shot" && mode === "move" };
    const width = track.getBoundingClientRect().width, x0 = event.clientX, layout = sorted(items).map(({ id, start, end }) => ({ id, start, end }));
    const handle = event.currentTarget;
    let result = null;
    try { handle.setPointerCapture(event.pointerId); } catch {}
    actions.beginPointer();
    block.classList.add("drag");
    handle.onpointermove = (move) => {
      result = dragTo(items, drag, (move.clientX - x0) / width * axis, S.duration);
      const moved = result.items.find((entry) => entry.id === item.id);
      block.style.left = pct(moved.start); block.style.width = pct(moved.end - moved.start);
      if (kind === "shot" && result.target !== null) {
        const others = sorted(items.filter((entry) => entry.id !== item.id));
        info.textContent = result.target < others.length ? `Release: goes before ${actions.shotLabel(others[result.target].id)}. The other shots move up.`
          : `Release: goes to the end, after ${actions.shotLabel(others[others.length - 1].id)}.`;
      } else info.textContent = `${span(moved.start, moved.end)} · length ${fmt(moved.end - moved.start)}`;
    };
    const finish = (cancelled) => {
      handle.onpointermove = handle.onpointerup = handle.onpointercancel = handle.onlostpointercapture = null;
      block.classList.remove("drag");
      if (cancelled) { block.style.left = pct(item.start); block.style.width = pct(item.end - item.start); info.textContent = DEFAULT_HINT; }
      actions.endPointer();
      if (cancelled) return;
      S.timelineFocus = { kind, id: item.id };
      const moved = result?.items.find((entry) => entry.id === item.id);
      if (!moved || (moved.start === item.start && moved.end === item.end)) { actions.select(kind, item.id); return; }
      const changed = result.target !== null && kind === "shot" ? reorder(result.items, item.id, result.target, layout) : result.items;
      if (kind === "shot") actions.setShots(changed, item.id);
      else if (kind === "control") actions.setControls(changed, item.id);
      else actions.setClips(changed.concat(S.audio.filter((clip) => clip.lane !== item.lane)), item.id);
    };
    handle.onpointerup = () => finish(false);
    handle.onpointercancel = handle.onlostpointercapture = () => finish(true);
  }

  function selectable(block, kind, item, label) {
    block.setAttribute("role", "button"); block.setAttribute("tabindex", "0");
    block.setAttribute("aria-label", `${label}: ${span(item.start, item.end)}`);
    Object.assign(block.dataset, { timelineKind: kind, timelineId: item.id });
    block.onkeydown = (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation(); S.timelineFocus = { kind, id: item.id }; actions.select(kind, item.id);
    };
  }

  function dropZone(track, onDrop, overClass = "over") {
    const line = h("span", { class: "h3s-drop", hidden: true });
    track.append(line);
    track.ondragover = (event) => { event.preventDefault(); track.classList.add(overClass); line.hidden = false; line.style.left = pct(secondsAt(event, track)); };
    track.ondragleave = () => { track.classList.remove(overClass); line.hidden = true; };
    track.ondrop = (event) => { event.preventDefault(); track.classList.remove(overClass); line.hidden = true; onDrop(secondsAt(event, track), actions.takeDragged()); };
  }

  function shotBlock(shot, track) {
    const selected = S.selected?.kind === "shot" && S.selected.id === shot.id;
    const block = h("div", { class: selected ? "h3s-shot sel" : "h3s-shot", style: { left: pct(shot.start), width: pct(shot.end - shot.start) },
      title: shot.text || "No text yet" });
    selectable(block, "shot", shot, actions.shotLabel(shot.id));
    const grip = (side) => h("span", { class: "h3s-grip", style: { [side]: 0 }, onpointerdown: (event) => grab(event, "shot", shot, side, S.shots, track, block) });
    block.onpointerdown = (event) => grab(event, "shot", shot, "move", S.shots, track, block);
    block.ondragover = (event) => { event.preventDefault(); event.stopPropagation(); };
    block.ondrop = (event) => { event.preventDefault(); event.stopPropagation(); actions.assign(shot.id, actions.takeDragged()); };
    const chips = shot.media.map((binding) => S.byId.get(binding.context_id)).filter(Boolean)
      .map((entry) => h("span", { class: "h3s-chip", style: { background: entry.bg, color: entry.color } }, entry.name));
    // A Keyframe in the shot: a diamond at its time, so moving the shot visibly takes it along.
    // A binding whose card is not connected (yet) has no entry: no mark, as no chip.
    const marks = shot.media.filter((binding) => S.byId.has(binding.context_id) && isKeyframe(binding, S.byId.get(binding.context_id))).map((binding) => {
      const entry = S.byId.get(binding.context_id), at = keyframeAt(binding, shot), length = shot.end - shot.start;
      return h("span", { class: "h3s-keymark", title: `${entry.name}: Keyframe at ${fmt(shot.start + at)}`,
        style: { position: "absolute", top: "2px", left: `calc(${length ? (at / length) * 100 : 0}% - 5px)`, width: "10px", height: "10px",
          transform: "rotate(45deg)", background: entry.color, border: "1px solid #0B0E13", pointerEvents: "none" } });
    });
    block.append(...marks);
    block.append(grip("left"), h("div", { class: "h3s-shot-body" },
      h("span", { class: "h3s-row", style: { gap: "8px", fontSize: "12px" } }, h("strong", {}, actions.shotLabel(shot.id)),
        h("span", { class: "h3s-muted", style: { fontFamily: "IBM Plex Mono, Consolas, monospace" } }, span(shot.start, shot.end)),
        S.suggestions[shot.id] ? h("span", { class: "h3s-chip", style: { background: "#3A2F66", color: "#E1D8FF" } }, "AI suggestion") : null),
      h("span", { class: "h3s-shot-text", style: { color: shot.text ? "#C9D1DE" : "#7F8A9C" } }, shot.text || "No text yet"),
      h("span", { class: "h3s-row", style: { gap: "4px", marginTop: "auto", flexWrap: "nowrap" } }, chips)),
      grip("right"));
    return block;
  }

  function shotTrack() {
    const track = h("div", { class: S.ghosts.length ? "h3s-track ghosting" : "h3s-track", style: { height: "calc(84px + var(--h3s-grow, 0px))" } }, grid());
    dropZone(track, (sec, id) => actions.newShot(sec, id));
    if (!S.shots.length && !S.ghosts.length)
      track.append(h("div", { class: "h3s-empty" }, "No shots yet: drag Content here, use “+ Shot” or “Whole prompt = one shot”. Without shots the prompt carries the whole video."));
    for (const shot of sorted(S.shots)) track.append(shotBlock(shot, track));
    for (const ghost of S.ghosts)
      track.append(h("div", { class: "h3s-shot ghost", style: { left: pct(ghost.start), width: pct(ghost.end - ghost.start) } },
        h("span", { style: { fontSize: "12px", color: "#C9BBFF", fontWeight: 600 } }, `Suggestion · ${span(ghost.start, ghost.end)}`),
        h("span", { class: "h3s-shot-text", style: { color: "#C9BBFF" } }, [ghost.text, ...(ghost.spoken || []).map((line) => `“${line.text}”`)].join(" "))));
    return track;
  }

  function clipBlock(clip, items, track, kind = "clip") {
    const entry = S.byId.get(clip.context_id), selected = S.selected?.kind === kind && S.selected.id === clip.id;
    const block = h("div", { class: selected ? "h3s-clip sel" : "h3s-clip", style: { left: pct(clip.start), width: pct(clip.end - clip.start),
      borderColor: selected ? undefined : entry?.color }, title: `${entry?.name || clip.context_id}: ${span(clip.start, clip.end)}, from ${fmt(clip.offset)} in the file` });
    selectable(block, kind, clip, `${kind === "control" ? "Control" : "Audio"}: ${entry?.name || clip.context_id}`);
    const grip = (side) => h("span", { class: "h3s-grip", style: { [side]: 0 }, onpointerdown: (event) => grab(event, kind, clip, side, items, track, block) });
    block.onpointerdown = (event) => grab(event, kind, clip, "move", items, track, block);
    block.append(grip("left"), h("span", { class: "h3s-clip-label" },
      h("span", { class: "h3s-swatch", style: { background: entry?.color || "#B38CF5" } }),
      h("strong", {}, entry?.name || "Not connected"), h("span", { style: { color: "#B9ADD6" } }, `${kind === "control" ? entry?.controlKind || "canny" : MODE_SHORT[clip.mode]} · ${span(clip.start, clip.end)}`)), grip("right"));
    return block;
  }

  function sourcePicker(kind, name, items, laneId = "") {
    const choices = (S.contexts || []).filter((entry) => kind === "control"
      ? entry.media === "video" && entry.usage.includes("control") : entry.media === "audio");
    const sec = nextClipStart(items, S.duration);
    return h("select", { class: "h3s-lane-source", "aria-label": `Add ${kind === "control" ? "control" : "audio"} clip to ${name}`,
      disabled: !choices.length || sec === null,
      title: !choices.length ? `Connect ${kind === "control" ? "a Control video" : "an Audio"} card first`
        : sec === null ? "No free room on this lane: shorten or move a clip first" : `Add a clip to ${name}, after existing clips or in free room`,
      onchange: (event) => {
        if (!event.target.value || sec === null) return;
        if (kind === "control") actions.newControl(sec, event.target.value);
        else actions.newClip(laneId, sec, event.target.value);
      } }, h("option", { value: "" }, "+"), choices.map((entry) => h("option", { value: entry.id }, entry.name)));
  }

  function laneRow(laneId, index) {
    const items = S.audio.filter((clip) => clip.lane === laneId);
    const track = h("div", { class: "h3s-track", style: { height: "34px" } }, grid());
    dropZone(track, (sec, id) => actions.newClip(laneId, sec, id));
    if (!items.length) track.append(h("span", { class: "h3s-empty", style: { justifyContent: "flex-start", fontSize: "12px" } }, "empty · use + at left, or drag audio here"));
    for (const clip of sorted(items)) track.append(clipBlock(clip, items, track));
    const name = h("span", { class: "h3s-lane-name" }, h("span", { class: "h3s-swatch", style: { background: "#B38CF5" } }), `Audio ${index + 1}`,
      sourcePicker("clip", `Audio ${index + 1}`, items, laneId),
      items.length ? null : h("button", { class: "h3s-btn ghost small", title: "Remove empty audio lane", "aria-label": "Remove empty audio lane",
        onclick: () => actions.removeLane(laneId) }, icon("close", 12)));
    return lane(name, track);
  }

  function newLaneRow() {
    const zone = h("button", { class: "h3s-lane-add", onclick: () => actions.addLane() }, icon("plus"), "New audio lane · drag audio here or click");
    zone.ondragover = (event) => { event.preventDefault(); zone.classList.add("over"); };
    zone.ondragleave = () => zone.classList.remove("over");
    zone.ondrop = (event) => { event.preventDefault(); zone.classList.remove("over"); actions.addLane(actions.takeDragged()); };
    return lane(h("span"), zone);
  }

  function controlRow() {
    const items = S.control || [], track = h("div", { class: "h3s-track", style: { height: "40px" }, "aria-label": "Control lane" }, grid());
    dropZone(track, (sec, id) => actions.newControl(sec, id));
    if (!items.length) track.append(h("span", { class: "h3s-empty", style: { fontSize: "12px" } }, "Use + at left or drag a Control video card here · Canny, Pose, Depth or Inpaint"));
    for (const clip of sorted(items)) track.append(clipBlock(clip, items, track, "control"));
    return lane(h("span", { class: "h3s-lane-name" }, h("span", { class: "h3s-swatch", style: { background: "#E6BE57" } }), "Control",
      sourcePicker("control", "Control", items)), track);
  }

  function partsRow() {
    const track = h("div", { class: "h3s-track", style: { height: "30px", border: 0 } });
    const chosen = S.selectedRange;
    for (const chunk of S.plan?.chunks || []) {
      const [color, bg] = partColor(chunk.index), hit = chosen && chosen[0] < chunk.end_s && chosen[1] > chunk.start_s;
      track.append(h("div", { class: "h3s-part", style: { left: pct(chunk.start_s), width: pct(chunk.end_s - chunk.start_s), borderColor: color, background: hit ? bg : "#141922" },
        title: chunk.picture ? `Picture ${chunk.index + 1}: this shot as one picture` : `Part ${chunk.index + 1}: ${chunk.delivered_frames} new frames${chunk.head_frames ? `, with ${chunk.head_frames} preceding frames for continuity` : ""}` },
        h("span", { class: "h3s-swatch", style: { background: color } }), `${chunk.picture ? "Picture" : "Part"} ${chunk.index + 1} · ${span(chunk.start_s, chunk.end_s)}`));
    }
    // A failed plan is said in warning colour: in grey small print it read like "still planning" (2026-10-11).
    if (!S.plan) track.append(S.planError ? h("span", { class: "h3s-warn", role: "alert", style: { fontSize: "13px", padding: "4px 8px" } },
      `The plan failed: ${S.planError}`) : h("span", { class: "h3s-empty", style: { fontSize: "12px" } }, "Planning …"));
    return lane(h("span", { class: "h3s-lane-name" }, "Render parts"), track);
  }

  const ghostBanner = S.ghosts.length ? h("div", { class: "h3s-banner" },
    `AI suggestion: ${S.ghosts.length} shots from your prompt (dashed). ${S.shots.length ? `Accept replaces your ${S.shots.length} shots; audio lanes stay.` : "Nothing changes until you accept."}`, h("span", { class: "h3s-grow" }),
    h("button", { class: "h3s-btn ai", onclick: actions.acceptGhosts }, "Accept"), h("button", { class: "h3s-btn ghost", onclick: actions.dropGhosts }, "Discard")) : null;
  const summary = S.plan ? `${S.plan.chunks.length} ${S.plan.chunks.length === 1 ? "part" : "parts"}, delivers ${fmt(S.plan.total_s)} (${S.plan.total_frames} frames)` : "";

  const scroller = h("div", { class: "h3s-time-scroll", tabindex: "0", role: "region", "aria-label": "Timeline tracks",
    onscroll: (event) => {
      const el = event.currentTarget, room = el.scrollWidth - el.clientWidth;
      rememberTimeline(S, { ...view, scroll: room > 0 ? el.scrollLeft / room : 0 });
    } }, h("div", { class: "h3s-time-tracks", style: { width: `calc(128px + (100% - 128px) * ${view.zoom})` } },
    lane(h("span", { class: "h3s-lane-name" }, "Time (s)"), h("div", { class: "h3s-ruler" },
      ticks.map((t) => h("span", { class: "h3s-tick", style: { left: pct(t) } }, `${t}`)))),
    lane(h("span", { class: "h3s-lane-name" }, h("span", { class: "h3s-swatch", style: { background: "#8FC1FF" } }), "Shots"), shotTrack()),
    S.lanes.map(laneRow), newLaneRow(), controlRow(), partsRow()));

  return h("section", { class: "h3s-card h3s-timeline" }, timelineNavigation(S, actions),
    h("div", { class: "h3s-row" }, tip(HOW), info, h("span", { class: "h3s-grow" }),
      h("button", { class: "h3s-btn small", onclick: () => actions.addShot() }, icon("plus"), "Shot"),
      h("button", { class: "h3s-btn small", onclick: () => actions.addLane() }, icon("plus"), "Audio lane")),
    ghostBanner,
    scroller,
    h("div", { class: "h3s-row", style: { marginTop: "4px" } }, h("span", { class: "h3s-lbl" }, "Render parts"),
      h("span", { class: "h3s-lbl", title: "H3 produces lengths in fixed frame steps (17·k+5 at 24 FPS)." }, summary)),
    );
}
