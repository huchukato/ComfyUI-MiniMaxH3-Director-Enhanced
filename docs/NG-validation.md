# H3 Director NG validation

## Video continuation update (2026-10-15)

The historical single-frame Continue results below are superseded by the current selected-tail path documented in
[NG.md](NG.md). Continue now uses a hidden native 39-frame source prefix with matching sound when enabled, in both
FL2VA and Ref2VA. Pure Continue does not also send a general full-clip reference. First frame pictures with separate
locked sound remain supported.

Four complete native/Director comparisons (both models, with and without an original-song lock) matched input video,
input audio, conditioning and sampled video/audio latents exactly. Each used 20 steps, res_multistep/simple, Sigma 12/3,
384×576, fixed seed and no turbo LoRA. A real three-part Render Sequence delivered 306 frames / 12.75 s with 39/22/39
hidden prefixes; the song matched the correct source position in every part at correlations 0.9988–0.9991.
Separate collector exports delivered exactly 102 frames / 4.25 s and held the selected song offset at 5.875 s.
A 44.1 kHz source-audio test also matched the native VAE conditioning exactly after matching TrimAudioDuration rounding.

Software: 1,032 NG tests, 1,031 passed and one environment-dependent skip; Legacy 374/374 + 74/74; compileall and all
67 JavaScript syntax checks. These are execution and signal checks. The new videos still require user listening/viewing
review for voice, melody, lip sync and an invisible picture seam. Evidence is in the local notes:
`_notes/NG/CODEX-AV-FORTSETZUNG-UMSETZUNG-2026-10-15.md` and `continuation-av-audit-2026-10-15/verified-product-results.json`.

Local product work on branch `ng`, based on the existing NG foundation. Released as 1.0.0 on 2026-10-26.
No push, tag or publication. New user TXT/PNG references define the Connector/Director/Output and separate AI Loader architecture.

## Complete Context names and card capacity: E40 (2026-10-03)

Mixed compiler passes could turn `@Rain Track` into `<Subject 1> Track` or a longer guide into an audio
reference plus a suffix. The common matcher now considers all Context names when choosing the longest
candidate, while each pass still resolves only its retained native labels/prose. Seven new contracts cover
Subjects, scoped assets/text, video, voice, multiple locks/guides, missing sources, Unicode, dialogue and raw overrides.

An actual four-audio-card run exposed a second error: the Connector's three-card schema silently omitted the
second lock. Context groups now permit 15 cards per medium, including guides and locks; native H3 reference
caps and Inspector warnings are unchanged. Two further contracts exercise ComfyUI's real V3 expansion for
4 audio/4 video/10 image cards and check two voices/two locks with a paired video soundtrack.
Frontend restoration preserves connected cards and the next empty port, with a finite 15-card cap.

Save/Reload also exposed shared radio groups: cards were created before native IDs were assigned, so only
the last audio/video card displayed its saved selection. Each panel now owns a unique temporary DOM group.
The new JS regression and fresh-browser check retain both Voice selections and both Lock selections.

Native two-stage API run `4da4d79a` passed in 135.83 s; saved UI run `843695ab` passed in 116.797 s.
Both produced 294 frames at 256×256, 4 steps, 12.25 s video/audio. Independent API checks verify lock source
windows 2–7 and 1–3 s, source VAE difference 0, held audio within 1e-5, exact next video tails and restored
audio-tail conditioning after expiry. Per-chunk lock counts are 2/1/0; paired video and voices keep Audio1/2/3.
The Inspector shows the correct prose/native mappings and budget 5 images, 1 video, 2 standalone audio, total 8.
Eleven direct-file cards plus Text restore without media input sockets or an ng_product_nodes load error.

Final joint suite: 416 NG/415 pass/one existing Windows symlink skip, legacy 371/74, five JS suites,
JS syntax, compileall and diff check pass. Other ongoing Text/AI UI edits were preserved separately.
Evidence: external `_notes/NG/34-mention-ownership-and-context-capacity.md`, `experiments/e40_*`,
and saved workflow `H3 NG - complete names two locks E40 verified.json` in the user's workflows folder.
Overlapping locks retain the existing later-card precedence, rather than additive mixing; source selection
is not a soundtrack placement control. No listening, arbitrary sampler/upscale or product-quality acceptance.

## Audio lock names and native sampler stages: E39 (2026-10-03)

Known lock names now resolve to prose, with a card warning for the absent numbered reference or an ended lock.
Paired video soundtracks and voices retain their native Audio1/2/3 labels. Raw prompts and unknown names stay intact.
Seven compiler/adapter contracts cover source selections, mixed roles, shared files and boundaries.

A weighted split-schedule run exposed a second error: initial source audio and masks matched exactly, but the
final locked latent differed by 12.026966. A single full schedule passed. The partial schedule's noisy output
became the next sampler's inpaint source. Output now binds an `OUTER_SAMPLE` adapter through ModelPatcher;
each stage reloads/native-encodes the declared source and restores only held audio positions and their mask.
Free video/audio values, native arguments, other wrappers, CFG/noise/sigmas and collection remain unchanged.
Four further contracts cover stage transitions, soft/absent masks and node integration. No extra node or tensor cache.

Native three-chunk checks at 256×256/4 steps passed: two SamplerCustomAdvanced stages `48093769` (121.58 s),
ordinary KSampler `439a60fe` (113.34 s), and UI Save/Reload/run `4b9db414` (115.53 s).
Each produced 294 frames and 12.25 s AV; API probes measured initial source difference 0, final held difference
at most 1.1920928955078125e-7 and exact previous AV tails after lock expiry. References: paired video 80 audio
steps, VoiceA 80, VoiceB 60; Picture slots 5/4/5. Source selection 2–7 s is retained.
Eleven direct-file/text cards, one Output/loop/normal RandomNoise/CFGGuider CFG 1, inspector budget 5 images,
1 video, 2 standalone audio references, total 8. No media input ports or workflow-load error.

