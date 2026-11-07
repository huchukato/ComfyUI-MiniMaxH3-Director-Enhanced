// Studio data rules: document round trip, 0.1 s grid, reorder, lanes, render-part file windows and canvas presets.
import assert from "node:assert/strict";
import * as model from "../../../js/ng/h3s_model.js";
import * as canvas from "../../../js/ng/h3s_canvas.js";

const shot = (id, start, end) => ({ id, start, end, text: id, media: [], spoken: [], locked_fields: [], draft: null });

// Document: old timed text, shots plus lanes, empty project.
{
  const old = model.readProject("0-4: A walk.\n4-8: A turn.");
  assert.equal(old.shots.length, 2);
  assert.deepEqual([old.audio, old.lanes], [[], []]);
  const clip = model.newClip("song", "lane_a", 0, 20);
  const text = model.writeProject({ shots: old.shots, audio: [clip], lanes: ["lane_a", "lane_b"] });
  const back = model.readProject(text);
  assert.deepEqual(back.audio, [clip]);
  assert.deepEqual(back.lanes, ["lane_a", "lane_b"], "empty lanes are kept");
  assert.equal(back.shots[1].text, "A turn.");
  assert.equal(model.writeProject({ shots: [], audio: [], lanes: [] }), "", "an empty project leaves the Prompt in charge");
  assert.deepEqual(model.readProject('{"format":"h3-director-shots","schema_version":1,"shots":[],"audio":[{"id":"x"}]}').skipped, ["x"],
    "an invalid clip is named and left out (BUG-002), not an error for the whole document");
}

// Grid and formatting.
{
  assert.equal(model.r1(3.14159), 3.1);
  assert.equal(model.fmt(10), "10 s");
  assert.equal(model.fmt(10.125), "10.1 s");
  assert.equal(model.span(0, 6.5), "0–6.5 s");
}

// Moving and edges stay between neighbours on the 0.1 s grid.
{
  const shots = [shot("a", 0, 6), shot("b", 6, 13), shot("c", 13, 20)];
  const edge = model.dragTo(shots, { id: "b", mode: "right", start: 6, end: 13 }, 0.26, 20);
  assert.deepEqual(edge.items.find((s) => s.id === "b"), { ...shots[1], end: 13 }, "an edge stops at the next shot");
  const left = model.dragTo(shots, { id: "b", mode: "left", start: 6, end: 13 }, 0.34, 20);
  assert.equal(left.items.find((s) => s.id === "b").start, 6.3);
  const short = model.dragTo(shots, { id: "b", mode: "right", start: 6, end: 13 }, -9, 20);
  assert.equal(short.items.find((s) => s.id === "b").end, 6.5, "a shot keeps its minimum length");
}

// Carrying a shot over others reorders it; lengths and the old gaps stay.
{
  const shots = [shot("a", 0, 6), shot("b", 6, 13), shot("c", 15, 20)];
  const layout = model.sorted(shots).map(({ id, start, end }) => ({ id, start, end }));
  const drag = { id: "a", mode: "move", start: 0, end: 6, reorder: true };
  const moved = model.dragTo(shots, drag, 14, 20);
  assert.equal(moved.target, 2, "dropped behind the last shot");
  const result = model.reorder(moved.items, "a", moved.target, layout);
  assert.deepEqual(model.sorted(result).map((s) => [s.id, s.start, s.end]), [["b", 0, 7], ["c", 7, 12], ["a", 14, 20]], "gaps stay where they were in the row");
  const free = model.dragTo([shot("a", 0, 2), shot("b", 10, 12)], { id: "a", mode: "move", start: 0, end: 2, reorder: true }, 4, 20);
  assert.equal(free.target, null, "free room means no reorder");
  assert.deepEqual([free.items[0].start, free.items[0].end], [4, 6]);
}

// New items fill the free room at the drop point.
{
  const shots = [shot("a", 0, 6), shot("b", 9, 20)];
  assert.deepEqual(model.placeAt(shots, 7, 20, 4), { start: 7, end: 9 });
  assert.equal(model.placeAt(shots, 3, 20, 4), null, "no room inside a shot");
  assert.deepEqual(model.placeAt([], 18, 20, 4), { start: 18, end: 20 });
}

