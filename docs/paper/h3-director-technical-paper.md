# Long-form audio-video generation with MiniMax H3: a shot planner, pinned continuation and a seam-aware compiler

**Technical report, draft v0.2 — October 2026.** The MiniMax H3 Director for ComfyUI (`ComfyUI-MiniMaxH3-Director`,
branch `ng`, version 1.0.0), maintained by seesee75. GPL-3.0.

Measurements were made on one machine (RTX 5060 Ti 16 GB, ComfyUI 0.41, H3 int8 checkpoints) and, unless stated
otherwise, with **one seed per condition**. They show the direction and size of effects, not distributions.

---

## Abstract

MiniMax H3 generates video and sound together, but one sampling run covers at most about 15 seconds. We describe a
ComfyUI node pack that turns a storyboard of shots, pictures, voices and songs into a video of any length. The project is
planned as a chain of *render parts* on H3's frame grid and sampled part by part inside ComfyUI's native loop. Each part
continues the previous one by pinning the last latent frames of picture *and* sound as never-denoised keyframes; the
parts are decoded jointly in latent space, and the sound is cut on absolute story time and crossfaded into the next
part's own take of the same moment. A compiler writes, for every part, the structured prompt H3 was trained on, with only
the share of each shot that falls into that part. We report what the chain preserves (sound correlation 0.92 across a
seam against 0.13 without pinning; a locked song keeps 0.97 envelope correlation over seams at a constant −4 ms offset),
where it fails (generated sound loses its highs over many parts; a pinned head delays a new action by about 2.4 s; a shot
change in the last two seconds of a part is cut twice) and the planning rules derived from those failures. Two further
measured results: parts of up to 30 s at small picture sizes, and an optional step forecast that cuts sampling time by a
third.

## 1 · Introduction

Text-to-video models produce short clips. Films, music videos and stories need minutes, several shots, recurring
characters with their voices and often a song that must stay exactly as it is. Concatenating independent clips fails in
four visible ways: the picture jumps at every join, the sound restarts, characters change their look, and a story written
for the whole video is replayed in every clip.

This report describes how the H3 Director addresses each failure with a mechanism that was measured rather than assumed.
Its contributions are:

1. **A planner** that cuts a project into render parts on H3's `17k + 5` frame grid with near-equal lengths, moves part
   edges away from shot changes, and lets parts grow beyond 15 s when the picture is small (§4).
2. **Pinned continuation of picture and sound** inside ComfyUI's native `StartLoop`/`EndLoop`, using H3's own keyframe
   conditioning, with exact sub-frame alignment of the sound window (§5).
3. **A seam-aware collector** that decodes all parts as one latent and crossfades the sound at the joins (§5.3).
4. **A per-part prompt compiler** that writes H3's training notation and shares long shots between parts without
   replaying actions or camera moves (§6).
5. **A measured set of rules** (§7–§8) that turn the failures of long chains into planner warnings and edge moves.

Everything runs with ComfyUI's own H3 nodes and samplers; the pack patches neither ComfyUI nor the model.

## 2 · Background

### 2.1 MiniMax H3

- **Two checkpoints.** `fl2va` (first/last frame to video+audio) generates from text and optional frame pictures;
  `ref2va` (reference to video+audio) takes reference pictures, videos and sounds that are *not* frames of the result.
  Both share a Qwen3-VL text encoder that reads the prompt together with the reference pictures.
- **Packed AV latent.** Picture and sound form one latent, a `NestedTensor` of a video latent and an audio latent. A video
  latent step covers 1, 4, 4, 4, 4 pixel frames in a repeating cycle; the audio latent runs at 40 steps per second, so
  one pixel frame at 24 fps is 5/3 audio steps.
- **Frame grid.** A sampled clip has `N = 17k + 5` frames (5.2 s, 10.1 s, 15.1 s …).
- **Trained range.** 96–360 frames per clip (4–15 s) at about 0.9 megapixels (1280×704).
- **Keyframes.** ComfyUI's H3 integration accepts `minimax_keyframes` in the conditioning: latent rows placed at a frame
  index of the new clip and never denoised. This is the mechanism we use for continuation.
