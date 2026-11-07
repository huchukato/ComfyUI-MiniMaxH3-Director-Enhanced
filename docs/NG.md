# H3 Director NG

NG is the second-generation Director in this pack: videos of any length, rendered as several H3 parts
that continue into each other. It separates reusable media (Context nodes), model connections (Context
Connector), story editing (the **Studio**) and rendering (native ComfyUI sampling).
The original timeline Director remains available as **Legacy** with its existing node ID and workflows.
Version 1.0.0 is published (GitHub and the Comfy Registry); 1.0.0-beta.1 was its pre-release.


## Start with a connected workflow

Use **example_workflows / H3 Director - 1 Text to video.json** for a complete text-to-video graph.
Choose your installed H3 FL2VA model, CLIP of type `minimax`, video VAE and audio VAE. The examples use development filenames;
replace model selections if your installation differs. No models or reference media are bundled.

```text
MODEL / CLIP / video VAE / audio VAE ─┐
Image / Video / Audio / Text contexts ├→ H3 Context Connector
H3 AI Loader (optional) ─────────────┘          ↓
                                         H3 Director  (the Studio is the node)
                                              ↓
                                      H3 Director Output
                                              ↓ sequence
                                      H3 Render Sequence
                                              ↓ VIDEO
                                          SaveVideo
```

For a character and voice, open **H3 Director - 2 Characters and voice.json**, select your own picture and voice in their Context nodes,
and connect the H3 Ref2VA model. Give each context a distinct name; `@Mage` refers to the image named Mage.

## The Director node

The Director node **is** the Studio: the whole Studio described below is the node's face in the graph, and the node is as tall as
its content. The Studio writes the node's own widgets, so ComfyUI's unsaved-changes marker and Save/Reload include every edit.
Keys pressed inside it stay there (Delete on one of its buttons does not delete the node); Ctrl/Cmd shortcuts still reach ComfyUI.

A Director saved by the former compact node (440 px wide) grows once when the workflow is loaded, and the nodes to the right
of it and below it move along so nothing overlaps; the same happens for Context nodes saved before they became full cards.

## The Studio

**Control video:** Context Video cards can load or generate Canny, Pose and Depth videos. Place them on the Studio's separate
Control lane and connect the ControlNet `model_patch` at the Context Connector. Render Sequence applies it per part, skips
uncontrolled parts and includes control changes in Resume. Partially covered parts hold edge frames; [setup and limits](NG-control.md).
**Inpaint** keeps the original video and a separate mask on the same card. Generate a mask through SAM3 using an object description,
or load/upload a ready mask; adjust bounding box/silhouette and grow, then place the card on the Control lane.

**Full screen** in the Studio's header lifts the same Studio over the whole window; **Esc** or **Back to graph** puts it back
into the node. It has no inner scroll areas. Below about 960 px of width the side panel moves under the timeline. **Generate** queues the connected workflow, exactly like ComfyUI's Queue button.

### Make H3 prompt

The quickest way to a finished prompt, for anyone who does not want to write one. Choose a **direction** (Let the AI decide,
Music video, Song, Story, Action / fight, Calm scene, Dance, Horror, Comedy, Romance, Spicy 18+), whether anyone speaks
(No speech, Dialogue, Narrator, Singing; with words, their language) and press **Make H3 prompt**. Pictures on Context cards
are enough; the Prompt is optional with pictures and is used when there is one. The Director's **Duration** sets the length.

1. The AI is shown the pictures (with their card descriptions) and plans the whole video: the Look, timed shots with action
   and camera, spoken or sung lines, ambience and music. Words you write in quotes or after "says:" are used as they are;
   otherwise the AI writes short lines in the chosen language. Lyrics on an Audio card stay the song's (timed as usual).
   A picture card without a description gets one from this answer.
2. The plan replaces the shots (another view of a figure, "Belongs to", and a place picture are bound to the shots that show
   them), then every render part is written out by the part writer with the direction and that part's pictures, checked and
   kept as the part's own prompt. A part whose answer breaks a rule keeps its compiled prompt and is counted in the message.
3. **Undo** in the message puts the shots, Look, sound fields and card descriptions back. It is also available if Cancel
   or a failed part request stops the build after the plan was applied.