// A lane clip keeps its own clock across render parts.
{
  const clip = { start: 4, end: 18, offset: 10 };
  const chunks = [{ index: 0, start_s: 0, end_s: 10 }, { index: 1, start_s: 10, end_s: 20 }];
  assert.deepEqual(model.clipParts({ ...clip, mode: "lock" }, chunks), [{ index: 0, story: [4, 10], file: [10, 16], reference: false },
    { index: 1, story: [10, 18], file: [16, 24], reference: false }]);
  // BUG-022: a reference clip is not played in slices; each touched part gets its whole window.
  assert.deepEqual(model.clipParts({ ...clip, mode: "ref" }, chunks).map((part) => part.file), [[10, 24], [10, 24]]);
  // BUG-020: several windows of one audio card are several native inputs.
  assert.equal(model.chunkBudget({ refs: [{ kind: "audio", ctx_id: "song" }, { kind: "audio", ctx_id: "song" }, { kind: "lock", ctx_id: "song" }] }).audio, 2);
  assert.deepEqual(model.clipToFit([{ start: 2, end: 30 }, { start: 19.9, end: 25 }], 20), [{ start: 2, end: 20 }]);
  assert.equal(model.partColor(7)[0], model.PART_COLORS[1][0]);
}

// Canvas: the Legacy presets and fit.
{
  assert.equal(canvas.presetValue(0, 0), "auto");
  assert.equal(canvas.presetValue(1344, 768), "1344x768");
  assert.equal(canvas.presetValue(1000, 768), "custom");
  assert.deepEqual(canvas.fitAspect(canvas.NATIVE_MP * 1e6, 9 / 16), [768, 1344], "the Legacy 9:16 budget fit");
  assert.deepEqual(canvas.fitAspect(canvas.NATIVE_MP * 1e6, 16 / 9), [1344, 768]);
  assert.equal(canvas.nearestAspect(1344, 768), "16:9");
  assert.equal(canvas.nearestAspect(1000, 333), "");
  assert.equal(canvas.snap32(1000), 992);
  assert.equal(canvas.canvasInfo(1920, 1088)[1], "warn");
  assert.equal(canvas.canvasInfo(0, 0)[1], "");
}

// Reference slots per render part (moved from the former Inspector, same three cases).
{
  const refs = (...list) => ({ refs: list.map(([kind, ctx_id]) => ({ kind, ctx_id })) });
  assert.deepEqual(model.chunkBudget(refs(["picture", "alice"], ["picture", "coat"], ["picture", "bob"], ["picture", "coat"], ["video", "move"],
    ["audio", "voice_a"], ["audio", "voice_b"])), { image: 4, video: 1, audio: 2, total: 7 }, "a shared asset takes one Picture slot per Subject");
  assert.deepEqual(model.chunkBudget(refs(["picture", "alice"], ["picture", "coat"], ["picture", "bob"], ["picture", "coat"], ["picture", "start"],
    ["first_frame", "start"], ["continue_video", "move"], ["keyframe", "key"], ["lock", "sound"], ["audio", "voice_a"], ["audio", "voice_b"])),
    { image: 5, video: 0, audio: 2, total: 7 }, "a frame that is a Picture reuses its slot; guides and locks are not reference tokens");
  assert.deepEqual(model.chunkBudget(refs(["first_frame", "frame"], ["last_frame", "frame"])), { image: 2, video: 0, audio: 0, total: 2 });
}

// A known turbo LoRA is found in the shared profile table whatever its folder and case; the user picks the LoRA, nothing is preset.
{
  const { readFileSync } = await import("node:fs");
  const table = JSON.parse(readFileSync(new URL("../../../js/ng/turbo_profiles.json", import.meta.url), "utf8"));
  assert.equal(model.turboProfile(table, "MiniMax-H3\\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors").steps, 6);
  assert.equal(model.turboProfile(table, "minimax-h3/MINIMAX_H3_TURBO_4STEP_CKPT500_PRUNED_COMFYUI.safetensors").steps, 8);
  assert.equal(model.turboProfile(table, "flux2/Flux2TurboComfyv2.safetensors"), null);
  assert.equal(model.turboProfile(table, "none"), null);
}

// "+ Shot" always finds a place: room after the selected shot, else any free room, else it halves a shot.
{
  const at = (id, start, end) => ({ id, start, end });
  let made = model.addShotAt([at("a", 0, 4)], null, 8);
  assert.deepEqual([made.shots.at(-1).start, made.shots.at(-1).end, made.split], [4, 8, undefined], "free room after the last shot");
  made = model.addShotAt([at("a", 2, 8)], null, 8);
  assert.deepEqual([made.shots.at(-1).start, made.shots.at(-1).end], [0, 2], "free room before it when the end is full");
  made = model.addShotAt([at("a", 0, 8)], null, 8);
  assert.equal(made.split, "a", "a full timeline (Whole prompt = one shot) halves the shot");
  assert.deepEqual(made.shots.map((s) => [s.start, s.end]), [[0, 4], [4, 8]]);
  made = model.addShotAt([at("a", 0, 3), at("b", 3, 8)], "a", 8);
  assert.equal(made.split, "a", "the selected shot is the one that is halved");
  assert.deepEqual(made.shots.map((s) => [s.start, s.end]).sort((x, y) => x[0] - y[0]), [[0, 1.5], [1.5, 3], [3, 8]]);
  assert.equal(model.addShotAt([at("a", 0, 0.5), at("b", 0.5, 1)], null, 1), null, "nothing to halve below the minimum length");
  // No result ever overlaps.
  for (const shots of [[at("a", 0, 8)], [at("a", 0, 4), at("b", 4, 8)], [at("a", 1, 2), at("b", 5, 8)]]) {
    const list = model.sorted(model.addShotAt(shots, null, 8).shots);
    list.slice(1).forEach((shot, i) => assert.ok(shot.start >= list[i].end - 1e-9, "shots do not overlap"));
  }
}

