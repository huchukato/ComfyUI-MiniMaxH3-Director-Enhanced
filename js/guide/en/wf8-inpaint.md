# Workflow 8 · Inpaint: replace a figure

A person in your footage is replaced by your character; the rest of the video (the place, the light, the camera) stays. A **mask
video** marks the area to redraw: white is regenerated, black is taken from the footage.

![The whole workflow](../images/wf8-overview.jpg)

**What you need:** a picture of your character and the footage with the person to replace.
The example opens with `h3-example-hero.jpg`, the footage `h3-example-walk.mp4` and its mask `h3-example-walk-mask.mp4`.

**The steps in short**

1. Put your character into the **Image** card (*Hero*) and the footage into the **Video** card (*Footage*).
2. In the Video card type **What to mask** (e.g. `person`) and press **Generate mask (SAM3)** (once).
3. The clip is already on the Director's **Control** lane; adjust its length if needed.
4. Press **Generate** in the Director.

## 1 · Models and the ControlNet

![The model loaders](../images/wf8-models.jpg)

The same loaders as in Workflow 7, including the **ControlNet (model patch)** loader with
`minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors` on the Connector's **model_patch** input.

For the mask you also need **SAM3**: `sam3.1_multiplex_fp16.safetensors` in `models/checkpoints`. It is only used when
you press *Generate mask*; rendering does not load it.

## 2 · The footage card

![Video card with Inpaint](../images/wf8-card-video.jpg)

- **Use as: Control video**, **Control video: Inpaint (mask + source)**. The card's own video is the source.
- **What to mask**: what SAM3 should find, e.g. `person`, `woman in red`, `dog`. **Generate mask (SAM3)** saves a black
  and white mask video next to the source (about 6 minutes for the 20 s example walk). A ready mask video can also be
  chosen or uploaded.
- The preview shows the raw mask. The shape for rendering is chosen below it:
  - **Bounding box** (recommended): a box around the figure, so the new figure may be wider, taller or differently dressed.
  - **Silhouette**: only the outline of the found figure; for a very similar figure.
  - **Grow (pixels)**: widens the mask at the render size; 16 by default.
  Changing the shape or Grow does not run SAM3 again.
- Mask and source must start at the same time in the file. The card's range and the clip's offset apply to both; a
  shorter file holds its last frame.

## 3 · H3 Director

![H3 Director with the mask clip](../images/wf8-director.jpg)

- **Mode: References** — your character's picture is the reference for the new figure.
- The **Control** lane holds the clip *Footage · mask · 0–10 s*.
- The shot names the character: *@Hero turns around and walks away deep into the dark stone hall, exactly where the
  person in the footage walks …*. Describe the scene as it is in the footage, so the new figure fits into it.

## Tips

- Describe in the shot what the person in the footage does (walk, turn, sit down); the mask only says *where*.
- After changing the footage, generate or choose its matching mask again.
- If parts of the old person stay visible, raise **Grow** or switch to **Bounding box**.
- Inpaint and other control clips (pose, depth) can follow each other on the Control lane.
