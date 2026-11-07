# Workflow 5 · Pictures

The Director can make pictures instead of a video: **one picture per shot**. Good for stills of your character in
different places, for first frames of a later video, or to try a scene quickly.

![The whole workflow](../images/wf5-overview.jpg)

**The steps in short**

1. Put your character into the **Image** card (*Use as: Reference*; the example opens with `h3-example-hero.jpg`).
2. Write one shot per picture in the Director.
3. Press **Generate**. The pictures are saved by **Save Image**.

## 1 · Models

![The model loaders](../images/wf5-models.jpg)

The same six loaders as in every workflow.

## 2 · H3 Director with Output: Pictures

![H3 Director](../images/wf5-director.jpg)

- **Output: Pictures** — every shot becomes one picture. The timeline shows *Picture 1, 2, 3* instead of render parts.
- **Resolution** at the bottom: here 1344×768 (16:9). Pictures can be larger than video, up to about 3 megapixels.
- A shot with only text is text-to-image. Cards on a shot are references: a character, an outfit, a place and a pose
  drawing can be put together into one picture.
- A **First frame** picture on a shot is changed as the shot says and otherwise kept. With an edit mask on its card
  (pencil on the Image card → *Mask*) only the masked area changes.

## 3 · H3 Render Sequence and Save Image

![H3 Render Sequence](../images/wf5-render.jpg)

In Pictures mode the Render Sequence gives the pictures on its **images** output.

![Save Image](../images/wf5-save.jpg)

The pictures land in `output/H3/` and are also copied to `input/h3-director-stills`, so every Image card can use them.

## Tips

- With Turbo on a picture takes about 30–45 seconds (measured: 33 s at 3 megapixels, 42 s with four reference pictures).
- A picture you like can open a shot of a video: choose it in an Image card with *Use as: First frame* (Workflow 4).
