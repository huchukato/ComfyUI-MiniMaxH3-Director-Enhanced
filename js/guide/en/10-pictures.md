# Pictures and the picture editor

## Pictures output

**Output: Pictures** in the Director makes one picture per shot instead of a video (Workflow 5). The pictures are saved to
`output/H3/` and copied to `input/h3-director-stills`, so every Image card can choose them — for example as the first frame
of a video shot.

![Pictures output](../images/wf5-director.jpg)

- A shot with only text is text-to-image.
- Cards on a shot are references: a character, an outfit, a place and a pose can be put together in one picture.
- A **First frame** picture on a shot is changed as the shot says and otherwise kept.

## The picture editor

The **pencil** on an Image card opens the editor in a window over the graph. It has three tabs; every result can be added
as a **new card** (connected to the Connector for you).

![The Image card](../images/wf2-card-image.jpg)

### Mask

Paint with **Brush** and **Eraser** what may change, or write what to find (e.g. `mug`) and press **Find with SAM 3.1**.
**Save mask** stores it on the card: white changes, the rest stays. Used by the **Pictures** output: only the masked area
of a First frame picture is redrawn. Needs SAM3 for *Find* (chapter 2).

### Structure

**Pose**, **Edges (Canny)** or **Depth** of this picture, as a new card. Put it on a shot of the Pictures output and the new
picture takes over the pose or layout; it is never drawn itself. Pose and Depth need their models (chapter 2).

### Sheet

- **Make character sheet**: H3 circles the figure once and keeps six views — front, left, back, right, three-quarter and
  the face. About 4 minutes with the References turbo LoRA. **Use as this card's picture** or **Add as new card**.
- **Make place sheet**: H3 turns once inside the place and keeps six views all around. About 9 minutes.

A sheet helps H3 keep a figure the same from every side; put it on the figure's card, or add it as a card that **Belongs
to** the figure.

## Place like an earlier shot

In a shot's panel, **Place** can be set to *Like Shot 1* (any earlier shot). The Director then takes a picture of that
shot's place from its own render and gives it to the later shot as a place reference, so a room you come back to looks the
same.

| Picture | What it is |
|---|---|
| **Without people** (default) | the frame with the least person in it; if someone is still there, Qwen Image 2.1 paints them out |
| **As rendered (1 s in)** | the frame one second into the earlier shot |
| **From another view …** | Qwen paints the place from the camera you write, e.g. *from the bar toward the door* |

Such a shot starts a render part of its own (a cut), because the picture exists only once the earlier shot is rendered.
*Without people* and *From another view* need SAM3 and Qwen Image 2.1 (Settings → Models).