- **Prompt notation.** H3 was trained on a structured prompt: `subject_definitions`, `summary`, `retention_analysis`,
  `detailed_description` with `[Shot N]` markers and cut times (`At 00:04.500, the camera cuts to …`), spoken lines as
  `<d>…</d>` with a speaker, and two sound fields. References are named `<Picture N>`, `<Video N>`, `<Audio N>` in the
  order they are attached.

### 2.2 ComfyUI

ComfyUI executes a graph of nodes lazily. Since 0.37 it has native loop nodes: `StartLoop` iterates over a list and
`EndLoop` accumulates a value per iteration and feeds the last one back as `current_iteration_value`. Our render node
expands into such a loop at run time, so sampling, previews, progress and Stop behave as in any ComfyUI workflow.

## 3 · Related work

- **ComfyUI-H3-Motion-Context** (NikoDemon80) pins the previous clip's tail into the next clip's conditioning. We studied
  its claims, reproduced the core one (§7, E2) and implemented pinning anew inside the native loop, including sound.
- **ComfyUI-Spectrum-MiniMax-H3** (xmarre) forecasts sampling steps; we measured it as an optional speed-up (§8).
- The legacy timeline editor of this pack derives from the **LTX Director** by WhatDreamsCost and CGlide (GPL-3.0).
- MiniMax's own hosted pipeline rewrites user prompts into the training notation; our part writer (§6.5) does the same
  per part with a local or API model.

## 4 · System architecture

![The product workflow](../../js/guide/images/wf2-overview.jpg)

The user works with five kinds of nodes (figure above):

1. **Context cards** (Image, Video, Audio, Text) hold one medium each and say what it is for (*reference*, *first frame*,
   *voice*, *lock*, *control* …). They carry a stable ID, so a shot can bind a card and a card can belong to another
   (*Belongs to*: a side view to its figure, a voice to its speaker).
2. The **Context Connector** gathers models, text encoder, VAEs, cards, an optional AI provider and an optional ControlNet
   patch into one typed object.
3. The **H3 Director** contains the Studio: prompt, look, shots on a timeline, audio and control lanes and settings. Its
   output is a *plan*, not a latent.
4. **H3 Render Sequence** expands into the native loop: per part it builds the conditioning, pins the previous part,
   samples, keeps the finished part on disk for resume, and accumulates.
5. **Collect** decodes all parts into one video and one sound track.

The code is layered. `ng/core` is pure planning (shots, parts, compiler) with no ComfyUI or torch import; `ng/adapters`
connects it to ComfyUI (conditioning, pinning, decoding, files); `ng/nodes` are thin V3 nodes. The core is covered by
about 1,100 unit tests that run without a GPU.

The project is one JSON document stored in the Director's `shots` widget:

```json
{"format": "h3-director-shots", "schema_version": 1,
 "shots": [{"id": "s2", "start": 5, "end": 10, "text": "Medium shot from below: @Keeper climbs the spiral stairs ...",
            "media": [{"context_id": "ctx_hero", "role": "context"}],
            "spoken": [{"speaker_id": "", "language": "English", "delivery": "says", "text": "The storm is coming."}]}],
 "audio": [{"id": "c1", "context_id": "song", "start": 0, "end": 30, "offset": 0, "mode": "lock", "lane": "l1"}],
 "audio_lanes": ["l1"], "look": "Cinematic, warm dusk light."}
```

## 5 · Planning render parts

### 5.1 Lengths on the grid

A continued part is sampled with the previous part's tail in front of it (the *head*, `h` frames) and delivered without
it:

```
sampled = h + delivered,   sampled ∈ {17k + 5},   96 ≤ sampled ≤ N_max
```

The head windows are whole video latent steps counted from a cycle start: `h ∈ {5, 22, 39, 56}` (2, 7, 12, 17 steps), so
the head can be cut out of the latent exactly. For `n` parts and `R_i` frames still to deliver before part `i`, the
planner chooses, part by part, the legal length nearest to the remaining average (error diffusion):

