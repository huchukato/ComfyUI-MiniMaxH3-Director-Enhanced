# Voices, dialogue and songs

H3 makes picture and sound together. Without any sound file it still makes sound: steps, wind, voices. Sound files and
spoken lines tell it more.

## Spoken lines

![A shot with a spoken line](../images/wf2-studio-shot.jpg)

In a shot, **+ Spoken line** adds a line that is said **word for word**:

- **Speaker**: a figure (a card), or *Narrator* for a voice without a picture.
- **Language**: the language the line is spoken in.
- **Delivery**: *says*, *sings*, *whispers*, *shouts* or *murmurs*. A sung line needs *sings*.
- Several lines in one shot are said in their order. Short lines (one sentence per 2–3 seconds) come out best.

## A voice for a figure

Put a short sound file of the voice (3–10 s of clean speech, no music) into an **Audio** card:

- **Use as: Voice**, **Whose voice**: the figure. Every line of that figure uses this voice (References mode).

## Sounds on audio lanes

Drag an Audio card onto an **audio lane** in the timeline. A clip on a lane plays on its own time, across shots and render
parts. Click the clip to choose how H3 uses it:

| Role | What happens |
|---|---|
| **Lock exactly** | the sound is kept exactly as it is; H3 makes the picture to it (songs, a finished sound track) |
| **Copy as closely as possible** | H3 is asked to reuse the sound; it may change |
| **Reference only** | only mood, voice and style |

**From second in file** chooses where in the file the clip starts. In First / last frame mode a clip can only be locked.

## Songs

![The song card](../images/wf3-card-audio.jpg)

1. Audio card: **What is in it: Music**, **Use as: Lock**, **Whose voice**: the singer.
2. The button with the card's name next to *Duration* (e.g. **= Song**) makes the video as long as the song.
3. **Lyrics** (optional): one sung line per row. **⟳ Time with Whisper** finds when each line is sung (it needs the Whisper
   model, chapter 2); **Stamp line** sets the selected line's time by ear while the song plays. Each render part then gets
   only the lines sung in it, so the lips match.

A locked song stays exact in every render part: when the parts are put together, the original sound is laid back over
the locked span, so it does not get dull at the joins.

## Ambience and music

In **Settings → Sound, style and transitions**:

- **Ambience**: the background sound of every part, e.g. *Footsteps on cobblestones, distant voices*.
- **Music**: background music in words, or *N/A* for none.
- **Transition between render parts**: *Continue picture and sound* (default) carries about a second of sound into the
  next part, so it runs on without a break.

## Tips

- A spoken line that H3 does not say is often too long for its shot: give it more time or split it.
- Music or noise in a voice sample changes the voice.
- Words in quotes in the Prompt are kept as they are when the AI writes the shots.