The direction and speech are saved with the Director node. **Spicy 18+** is for adults only: a request or card that speaks
of a minor is refused before any AI is asked, and the AI is told to refuse a picture that suggests one. Whether a model writes
explicit scenes depends on the model (qwen3.5:9b writes them sensual but restrained).

### Prompt and Content

**Prompt** is the story: what happens, in any language, lyrics included. Without shots, the prompt alone carries the project:
a text-only video needs nothing else. A Text card used as **Scene / story** is read the same way, so the story may live in
either place.

- **AI: split into shots** asks the optional AI provider to turn the story into timed shots: action, the camera as a sentence,
  every spoken or sung line as its own entry (speaker, language, delivery, exact words), plus the **Look**, ambience and music.
  It is told when the song sings each lyric line (see the Audio card) and does not repeat those lines; it starts a new shot only
  when the view changes, as MiniMax's guide asks. The proposal appears as dashed shots; **Accept** replaces the current shots
  (and clears the parts' own prompts, which belonged to the old plan), **Discard** leaves everything unchanged. Audio lanes are
  never touched by a proposal.
- **Whole prompt = one shot** turns the prompt into one shot spanning the project.
- **Look (every part)** is what all render parts share: style, place, light. Once there are shots, H3 gets the shots and the Look;
  the Prompt itself is not pasted into every part again (a 27 s song carried its whole verse into each of three parts that way).
  In First / last frame mode the Look opens `[Shot 1]`, in References mode it stands before `[Shot 1]`, as the two guides ask.
- A shot that runs over several render parts gives each part only the action of its own share of the shot's time: time beats
  in the shot text (`2.5–5s: …`, seconds from the shot's start) go to the parts they fall in, re-timed to the part; other text
  is cut into sentences and clauses laid over the shot's time by length. Inside a sentence it is cut only at words that say one
  step follows another (`…, then`, `and then`, `, before` / `until` / `ending` / `finally`, `and back toward`), so a shot written
  as one sentence is shared too; a clause goes to a part only when at least a quarter of its time lies there. A shot whose rest lies only in a part's
  pinned head gets no new action. Before, each part replayed the whole action (a 20 s walk away and back was walked twice).
- Each later part of a shot gets "Continue the same scene and action from the preceding video …" before its text, and sentences that move the
  camera (`push`, `pull`, `zoom`, `pan`, `dolly`, `orbit`, …) are left out there; a held camera stays. Every part read
  "the camera pushes in" as a push of its own: in a 20 s shot over three parts the zoom built up until H3 cut away to a
  glossy close-up (real minute 2026-10-11, cut at 33.4 s; gone with this rule, same seed).

Later shots normally receive a timestamped camera cut. An explicit `without cutting`, `No camera cuts`, or continuous/single
take instruction in the shot or shared Look/rules prevents an added cut. Explicit transition text remains unchanged.

**Content** shows one card per Context node connected to the Context Connector, in its context colour, plus a plain **Text-Shot** card.
Drag a card onto the empty timeline to create a shot with it, onto a shot (or click it while a shot is selected) to assign it,
or an audio card onto an audio lane. Cards the current mode cannot use are dimmed (for example a Motion reference in First / last frame mode).
Files are chosen in the Context nodes themselves, not in the Studio.
**Continue from video** uses the last 39 frames before the card's selected source end as hidden movement context, with
matching audio when **Its own sound** is sent along. FL2VA and Ref2VA both use native time-anchored guides. Short selections
use 22, 5 or 1 frame and show a warning. The final original source frame is included, independent of the source frame rate.
Render Sequence removes this prefix from picture and sound; Duration describes the new footage. The original source can
be joined to it with native Concatenate Video. A later shot with its own Continue source starts an independent render part.
Video decoding keeps native float colours and display rotation and reads source timing relative to the video's first timestamp.

### Timeline

All tracks share one time axis on a **0.1 s grid**.

- **Shots**: drag a shot to move it, drag its edges to change start or end. Drag a shot over another and release to reorder;
  the others close up behind it while gaps stay where they were. A click selects the shot. **+ Shot** adds a 4 s text shot in free room after the selected (or last) shot, else in any free room;
  on a full timeline it halves the selected shot and says so.
- **Audio lanes** run independently of the shots, so a song placed on a lane plays continuously across shots and render parts
  instead of restarting per shot. **+ Audio lane** (or the empty drop zone) adds a lane; drop audio Content on it, move the clip,
  trim it at its edges. A clip has its own story range and **From second in file** (start offset in the file).
  An empty lane can be removed. There are no fixed lanes for voice, music or effects.
- **Render parts** show how the planner splits the project into H3 runs (about 10 s by default), each in its own colour.
  A part's tooltip shows its frames and the frames carried over from the previous part.

Render-part length is a planning preference. The planner limits the number of parts to H3's valid clip lengths.
Reducing the project duration removes newly cut fragments shorter than 0.5 seconds; Undo restores the timeline.
Complete short records from older projects remain intact when they fit within the new duration.
Trimming an audio clip's left edge advances **From second in file** equally for Lock, Copy and Reference,
stopping at the beginning of the file. Moving a clip keeps its file offset.
Renaming a connected Context also updates its `@Name` mentions in the Look, part prompts and spoken text,
including projects without shots. Clip ranges and Context/speaker IDs remain intact.

### Right column: Mode and the selected item

**Mode** is the central choice and applies to the whole project:

| Choice | H3 model | Uses |
|---|---|---|
| **First / last frame** (FL2VA) | first/last-frame model | first and last frame, keyframes, sound |
| **References** (Ref2VA) | reference model | figures, places, videos and voices as references; timed image guides |

Older workflows saved with `auto` keep it and show it as automatic; it is also selectable under **More settings**.

**AI shots** begin with the framing and say how the camera moves (amplitude and speed) or that it holds a static shot. A shot
longer than 5 s is written in time beats from its own start ("0–5s: ... 5–10s: ..."); the AI never changes shot times.

**Turbo** renders with a few-step H3 turbo LoRA. Each mode has its own LoRA selection; nothing is preselected, the user chooses.
A known LoRA (`js/ng/turbo_profiles.json`: the official ComfyUI LoRAs, Taomate, the ckpt500 turbo) brings its measured steps,
sampler and scheduler: the Studio's settings jump to them, and each render part samples with the values of its own model's LoRA,
so a video mixing First / last frame and References parts renders each part right. An unknown LoRA renders with the Director's
Steps, Sampler and Scheduler; without a LoRA the Studio warns. CFG stays 1: every official H3 template uses BasicGuider.

Below it is the panel of the selected item:

- **Shot**: start/end, **What happens?**, the Content assigned to this shot, and its spoken lines in order, each with
  speaker (or narrator), language, delivery (says, sings, whispers, shouts, murmurs; a song needs *sings*) and text; **+ Spoken line** adds one, × removes one. **AI: suggest / improve text** asks the
  provider for this shot's text; the suggestion is shown with **Accept** / **Discard** and changes nothing until accepted.
  The panel lists the render parts the shot falls into.
- **Audio clip**: start/end on the story, the offset in the file and how H3 uses it:
  **Lock exactly** (encoded source audio is pinned), **Copy as closely as possible** (H3 is asked to reuse the sound) or
  **Reference only** (mood, voice, style). In First / last frame mode H3 can only take a clip as lock.

### Settings bar

The bar under the timeline has two rows that are always visible:

- **Video**: duration in seconds (any value on the 0.1 s grid; **= <audio card>** takes the length of the longest connected audio,
  e.g. a 27 s song; a longer duration lets the shot that reached the old end run on), render-part length (Auto = about 10 s), resolution preset, width/height, **Picture size** fold-out, FPS (H3 is 24 fps).
- **Sampling**: seed with random toggle, steps, sampler, scheduler, **More settings** fold-out.

Resolution follows the Legacy Director: presets **Native** (short side 768), **Fast** (short side 480) and **Above native** (1920×1088), **From first picture (H3 chooses)**,
and custom sizes on H3's /32 grid. The **Picture size** fold-out has aspect ratio, megapixels, **Fit pictures** (crop, stretch, pad,
pad green) and **Reference images** (*Like video* is fastest).
With width and height 0, the size comes from the first frame picture, or else from the first image, using H3's rule
(short side 768, area at most 768·1344, multiples of 32); without any picture it falls back to 1344×768 and says so.

**More settings** contains continuity between render parts (picture and sound / picture only / hard cuts), the overlap,
ambient sound, music, style and the video/audio sigma shifts.

### Prompts per render part

**Show prompts** opens a drawer at the bottom with the actual prompt each render part receives, coloured like its part,
its reference budget (pictures/videos/audio used of H3's limits) and all plan warnings with a short heading. A badge says where
each part's prompt comes from: compiled, AI-written, edited, or manual.

- **Write with AI** (one part) or **Write all parts with AI** asks the AI Loader's model to write the part out in full, the way
  MiniMax's own hosted pre-processing does. The AI writes only prose: the description and the two sound fields. The alignment
  line, subject definitions, summary, retention analysis, cut times, every `<d>` line, the speaker IDs and the labels stay the
  planner's. What a model reliably gets slightly wrong is put back (a time on Shot 1, a sung line without its speaker,
  re-punctuated lyrics, lyric lines left out); anything else is refused with the reason and nothing changes. **Accept** stores it.
- **Edit** lets you write the part yourself; **Save** stores it, **Reset** returns to the compiled prompt.
- An AI-written or edited prompt is kept with the plan it was written for. When the plan of that part changes (timing, shots,
  media, Look), the compiled prompt is used again and the badge says "own prompt outdated".
- **Manual prompt** under More settings still replaces every part's prompt.

While an AI action runs, a status at the bottom of the window shows the elapsed time against the AI Loader's timeout and
**Cancel**. Failures stay there until dismissed; short confirmations disappear by themselves.
This is the compiler's real output, refreshed live while you edit.

## Rendering paths

- **Simple**: Director → Director Output → Render Sequence → SaveVideo (the text studio example). Render Sequence expands into
  native StartLoop/List, conditioning, SamplerCustomAdvanced and EndLoop with normal previews and Stop. When Turbo is on,
  `LoraLoaderModelOnly` is inserted on the model.
- **Your own sampler**: **H3 Director NG - native sampler.json**. Director Output supplies native `MODEL`, positive/negative
  `CONDITIONING`, `LATENT`, fps, width/height, prompt and seed for one chunk; **sequence** carries the whole project.
  An internal continuation requires the previous chunk's raw latent on `previous`; a part with its own Continue video does not.
  Native LATENT ports include the hidden prefix; use NG Collect or Render Sequence to remove it from picture and sound.
- **Live preview**: load `taeh3.safetensors` with Load VAE and connect it to Context Connector's `preview VAE`. Render Sequence
  then previews every part itself (its player appears on the node with the first frames). With your own sampler, put
  **🎯 Preview Override (live)** between Director Output's MODEL and your guider and connect Director Output's `preview VAE` to it. Both players buffer, with pause,
  scrubbing and independent playback/update status. At 24 FPS they retain
  every decoded frame and the clip's full duration. See [decoder setup and controls](legacy-director.md#live-preview-while-sampling).
- **References**: every path calls ComfyUI's own H3 nodes and never patches them. Before the call the Director brings pictures
  and reference video frames to the Qwen size of H3's released processor and cuts a reference video's soundtrack to the frames
  the stock node keeps (`minimax_refprep.py`).
- **Resume after a crash**: Render Sequence keeps every finished render part's raw latent in `output/h3-director-resume`. Queue the
  same plan again and the finished parts come from disk without sampling; a changed part and every part after it render again.
  A shot change usually lies a few frames before the end of a part (H3's frame grid; a cut right after a join would come about
  2.5 s late), so that part already shows the new shot's first frames: editing a shot's text renders the part before it again too.
  Files older than 14 days are removed. The models are not part of the key: after swapping a checkpoint, empty the folder.
  The Studio's **Resume** switch (under Turbo) turns it off. Its box **Delete the kept parts when the video is done** (on by
  default) removes a video's parts once it is put together, so they do not fill the disk unseen.