```
d_i = argmin_{d ∈ D(h_i)} | d − R_i / (n − i) |
```

**Listing 1** — `ng/core/chunks.py`, `plan_lengths` (abridged):

```python
lengths, remaining = [], total_frames
for position in range(count):
    options = first_options if position == 0 else next_options
    ideal = remaining / float(count - position)
    lengths.append(_pick(options, ideal))      # nearest legal delivered length
    remaining -= lengths[-1]
```

A 60 s project with 10 s parts therefore becomes six parts of nearly equal length, and the total differs from the request
by at most one grid step (reported to the user as `length_snapped`).

### 5.2 Part edges and shot changes

Two measured effects decide where a part may end (§7):

- A pinned head holds the old action for about **2.4 s** (E7). A shot starting less than `L = 60` frames (2.5 s) after an
  edge comes late.
- A shot change in a part's **last two seconds** is cut twice (M18/M19).

The planner moves an edge in whole 17-frame steps so that no shot starts in the window `(edge − 48, edge + 60)` frames.
Both directions are tried, smaller move first, and a move is taken only if both neighbouring parts stay in range; the
total length never changes.

**Listing 2** — `ng/core/boundaries.py`:

```python
def _candidates(boundary, shot_start):
    earlier = -(-(boundary - (shot_start - LATE_CHANGE_FRAMES)) // STEP) * STEP
    later = -(-((shot_start + LATE_CHANGE_FRAMES) - boundary) // STEP) * STEP
    return sorted((-earlier, later), key=abs)
```

A shot that opens on its own first-frame picture starts an **unpinned** part instead: inside a pinned part H3 took such
a picture as the *end* of the running take and cut one frame after it.

### 5.3 Longer parts at small sizes

The 15 s limit is a limit of tokens, not of frames (§8, M13). The planner allows

```
N_max(W, H) = 360                                    if ⌊360·1280·704 / (W·H)⌋ < 377
            = min(719, ⌊360·1280·704 / (W·H)⌋)       otherwise
```

so sizes near 1280×704 keep the trained 360 frames and small pictures get up to 719 frames (29.96 s).

## 6 · Continuation and collection

### 6.1 Pinning picture and sound

The previous part's last latent steps are attached to the next part's conditioning as keyframes: video steps at their
real pixel-frame offsets from frame 0, and an audio window that *ends* where the pinned picture ends.

**Listing 3** — `ng/adapters/conditioning.py`, `_keyframes`:

```python
video_pin = pin.video_pin(continuity.video_frames, int(video.shape[2]))
frames = [{"resolved_frame_index": offset, "latent": block}
          for offset, block in zip(video_pin.offsets, latents.video_blocks(video, video_pin))]
if continuity.mode == "video_audio":
    audio_pin = pin.audio_pin(continuity.audio_frames, int(audio.shape[-1]), int(video.shape[2]), video_pin.span)
    frames.append({"resolved_frame_index": audio_pin.index, "audio_latent": latents.audio_tail(audio, audio_pin.steps)})
```

The audio anchor is fractional and usually negative. With `r` pinned audio steps (24 frames = 40 steps), `h` head frames
and the previous clip's audio grid overhang `o` (exactly 0 or ±1/3 step for legal clips):

```
e = round( 5/3 · (h + 3/5 · o) ),     index = (e − r) / (5/3)
```

Snapping `e` onto the target's own audio grid removed a constant 8 ms lateness measured without it (E2: best lag
−8.5 ms).

### 6.2 What the chain loses

Over six parts (E6) the sound became dull: the share above 4 kHz fell from 0.0055 to 0.0005 (about an eleventh) and the
spectral centroid dropped from part three on, while picture sharpness and colour stayed constant. The planner warns
above four joins (`audio_dulling`); where the sound must stay exact the user locks it (§6.4).

### 6.3 Joint decode and the sound seam

