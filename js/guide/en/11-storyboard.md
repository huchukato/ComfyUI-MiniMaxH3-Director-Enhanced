# Storyboard

**H3 Storyboard** lays out a storyboard sheet in the node: a title line with your characters, then 1–9 numbered panels,
each with its time, title, caption and the shot text for H3. Workflow 6 walks through an example; this chapter lists
everything the node can do.

![The example sheet](../images/wf6-sheet.jpg)

## Wiring

One cable: the Context Connector's **H3 context** output (the one that goes to the Director) into the Storyboard's
**H3 context** input. Through it the Storyboard sees your picture cards, the AI and the Director. It hands the Director
nothing by cable; its buttons write into the Director. Its outputs are optional: **sheet** (the sheet as drawn),
**panels** (each panel's picture) and **shots** (the panels as the Director's shots). Left unconnected, the node does not
run with the workflow.

## The board

| Field | What it does |
|---|---|
| **Panels** | 1–9 panels in a grid |
| **Panel format** | 16:9, 9:16, 1:1, 4:3, 3:4, 21:9 — the shape of the video |
| **Gear** | the models the storyboard uses, found or missing, with downloads |
| **Undo / Redo** | every change on the board |
| **Title / Subtitle** | the sheet's title line; your character cards appear under it |
| **What should happen** | the story in a few sentences, for the AI |
| **AI: write panel texts** | the AI writes the sheet's title and every panel's title, caption and shot text; times stay |
| **Redraw all panels** | every panel's collage redrawn with Qwen Image 2.1 |

## A panel

| Field | What it does |
|---|---|
| **Seconds** | the panel's length; panels follow each other (5 s, 5 s … are 0–5, 5–10 …) |
| **Title** | the title on the sheet |
| **+ Picture** | a picture from your cards, from this storyboard, the input folder (search) or **Upload…** |
| **+ Text / + Colour** | a text layer or a colour area |
| **+ Figure from a sheet** | Qwen Image 2.1 draws a character card's figure in the pose you write, without background (about 30 s) |
| **+ Background** | Qwen Image 2.1 draws an empty place in the panel's format (about 20 s) |
| **Redraw with Qwen Image 2.1** | the panel's collage painted as one finished picture, a new layer on top (about a minute) |
| **First frame / Last frame of its shot** | *Send to Director* uses the panel's picture as that frame of its shot |
| **Caption on the sheet** | the line under the panel |
| **Shot text for H3** | what H3 renders: framing, action, camera; time beats for a long panel |

## Layers

| Action | How |
|---|---|
| Select | click it on the panel or in the list |
| Move | drag it on the panel |
| Size / turn | mouse wheel / **Shift** + mouse wheel, or the **Size** and **Rotation** sliders |
| **Opacity**, **Mirror**, **Centre** | in the layer's controls |
| **Cut out** | removes a picture's background (ComfyUI's Remove Background with BiRefNet); Undo brings it back |
| **Use on all panels** | copies the layer to every other panel at the same place |
| In front / behind | the arrows in the list |
| **Hide / Show**, remove | in the list |

Pictures dragged from a folder or from ComfyUI's queue land on the panel they are dropped on; several stand side by side.

## Into the Director

| Button | What it does |
|---|---|
| **Use in Director** | draws the sheet into `input/h3-storyboard` and adds a Context card with it (*Use as: Storyboard*) at the Connector |
| **Send to Director** | panels become shots (times and shot texts), the sheet goes on every shot, marked panels become first or last frames; sound lanes, Look and Prompt stay |
| **Sync from Director** | lengths and texts changed in the Director go back into the panels |

## Saving and reloading

The board is saved with the workflow. The drawn sheet is a PNG that carries the whole storyboard: drag it onto any H3
Storyboard and every panel, layer and text comes back (Undo goes back). Pictures you made are saved in
`input/h3-storyboard`.

## Models

| Feature | Needs (chapter 2) |
|---|---|
| + Figure from a sheet, + Background, Redraw | Qwen Image 2.1, its text encoder and VAE |
| Cut out | BiRefNet (`birefnet.safetensors`) |
| AI: write panel texts | an H3 AI Loader on the Connector |

Without them the storyboard still works with your own pictures and texts.

## Tips

- A storyboard plans shots in **References** mode.
- Characters look like themselves when they come from their sheets: use **+ Figure from a sheet** or cut-outs of the
  sheet, then **Redraw** the panel so light and style fit together.
- Write the side each character stands on into the shot text; H3 follows the text more than the picture.
- Four to six panels for 10–30 seconds.
