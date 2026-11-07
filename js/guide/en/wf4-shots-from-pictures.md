# Workflow 4 · Shots from pictures

Every shot starts exactly on one of your pictures and comes to life from there. This is **First / last frame** mode
(FL2VA): the picture is the first frame of the shot, not a reference.

![The whole workflow](../images/wf4-overview.jpg)

**What you need:** one picture per shot, all in the same format. The example's Resolution is *From first picture*: the
video takes the pictures' shape (here portrait, 768×1152).
The example opens with three views of the same figure (`h3-example-hero-side/front/back.jpg`).

**The steps in short**

1. Put one picture into each Image card (*Opening 1, 2, 3*).
2. In the Director write for each shot what happens *after* its picture.
3. Press **Generate**.

## 1 · Models

![The model loaders](../images/wf4-models.jpg)

The same six loaders as in every workflow. This mode uses the **First / last frame** model.

## 2 · Content: the pictures

![An opening picture](../images/wf4-card-image.jpg)

Each card is set to **Use as: First frame**. A picture that does not fit the video's format is fitted by **Fit
pictures** in the Settings (*Crop* by default). Crop cuts from the middle: a portrait picture in a landscape video loses
its top and bottom — the head may be cut off. Keep pictures and video in the same shape, or choose *Pad*.

## 3 · H3 Director

![H3 Director](../images/wf4-director.jpg)

**Mode: First / last frame**. Each shot has its own picture.

![Shot 2 and its picture](../images/wf4-studio-shot.jpg)

- **Content in this shot**: *Opening 2 — First frame*. Drag a card from **Content** onto a shot to bind it; the role
  (First frame, Last frame, Reference …) can be changed per shot.
- **What happens?**: only what happens after the picture, and how the camera moves.

How the Director renders it: a shot that opens on its own picture starts a render part of its own, so the picture lands
exactly on the first frame. Inside a long shot the next part continues the running take and gets the opening picture as a
reference for faces and clothes, so the look stays the same.

## 4 · Render and save

**H3 Render Sequence** → **Save Video** in `output/H3/`.

## Tips

- Pictures of the same scene in the same light give smooth shot changes.
- A **Last frame** picture on a shot makes the shot end on it.
- Pictures that should only show who someone is (not a frame) belong in Workflow 2 (References).