Decoding each part alone ended it on an unblended VAE lookahead and restarted the decoder on the regenerated head: a
one-frame brightness jump at every join (up to +0.011 luma). The collector therefore joins a chain **in latent space**
(each head dropped) and decodes it in windows that start one VAE clip early. The video VAE decodes clips of 5 latent steps
(17 frames) and blends each clip's first frames with the previous clip's lookahead; a window

```
start = max(⌊(s − o)/17⌋ − 1, 0) · 5,     stop = (⌊(e − o − 1)/17⌋ + 1) · 5 + 2
```

(`s`, `e` the part's story frames, `o` the run's origin) gives every delivered frame the decode a single long clip would.

Sound is decoded per part, cut at **absolute** story boundaries so that rounding never accumulates
(`round(e/24·rate) − round(s/24·rate)` samples per part), and the earlier part's last 10 ms are crossfaded into the later
part's own decode of the same moment (its head).

**Listing 4** — `ng/adapters/collect.py`, `_crossfade`:

```python
if held is not None:
    if chunk.head_frames and not chunk.continuation_id and head >= held.shape[-1]:
        ramp = torch.linspace(0.0, 1.0, held.shape[-1], dtype=held.dtype, device=held.device)
        held = held * (1 - ramp) + whole[..., head - held.shape[-1]:head].to(held) * ramp
    wave = torch.cat([held.to(wave), wave], -1)
```

Butted together, the waveform jumped at every join by 2–4× the largest sample step elsewhere (M19). Long projects use
`write_video`, which does the same one part at a time straight into an H.264/AAC file (177 s at 768×1152 are 45 GB of
float32 frames). Output streams are tagged BT.709; untagged BT.601 showed green 160 as 143 in browsers.

### 6.4 Locked sound

A song or fixed dialogue is encoded with the audio VAE and placed into the audio latent with a **noise mask of zero**
inside its spans; the sampler keeps it and generates only the picture (and free sound elsewhere).

**Listing 5** — `minimax_director.py`, `lock_audio_latent` (abridged):

```python
mask = torch.ones_like(audio)
for start, end in spans:
    first, last = max(0, floor(start * fps)), min(length, ceil(end * fps))
    mask[..., first:last] = 0.0
out["samples"] = NestedTensor((video, held))
out["noise_mask"] = NestedTensor((torch.ones_like(video), mask))
```

A lock inside a part's head wins over the audio pin (the picture pin stays). With custom multi-stage samplers, an
`OUTER_SAMPLE` wrapper restores the locked positions before every stage. When a song covers the whole video, the
collector puts the original waveform back from the file in every part, so a long chain does not dull it.

### 6.5 Rendering inside ComfyUI

`H3 Render Sequence` expands at run time into `StartLoop(List) → build conditioning → pin → SamplerCustomAdvanced →
EndLoop(accumulate)`. With Turbo on, `LoraLoaderModelOnly` is inserted with the LoRA's measured steps, sampler and
scheduler; CFG stays 1 as in every official H3 template. Each finished part's raw latent is kept in
`output/h3-director-resume` under a key of its plan, media stamps and settings; queued again, finished parts load from disk
and a changed part renders again together with every part after it. The same plan can be sampled by the user's own nodes
(Workflow 9): `H3 Director Output` supplies model, conditioning, latent, seed, sampler and sigmas per part.

## 7 · Compiling the prompt of each part

### 7.1 One notation, per part

For each part the compiler collects the cards bound to the shots in that part (plus unbound cards, which are global),
numbers the references in the order they reach the model, writes `subject_definitions` and `retention_analysis` from the
cards, and writes the part's shots with cut times relative to the sampled clip (head included). Pictures of the same
figure are presented together as one Subject (*Belongs to*).

### 7.2 Sharing a long shot

A shot longer than a part was first sent whole to every part; the first part played the whole action and the next played
it again. The compiler now gives each part its share of the shot's text: time beats written as `0–5s: …` go to the part
they fall in, re-timed to the part; plain text is cut into clauses at words that say one step follows another (`then`,
`before`, `until` …) and laid over the shot's time by length. Two exceptions came from tests:

- **Camera sentences belong to the whole shot.** Shared by length, "The camera holds a stable side view" went to the
  second part only, and the first pushed in to a close-up. Camera sentences go to every part of the shot.
- **A continued part does not repeat a camera move.** Each part read "the camera pushes in" as a new push (three push-ins
  over a 20 s shot). Moves are dropped in continued parts; when no camera sentence is left, the part gets
  "The camera holds a static shot, keeping the framing of the preceding video."

### 7.3 Lines and speakers

**Listing 6** — `ng/core/shot_share.py`, `lines_here`:

```python
SPEAK_MIN_FRAMES = 48       # two seconds
if shot.carried:
    return chunk.story_start_f - shot.shot_start_f < SPEAK_MIN_FRAMES
if shot.continues:
    return chunk.story_end_f - shot.shot_start_f >= SPEAK_MIN_FRAMES
return True
```

A line belongs to the part in which its shot starts, unless the shot starts in that part's last two seconds; then the next
part says it (a line placed 0.3 s before an edge was spoken over the previous shot).

### 7.4 Identity across parts

- In References mode, three pictures of one figure left as independent cards became three Subjects, and H3 switched
  between them. The planner flags independent character pictures with mostly the same description.
- In First/last-frame mode a part that continues a shot had no picture at all. After a push-in to the face the next part
  invented a different dress. Giving that part the shot's opening picture as a *reference* (not a frame) kept the dress
  and the staff in all six parts of a minute.

### 7.5 Effects and the AI writer

The official effect embeddings (`minimaxh3_*`, e.g. bullet time) are written after the shot's action in the part where
the shot starts; they took over the camera in both modes. An optional AI writer (local or API model) rewrites each part's
description inside fixed rules: shot markers, cut times, labels and every `<d>` line are kept word for word, small slips
are repaired, and a rewrite that changes the rest is refused.

## 8 · Experiments

### 8.1 Setup

RTX 5060 Ti 16 GB, int8 H3 checkpoints, `res_multistep` + `simple`, 12 steps for E-series chains (8 for E11/E12), 20 or 8
(Turbo) for M-series. E-series scenes are static or simple (a street musician, a walking woman); M-series are one-minute
music videos with a singer from one character picture.

**Metrics.** *Waveform correlation* across a join: normalised cross-correlation between the pinned head's sound and the
end of the previous part, best lag within ±60 ms. *Envelope correlation*: the same on a 10–50 ms RMS envelope. *Head
deviation*: mean absolute pixel difference between the pinned head and the end of the previous part (0–1 scale). *Jump at
the cut*: frame difference at the join divided by the median frame-to-frame difference. *Lock fidelity*: envelope and
chroma correlation between output and source song. Sound was also transcribed with Whisper to check spoken lines; most
results were not judged by a listener.

### 8.2 Continuation (E2, E4, E6)

| Pinned (E2, two parts) | Waveform | Envelope | Head deviation | Jump at the cut |
|---|---|---|---|---|
| nothing | 0.13 | −0.16 | 0.259 | 40.9× |
| picture | 0.18 | 0.07 | 0.013 | 2.3× |
| picture + sound | **0.92** | **0.78** | 0.013 | 2.2× |

Only pinning both continues both. Head windows (E4): 5 / 22 / 39 picture frames gave waveform correlation 0.88 / 0.92 /
0.94 and the same head deviation (0.012–0.013); a larger window costs more discarded time (0.2 / 0.9 / 1.6 s); a 48-frame
sound window brought nothing over 24. Over six parts (E6) the per-join waveform correlation stayed at 0.88–0.92 with no
decay, and picture and sound were exactly equally long (634 frames, 26.417 s).

### 8.3 Edges and actions (E7, M18/M19)

A new action asked for from the first frame of a pinned part started **2.4 s** after the join; a prompt such as "first
keep playing for three seconds" did not steer the timing. In a Ref2VA minute a shot change 0.04 s before an edge was cut
twice (18.38 s and 20.04 s); after edge alignment (§5.2) the same minute had one cut at 19.83 s for a shot at 20.0 s.