- **Control video (experimental)**: **H3 Control Video** between Director Output's MODEL and the guider steers each part with a
  pose, depth or edge video (MiniMax H3 Fun ControlNet-Union via ComfyUI's `ModelPatchLoader` and its apply node), or with a mask
  and the source video behind it. The videos run on the story timeline at 24 fps; each part gets its own window, head included.
  Make the control video with ComfyUI's own nodes: SDPose (pose), Canny, MoGe or Depth Anything (depth), SAM3 Video Track (masks).
  ComfyUI's **Detect Edges (Canny)** works on the whole batch at once (240 frames of 720x1280 ran out of memory on 8 GB): put
  **Rebatch Images** (16) before it and **Rebatch Images** (4096) after it. Measured (10 s walk, Luna from her sheet): canny at 1.0
  follows the source's path and framing exactly and keeps Luna's face and hair, but takes over outlines such as the source's
  cloak; at 0.5 Luna keeps her own outfit and hair, the walk to the close-up stays, the framing is looser. Depth at 1.0 carried
  the other figure's hair over, 0.5 does not.
- **Editable loop**: **H3 Director NG - native chunk loop.json** or **two sampler chunk loop.json**. The Director's **chunks** starts
  the loop and one Director Output inside it prepares each chunk. See [connections and continuity contract](NG-external-sampling.md).

## H3 Storyboard

**H3 Storyboard** (`NGStoryboard`) lays out a storyboard in the node, in the look of a ChatGPT storyboard sheet: a title line,
1 to 9 numbered panels in a grid (panel format 16:9, 9:16, 1:1, 4:3, 3:4 or 21:9), each with its time and title on the
picture and a caption below.

- **Wiring:** one cable, from the Context Connector's **H3 context** output (the same output that goes into the Director) to
  the Storyboard's **H3 context** input. Through it the editor sees the picture cards and the Connector's AI provider. The
  Storyboard hands the Director nothing by cable: **Send to Director** writes the shots into the Director and adds Context
  cards that load the drawn files from `input/h3-storyboard`, so there is no loop. The outputs are optional, for saving the
  sheet and panels or using them in another workflow; left unconnected, the node does not run with the workflow at all.
- **Panels:** each has its seconds (panels follow each other: 10 s, 2.5 s, ... are 0-10, 10-12.5, ...), a title, the caption
  on the sheet and the **shot text** H3 renders. Its picture is a stack of layers: pictures (from the Context cards connected
  through **H3 context**, from the input folder including subfolders, or uploaded to `input/h3-storyboard`), texts and a
  colour. Drag a layer to move it; the mouse wheel sizes it, with Shift it turns; Mirror, Opacity, order and Hide in the
  layer list. Undo / Redo in the header.
- **Cut out** removes a picture's background with ComfyUI's own Load Background Removal Model and Remove Background
  (`models/background_removal`, e.g. `birefnet.safetensors`), queued as a small job; the result is a PNG with transparency
  in `output/h3-storyboard`. Undo brings the original back.
- **AI: write panel texts** (the AI provider of the Context Connector on **H3 context**): from "What should happen" the AI writes the
  sheet's title and subtitle and every panel's title, caption and shot text, with the Studio's rules (framing, camera, time
  beats for a panel longer than 5 s). Panel times are never changed; texts the user wrote are kept in meaning.
