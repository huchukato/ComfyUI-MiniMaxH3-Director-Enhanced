# 1 · Start here

The **H3 Director** makes videos of any length with MiniMax H3: you plan shots on a timeline, the Director cuts the video
into render parts of about ten seconds, renders them one after another and joins them into one video with sound. Picture
and sound continue across every join.

![A complete workflow](../images/wf2-overview.jpg)

## How a workflow is built

Every workflow has the same chain, from left to right:

| Step | Nodes | What they do |
|---|---|---|
| 1 · Models | six ComfyUI loaders | load the two H3 models, the text encoder, the video, audio and preview VAE |
| 2 · Content | H3 Context Image / Video / Audio / Text | your pictures, videos, sounds and notes, each as a card with a name |
| 3 · Director | H3 Context Connector, H3 AI Loader, **H3 Director** | collect everything; plan the shots in the Studio |
| 4 · Render | H3 Render Sequence → Save Video | render all parts and save the video |

The **H3 Guide** (this node) does nothing when the workflow runs; you can delete it.

## Which workflow first?

| You want … | Open |
|---|---|
| a video from text alone | Workflow 1 · Text to video |
| your own character and voice | Workflow 2 · Characters and voice |
| a singer to your song | Workflow 3 · Music video |
| shots that start on your pictures | Workflow 4 · Shots from pictures |
| pictures instead of a video | Workflow 5 · Pictures |
| to plan with a storyboard sheet | Workflow 6 · Storyboard |
| movement from another video | Workflow 7 · Control video |
| to replace a person in footage | Workflow 8 · Inpaint |
| your own sampler nodes | Workflow 9 · Custom sampling (advanced) |

The workflows are in ComfyUI under **Templates** (or in the folder `example_workflows` of this node pack). Each one
opens with its chapter of this guide.

## Your first video

1. Open **Workflow 1 · Text to video**. Missing model files are offered for download (chapter 2).
2. Press **Generate** in the Director.
3. The video lands in `ComfyUI/output/H3/`.

Then change the shots, or go on with Workflow 2 for your own character.

## Words used in this guide

- **Shot**: one piece of the story on the timeline, with its own text (what happens, the camera).
- **Render part**: one H3 run of about 10 s. The Director plans them by itself; you see them under the timeline.
- **Card**: a Context node with one picture, video, sound or text. Its name is used as `@Name` in shots.
- **Mode**: *References* (Ref2VA, your pictures and voices as references) or *First / last frame* (FL2VA, shots start or
  end on your pictures). See chapter *References or first frames*.
- **Turbo**: renders with a turbo LoRA in 6–8 steps instead of 20, about three times faster.
