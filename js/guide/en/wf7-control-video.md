# Workflow 7 · Control video (pose, canny, depth)

Your character moves like the person in another video. A **control video** (pose skeletons, edges or depth) steers the
movement through the official H3 ControlNet; your Image card decides who is seen.

![The whole workflow](../images/wf7-overview.jpg)

**What you need:** a picture of your character and a video with the movement (a person walking, dancing …).
The example opens with `h3-example-hero.jpg`, the walk `h3-example-walk.mp4` and its pose video `h3-example-walk-pose.mp4`, so it renders without converting first.

**The steps in short**

1. Put your character into the **Image** card and the movement video into the **Video** card (*Motion*).
2. In the Video card choose **Pose**, **Canny** or **Depth** and press **Generate** (once).
3. The clip is already on the Director's **Control** lane; adjust its length if needed.
4. Press **Generate** in the Director.

## 1 · Models and the ControlNet

![The model loaders](../images/wf7-models.jpg)

Next to the six usual loaders the green **ControlNet (model patch)** loader loads the official H3 ControlNet:

![ControlNet loader](../images/wf7-patch.jpg)

| File | Folder |
|---|---|
| `minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors` | `models/model_patches` |

It is connected to the Connector's **model_patch** input.

## 2 · The control video card

![Video card as control video](../images/wf7-card-video.jpg)

- **Use as: Control video**.
- **Control video**: *Pose* (skeletons of the person), *Canny* (edges) or *Depth*. **Generate Pose / Canny / Depth** runs
  once through ComfyUI's queue (Pose took about 5 minutes for the 20 s example walk) and saves the result in
  `input/h3-control`; rendering reuses that file. A ready control video can also be chosen directly.
- **Part of the file to use**: drag across the strip to use only a part of the video.

Extra models for the conversion (the gear of the card shows what was found):

| Kind | Needs |
|---|---|
| Canny | nothing extra |
| Pose | `rt_detr_v4-x-hgnet_fp16.safetensors` (`models/diffusion_models`) and `sdpose_wholebody_fp16.safetensors` (`models/checkpoints`) |
| Depth | `moge_2_vitl_normal_fp16.safetensors` (`models/geometry_estimation`) |

## 3 · H3 Director

![H3 Director with the control lane](../images/wf7-director.jpg)

The **Control** lane under the shots holds the control clip (*Motion · pose · 0–10 s*). Drag a Video card with *Control
video* onto the lane to add one; move or trim clips with the mouse. Control works in **both modes**.

![ControlNet strength in the settings](../images/wf7-studio-settings.jpg)

In **Settings → ControlNet**: **Strength** 1 follows the source closely; 0.5 keeps more of your figure's own shape.
**Denoising range** (advanced) is a share of the sampling steps, not of video time.

## Tips

- ControlNet works on whole render parts. If a clip covers only part of a render part, its first or last frame is held to
  the edges; the Studio warns about it. Let clips cover whole parts, or make the parts shorter.
- The figure in the control video and yours should have a similar build; strength 0.5–0.7 helps when they differ.
