# References or first frames

H3 has two models. The **Mode** in the Director chooses which one renders the project.

| Mode | H3 model | Your pictures are … | Good for |
|---|---|---|---|
| **References** (Ref2VA) | `minimax_h3_ref2va` | references: who is seen, what they wear, where | characters, voices, songs, several figures |
| **First / last frame** (FL2VA) | `minimax_h3_fl2va` | the exact first or last frame of a shot | shots from your pictures, text-only videos |

## References

![References mode](../images/wf2-director.jpg)

- Pictures, videos and voices are references. A figure stays recognizable in every shot, from any angle the shot asks for.
- Up to several figures, outfits, places and a voice per figure.
- A **First frame** picture still works here, as a timed guide; it is close to the picture, not pixel-exact.
- A **Storyboard** card plans the shots (Workflow 6).

## First / last frame

![First / last frame mode](../images/wf4-director.jpg)

- A shot with a **First frame** picture starts exactly on it; a **Last frame** picture ends it.
- A **Keyframe** is reached at its time inside a shot: the Director ends a render part on it and the next part continues
  from there. It moves by up to a third of a second to H3's frame grid.
- A **Reference** picture stays a reference next to the frames: it keeps the face and clothes the first frame does not
  show.
- Without any picture (text only) the Director uses this model.
- Sound can only be locked here, not copied or used as a voice.

## Automatic

Older workflows may show *Automatic*. Then the Director decides by the cards: a Reference picture or a voice chooses
References, otherwise First / last frame. Set the mode yourself when you know what you want.

## Which one?

- Your character should **look the same** in different places → **References**.
- A shot should **start exactly** on a picture you made → **First / last frame**.
- Both in one video: make the pictures in **Pictures** output first (Workflow 5), then use them as first frames.