Final joint suite: 407 NG/406 pass/one existing Windows symlink skip, unchanged legacy 371/74, five JS suites,
all JS syntax checks, compileall and diff check pass. Concurrent Text/AI work was preserved in parent 1738436.
Private fixture/verification mistakes were corrected separately; no product tests were removed or weakened.
Evidence: external `_notes/NG/33-audio-lock-mentions.md` and `experiments/e39_*`, native output `ng_lab/e39`.
Per-stage source/VAE work has a cost; these timings establish correctness, not a speed improvement.
No arbitrary third-party sampler, upscale, identity/voice/seam or final product-quality acceptance is implied.

## Guide boundaries and timing controls: E36 (2026-10-03)

A timed Keyframe/Storyboard beyond the actual snapped video end was silently omitted when its name was not mentioned.
Planning now warns with the card name and last valid frame time while preserving the input. Boundary frames and snapped
end padding remain valid; conditioning is unchanged. Five new contracts cover all continuity modes and native First/Last
with distinct timed-image guides at identical offsets.

Browser testing found valid partial ContextOptions stopped card synchronization before displaying the stored time.
The frontend now fills backend defaults when reading options. Time controls accept frame-accurate fractions and commit
valid edits immediately, including when saved while focused; empty/invalid edits preserve the previous value.
One JS fixture reproduces and verifies default loading, retention, precise time input and edit persistence.

Final 383 NG checks: 382 passed/one existing Windows symlink skip; Legacy 371/371 and 74/74, five JS suites,
JS syntax, Python compilation, structure and diff checks passed. Weighted mixed native three-chunk/two-sampler Run:
73.81 s, 294 frames/392000 samples at 32 kHz, 12.25 seconds. Global frame 107 is local frame 22 after the continuity head;
global frame 293 is local frame 123. Both source VAE guides and both subsequent AV tails match exactly.
Weighted FL Run: 16.27 s, 124 frames/165333 samples, four retained guides at [0,123,0,123], native Picture 1/2 labels.
Actual browser Save/Reload/Run: 69.788 s, 294 frames/12.25-second video/audio. Valid 12.208 is persisted and clears the
warning; restored 20 is persisted and restores the warning. Twelve Context cards retain direct file loading, one Director
Output in the loop, normal RandomNoise, CFGGuider CFG 1 and two freely connected native samplers. No loading-aborted error.

All loaded Python sources match the runs; the only changed JS control module was verified in a fresh browser context.
The private dynamic-loader server and own tabs are closed, the lab junction moved reversibly outside custom_nodes,
and the user server preserved. Existing foreign E38 text styling is retained without claiming its complete visual acceptance.
No sampler/model math change, native Windows loader repair or perceptual quality acceptance. Evidence and exact local
commit: `_notes/NG/30-guide-boundaries.md`, `experiments/e36_*`. No push, tag or publication.

## Native frame-guide names and Inspector budget: E35 (2026-10-03)

Known `@Name` references to frame guides previously remained unresolved, and FL-only workflows had no Picture labels
even though native ImageToVideo sends first/last images to its tokenizer. The compiler now follows that native ordering
and uses existing Picture numbers for Ref2VA anchors. Unnumbered Continue/AddGuide frames use descriptive prose with
a warning; guides absent from a chunk report availability. Unknown names and raw prompt overrides are preserved.
The Inspector budget now counts actual reference presentations, excluding duplicated Ref2VA anchors and unnumbered
Continue/AddGuide/audio-lock conditioning. First and last pictures from the same FL card still consume two image slots.

Eight new Python contracts and two JS fixtures reproduce and verify these changes. 378 integrated NG checks:
377 passed/one existing Windows symlink skip; Legacy 371/371 and 74/74, five JS suites, syntax/structure/diff checks passed.
Weighted mixed API Run: 299.47 s, three chunks, 294 frames/392000 samples at 32 kHz, 12.25 seconds;
native Picture counts 5/4/5, Voice Audio 1/2 lengths 80/60, exact selected continuation frame and both previous AV tails.
Weighted FL-only Run: 32.36 s, 124 frames/165333 samples at 32 kHz; native first/last guides and Picture 1/2 confirmed.
Saved/reloaded example `H3 NG - native guide names E35` and actual browser Run: 188.526 s, 294 frames,
12.25-second video/audio. Fresh Inspector shows images 5, video 0, audio 2, total 7; all nine Context cards load files directly.
One Director Output, normal RandomNoise, native CFGGuider CFG 1 and two freely connected native samplers are preserved.

Two classic native Windows loaders crashed while reading weights before Director execution, including with mmap disabled.
Their logs remain; the successful private instance used the existing dynamic loader with fast disk and disabled pinned memory.
No ComfyUI core code changed and no native loader repair or perceptual quality acceptance is claimed.
The private server and bound tabs are closed; the test junction was moved reversibly outside custom_nodes after deletion
review was blocked. The user server was preserved. All loaded Python sources match the render; the changed Inspector
was verified in a fresh browser context. Source manifests, evidence and limits: `_notes/NG/29-guide-mentions.md`, `experiments/e35_*`.
The own E35 changes are committed locally after validation; the exact commit is recorded in the external E35 source manifest.
Existing E33/E34 code remains in `486e0047`. No push, tag or publication.

## Short video Continue selections: E34 (2026-10-03)

Continue previously read 24 frames even when the selected source window was shorter than one second, so its last
guide image could come from beyond the chosen end. The compiler now limits that interval on the existing source frame grid.
NG accepts a single continuation guide image while retaining the five-frame minimum for video references.
The shared decoder has optional strict error propagation for NG; other Legacy callers keep their existing fallback.

Five new contracts cover short/long windows, single-frame guides, actual lossless frame-indexed decoding and invalid files.
370 integrated NG checks: 369 passed/one existing Windows symlink skip; Legacy 371/371 and 74/74, five JS suites and syntax/structure checks passed.
Weighted mixed API Run: 176.02 s, three chunks, 294 frames/392000 samples at 32 kHz, 12.25 seconds;
the actual native VAE guide equals the last selected source frame exactly, and both subsequent AV tails match exactly.
Browser edit/Save/Reload and native Run: 104.77 s, 294 frames, 12.25-second image/audio; actual submitted graph retains the window.
Saved example: `H3 NG - short video Continue E34`. Contexts still load files inside their cards; external native sampling is preserved.

