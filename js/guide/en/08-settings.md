# H3 Director: all settings

Every field of the H3 Director in one place, from top to bottom. How to work with shots and the timeline is in chapter
*The Studio*; every field also has an ⓘ in the node.

![H3 Director](../images/wf2-director.jpg)

## Header

| Field | What it does |
|---|---|
| **Full screen** | lifts the Studio over the whole window; **Esc** or **Back to graph** puts it back |
| **AI connected** | an H3 AI Loader is connected and ready |
| **Show prompts** | opens *Prompts per render part* at the bottom |
| **Gear** | opens the Settings window (below) |
| **Generate** | queues the workflow, the same as ComfyUI's Run |

## Prompt

| Field | What it does |
|---|---|
| **Prompt** | what the video is about; with no shots it alone makes a text video |
| **Look** | style, place and light every render part shares |
| **Make H3 prompt** | the AI plans the whole video from your cards: Look, timed shots, lines, sound |
| Direction (*Let the AI decide*, *Music video*, *Song (singing)*, *Story*, *Action / fight*, *Calm scene*, *Dance*, *Horror / suspense*, *Comedy*, *Romance*, *Spicy 18+*) | the kind of video *Make H3 prompt* writes |
| Speech (*No speech*, *Dialogue*, *Narrator*, *Singing*) and language | whether anyone speaks, and in which language |
| **AI: split into shots** | the AI cuts the Prompt into shots; shown dashed until **Accept** |
| **Whole prompt = one shot** | one shot over the whole length with the Prompt as its text |

## Right side

| Field | What it does |
|---|---|
| **Output: Video / Pictures** | a video, or one picture per shot (Workflow 5) |
| **Mode: First / last frame / References** | which H3 model renders (chapter *References or first frames*) |
| **Turbo on** | renders with the turbo LoRA of the mode (Settings → Turbo) |

## Content and timeline

| Field | What it does |
|---|---|
| **Content** | one card per Context node; drag onto the timeline, a shot or an audio lane |
| **Undo / Redo** | the last changes on the timeline |
| **− / + / Fit project / Fit selection** | zoom of the timeline |
| **+ Shot** | a 4 s shot after the selected one |
| **+ Audio lane** | a new lane for a sound card |
| **Control +** | a control clip from a Video card set to *Control video* |
| **Render parts** | how the Director cuts the video into H3 runs (read only) |

### A selected shot

![A selected shot](../images/wf2-studio-shot.jpg)

| Field | What it does |
|---|---|
| **Start / End** | the shot's time in seconds (0.1 s grid) |
| **What happens?** | framing, action and camera; `@Name` names a card |
| **AI: suggest text / AI: improve text** | a text from the AI, shown until **Accept** or **Discard** |
| **Content in this shot** | the cards on this shot and their role here: *Reference*, *First frame*, *Last frame*, *Keyframe*, *Storyboard* … |
| **Seconds after shot start** | for a *Keyframe*: when the picture is reached |
| **Place** | *Its own place* or *Like Shot N* (reuse an earlier shot's place) |
| **Picture** | for *Like Shot N*: *Without people*, *As rendered (1 s in)* or *From another view …* with a camera text |
| **Effect** | an official H3 camera effect such as *Bullet time* (only when its files are installed) |
| **+ Spoken line** | a line said word for word: speaker (or *Narrator*), language, delivery (*says*, *sings*, *whispers*, *shouts*, *murmurs*), text |
| **In:** | the render parts the shot lies in |

### A selected audio clip

| Field | What it does |
|---|---|
| **Start / End** | where the sound plays in the video |
| **From second in file** | where in the file it starts |
| **Lock exactly / Copy as closely as possible / Reference only** | how H3 uses the sound (chapter *Voices, dialogue and songs*) |

### A selected control clip

| Field | What it does |
|---|---|
| **Start (s) / End (s)** | where the control video steers |
| **From second in file** | where in the control video it starts |

## Bottom

| Field | What it does |
|---|---|
| **Duration** | the video's length in seconds; a button such as **= Song** takes an audio card's length |
| **Resolution** | *From first picture (H3 chooses)*, *Native* (short side 768), *Fast* (short side 480), *Above native* (1920×1088) or *Custom size* |
| **Settings** | the same window as the gear |
| Summary | length, shots, render parts, size, mode and steps |

## Settings window

![Settings](../images/wf2-studio-settings.jpg)

### Video

| Field | What it does |
|---|---|
| **Render part** | *Auto* (about 10 s), 5, 8, 10, 15 or 30 s (small sizes only); shorter needs less memory |
| **Width / Height** | the size on H3's grid of 32; empty = automatic |
| **Aspect ratio / Megapixels** | set the size by shape and area |
| **Fit pictures** | *Crop*, *Stretch*, *Pad*, *Pad green*: how a picture of another shape is fitted |
| **Reference images** | *Like video (fast)* or *Large, 2048 px* (keeps faces better, slower; References mode) |

### Sampling

| Field | What it does |
|---|---|
| **Seed** and the dice | another seed gives another take of the same shots |
| **Steps / Sampler / Scheduler** | used without Turbo or with an unknown LoRA; a warning names pairs that spoil H3 pictures |
| **Spectrum** | only when the Spectrum nodes are installed: about a third faster at 20 steps (Turbo off) |
| **Shift video / Shift audio** | H3's sigma shifts, 12 and 3 |

CFG is always 1, as in every official H3 template.

### Turbo

| Field | What it does |
|---|---|
| **Turbo LoRA first / last frame** | the LoRA for FL2VA parts |
| **Turbo LoRA references** | the LoRA for Ref2VA parts |

A known LoRA shows its measured values (*Known LoRA: 6 steps · res_multistep · simple*); *none* warns.

### ControlNet

Shown when a Video card is a control video.

| Field | What it does |
|---|---|
| **Strength** | 1 follows the control video closely; 0.5 keeps more of your figure's shape |
| **Denoising range: Start / End** | share of the sampling steps the ControlNet works in (0–1), not video time |

### After a crash

| Field | What it does |
|---|---|
| **Resume on** | finished parts are kept in `output/h3-director-resume`; queued again, only missing parts render |
| **Delete the kept parts when the video is done** | cleans up after a finished video |

### Sound, style and transitions

| Field | What it does |
|---|---|
| **Ambience** | background sound of every part, in words |
| **Music** | background music in words; *N/A* = none |
| **Style** | *Cinematic*, *Anime*, *Documentary*, *Photorealistic* or none; adds words, loads no model |
| **Transition between render parts** | *Continue picture and sound*, *Continue picture only*, *Hard cuts* |
| **Overlap** | 5, 22 (default, 0.9 s), 39 or 56 frames of the previous part that the next one sees |

### Models

![Every model file with its download](../images/wf2-studio-models.jpg)

Every file H3 Director uses, grouped (H3, Turbo, Control, Pictures, Sound): found with its file name, or missing, and
always with its download link and size. Below it the files for place pictures (SAM3, Qwen Image 2.1) can be chosen when
yours are renamed. All links are also in chapter 2.

### Manual prompt

Replaces the prompt of **every** render part. Leave it empty unless you write the whole H3 prompt yourself.

## Prompts per render part

![Prompts per render part](../images/wf2-studio-prompts.jpg)

| Field | What it does |
|---|---|
| Badge | where the part's prompt comes from: compiled, AI-written, edited, manual, or *own prompt outdated* |
| **Write with AI / Write all parts with AI** | the AI writes the part out in full; timing, names and spoken lines stay the planner's |
| **Edit / Save / Reset** | write the part yourself, store it, or go back to the compiled prompt |
| Notes | the planner's warnings for this part |
