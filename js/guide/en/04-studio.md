# The Studio: shots and timeline

The H3 Director node **is** the Studio: everything is edited inside the node and saved with the workflow.

![H3 Director](../images/wf2-director.jpg)

## Header

- **Full screen** lifts the Studio over the whole window; **Esc** or **Back to graph** puts it back.
- **AI connected** shows that an H3 AI Loader is ready (chapter *Writing with the AI*).
- **Show prompts** opens *Prompts per render part* at the bottom.
- The **gear** opens the Settings (chapter *Settings*).
- **Generate** queues the workflow, the same as ComfyUI's Run.

## Prompt, Look and Content

- **Prompt**: what the video is about. Without shots the Prompt alone is enough for a text video.
- **Look**: what every render part shares — style, place, light.
- **Make H3 prompt**, **AI: split into shots** and **Whole prompt = one shot** turn the Prompt into shots (the first two
  need the AI).
- **Content**: one card per Context node on the Connector, plus a plain **Text-Shot**. Drag a card onto the empty
  timeline to make a shot with it, onto a shot to use it there, or an audio card onto an audio lane. Cards the current mode
  cannot use are dimmed.

## Timeline

All lanes share one time axis on a 0.1 s grid. **−** / **+** zoom, **Fit project** shows everything; the arrows are Undo
and Redo.

- **Shots**: drag a shot to move it, drag its edges to change start or end, drop it on another shot to change the order.
  **+ Shot** adds a 4 s shot after the selected one.
- **Audio lanes**: a sound on a lane runs on its own, across shots and render parts (a song is not restarted per shot).
  **+ Audio lane** adds one; move and trim the clip with the mouse.
- **Control**: control videos and masks (Workflows 7 and 8).
- **Render parts**: how the Director cuts the video into H3 runs, each in its own colour. You do not edit them; they follow
  the shots, the duration and the render-part length in the Settings.

## The right side

**Output** (*Video* or *Pictures*), **Mode** (chapter *References or first frames*) and **Turbo**. Below it the selected
item:

![A selected shot](../images/wf2-studio-shot.jpg)

- **A shot**: start and end, **What happens?** (the action and the camera, `@Name` for a card), **Content in this shot**
  with the role of each card, and the **Spoken** lines. **AI: improve text** suggests a better shot text. **Place**
  reuses the place of an earlier shot (chapter *Pictures*); **Effect** adds an official H3 camera effect such as *Bullet
  time*, when its files are installed.
- **An audio clip**: its time on the story, **From second in file** and how H3 uses it (*Lock*, *Copy*, *Reference*,
  chapter *Voices, dialogue and songs*).
- **A control clip**: its time and offset in the file.

## Bottom

**Duration** in seconds (a button such as **= Song** takes the length of that audio card), **Resolution** (*Native*, *Fast*, *Above native*,
*From first picture* or a custom size) and **Settings**. On the right a summary: length, shots, render parts, size, mode
and steps.

## Prompts per render part

![Prompts per render part](../images/wf2-studio-prompts.jpg)

Exactly the prompt each render part sends to H3, in the part's colour, with the planner's notes. A badge says where it
comes from: compiled, AI-written, edited or manual.

- **Write with AI** / **Write all parts with AI** lets the AI write the part out in full; the timing, the names and the
  spoken lines stay the planner's.
- **Edit** writes the part yourself; **Reset** returns to the compiled prompt.
- When the shots of a part change later, its own prompt is marked *outdated* and the compiled one is used again.

## How to write a shot

- Start with the framing (*Medium shot*, *Close-up from below*), then the action, then **one sentence for the camera**
  (*The camera tracks beside her*, *Static shot*). Without a camera sentence H3 chooses its own and may cut away.
- Say clearly in which direction someone moves.
- A shot longer than 5 s can be written in time beats: `0–4s: … 4–8s: …`.
- A new action needs about two seconds after a shot starts.
- A change of view is a new shot; the Director adds the cut.