This fixes the source selection for the existing last-source-frame guide, not the separate Last Frame continuity mode.
No motion/audio-tail extraction or perceptual quality acceptance is claimed. This chat preserved the user server;
the previously running process required a restart for new Python sources. Sources and limits: `_notes/NG/28-video-continue-windows.md`, `experiments/e34_*`.
The private test server/tab/lab junction are cleaned up after its queue emptied; test sources and evidence remain.
The user process was preserved at that cleanup. At later documentation closeout PID 33504 was gone; after an observed
listener gap the final snapshot shows 8189/PID 43000. This chat did not start or stop that server and claims no render
acceptance for the newly started user instance (`e34_environment_final.json`).
At closeout, existing local commit `486e0047` includes the E33/E34 code as well as the concurrent provider work;
this chat did not create that commit. Only this documentation closeout remains uncommitted. No push, tag or publication.
The final source manifest confirms all loaded Python sources are unchanged since the weighted run. Six concurrently
changed frontend modules are identified separately and covered by the later final checks; no fresh browser acceptance is claimed for them.

## Shared assets, voice windows and Context text: E33 (2026-10-03)

Two Subjects share one image asset, video/soundtrack and scoped text; two independent Voice cards read different
windows from the same file. Native presentation contains four Pictures, paired Audio 1/Video 1 and Voice Audio 2/3.
All three chunks keep their IDs and labels. Actual reference audio lengths are 120/80/60 at H3's 40 Hz timebase.
The API render passed in 340.23 s: 294 frames, 392000 samples at 32 kHz, 12.25 seconds, exact previous AV tails.

Browser testing found that Subject rename updated Director idea/shots but left the old name in Context Text.
The Text editor now uses the existing stable-ID/casefold resolver and saves its previous name map in workflow properties.
The Inspector now counts each shared native Picture presentation in the budget instead of counting its card only once.
Regression tests reproduce both failures; Unicode, multi-word names, prefix boundaries and saved properties are covered.

Saved/reloaded example `H3 NG - shared assets two voices E33` keeps both asset owners, both voice windows and renamed text.
The corrected native browser Run passed in 244.311 s: 294 frames, 32-kHz audio, 12.25 seconds; all compiled prompts resolve.
One Director Output in the native loop, normal RandomNoise, CFGGuider CFG 1, two native samplers and direct file sources remain.
363 integrated NG checks: 362 passed/one existing Windows symlink skip; Legacy 371/371 and 74/74, five JS suites,
syntax/structure/Python checks passed. A stale model-list test was aligned with the concurrent registry-default behavior
using a local HTTP fixture; the provider implementation remains its owner's work.

Classic native memory loading is confined to the private test instance; the earlier aimdo 1450 issue remains unresolved.
Equal test images and short test WAVs establish routing and windows, not perceptual identity, voice quality or seams.
The private test server, tabs and lab junction were removed after its queue emptied; user 8189/PID 33504 is preserved.
E30–E32 remain locally committed as `705bc72`; E33 is uncommitted. Evidence and limits: `_notes/NG/27-shared-assets-and-voices.md`,
`experiments/e33_*`, `output/ng_lab/e33/e33_shared_*` and `e33_gui_00002_.mp4`.

## Local commit verification: E30–E32 (2026-10-03)

The Director changes were staged separately from the concurrent, uncommitted AI Loader refactor.
The exact staged source tree passed 279 NG checks (278 passed/one existing Windows symlink skip),
Legacy 371/371 and 74/74, all four JS logic suites, NG JS syntax and Python compilation.
Shared files contain only Subject ownership or native workflow-restoration changes in this snapshot;
the provider registry, requests, settings and branding remain in the working tree.
Earlier GPU/browser evidence below concerns the integrated development tree; no new render is claimed here.
Local evidence: `_notes/NG/experiments/e32_commit_manifest.json` and `e32_commit_*.log`.

## Subject assets and workflow compatibility: E32 (2026-10-03)

Simple image/video/text ownership is stored as optional v1 `subject_ids`. Grouped image references share a native
Subject while keeping their own `ng_item`/Picture ownership. Shared assets, card order, equal files, voice binding,
property preservation, mixed video/soundtrack/voice/text, caps, unavailable guides, presets and exact override are covered.
Actual installed H3 node/tokenizer checks cover two Subjects with a shared image and paired audio token order.
Fixed voice casefold and invalid text scopes after a Subject is dropped by the native reference budget.

Native widget restoration also preserves old AI Loader arrays after inserted numeric fields: defaults come from
the Python schema, original arrays are read before ComfyUI's positional migration, named values stay authoritative.
Six-field, Source-based, removed disk-switch and current formats are covered, including older still-running backends
and lazy legacy disk-provider arguments. No new AI request, model cache or second provider implementation.

318 NG checks: 317 passed/one existing Windows symlink skip; Legacy 371/371 and 74/74; core coverage 98.90%.
The suite includes concurrent provider work. Python/JS/structure checks passed; existing tests remain exercised.
Real native two-stage API render: 238.41 s, three chunks, CFG 1/normal RandomNoise, five file-loaded Contexts,
294 frames/392000 samples at 32 kHz, 12.25 seconds, exact previous video/audio tails in both continued chunks.
Browser checkbox assignment, rename, Save/Reload, old-format loading, canonical Inspector colors and native Run passed:
247.931 s, 294 frames, 12.25-second image/audio. Saved example: `H3 NG - subject assets E32 verified`.

The initial dynamic-loader run sampled three chunks but failed during Video VAE decode with Windows/aimdo error 1450
(`HostBuffer.read_file_slice failed`). Evidence is retained; successful functional runs use the classic native memory loader
only on the private test server (`--disable-dynamic-vram --disable-async-offload --disable-pinned-memory`).
This is an unresolved local native-loader issue, not a claimed NG/model-math fix. User 8189 is preserved.
Sources and precise limits: `_notes/NG/26-subject-assets.md`, `experiments/e32_*`, `output/ng_lab/e32/e32_assets_*`.
Independent Subjects without images, nested relationships, extracted multiple voices and perceptual/seam quality remain open.

## Editor and Inspector reference mapping: E31 (2026-10-03)

