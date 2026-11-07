# Workflow 9 · Custom sampling (advanced)

The same lighthouse video as Workflow 1, but instead of **H3 Render Sequence** you see the sampling itself: ComfyUI's own
loop runs once per render part, with ordinary sampler nodes you can change or extend.

![The whole workflow](../images/wf9-overview.jpg)

Use it when you want your own sampler, a second sampling stage, a different guider or your own preview. For everything
else the Render Sequence of the other workflows is simpler and does the same.

## 1 · Models and Director

![H3 Director](../images/wf9-director.jpg)

The six loaders, the Connector and the Director are the same as in Workflow 1. The Director has two outputs: **result**
(the whole plan) and **chunks** (the list of render parts).

## 2 · Your own sampler: one pass per render part

![The sampling loop](../images/wf9-group-loop.jpg)

| Node | What it does |
|---|---|
| **Start Loop** (List) | takes the Director's **chunks** and runs the body once per render part; *list_item* is the current part, *current_iteration_value* the latent of the part before |
| **H3 Director Output** | prepares the current part: MODEL (with the turbo LoRA when Turbo is on), positive and negative conditioning, the empty AV latent, the **seed**, and the Director's **cfg**, **sampler** and **sigmas** |
| **H3 Live Preview** | puts the live preview (taeh3) on the model, so you see each part while it is sampled |
| **RandomNoise** | noise from Output's seed (the Director's seed plus the part's number) |
| **CFGGuider** | the guider; cfg comes from Output and is always 1 for H3 |
| **SamplerCustomAdvanced** | samples the part with Output's sampler and sigmas |
| **End Loop** | collects every part's finished latent (*accumulate* on) and hands it to the next part, which continues from its end |

Rules for your own changes:

- Keep everything that uses Output's values **inside** the loop. A link from inside the loop to a node outside it is
  refused by ComfyUI ("loop boundary").
- Return the **complete** audio-video latent of each part to both inputs of End Loop; the next part needs it to
  continue picture and sound.
- With two sampling stages (SplitSigmas), give the second stage the first stage's output and DisableNoise; use Output's
  model in both. A locked song stays locked in every stage.

## 3 · Output: put the parts together and save

![Collect and save](../images/wf9-group-output.jpg)

- **NG Collect** decodes all parts with the video and audio VAE, removes the overlap each part repeated from the one
  before and joins picture and sound. Its **fps** output (24) goes to CreateVideo.
- **CreateVideo** → **Save Video** writes `output/H3/custom_sampling_00001_.mp4`.

For a long video (a whole song) use **NG Collect Video** instead of NG Collect: it writes the file part by part and
needs far less memory.

## Tips

- The Director's Steps, Sampler and Scheduler (or the turbo LoRA's) arrive through Output; change them in the Studio,
  not in the sampler nodes.
- Resume after a crash is a feature of the Render Sequence; this loop renders every part again.
