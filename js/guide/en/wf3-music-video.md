# Workflow 3 · Music video

A singer from your picture sings your song. The song stays exactly as it is (it is *locked*); H3 makes the picture and
the lip movement to it. The example has three shots of ten seconds.

![The whole workflow](../images/wf3-overview.jpg)

**What you need:** a picture of the singer and the song as an audio file (mp3, wav, flac).
The example opens with `h3-example-hero.jpg` and the song `h3-example-song.mp3`; choose your own files in the cards.

**The steps in short**

1. Put the picture into the **Image** card and the song into the **Audio** card.
2. Adjust the **Look** text card to the style you want.
3. In the Director press **= Song** next to *Duration* to make the video as long as the song, or keep 30 s for a test.
4. Press **Generate**.

## 1 · Models

![The model loaders](../images/wf3-models.jpg)

The same six loaders as in every workflow (see Workflow 1). A song with a singer uses the **References** model.

## 2 · Content

### The singer: Image card

![The singer](../images/wf3-card-image.jpg)

*Use as: Reference*. Describe the singer in **Description** (face, hair, outfit). For several views of the same singer
(side, back) add more Image cards and set **Belongs to** to the first one.

### The song: Audio card

![The song](../images/wf3-card-audio.jpg)

- **What is in it**: *Music*. **Use as: Lock** — the song is kept exactly, in every render part, without getting dull.
- **Whose voice**: the singer. The Director then knows whose lips move.
- **Lyrics** (optional): paste the lyrics, one sung line per row. **Time with Whisper** finds when each line is sung;
  the Director then writes each line into the part where it is heard.
- The range above the waveform is the part of the file that is used.

### The style: Text card

![The look](../images/wf3-card-text.jpg)

A **Text** card with *Use as: Style / direction* is added to every render part: colours, light, kind of film. The
**Quick insert** buttons on the right add common lines.

## 3 · H3 Director

![H3 Director](../images/wf3-director.jpg)

- **Mode: References** — the singer's picture and the song are references.
- **Content** shows the Look, the Singer and the Song.
- **Duration**: **= Song** sets the length of the song.

![A shot](../images/wf3-studio-shot.jpg)

Every shot names the singer with `@Singer` and says how the camera moves. A change of view (profile, three-quarter,
over the shoulder) is a new shot; the Director keeps the song running across the cut.

### What goes to H3

![Prompts per render part](../images/wf3-studio-prompts.jpg)

**Prompts per render part** shows for each part the sung lines it contains and the planner's notes.

## 4 · Render and save

The same as in Workflow 1: **H3 Render Sequence** → **Save Video** in `output/H3/`.

## Tips

- A whole song (3 minutes) takes several hours at 1280×704; try 30 s first.
- If the picture shows the singer from behind, she cannot sing visibly there — plan the shots so the face is seen when
  the important lines come.
- Words in a shot text such as "remembering her lost master" can make H3 show that person. Describe only what should be
  seen.