- **Outputs:** `sheet` (the sheet as drawn), `panels` (each panel's picture, without caption) and `shots` (the panels as the
  Director's shot document). The browser draws the pictures when the workflow is queued and uploads them to
  `input/h3-storyboard`; an API graph queued without the browser has no sheet.
- **Use in Director** draws the sheet and adds a Context card with it (usage Storyboard), connected to the Context
  Connector of the **H3 context** input when there is one.
- **Qwen Image 2.1: + Figure from a sheet** draws a character card's figure in the pose and camera angle you write, on a
  transparent background (the RGBA wording of ComfyUI's Qwen Image 2.1 template; portrait, square or landscape, about 30 s).
  **+ Background** draws an empty place in the panel's format (about 20 s). Both go onto the panel and into the board's
  pictures: "+ Picture" offers them, and every picture already on a panel, under **From this storyboard** on every panel.
  **Use on all panels** copies a layer onto every other panel at the same place (a bottom layer goes under).
- **Drag and drop:** picture files dragged from a folder onto the Storyboard land on the panel they are dropped on (a
  panel of the sheet, or the panel canvas at the drop point; anywhere else: the selected panel). Several files stand side
  by side. Pictures dragged from ComfyUI itself (queue, the board's own thumbnails) work the same way without a new upload.
- **Redraw with Qwen Image 2.1** (per panel, or **Redraw all panels**): the panel's collage is image 1 and keeps its
  composition; the Context cards of the characters the panel names (else all character cards, up to four) are the
  references. ComfyUI's own Qwen Image 2.1 nodes run as a queued job (25 steps, Euler, CFG 1, about a minute); the result
  is a new layer over the collage, which stays below it. Needs `qwen_image_2.1` (diffusion_models), `qwen3vl_8b`
  (text_encoders) and `qwen_image_2.1_vae` (vae).
- **Send to Director** turns the panels into the H3 Director's shots (times and shot texts; the Director's sound lanes,
  Look and Prompt stay), puts the sheet's card on every shot (role Storyboard) and, for a panel marked **First frame of
  its shot**, adds a card with the panel's picture and binds it as that shot's first frame. The Director is the one on
  the same Context Connector (or the only one); its shots are replaced after a question.

## Product nodes

| Node | Responsibility |
|---|---|
| H3 AI Loader | Optional local/API provider configuration; a separate `NG_AI_PROVIDER`, not a diffusion MODEL |
| H3 Context Connector | Native model/CLIP/video VAE/audio VAE ports, optional preview VAE and AI, and four dynamically growing Context groups |
| H3 Director | The Studio itself in the graph (Full screen on demand); outputs the project result and the chunk list |
| H3 Director Output | Current chunk's native sampler values, seed and steps/cfg/sampler/scheduler (also as SAMPLER and SIGMAS), optional preview VAE, plus complete sequence packet for the simple render path |
| H3 Context Image | Full card: picture (also by dropping a file on the card), what is in it, default role, what to keep, figure link, description, preset |
| H3 Context Video | Full card: player, part of the file, motion/camera/continue roles, its own sound |
| H3 Context Audio | Full card: waveform with selection, voice/copy/lock roles, whose voice, listening controls |
| H3 Context Text | Full card: note, quick insert, templates, role (Scene / story is read by the AI split) |
| H3 Render Sequence | Expanded native List loop, sampler and collector; outputs VIDEO, IMAGE, AUDIO and notes |

The technical nodes remain available under **MiniMax H3 / NG / Technical** (NG Chunk Planner, NG Chunk Conditioning,
NG Collect, NG Collect Video for long projects, NG Project Chunks, NG Studio Laboratory). Saved IDs remain valid.

## Project data

Shots and audio clips are stored in the Director's `shots` widget as one JSON document (`format: "h3-director-shots"`).
Old timed text such as `0-4: @Mage looks up.` still loads. See [the shot contract](NG-shots.md).
New Director widgets (`turbo`, the two turbo LoRAs, `resize_method`, `ref_image_size`) are appended at the end, so older
workflows keep their values; an older NG workflow's trailing empty value is repaired on load.

H3 renders at **24 fps** on its `17k + 5` frame grid. The plan reports the real finished length and warns about rounding.
One resolution applies to the whole project. `chunk_seconds = 0` selects the planner's 10-second target; H3's trained chunk range is 4–15 seconds.
The style choice adds prompt instructions; it does not load a different model.

In First / last frame mode the prompt carries no `@refN` tags: mentions become plain names and a spoken line becomes `@voice(Name) says:`.

## Context cards

Each Context node is a full card in the graph (Image, Video, Audio, Text). The card says **what** the material is and
**who** it belongs to; **when** and **how long** it plays is set in the Studio (shots and audio lanes). The node grows with
its card, so cards never overlap their neighbours.

- **Top row:** name (`@Name` in the Studio), the file from ComfyUI's input folder with **Upload**, and whether the AI has
  analysed it. Files resolve inside the input directory; missing files stop rendering by name.
- **What is in it:** the content kinds of this medium. **✦ Analyze** asks the connected AI; its suggestion is shown with
  **Accept / Discard** and changes nothing until accepted.
- **Use as (default):** the role the card has unless a shot or lane clip in the Studio says otherwise. The hint under it
  knows the Director's mode and warns when a role does nothing there (e.g. a reference picture in First / last frame mode).
- Where a card is used shows in the Studio's shots and lanes; a card bound to no shot is part of every render part.
- **Preset** (save / load) and **Color** at the bottom.

**Image:** preview, **Keep in the video** (identity, outfit, pose, background — guidance for H3, not pixel-exact),
**Belongs to** (an outfit or pose picture presented together with a figure; empty = the picture is a figure of its own)
and a description. First / last frame open or end the video, or the shot the picture is dropped on in the Studio.
Global first / last frame cards also become timed native guides in References mode; they do not guarantee pixel-exact output.
A Keyframe dropped on a shot gets a time in the shot: **Seconds after shot start** in the shot's Content list (new ones
start in the middle; the video time and where the plan put it are shown next to it, and a diamond marks it on the shot).
Moving the shot takes the keyframe along. In First / last frame mode with continuity the Director ends a render part on
the keyframe, as that part's last frame, and the next part keeps its pin, so the shot runs on through the picture. H3 is
trained on pictures at the first and last frame; one inside a part was hit and then cut away one frame later (measured
2026-10-11). Parts end on H3's grid, so the keyframe moves up to a third of a second (`keyframe_moved`); one closer than
about 3.5 s to the shot's start, its end or another picture stays inside the running part (`keyframe_too_close`).
In each shot's Content list a picture can also take another role than its card has (Reference, First frame, Last frame,
Keyframe), e.g. one picture that ends one shot and opens the next. A storyboard plans the shots it is on (References mode;
a render part that holds only some of its shots names their panels); a keyframe without a time in the shot uses a time
stored on an older card, else the shot's start.
In First / last frame mode a Reference picture stays a reference: H3 gets it next to the first and last frame and keeps the
figure recognizable (face, outfit, props it cannot see in the first frame). It never becomes the First frame; for a start
picture choose First frame.
Guide time is sampled on H3's latent grid.
Before ComfyUI's H3 nodes get them, pictures and reference video frames are brought to the Qwen size of H3's released
processor (pictures 65,536–16,777,216 pixels, videos 4,096–25,165,824 across all sampled frames).

