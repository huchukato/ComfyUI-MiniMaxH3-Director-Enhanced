# Content cards

Every picture, video, sound and note is a **card**: an H3 Context node connected to the Context Connector. The card says
**what** the material is and **who** it belongs to; **when** it plays is set in the Studio.

## What every card has

- **Name** (top left): used as `@Name` in the shots. Renaming a card renames its mentions too.
- **File** with **Upload**, or drop a file onto the card. Files come from ComfyUI's `input` folder.
- **What is in it** and **✦ Analyze**: the AI suggests the content, the role and a description; nothing changes until you
  press **Accept**.
- **Use as (default)**: the card's role, unless a shot in the Studio gives it another one. The hint below warns when a
  role does nothing in the Director's mode.
- **Description**: one sentence of what is seen or heard. H3 reads it with the medium.
- Where a card is used shows in the Director's shots and lanes. A card that no shot uses is part of every render part.
- **Preset** (save and load the card's settings) and **Color**.

## Image

![H3 Context Image](../images/wf2-card-image.jpg)

| Use as | What it does |
|---|---|
| Reference | keeps the figure, outfit or place recognizable (References mode) |
| First frame / Last frame | the shot (or the video) starts or ends on this picture |
| Keyframe | the picture is reached at a time inside a shot (set the time in the Studio) |
| Storyboard | a storyboard sheet that plans the shots (References mode) |

- **Keep in the video**: how strictly H3 keeps identity, outfit, pose and background. It guides H3; it is not pixel-exact.
- **Belongs to**: a second picture of the same figure (side, back, an outfit) belongs to the first one; otherwise H3 sees
  two people.
- The **pencil** opens the picture editor (chapter *Pictures and the picture editor*).

## Video

![H3 Context Video](../images/wf7-card-video.jpg)

| Use as | What it does |
|---|---|
| Motion reference | H3 copies the kind of movement |
| Camera reference | H3 copies the camera movement |
| Continue from video | the new video continues the end of this one (its last frames are hidden context) |
| Whole structure | movement, camera and rhythm together |
| Control video | pose, edges, depth or a mask steer the picture exactly (Workflows 7 and 8) |

**Part of the file to use**: drag across the strip. **Its own sound**: send the video's sound along or ignore it.

## Audio

![H3 Context Audio](../images/wf2-card-audio.jpg)

| Use as | What it does |
|---|---|
| Voice | the voice of a figure (choose it in **Whose voice**) |
| Copy | H3 is asked to reuse the sound as closely as it can |
| Lock | the sound is kept exactly (songs) |
| Music style / Rhythm / Sound reference | mood and style only |

The range above the waveform is the part that is used. **Listen here** only changes playback in the browser. **Lyrics**:
see chapter *Voices, dialogue and songs*.

## Text

![H3 Context Text](../images/wf3-card-text.jpg)

A note in any language. **Scene / story** is read like the Prompt; every other role (*Style / direction*, *Rule*,
*Character*, *World lore*, *Camera rule*, *Dialogue rule*, *Constraint*, *General*) goes into every render part. **Quick
insert** adds common lines.

## Several cards, one file

One file can be used by several cards, each with its own name, range and role — for example the same song once as
*Lock* for the sound and once as *Music style*.