// Several spoken lines per shot: each one is edited on its own, order and the untouched lines stay.
{
  const a = { schema_version: 1, text: "Hello.", speaker_id: "mage", voice: "a narrator", language: "German", delivery: "says" };
  const b = { schema_version: 1, text: "Hi.", speaker_id: "", voice: "a calm man", language: "English", delivery: "whispers" };
  let lines = model.editSpoken([a, b], 1, { text: "Hi there." });
  assert.deepEqual(lines, [a, { ...b, text: "Hi there." }], "the second line changes alone, its voice and delivery stay");
  lines = model.addSpoken(lines);
  assert.equal(lines.length, 3);
  assert.equal(lines[2].language, "English", "a new line takes the previous line's language");
  lines = model.editSpoken(lines, 2, { text: "Bye.", speaker_id: "mage" });
  assert.deepEqual(model.removeSpoken(lines, 0).map((line) => line.text), ["Hi there.", "Bye."]);
  assert.deepEqual(model.editSpoken([], 0, { text: "First." }).map((line) => [line.text, line.language]), [["First.", "English"]], "the first input creates the line");
  assert.deepEqual(model.editSpoken([{ ...b, delivery: "says" }], 0, { text: "", speaker_id: "" }), [], "clearing the only plain English line leaves the shot without dialogue");
  assert.equal(model.editSpoken([b], 0, { text: "", speaker_id: "" })[0].delivery, "whispers", "a chosen delivery stays while retyping, like a language");
  // BUG-035: a language picked before typing, or kept while retyping, is not thrown away.
  assert.deepEqual(model.editSpoken([], 0, { language: "German" }).map((line) => [line.text, line.language]), [["", "German"]]);
  assert.equal(model.editSpoken([a], 0, { text: "", speaker_id: "" })[0].language, "German", "retyping a German line keeps German");
  assert.equal(model.editSpoken([a, b], 0, { text: "", speaker_id: "" }).length, 2, "an emptied line among others stays until removed");
}

// BUG-002: one bad audio clip is left out on its own; the shots and the other clips stay editable.
{
  const shot = { id: "s1", start: 0, end: 4, text: "Walk.", media: [], spoken: [], locked_fields: [], draft: null };
  const good = { schema_version: 1, id: "c1", context_id: "song", start: 0, end: 4, offset: 0, mode: "lock", lane: "l1" };
  const text = JSON.stringify({ format: "h3-director-shots", schema_version: 1, shots: [shot],
    audio: [good, { ...good, id: "bad", start: 5, end: 2 }, { ...good, start: 6, end: 8 }], audio_lanes: ["l1"] });
  const project = model.readProject(text);
  assert.equal(project.error, "");
  assert.deepEqual([project.shots.map((s) => s.id), project.audio.map((c) => c.id), project.skipped], [["s1"], ["c1"], ["bad", "c1"]]);
  assert.equal(model.readProject("{ broken").error.length > 0, true, "unreadable JSON is still an error that keeps the original");
}

// BUG-001: a shorter duration names what it removes and what it only shortens.
{
  const items = [{ id: "a", start: 0, end: 6 }, { id: "b", start: 6, end: 12 }, { id: "c", start: 12, end: 20 }];
  const cut = model.trimToDuration(items, 10);
  assert.deepEqual([cut.items.map((i) => [i.id, i.end]), cut.removed, cut.shortened], [[["a", 6], ["b", 10]], ["c"], ["b"]]);
  assert.deepEqual(model.trimToDuration(items, 30), { items, removed: [], shortened: [] });
  // A longer project: the shot that reached the old end follows it (a 10 s shot left 17-27 s of a song without text).
  const grown = model.growToDuration(items, 20, 27);
  assert.deepEqual([grown.items.map((i) => i.end), grown.grown], [[6, 12, 27], ["c"]]);
  assert.deepEqual(model.growToDuration([{ id: "a", start: 0, end: 8 }], 10, 27).grown, [], "a shot that stopped earlier stays");
  assert.deepEqual(model.growToDuration(items, 20, 15).grown, [], "shorter is trimToDuration's job");
}