Fixed the two E30 display discrepancies: Unicode casefold aliases now highlight and rename with their stable context ID;
the Inspector uses canonical compiler `prompt_labels`, so Audio 1 belongs to the video soundtrack and Audio 2 to the voice.
Picture and Subject numbers use the planner's ownership mapping. Optional v1 display metadata roundtrips and loads older saves;
the still-running older backend has a narrow refs-based display path reading actual `context_options` JSON.
Browser Unicode folding matches Python across every scalar value, verified independently in JS and Python. No new dependency.

263 NG checks: 262 passed/one existing skip; Legacy 371/371 and 74/74; core coverage 98.69%; Python/JS/structure checks passed.
Actual browser rename, Save/Reload, three Inspector views and native two-stage Run passed: 294 frames, 12.25-second video/audio,
120.622 s. An additional mixed image/video-soundtrack/voice/text native two-stage run passed in 100.58 s with canonical labels
and exact prior AV pins in all continued chunks. These are functional mapping checks, not perceptual quality acceptance.
Private 8191 only; the user server 8189 and concurrent UI work are preserved. File-only contexts and E27 sampling stay intact.
Evidence and current limits: local `_notes/NG/25-ui-reference-mapping.md` and `experiments/e31_*`.

## Shared media files keep their own card identity: E29 (2026-10-03)

A file may be reused by several context cards. Each card now keeps its own identity, source window and role instead of
adopting the first card that pointed at that file. Prompt labels are numbered in the order the media actually reach
the model: all videos, then the soundtrack of each video that carries audio, then standalone audio cards. A video
with a soundtrack is declared as `<Audio N> is the soundtrack of <Video N>` and takes that number before a subject's
voice. `@Name` in idea, shots and text rules resolves to the label of the specific card, so two cards on one video no
longer swap labels.