**Video:** player and **Part of the file to use** (drag across the strip). Motion / camera / whole structure send references
and prompt guidance, not exact copies. **Continue from video** uses the selected tail as a hidden video prefix.
**Its own sound** ignores the soundtrack or sends it along. For Continue it anchors the matching tail in both FL2VA and
Ref2VA; pure Continue does not additionally send the whole clip as a general reference. Other video reference roles keep
their paired video/audio references in Auto or Ref2VA. Without the full original song, voice and melody may still change.
To continue an existing full song, add an Audio card with **Lock** and select the source offset where the new footage
begins (5.875 s after a 5.875 s source clip). First frame pictures with a separate audio card remain supported.
A reference video is cut to H3's 17k+5 frame grid (72 selected frames keep 56), as ComfyUI's node does; its paired soundtrack is
cut with it.

**Audio:** play button and waveform; drag in it to choose the part of the file. **Whose voice** names the figure for the
Voice role and the singer of the Lyrics. **Listen here** (volume, fades) only affects playback on the card. Voice guides
timbre, Copy asks H3 to reuse sound, and Lock pins encoded source audio during sampling. Both NG collectors restore the original
source waveform inside Lock spans, with the selected source offset and overlapping tracks mixed; sound outside stays generated.
The export codec can still change samples. This avoids short silent tails caused by rounding the native audio latent grid.

