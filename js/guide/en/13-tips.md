# Tips and problems

## Writing shots

- **Framing, action, camera** — in this order, one camera sentence per shot. Without it H3 chooses its own camera and
  may cut away or zoom in.
- Say **in which direction** someone moves: *climbs up the stairs, facing the steps ahead of him*. "Climbs the stairs"
  alone came out as walking backwards.
- Describe **only what is seen**. "Remembering her lost master" can make H3 show that master.
- A new action needs about **two seconds** after a shot starts; shots under 3 s often show only the beginning.
- A change of view is a **new shot**. A long shot can be written in time beats: `0–4s: … 4–8s: …`.
- If a take is not right, try another **seed** (Settings → Sampling) before rewriting.

## Problems and what helps

| You see | What helps |
|---|---|
| A model loader is red, *file not found* | download the file (chapter 2) or choose your own file in the loader |
| *Turbo needs a turbo LoRA* | choose the LoRA in **Settings → Turbo**, or switch Turbo off |
| Out of memory | **Render part: 5 s**, the int8 video VAE, or **Resolution: Fast** |
| A white veil over the video (References turbo) | 6 steps instead of 4 — the known LoRA sets it by itself |
| The same figure appears twice | a second picture of a figure needs **Belongs to** that figure |
| A figure looks different later in a long video | use **References** mode; give the figure a character sheet (picture editor) |
| A spoken line is missing or cut off | give the shot more time, or split the line |
| The voice sounds wrong | use a clean voice sample, 3–10 s, no music |
| A song gets dull or the lips are off | **Use as: Lock** for the song; time the lyrics with Whisper |
| A visible jump at a join | **Transition: Continue picture and sound**; the planner places joins away from new actions |
| A room looks different when you come back | **Place: Like Shot N** in the later shot (chapter *Pictures*) |
| *needs a connected Video card with Use as: Control video* | connect the card to the Connector and set it to *Control video* |
| *has no video yet* | choose or upload a video on that card |
| ComfyUI crashed during a render | queue the same project again: finished parts are loaded (**Resume**) |
| The AI buttons are grey | connect an **H3 AI Loader** (chapter *Writing with the AI*) |
| The AI describes things that are not in the picture | the model cannot really see pictures; try `qwen3.5:9b` |

## Times (16 GB card, 1280×704, Turbo on)

| Job | About |
|---|---|
| 15 s text to video | 15–20 minutes |
| One picture (Pictures output) | 30–45 seconds |
| Character sheet | 4 minutes |
| 10 s with a control video (pose or inpaint) | 35–45 minutes |
| Pose or SAM3 mask of a 20 s video (once) | 5–6 minutes |

Longer videos take longer in proportion; try 15–30 s first, then make the whole length.

## Where things are saved

| What | Folder |
|---|---|
| Finished videos and pictures | `output/H3/` |
| Pictures for later use | `input/h3-director-stills` |
| Control videos and masks | `input/h3-control` |
| Storyboard pictures | `input/h3-storyboard` |
| Finished render parts (Resume) | `output/h3-director-resume` |
| Card presets | `user/default/minimax_h3_ng/contexts` |

## The guide node

The **H3 Guide** does nothing when the workflow runs. Delete it when you no longer need it, or add it to any workflow
(*MiniMax H3 → NG → H3 Guide*) and choose a chapter.

## Help from an AI agent

An AI agent (Claude, ChatGPT, …) with access to your computer can install the pack, check your models and find what went
wrong: point it at `SKILL.md` in the node pack's folder. It lists the installation, the models, the example workflows and
the usual problems with their fixes.