Three failures were reproduced first (two video cards on one file lost the second window; the first audio card's trim
leaked onto a subject's voice; soundtrack and standalone voice both claimed `<Audio 1>`), then fixed and re-measured.
The old `source_shared` warning no longer describes the old behaviour as intended.

253 NG tests: 252 passed/one existing Windows symlink skip. Legacy 371/371 and 74/74; core line coverage 98.66%;
Python compile, JS syntax and JS logic checks passed.

Four actual H3 GPU variants on the installed int8 model at 256x256/four Euler steps/CFG 1, twelve seconds in three
chunks, each with real weights and file-loaded image/video/audio/text contexts: mixed references 122.53 s, two sampler
stages 97.00 s, duplicate files on several cards 154.33 s, Render Sequence 98.25 s. Every variant delivered 294 frames
and 392000 audio samples at 32 kHz; every continued chunk matched the previous latent tail exactly for video and audio;
the duplicate-file run kept both card IDs and their separate windows and declared the soundtrack before the voice.

These are functional and mapping checks at low resolution. Listening, seam quality, long-chain identity and multiple
seeds remain unmeasured. Full current evidence: local `_notes/NG/23-media-identity.md` and `experiments/e29_*`.

## Unicode compiler mentions: E30 (2026-10-03)

Fixed three reproduced image/video/audio compiler exceptions caused by inconsistent regex and name folding.
One shared resolver follows Unicode casefold name equivalence, resolves expansions such as Straße/STRASSE, and preserves
unknown aliases instead of crashing. Distinct dotted-I/ASCII names stay distinct. All four media types and chunk boundaries are tested.
257 NG checks: 256 passed/one existing skip; Legacy 371/371 and 74/74; core coverage 98.66%.
An actual mixed-reference H3 render and browser Save/Reload/two-stage Run passed at 256×256/four Euler steps/CFG 1:
294 frames and 12.25-second video/audio, with exact measured prior AV pins in the instrumented API loop.
The draft highlighting and Inspector audio tooltip/color discrepancies observed here were subsequently fixed in E31 above.
See local `_notes/NG/24-unicode-mentions.md` for evidence and limits. File-only contexts and E27 sampling are unchanged.

## File contexts, native media labels and workflow reload: E29 (2026-10-03)

Context Image/Video/Audio use file selection/upload in their own cards; the user rejected extra native media inputs.
E27 sampling stays intact. Fixed three reproduced media bugs: distinct cards using the same video file lost their identity,
Voice inherited another audio card's trim, and paired video audio displaced standalone Voice labels in H3's actual presentation.
Compilation now retains card identity and resolves Video/Audio mentions against retained references; manual prompt override stays untouched.

Fixed the reported `ng_product_nodes.js` configure crash when refreshed JS expects a sigma-shift widget absent from the
still-running Python backend. The real extension reproduces the pre-fix exception; regression checks cover missing widgets,
old placeholder migration and preserved explicit false. Original workflow Save/Reload works with the unchanged old backend.

253 NG checks: 252 passed/one existing skip; Legacy 371/371 and 74/74; core coverage 98.66%; Python/JS/structure checks passed.
Four actual H3 GPU variants with image/video/paired audio/voice/text passed: one/two native samplers, duplicate source cards,
and Render Sequence. Each delivered 294 frames/392000 audio samples at 32 kHz. Open loops verified reference labels/windows
and exact prior AV pins. A file-only two-stage frontend graph also saved, reloaded and rendered successfully, preserving disabled shifts;
its MP4 has 294 frames and 12.25-second video/audio tracks. No perceptual quality or upscaler approval follows from these checks.
Full local evidence: `_notes/NG/23-media-identity-and-prompt-labels.md` and `experiments/e29_*`.

## One Director Output and native RandomNoise: E27 (2026-10-03)

The Director supplies the ordered chunks before the native loop. A single Director Output inside it prepares the current
MODEL, conditioning, AV latent and seed; Prepare Chunk is removed. RandomNoise and KSampler receive that chunk seed directly.
Original result/Output slots and the simple Render Sequence path remain available. The two editable loop examples use this topology.

Actual H3 GPU checks passed for one/two native sampling stages, ordinary KSampler, six chunks, Turbo LoRA, Ref2VA, audio lock
and all continuity modes. Native interrupt and recovery succeeded. The frontend saved, reopened and rendered the two-stage graph;
its submitted loop body includes Output and RandomNoise and keeps Director/Collect outside. Director.sigma shifts stay disabled
when an upstream native Sigma Shift is connected.

At 256×256/four Euler steps/CFG 1, six chunks delivered 719 frames and 958667 audio samples at 32 kHz.
Continued video/audio pins matched the previous latent tails exactly. Fixed-seed one-stage/KSampler/packaged outputs matched
in the recorded decoded comparison; two stages differed. No upscale or perceptual seam/identity acceptance is established.
246 NG tests: 245 passed/one existing Windows symlink skip. Legacy 371/371 and 74/74; core line coverage 98.34%; Python/JS checks passed.
Full current evidence: local `_notes/NG/21-single-director-output.md` and `experiments/e27_*`.

## Historical editable sampling: E26 (2026-10-03)

The E26 topology below was replaced by E27; its measurements remain evidence for that earlier revision.

In E26, Director Output supplied the chunk list directly. Prepare Chunk built current conditioning, AV latent and native noise/seed
inside one native List loop. Supplied examples contain one or two editable SamplerCustomAdvanced stages; Render Sequence remains available.
Actual H3 GPU checks passed for these stages, ordinary KSampler, six chunks, Turbo LoRA, Ref2VA, audio lock and all continuity modes.
Interrupt stops the native job; recovery succeeds without restarting. The frontend saved, reopened and rendered the two-stage graph.

At 256×256/four Euler steps/CFG 1, the six-chunk sample delivered 719 frames and 958667 audio samples at 32 kHz.
Every continued video/audio pin matched its previous latent tail exactly; source audio lock suppresses the audio pin as intended.
The fixed-seed one-stage, KSampler and packaged outputs matched in this test; the two-stage result differed.
Audio lengths now use absolute frame boundaries, and Collect owns decoder outputs across later calls.
245 NG tests: 244 passed/one Windows symlink skip. Legacy 371/371 and 74/74; core line coverage 98.34%; Python/JS checks passed.

These are functional low-resolution checks, not perceptual seam/identity approval or learned-upscaler validation.
Exact scripts, histories and failure/method corrections are recorded in the supplied local development notes
`_notes/NG/20-external-sampling-validation.md` and `experiments/e26_*`.

## Requirements audit: E17

All nine product nodes were compared again with the original specification, user TXT and nine PNG references. E17 identified missing requirements. E18 implements and tests native CLIP/Disk assistance, distinct Audio/Text layouts, context colors and the compiler inspector. Full analysis/control modes, subject/asset relationships, remaining layouts and Last Frame continuity remain open in that audit. The earlier native-media-input proposal was superseded by the user's file-source decision in E28. Earlier passing suites establish only their tested scope.

## Native AI and layout evidence: E18

Installed `qwen3vl_4b_bf16.safetensors`, native CLIPLoader type `stable_diffusion`: connected CLIP text analysis, disk text analysis, image analysis and a complete 0–8 s scene proposal succeeded. Browser CLIP/Disk Analyze and Apply succeeded; edited input disabled stale Apply, Cancel interrupted its own prompt, and changing settings invalidated the tested badge. The AI prompt excludes H3 rendering nodes. This does not establish audio support or full video-motion understanding.

194 NG tests: 193 passed, one existing Windows symlink skip; core trace 98.03%. New checks cover native provider/context/connector packets, bounded settings/capabilities, graph expansion, prompt pruning, full scene timing and known names, color/label identity and normalized Inspector Context parity. Legacy 371/371 and 74/74 still pass. Nine separate UI views and Inspector Override/Rebuild/Raw were checked in ComfyUI. Default Image/Video/Director details still require scrolling; reference-layout acceptance remains partial. Full evidence lives in the local `_notes/NG/14-native-ai-layout.md` and `experiments/e18_*` records.

## Automated checks

- 186 NG checks: 185 passed, one Windows symlink-permission skip. Ordinary path containment checks pass.
- 98.01% executable core-line coverage from the standard-library trace runner; line coverage does not establish render quality.
- Legacy compiler 371/371 and nodes 74/74 rerun successfully. No Legacy behavior tests removed.
- Existing registration tests now assert the exact requested H3 Context display names and NG/Technical categories; all functional checks remain.
- Native output types, raw+lazy model links, closed expanded graphs, roles/Preserve/preset round trips, source ranges,
  timed guide placement, paired-video audio numbering and provider/Auto-Direct validation have new checks.
- Frontend logic checks include Connector traversal/provider-field whitelist, stable-ID rename, references, story editing and downstream progress.
- Structural guards, Python compilation, JS syntax and diff whitespace checks run before local completion. No new pip dependencies.

Run from the pack root with ComfyUI's Python:

```powershell
python tests/ng/run_tests.py
python tests/ng/coverage_core.py
python test_plan.py
python test_node.py
python -m compileall -q ng
```

## Native product runs: E15

ComfyUI 0.37.0/frontend 1.53.6, Python 3.12.10, Torch 2.9.1+cu130, RTX 5060 Ti 16 GB, 384×576, 8 steps, fixed seed 321
(recovery 322). Native loop/sampler/collector. Functional low-resolution checks; no claim of production image quality.

| Variant | Chunks | Frames | Video/audio seconds | Runtime | Progress/previews |
|---|---:|---:|---|---:|---:|
| text |2|192|8.000/8.000|99.5s|16/19|
| image + voice |2|192|8.000/8.000|127.7s|16/19|
| timed image guide |2|192|8.000/8.000|99.8s|16/19|
| music lock |2|192|8.000/8.000|97.1s|16/19|
| native sampler outputs |1|107|4.458/4.459|40.0s|8/8|
| video + paired audio |1|107|4.458/4.459|131.6s|8/10|
| last-video-frame continuation |1|107|4.458/4.459|50.5s|8/10|
| recovery after interruption |2|192|8.000/8.000|95.3s|16/19|

4 seconds rasterize to 107 frames on H3's grid, as the planning warning says. AAC container rounding can differ by about 1 ms.
An initial missing expanded chunk-graph edge was fixed; its failure history is retained. Invalid Video test usage was corrected before queueing.
Interrupt after two progress events ends without a final MP4. Recovery runs in the same process without restart.

Lock/source envelope correlation is 0.974 overall, 0.974/0.968 before/after the join; chroma similarity 0.994 overall, 0.994/0.992 per chunk.
These are sample metrics, not unchanged-waveform or perceptual listening results.
Sparse contact sheets were inspected: bakery hands/dough persist over this sample's join, and the reference figure remains recognizable.
The timed image guide changes the character/scene at the requested part of the video; smoothness is not established by those sparse frames.

## Product UI checks

Real browser checks cover compact/detail cards, native model/context/output connections, Source upload, image content/Preserve presets,
explicit mock-provider Analyze/Apply and Auto Direct/Apply, audio range drag/playback, video player/paired-audio choice,
Text quick insertion/template use and Director modes/scene editing. Requests use a local deterministic fixture, not an external paid service.
Asynchronous native upload previews are hidden per Context node because its workspace already has a media preview.
Scene time fields commit on input. Save/reload preserves the edited timing and Context IDs. Generate from the restored product workflow succeeds: 192 frames, video/audio 8.000 seconds, native iteration 2/2 and live preview.

Exact histories, scripts, MP4 paths, test logs, browser screenshots and product Save/Reload evidence are in the supplied local
`_notes/NG/experiments/e15_*` folder. New examples are editable normal ComfyUI workflows.


The Connector accepts a second Video Context through a real dragged cable, grows its next empty input and retains both video links after save/reload.
Extra empty restored tails are removed only on the NG Connector; connected slots and gaps before them remain intact.
Waveform Zoom reaches 400% without altering the source range. Compact labels and the separate AI source cards are readable.
The current AI Loader's timeout, token limit and keep-alive reach the transport for Analyze/Auto Direct; an older six-widget provider configuration is migrated on restore.
Configured providers are labeled *not tested*. Native CLIP selection now enables assistant actions when the actual encoder is connected. Successful native requests record action/medium; model/settings changes invalidate the badge. No provider request runs during load or rendering.
Layouts use ComfyUI DOM widget sizing; remaining default sizing/scroll issues are tracked as open requirements.

## Practical limits

No human listening assessment or calibrated imperceptible-seam criterion. Single-seed runs and sparse frame inspection cannot establish
identity/audio quality across arbitrary long videos. Existing multi-chunk experiments show possible audio high-frequency loss and action delay.
Preserve, structure and camera instructions guide H3; Video Continue uses a last-source-frame guide.
Adaptive continuity/crossfades, broad multi-seed quality and the full multi-asset relationship graph remain further research.

## Historical foundation evidence

The earlier M0–M11/E13 checks below remain valid for their original technical scope. They did not establish the later product interface.

## Fresh live evidence: E13

Environment: ComfyUI 0.37.0, frontend 1.53.6, Python 3.12.10, Torch 2.9.1+cu130, RTX 5060 Ti 16 GB. Native List loops,
`SamplerCustomAdvanced`, 384x576, 8 steps, fixed iteration seeds. These are functional checks at low resolution/steps.

| Run | Chunks | Frames | Video / audio container seconds | Runtime | Progress / preview events |
|---|---:|---:|---|---:|---:|
| Text with manual shots | 3 | 719 | 29.958 / 29.959 | 334 s | 24 / 28 |
| Image and voice | 2 | 481 | 20.042 / 20.042 | 239 s | 16 / 19 |
| Audio lock | 2 | 192 | 8.000 / 8.000 | 100 s | 16 / 19 |
| Automatic reference continuation | 5 | 1195 | 49.792 / 49.792 | 599 s | 40 / 46 |

All completed successfully; exact output frame counts match the plan. AAC decoder padding can increase the decoded audio buffer
by about 22-26 ms in the shorter MP4 checks; container duration and collector length are recorded separately.

Text joins: image-step ratios 1.53x / 0.67x; audio click ratios 4.11 / 0.07. Reference join: 4.87x image, 0.84 click.
Five-chunk chain: image ratios 3.69x / 5.44x / 4.02x / 4.62x, relative to its small median frame step (0.0026 normalized greyscale).
Audio level ratios after/before those joins are 0.29 / 0.12 / 0.36 / 0.39; click ratios 0.27 / 0.00 / 1.80 / 0.64.
These ratios describe this sample; they have no calibrated perceptual acceptance threshold.

Sparse contact sheets show the reference character and sanctuary persisting across the chain. The text-only project changes
the baker's appearance in its later shot. This is not a multi-seed identity guarantee. Audio-lock envelope correlation to the source
is 0.953 before and 0.963 after the join, best offset 0 ms on a 10 ms measurement grid. Listening has not been verified.

Interrupting after two progress events stops the native loop with `execution_interrupted`, no final MP4 and no pending jobs.
After a fresh interruption on the final backend, a browser-queued Audio-Lock render succeeds in the same process without restart:
192 frames, video/audio 8.000 s, 94 s runtime. The UI shows iteration 1/2, sampling progress and the sampling preview.
The installed rgthree progress extension labels a generated inner-loop node `???` and can show over 100%; this is not used as
an NG correctness measure. Native sampling progress and the loop iteration label are checked separately.
The browser verifies saved presets, explicit local mock-provider analysis and Apply, all inspector modes, and persisted provider,
mode, identity and colour after workflow reload. Reload does not call the provider automatically.

Full histories, event traces, scripts, contact sheets and exact local output paths are kept in the supplied development folder
`_notes/NG/experiments/e13_*`. The local mock fixture is reproducible with `e13_mock_provider.py`; it is not an installed provider.
## E42 — One Director interface (2026-10-04)

E43a extends this baseline; its separate results are recorded below.

Obsolete workflow views are discarded, while render/story inputs and saved sizes remain.
Main settings stay editable without expanding details. AI action choices now match the loaded workflow.
The new frontend test checks real extension hooks with a DOM stand-in; registration tests check all ten technical IDs.
NG: 475 checks, 474 passed/one existing Windows skip. Legacy: 374/374 and 74/74; all six frontend suites passed.
An isolated ComfyUI browser session verified manual edits, two shots, compiler preview, mouse resize and Save/Reload.
No new GPU render or quality acceptance was performed for this frontend change.

## E43a — Structured shot foundation (2026-10-04)

The existing String widget now accepts a versioned shot document and old timed text.
Stable IDs, media bindings, manual spoken lines, locks and separate inactive drafts
survive serialization and chunk splitting. Actual compiled references are selected
per intersecting shot; global contexts and Subject dependencies retain their roles.
Preview and execution share the parser/compiler. Invalid structured input is retained
for repair and is never silently downgraded to legacy text.

NG: 496 checks, 495 passed/one existing Windows skip; Legacy 374/374 + 74/74.
All seven frontend suites, NG syntax checks, compileall and git diff checks passed.
New tests cover migration, malformed data, raster/head intersections, dependencies,
roles, exact dialogue, disconnected contexts, compiler/preview equivalence and UI
controls. Two new fixture assertions initially assumed an exact 10-second boundary;
they were corrected to the actual 243-frame boundary, with a separate regression
for a chunk extending into the next shot. No existing behavioral test was weakened.

A real browser on isolated CPU servers verified assigning an image, two manually
authored dialog lines in German/English, protection controls, manual editing of
protected words, real compiler output and Save/Reload. Shot IDs, bindings, exact
words and locks persist; width 780 px equals scrollWidth. The scene compiles Ref2VA
then T2VA as its reference scope ends. Adding dialogue keeps its controls open and
the protection count updates immediately; both found UI defects have regressions.

Evidence lives in `_notes/NG/experiments/e43_*`, especially the baseline counterprobe,
live preview, browser/reload JSON, saved workflow and screenshots. The E42 counterprobe
was run after implementation and is not presented as a before-code TDD run.
Own servers 8197/8198 and the browser tab are closed; user server 8189 is unchanged.
That running server needs a restart to use the new backend before structured shots
are used there. No GPU render or quality acceptance is claimed in E43a.

E43 remains partial. Required next: native render/adapter validation of scoped
references and per-chunk mode changes, plus the remaining binding/placement edge
contracts. E46 must provide ID-addressed drafts and selective AI Apply; currently
the old scene replacement is blocked for bindings, structured dialogue or locks.
Audio placement/mixing, media indicators, timeline work and human quality/design
acceptance remain open. See [the exact shot contract](NG-shots.md).

## E43b — Native scoped-shot validation (2026-10-04)

Fixed a reproduced role-order regression: alphabetically sorting scoped roles
could turn a context's `voice, copy` choice into `copy, voice`. Two tests failed
before the fix; inheritance and overlapping bindings now retain context/story
order and remove duplicates. Invalid-role fallback is tested too.
A separate failing counterprobe showed late, short copy/lock bindings can produce
no reference under the existing project-origin timing. They now report
`shot_audio_origin`; placement at a shot's own start is still unimplemented.

NG: 503 checks, 502 passed/one existing Windows skip. Legacy: 374/374 + 74/74.
All seven frontend suites, syntax, compileall and git diff checks passed.
New contracts cover Ref2VA/T2VA scope changes, stable Subject ownership after
label renumbering, inactive drafts, dialogue non-repetition, absolute keyframe
timing with carry, role priority and the visible audio-origin limit. A real
installed H3 tokenizer test checks scoped video, selected source interval,
paired soundtrack and standalone audio presentation. Its tensors are synthetic.

Two GPU jobs succeeded on a private server at 8199: native external sampling loop
(normal RandomNoise, KSamplerSelect Euler, BasicScheduler, CFG 1, sigma shift,
ConditioningZeroOut) and H3 Render Sequence's native loop. Both used three chunks,
Ref2VA → T2VA → Ref2VA, with bound image/voice references in the outer chunks.
The external observer confirmed actual models REF → FL → REF, seeds
20261043/44/45, exact preview/execution prompts and labels, both AV streams, and
7 video/1 audio carry-conditioning entries copied exactly from each prior tail.
These equality checks concern conditioning, not an assertion that generated
frames or sound are identical across a seam.

Both outputs: 277 decoded frames, 256×256, 24 fps, 369333 audio samples at 32000 Hz,
finite images/audio; duration difference is less than one audio sample. MP4 files
decode all 277 frames and include AAC audio. Contact sheets were produced for
inspection. Three sampling steps provide function smoke evidence only; no speech,
identity, seam, visual design or product-quality acceptance is claimed.

Evidence: `_notes/NG/experiments/e43b_*`, especially API fixtures, native/sequence
histories, before/after observations, verified output JSON, role/audio red-green
logs, full-suite logs and contact sheets. MP4s are in `ComfyUI/output/ng_lab/e43b`.
An initial new fixture assumed a shorter trained minimum; it was corrected to
107 sampled frames without changing the planner/tests. The initial Legacy command
used unittest module loading with embedded Python and failed to import the script;
the prescribed direct script runs passed and the failed launcher log is retained.

Audio placement/mixing and arbitrary interior first/last/continue anchors remain
explicit E45 work. E44 media indicators, E46 selective AI Apply and E47 provenance
remain open. The user server is preserved; own server/junction cleanup is recorded
in the section note. No push, tag, release or completion claim.

## E44 — Shot media indicators and input previews (2026-10-04)

Mixed shots now show all explicitly assigned, mentioned or speaker-bound Context
media, with distinct icons, Context colors and identity/role tooltips. Action and
structured dialogue have separate marks. Audio classification is explicit metadata:
Singing is additive to the existing content choices, with no acoustic detection claim.
The actual compiler Inspector remains the authority for conditioning.

The local preview adapter decodes only the first input-video frame. AI video
analysis retains its separate multi-frame sampler. Shot previews share requests
by file, refresh overwritten filenames, abort retired sources and ignore stale
responses. Updating the marks retains a focused action textarea. Preview bytes
never enter shot storage or the saved workflow.

NG: 507 checks, 506 passed/one existing Windows skip. Legacy: 374/374 + 74/74.
All eight frontend suites, compileall, layering/size guards and git diff checks passed.
Before implementation, two Python assertions failed (Singing absent; preview used
the AI frame sampler), and the new JS test failed because the media module was absent.
Existing behavioral tests were not relaxed. Additional tests cover mixed audio,
Unicode mention boundaries, disconnected IDs, decoder errors, focused edits,
shared I/O, retry, source replacement races and node disposal.

A private CPU server at 8200 verified actual image/video loading, mouse assignment
and removal, a second entirely manual shot, Refresh previews and Save/Reload.
Stored shot data and DOM identity/color/preview observations match after reload;
both displayed image hashes match the endpoint payloads. An independent PyAV
decode confirms the video payload is frame zero. A missing file returns HTTP 400
with actionable feedback. Director width and scrollWidth are both 843 px.

Evidence: `_notes/NG/experiments/e44_*`, especially `e44_verified.json`, browser
saved/reload JSON, image hashes, screenshot, saved workflow and red/green logs.
The fixture clone produced four native input-replacement console messages;
ComfyUI initialization produced two early graph-access messages. These are retained
in the browser log, so this is not a clean-console claim. The resulting Context
connections and persisted values were verified. Two initial Legacy commands used
the wrong `tests/` path; corrected root script runs passed and both logs remain.

Own server 8200/PID 36764 and its browser tab are closed; user server 8189/PID 21188
is preserved, with empty queues observed. No GPU render was needed for this preview
change. Visual design, output quality and the overall product remain unaccepted.
E45 audio placement/mixing, interior anchors and timeline work, E46 selective AI
Apply, and E47 provenance remain open. Contract: [NG-shot-media.md](NG-shot-media.md).

## E45a — Shared timeline axis and shot ordering (2026-10-04)

The Story and Generation tracks previously stretched different durations to the
same width. They now share an axis covering requested and delivered time. Preview
responses add exact story frame boundaries, fps and requested frame count from
the existing planner. Three-decimal duration labels and the grid warning agree;
the original requested value remains visible even for subframe input.

Shot selection highlights cards, bars and actual compiled chunk membership,
including pinned-head intersections. Earlier/later controls swap chronological
neighbors while preserving duration, gap, stable IDs and every non-timing field.
Overlaps/invalid ranges stay unchanged with feedback. Drag/resize use the shared
axis and zoomed DOM width; cancellation restores data. Removal stops bubbling
into the deleted card and moves selection to a remaining ID. Widget edits clear
the prior chunk track before requesting a new plan.

NG: 510 checks, 509 passed/one existing Windows skip; Legacy 374/374 + 74/74.
All nine frontend suites, syntax/compileall, layering/size guards and staged diff
checks passed. Before fixes: the timeline geometry assertion failed, the additive
preview fields were missing in all three duration cases, the warning said 10.12s
instead of 10.125s, removal bubbled, and a subframe wish was shown as a rounded frame
target. Each red log is retained; existing tests were not weakened.

The real planner and local endpoint confirm: 10 s/Auto → 243 frames/one chunk;
10 s/5 s target → 243 frames/two chunks; 120 s/10 s target → 2878 frames/twelve
chunks (119.917 s). These are delivered lengths; heads are included only in sampled
counts. Native sampling behavior and prompts are unchanged.

An isolated CPU browser at 8201 verified arrows and their inverse, then actual
mouse movement and both resize edges at 75% ComfyUI zoom. Saved/reloaded DOM
observations and workflow data match exactly; size 880×1300, width/scrollWidth
843 px, stable selection and all non-timing fields persist. An independent endpoint
probe compares track percentages to exact compiled frame boundaries and verifies
that the selected shot in chunk two exists only inside its 22-frame pinned head.
A second browser check sets 120/10: twelve chunks and 119.917 s are visible; the
requested-end marker is kept inside the track at 100% when output is shorter.

Evidence: `_notes/NG/experiments/e45a_*`, especially `e45a_verified.json`, live plan,
API cases, browser saved/reload JSON, head membership, drag data and screenshot.
Own server PIDs 52220/48752/26840 are stopped; port 8201 is closed; both working browser
tabs are closed. The first navigation preceded server readiness; binding its error
page was blocked by the browser URL policy. A fresh allowed localhost tab worked;
the failed tab was left temporary for automatic turn cleanup. Browser logs retain
four early graph-initialization messages, two Jobs API fetch failures during the
own-server restart and twenty warnings. No clean-console claim is made.

No GPU render or human design/quality acceptance was performed for this editor
change. E45 remains partial: shot audio placement, overlapping copy/lock mixing,
and interior anchor contracts are still open. E46 selective AI Apply and E47
provenance remain open. Contract: [NG-timeline.md](NG-timeline.md).

## Studio (S1–S8, 2026-10-04)

Built by Claude from the accepted clickable prototype; plan and decisions in `_notes/NG/45-studio-build-plan.md`.
Local commits on `ng`: `fc5901b` audio lane clips, `89755e8` turbo/canvas/fitting, `6ec31a6` Studio,
`bd26caa` settings bar, `8af8515` change tracker and turbo LoRA choice. No push, tag or publication.

Automated: 559 NG tests (one Windows symlink skip), Legacy 374/374 + 74/74, every `tests/ng/js/*.mjs` suite
(including `test_h3s_model.mjs` and `test_h3s_views.mjs` on a minimal DOM), size/layer limits in `test_structure.py`.

Browser, own CPU instance (port 8210, own user/output directory, in-memory database): open/close with Esc,
moving/resizing/reordering shots with real mouse input, Content drop, audio drop onto a lane with the file's real length,
typing while the live plan refreshes (focus kept), presets/megapixels/from picture, Turbo and mode, the per-part prompt
drawer, Save/Reload, and both AI buttons over `/ng/direct` with a mock provider (port 8211). At 1280×800 no horizontal
scrolling and no inner scroll areas; the page is 979 px tall and scrolls as a whole.

GPU, own instance (port 8212, RTX 5060 Ti), both runs through Render Sequence with Turbo:

| Run | Setup | Result |
|---|---|---|
| FL2VA | 8 s, two parts, 864×480; song locked as a lane clip at story 1–7 s from file second 20 | 192 frames, 138 s. Envelope correlation at the intended place 0.97 (control against the file start −0.07); best lag 1.00 s; part 1 and part 2 each 0.97, so the sound continues across the seam |
| Ref2VA | Mage picture and voice, two parts | 192 frames, 159 s; the figure is consistent across both parts |

Evidence: `_notes/NG/experiments/s8_*` (videos, frames, `measure.json`, `s8_measure.py`). All own instances were stopped;
the user's server on 8189 was not touched. No listening test or human quality acceptance.