// The Look rides in the shot document; with shots it opens every render part in place of the Prompt.
{
  const shot = { ...model.newShot(0, 8), text: "She sings." };
  const back = model.readProject(model.writeProject({ shots: [shot], audio: [], lanes: [], look: "Gothic hall, anime style." }));
  assert.equal(back.look, "Gothic hall, anime style.");
  assert.equal(model.readProject(model.writeProject({ shots: [shot], audio: [], lanes: [] })).look, "", "no look, no key");
  assert.ok(model.writeProject({ shots: [], audio: [], lanes: [], look: "kept" }).includes('"look":"kept"'), "a look alone is kept for later shots");
  assert.equal(model.readProject("0-4: A walk.").look, "", "timed text has no look");
  const parts = model.setPartPrompt(model.setPartPrompt([], 1, "k1", "second", "ai"), 0, "k0", "first", "user");
  assert.deepEqual(parts.map((entry) => entry.index), [0, 1]);
  assert.deepEqual(model.readProject(model.writeProject({ shots: [shot], audio: [], lanes: [], partPrompts: parts })).partPrompts, parts);
  assert.deepEqual(model.setPartPrompt(parts, 0, "", "", "user").map((entry) => entry.index), [1], "empty text removes the part's own prompt");
}

console.log("h3s model ok");

// Keyframes in a shot: own role or the card's, a time in seconds after the shot's start, and where the plan put it.
{
  const shot = { id: "s1", start: 20, end: 40 };
  const keyCard = { usage: ["keyframe"] }, refCard = { usage: ["reference"] };
  assert.equal(model.isKeyframe({ role: "context" }, keyCard), true, "the card's role counts when the shot keeps it");
  assert.equal(model.isKeyframe({ role: "keyframe" }, refCard), true, "a role chosen in the shot wins");
  assert.equal(model.isKeyframe({ role: "first_frame" }, keyCard), false);
  assert.equal(model.middleOf(shot), 10);
  assert.equal(model.keyframeAt({ at_s: 12.5 }, shot), 12.5);
  assert.equal(model.keyframeAt({ at_s: 99 }, shot), 20, "never past the shot's end");
  assert.equal(model.keyframeAt({}, shot), 0, "an older binding without a time sits at the shot's start");
  const plan = { fps: 24, chunks: [
    { index: 0, story_end_f: 723, shots: [{ shot_id: "s1" }], refs: [{ kind: "first_frame", ctx_id: "a" }, { kind: "last_frame", ctx_id: "k" }] },
    { index: 1, story_end_f: 961, shots: [{ shot_id: "s1" }], refs: [{ kind: "last_frame", ctx_id: "z" }] }] };
  assert.deepEqual(model.keyframeLanding(plan, "s1", "k"), { seconds: 30.08, part: 1, inside: false });
  plan.chunks[0].refs[1].kind = "keyframe";
  assert.deepEqual(model.keyframeLanding(plan, "s1", "k"), { seconds: null, part: 1, inside: true });
  assert.equal(model.keyframeLanding(null, "s1", "k"), null);
}

// The first picture's shape at three sizes (user 2026-10-18: smaller or larger, but keep the aspect, as in the Legacy Director).
{
  const portrait = 2 / 3, wide = 16 / 9;
  assert.deepEqual(canvas.pictureSize(portrait, "small"), [480, 736]);
  assert.deepEqual(canvas.pictureSize(portrait, "native"), [768, 1152], "native is the server's own picture size");
  assert.deepEqual(canvas.pictureSize(portrait, "large"), [1088, 1632]);
  assert.deepEqual(canvas.pictureSize(wide, "native"), [1344, 768], "native keeps H3's area cap");
  for (const tier of ["small", "native", "large"]) {
    const [w, h] = canvas.pictureSize(portrait, tier);
    assert.ok(Math.abs(w / h - portrait) / portrait < 0.04, `${tier} keeps the shape`);
    assert.equal(w % 32 + h % 32, 0);
  }
  assert.equal(canvas.presetValue(480, 736, portrait), "picture:small");
  assert.equal(canvas.presetValue(480, 736), "480x736", "without a picture the same size is the fixed Fast format");
  assert.equal(canvas.presetValue(1088, 1632), "custom", "and the large one a custom size");
  assert.equal(canvas.presetValue(0, 0, portrait), "auto");
}
