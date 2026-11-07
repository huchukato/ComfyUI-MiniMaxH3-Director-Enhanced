# Workflow 1 · Text to video

Your first video from text alone: three shots of a lighthouse at dusk, 15 seconds with sound and one spoken line. No
pictures or sound files are needed.

![The whole workflow](../images/wf1-overview.jpg)

**The steps in short**

1. Load the models once (blue, yellow, red and purple nodes on the left).
2. Read the three shots in the **H3 Director**, change them if you like.
3. Press **Generate** in the Director (or ComfyUI's Run).
4. The video is saved by **Save Video** in `output/H3/`.

On a 16 GB card the 15 seconds take about 15–20 minutes with Turbo on.

## 1 · Models

![The model loaders](../images/wf1-models.jpg)

| Node | File | Folder |
|---|---|---|
| Model: First / last frame | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` |
| Model: References | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (type `minimax`) | `models/text_encoders` |
| Video VAE | `minimax_h3_video_vae_fp16.safetensors` | `models/vae` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | `models/vae` |
| Preview VAE | `taeh3.safetensors` | `models/vae_approx` |

A text-only project uses the **First / last frame** model; the References model is only loaded when a project uses
character pictures or voices. Missing files are offered for download when you open the workflow.

## 2 · H3 Context Connector and H3 AI Loader

![H3 Context Connector](../images/wf1-connector.jpg)

The **Connector** passes the models and the content on to the Director. This workflow has no content cards; text alone
works. The **preview VAE** shows each render part while it is made.

![H3 AI Loader](../images/wf1-ai-loader.jpg)

The **AI Loader** is optional. With an AI model (for example Qwen through Ollama) the Director can write shots from your
prompt (**AI: split into shots**) or improve a shot's text (**AI: improve text**). Without it, write the shots yourself.

## 3 · H3 Director

![H3 Director](../images/wf1-director.jpg)

- **Prompt**: what the video is about. **Look**: the style every part shares.
- **Mode**: *Automatic → First / last frame* — with text only the Director picks FL2VA by itself.
- **Turbo on**: renders with the official turbo LoRA in 8 steps instead of 20.
- **Timeline**: three shots of five seconds. **Render parts** below shows that the Director renders the 15 seconds in two
  parts that continue into each other; you see only one video.

### A shot

![Shot 2 selected](../images/wf1-studio-shot.jpg)

Click a shot to edit it on the right.

- **What happens?** Describe the picture, the action and the camera in one or two sentences: *Medium shot from below: an
  old lighthouse keeper … climbs up the spiral stairs step by step, facing the steps ahead of him … The camera follows him
  upward.* Say clearly in which direction a figure moves; "climbs the stairs" alone can come out as walking backwards.
- **Spoken**: the line is said word for word. *Narrator* speaks without a picture of the speaker.
- **In:** at the bottom shows in which render parts the shot lies.

## 4 · H3 Render Sequence and Save Video

![H3 Render Sequence](../images/wf1-render.jpg)

Renders the parts one after another and puts them together into one video with sound.

![Save Video](../images/wf1-save.jpg)

The finished video: `ComfyUI/output/H3/text_to_video_00001_.mp4`.

## Tips

- One camera sentence per shot keeps H3 from choosing its own camera.
- A new action needs about two seconds after a shot starts; very short shots (under 3 s) often show only the beginning.
- Longer videos: set **Duration** at the bottom of the Director and add shots; the Director plans the render parts.