**Lyrics** on an Audio card are LRC lines, `[mm:ss.xx] words`, in seconds of the file; an empty stamped line is a pause.
**⟳ Time with Whisper** keeps your own words and takes only the times from a local Whisper model (`models/whisper/small.pt`
or larger; while a render runs it stays on the CPU). Without lines it writes down what it hears. **Stamp line** sets the
selected line's time by ear while the song plays. Where the card plays exactly (Lock or Copy, on an audio lane, a shot or the
whole project), each render part gets only the lines sung in it, as `<Subject 1> (S1) sings, <d>[English] …</d>` in the
shot where they are sung. Measured on the 27 s elf song: Whisper small heard all eight lines in 7 s.

**Text:** a note in any language, with **Quick insert** brackets, templates and the role. As **Scene / story** it is story:
the AI split reads it like the Prompt, and with shots it is not pasted into every part. In every other role (style, rule,
character, camera rule, …) it goes into every render part. The former **Build H3 prompt** is gone: it wrote a complete H3
block that then nested inside the Director's own; final prompts are written per render part in the Studio.

One file may be used by several cards: every card keeps its own name, part of the file and role. Prompt labels follow the
order the media reach the model. Renaming a card updates its `@Name` mentions through its stable ID.

## Figures and their assets

An independent reference picture is a figure (Subject). **Belongs to** on an image, video or text card links that asset
to a figure, for example an outfit picture and a walk-cycle video to Alice; audio uses **Whose voice**. The compiler
presents linked assets with their figure; `@Outfit` names its picture, `@Alice` the figure. Older workflows that linked one
asset to several figures keep that until the choice is changed on the card.

