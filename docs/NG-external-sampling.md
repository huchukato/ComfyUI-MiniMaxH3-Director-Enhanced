# Editable H3 chunk sampling

Open `example_workflows/H3 Director NG - native chunk loop.json` for one native sampler, or
`H3 Director NG - two sampler chunk loop.json` for a split schedule with two native samplers.
The same body runs for every planned chunk. H3 Render Sequence remains the packaged option.

Select your installed H3 model, minimax CLIP and both VAEs. The examples use a native Sigma Shift before the
Connector; **Apply Director sigma shifts** is therefore off on Output. Its default remains on for existing workflows.
The optional native LoRA loader is bypassed. Enable it and choose the LoRA's matching steps, sampler and shifts when needed.
CFGGuider explicitly uses CFG 1. The base examples use 20 steps; the recorded pipeline checks use 4 steps.

## Connections

1. Connect **H3 Director / chunks** to Start Loop's List input. This complete ordered list is planned outside the loop.
   No NG Project Chunks node is needed. Director's original result remains slot 0; chunks is slot 1.
2. Connect Director's **result** to the single **H3 Director Output / input** inside the loop.
   Connect Start Loop's `list_item` to Output's `loop_chunk`, and `current_iteration_value` to its `previous`.
3. Create the native Guider from Output's current model, positive and negative **inside the loop**. Use that same model
   for BasicScheduler. Output also supplies the initial AV latent and INT **seed** in appended slot 9.
   The seed is the Director's base seed plus the chunk index; its optional seed input overrides the base.
   Connect seed to the ordinary **RandomNoise / noise_seed**, then NOISE to SamplerCustomAdvanced.
   For the ordinary native KSampler, connect Output's seed directly to its seed input.
   **The Director's sampling settings** come out of Output too (slots 10–15), so the Studio's Steps, Sampler and Scheduler
   drive your own sampler: **steps**, **cfg** (always 1.0, H3 runs without classifier-free guidance), **sampler_name** and
   **scheduler** connect to KSampler, KSamplerSelect or BasicScheduler; **sampler** and **sigmas** are ready-made for
   SamplerCustomAdvanced (sigmas use this chunk's model, so the Director's shift is included). With Turbo on they carry 4 steps.
   Measured on the user's workflow: Director steps 4 reached BasicScheduler over the link, 243 frames rendered in 318 s.
4. Wire the sampling stages. Return the final, complete **AV LATENT** to both End Loop's `output_value` and
   `next_iteration_value`, with **accumulate on**. Include both video and audio, the whole sampled time axis and the pinned head.
5. Connect End Loop's accumulated latents and Director's original **chunks** list to NG Collect, with both VAEs.
   Feed its images/audio into CreateVideo, then SaveVideo. Take CreateVideo's fps from Collect's **fps** (24) or type 24.
   For long projects (a whole song) use **NG Collect Video** instead: same inputs, it decodes one render part at a time
   straight into an H.264/AAC file and connects directly to SaveVideo. NG Collect holds every frame at once (177 s at
   768×1152 are 4248 frames, 45 GB in float32), which does not fit in memory.

One Output prepares each current chunk; H3 Prepare Chunk has been removed. Its original nine outputs retain their slots.
Keep Output's sampler values and seed inside the loop. Sending an Output value directly past End Loop creates a native loop escape;
ComfyUI then refuses the run with "Invalid input: loop boundary" on Start Loop, End Loop and the node outside
(typically Output **fps** -> CreateVideo); use Collect's **fps** instead. Use sequence → H3 Render Sequence in a separate simple graph,
without Start Loop feeding that Output. Do not wire the loop back into the Director that supplies its own list.

## Two sampling stages

SplitSigmas provides high and low schedules. The first SamplerCustomAdvanced receives random noise and the high schedule.
Connect its **output**, which can retain noise, to the second sampler's latent; connect the low schedule and native DisableNoise
to that second sampler. Return the second sampler's finished AV latent to End Loop. The supplied example keeps one canvas.

For **Lock Audio**, Output binds the selected source to its current model through ComfyUI's `OUTER_SAMPLE` hook.
Every native stage restores only the locked audio positions before sampling; free audio and video retain the preceding
stage's values. This prevents a partial schedule's remaining noise from becoming the next stage's locked source.
Use Output's model for the Guider/KSampler in every stage. No extra lock/noise/guider node is required.
The source is loaded and encoded by the native audio VAE per stage, with no retained tensor cache. This adds work
to locked-audio stages; it does not change steps, sampler, noise, CFG, sigma shifts or collection.

This is a continuation of one schedule, with no upscale operation. A learned H3 upscale workflow can require the first stage's
`denoised_output`, its own re-noising and updated H3 reference conditioning. That is a separate integration; a generic image
latent resize does not establish H3 video/audio compatibility.

## Continuity and collection

The next chunk receives the previous **untrimmed** AV latent. Existing H3 pinning slices its video tail directly, without a VAE
round trip, and its audio tail onto the next chunk's conditioning. The default 22-frame video window is seven H3 latent steps;
the 24-frame audio window is 40 audio steps. The sampled head is removed from picture and sound only by Collect.
Locked source audio takes priority over the audio pin; the video pin remains.
The Connector accepts up to 15 Context cards per medium, including unnumbered frame guides and audio locks.
This does not raise H3's native reference budgets; the compiler and Inspector still enforce/report those caps.
Mentions use the longest complete Context name across roles, so `@Rain Track` cannot borrow the reference
number of a separate card named `Rain`. Missing sources and omitted guides keep their own meaning/warnings.
Lock card names use descriptive prose in the H3 prompt, with a card warning: a lock has no numbered `<Audio N>`
reference. Paired video soundtracks and voice references keep their own native numbers. An ended lock is reported
for that chunk and contributes no further source audio.
Multiple locks keep separate source selections. Each is placed at its story position (a shot binding starts at its
shot, an audio lane clip at its own start with its file offset), and overlapping locks are added before the audio VAE
encode and clamped to [-1, 1]. A lane clip continues across chunks; a shot binding restarts its source at every bound
shot. See [shot audio placement](NG-shot-audio.md) for the full contract.

Missing, trimmed or wrong-format continuity returns fail with an actionable error. Direct video pins require the previous
and new chunk at the same resolution. End Loop can separately carry a base-resolution latent while collecting a final-stage
latent, but an upscale pipeline still needs its own correct H3 conditioning and audio contract.

Collect owns copies of decoder outputs across later VAE calls. Audio lengths are computed from absolute story-frame boundaries,
so per-chunk rounding cannot accumulate samples at the joins. A short decoded audio stream is padded as before.

No external sampler settings are reset by the loop. Compatibility with arbitrary third-party samplers and upscalers is not implied.