### 8.4 Locked sound (E12)

Over two parts the result matched the song with envelope correlation 0.974 (0.974 / 0.971 per part) and chroma
0.994; the offset (−4.0 ms) was the same before the cut, after it and at the end.

### 8.5 Speed and length

| What | Result |
|---|---|
| Turbo LoRA (official FL2VA, 8 steps) vs 20 steps, 5 s at 1280×704 | 285 s vs 526 s, full camera orbit kept |
| Spectrum step forecast, 20 steps, two parts | 384 s → 239 s, same scenes, line spoken word for word |
| Draft at 640×352 → latent upscale → finish (3 of 8 steps small) | 197 s vs 253 s, clean; 2 of 8 steps left an artefact |
| One 30 s clip at 640×352 (M13) | 417 s, no drift, three lines in order; also held with motion and with a reference |
| 45 s and 60 s clips at 640×352 | no drift, but H3 ran out of story and repeated lines and actions |
| One-minute music video, FL2VA, six parts (after fixes) | same costume throughout, cuts only at the two intended shots |
| One-minute music video, Ref2VA, six parts (after fixes) | 4 cuts instead of 6 (2 intended), no double cut |

## 9 · Limitations

- Most numbers come from **one seed**, one scene and numeric measures; sound was not always judged by a listener.
- Generated sound still loses high frequencies over many parts; only locked sound is immune.
- The planner cannot force the exact frame of a cut; H3 places it within about half a second.
- Content still matters: a shot text about "remembering her missing master" made H3 show the master as a second figure.
- Parts above 30 s repeat content; a windowed refinement from a small draft to the target size is not built.
- ControlNet acts on whole render parts; a control clip that covers only part of a render part holds its edge frames.

## 10 · Conclusion

Long H3 videos need three things that a single clip does not: continuation of picture *and* sound across parts, a
decoder and sound path that leave no seam, and a prompt per part that knows which share of the story it tells. Each of
these was measured, and each measured failure became a planner rule. The result renders minutes with recurring
characters, voices and locked songs inside an ordinary ComfyUI graph.

## 11 · Reproducing

The unit tests run with `python tests/ng/run_all.py` in ComfyUI's Python (about 1,100 tests, no GPU). The example
workflows and their input files ship with the pack (`example_workflows`, `example_media`); the render paths of all
measurements are the same as in those workflows. The measurement scripts are tied to one machine and are not part of the
repository; the metrics are defined in §8.1.

## Appendix A · Constants

| Constant | Value | Source |
|---|---|---|
| Frame grid | `17k + 5` frames at 24 fps | H3 |
| Trained clip range | 96–360 frames | model card |
| Head windows | 5, 22, 39, 56 frames (default 22) | §5.1, E4 |
| Sound pin | 24 frames (1 s, 40 audio steps) | E4 |
| Late change | 60 frames (2.5 s) | E7 |
| Speak minimum | 48 frames (2 s) | §7.3 |
| Long part | ≤ 719 frames, frames × area ≤ 360 × 1280 × 704 | M13 |
| Dulling warning | more than 4 joins | E6 |
| Sound crossfade | 10 ms | M19 |
| VAE clip | 5 latent steps = 17 frames | ComfyUI H3 VAE |

## References

- MiniMax H3 models and prompt guide: Comfy-Org/MiniMax-H3 (Hugging Face) and MiniMax-AI/MiniMax-H3.
- ComfyUI: native loop nodes (`comfy_extras/nodes_loop.py`) and the H3 integration (`comfy_extras/nodes_minimax_h3.py`).
- NikoDemon80, ComfyUI-H3-Motion-Context: pinning the previous tail (studied, not used as code).
- xmarre, ComfyUI-Spectrum-MiniMax-H3: step forecasting (optional, installed by the user).
- Kijai, MiniMax-H3-TAE: the `taeh3` preview decoder.
- WhatDreamsCost and CGlide, LTX Director: the origin of the legacy timeline editor (GPL-3.0).