## Presets

Save/Save As writes a versioned JSON preset under the current ComfyUI user's `minimax_h3_ng/contexts` folder.
Preset names are separate for each media type: saving an audio preset replaces only an audio preset of that name.
Existing preset files remain readable.
Load restores source, roles, description, property preservation, timing, identity, Subject assignments and colour.
Media bytes and AI credentials are not included. Duplicate IDs are rejected, and ambiguous names are reported.

## Optional AI

Connect **H3 AI Loader** to the Connector for Studio assistance, or directly to a Context for analysis.
Without an AI connection everything works manually; the Studio's AI buttons are disabled and say why.
**Local** chooses an installed text encoder or a running Ollama/LM Studio server, **CLIP / Encoder** uses a connected generative
Load CLIP, **API** and **Custom** use compatible endpoints. See [native AI setup](NG-native-ai.md).
Credentials saved with the AI Loader are read from the requesting user's key store by every HTTP AI action. A stored key
takes precedence over the server environment fallback; workflow files store the variable name, not the secret.
H3's own conditioning encoder (`qwen3vl_32b_minimax_h3_*`, 50 of 64 layers, no output head) cannot write text; an AI job on it stops at once and says so. Use e.g. `qwen3vl_4b_fp8_scaled` (type stable_diffusion) or Ollama.
Splitting into shots always allows at least 2048 tokens, because a shot list cut off at a lower **Max tokens** is unusable.
Split and Make H3 prompt accept a complete JSON plan with surrounding explanatory text. Malformed or ambiguous answers
remain errors; the Max tokens hint is reserved for an unfinished JSON answer.

**✦ Analyze** on a Context card makes one explicit request; **Accept** fills description, content and "Use as" from the roles the card shows (a Text card: "Use as" only). What each AI function does and which models were tested: [native AI](NG-native-ai.md#what-each-ai-function-does-tested-2026-10-05).
Video analysis samples three frames across the first 15 seconds, using container duration when stream timing is absent.
In the Studio, AI proposals for shots are reviewed before they change anything ([shot drafts](NG-shot-drafts.md)).
Loading, connecting and rendering never trigger provider requests.

## Continuity and verification

`video_audio` pins a previous part's video tail and about a second of audio before the next part; `video` pins only picture,
and `none` renders independent clips. The collector removes pinned heads. With a pin, the picture is decoded across the joins
as one latent (each part's regenerated head dropped), one window at a time, so the video VAE's clip blending runs over the seam
instead of restarting at every part; sound is still decoded per part. In FL2VA with a pin, a shot with a First frame picture of
its own opens a new part without a pin, so the picture is the part's real first frame; the shot start moves to the nearest H3
grid frame (a plan note says by how much). Inside a pinned part H3 takes such a picture as the end of the running take
instead. A shot with a First and a Last frame is anchored at both ends; with the mode set to FL2VA a Reference picture counts
as First frame. The planner tries to place boundaries away from new story actions
and warns when it cannot. Audio on a lane is cut per part at its story position, so it continues across the seam.

Read [NG-validation.md](NG-validation.md) for automated checks and native GPU runs. Single-seed functional runs show feasibility;
long chains may drift in identity or sound, and pinned audio may lose high frequencies. An imperceptible seam and a human listening
assessment have not been established.

## Not in the Studio (yet)

- The old inspector's **Analyze all contexts** and raw Director-Context JSON view.
- Adaptive continuity/crossfades, Subjects without an image and a relationship graph remain further work.
