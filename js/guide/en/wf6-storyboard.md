# Workflow 6 · Storyboard

Plan the video as a storyboard sheet first, the way you would sketch it on paper: numbered panels, each with a picture,
a title, a caption and the shot text for H3. The example tells a 20-second story of two characters, **Luna** and
**Inferna**, who meet in a candle-lit hall, show each other their magic and seal a pact.

![The whole workflow](../images/wf6-overview.jpg)

This is the finished sheet of the example. Every panel was put together from a hall, Luna and Inferna as layers, then
redrawn by Qwen Image 2.1 into one picture:

![The example sheet](../images/wf6-sheet.jpg)

**The steps in short**

1. Put your characters into the **Image** cards (here a character sheet each).
2. In the **H3 Storyboard** fill the panels: pictures, title, caption, shot text — or let the AI write the texts.
3. Optional: **Redraw all panels** with Qwen Image 2.1.
4. Press **Use in Director** (the sheet becomes a card), then **Send to Director** (the panels become shots).
5. Press **Generate** in the Director.

The example opens with every step done; press **Generate** to render it.

## 1 · Models

![The model loaders](../images/wf6-models.jpg)

The same six loaders as in every workflow. Drawing with Qwen Image 2.1 and cutting out figures need extra models
(chapter 2); without them you place your own pictures.

## 2 · Content: two characters and the sheet

The **Luna** and **Inferna** cards hold a character sheet each (*Use as: Reference*). A sheet with front, side and back
keeps the figure the same from every angle. The third card is made by **Use in Director**: the drawn storyboard sheet,
*Use as: Storyboard*.

![The storyboard card](../images/wf6-card-image-storyboard.jpg)

## 3 · H3 Storyboard

The storyboard has its own group below the Director. It is wired by one cable: **H3 context** from the Connector.

![H3 Storyboard](../images/wf6-storyboard.jpg)

- **Top:** number of **Panels** (1–9), **Panel format** (16:9, 9:16, 1:1, 4:3, 3:4, 21:9), the gear (models), Undo /
  Redo and the three buttons to the Director.
- **Left:** **Title** and **Subtitle**, the sheet as it will be drawn (click a panel to edit it), and **What should
  happen** with **AI: write panel texts** and **Redraw all panels**.
- **Right:** the selected panel: **Seconds**, **Title**, its picture, the buttons to add layers, the layer list, the
  **Caption on the sheet** and the **Shot text for H3**.

### Pictures on a panel

![Adding a picture](../images/wf6-sb-picker.jpg)

**+ Picture** offers your Context cards, the pictures this storyboard already made (*From this storyboard*), every
picture of the input folder (with search) and **Upload…**. You can also drag picture files from a folder straight onto a
panel.

### Figures and backgrounds with Qwen Image 2.1

![Figure from a sheet](../images/wf6-sb-figure.jpg)

**+ Figure from a sheet** draws a character card's figure in the pose and camera angle you write, without background
(portrait, square or landscape, about 30 s).

![Background](../images/wf6-sb-background.jpg)

**+ Background** draws an empty place in the panel's format from your description of place, light and mood (about 20 s).
Both land on the panel and in *From this storyboard* for every other panel.

### Layers

![A selected layer](../images/wf6-sb-layer.jpg)

Click a layer on the panel or in the list. Drag it to move it; the mouse wheel sizes it, with **Shift** it turns. Below
the list: **Size**, **Rotation**, **Opacity**, **Mirror**, **Cut out** (removes the background), **Centre** and **Use on
all panels** (the same layer at the same place on every panel). The arrows put a layer in front or behind; **Hide**
keeps it but does not draw it.

### Redraw with Qwen Image 2.1

**Redraw with Qwen Image 2.1** (one panel) or **Redraw all panels** paints the collage anew as one finished picture: the
collage keeps the composition, the character cards the panel names are the references. The result is a new layer on
top; the collage stays below it — hide the new layer or press Undo to go back. About a minute per panel.

### Models of the storyboard

![The storyboard's models](../images/wf6-sb-gear.jpg)

The gear shows which Qwen Image 2.1 and background-removal files were found, with their download links.

## 4 · Into the Director

![H3 Director with the storyboard shots](../images/wf6-director.jpg)

- **Use in Director** draws the sheet into `input/h3-storyboard` and adds it as a card at the Connector.
- **Send to Director** turns the panels into shots: the times, the shot texts, the sheet on every shot (role
  *Storyboard*) and, for panels marked **First frame / Last frame of its shot**, the panel's picture as that frame. The
  Director's sound lanes, Look and Prompt stay; it asks before replacing its shots.
- **Sync from Director** brings lengths and texts you changed in the Director back into the panels.

![A shot from the storyboard](../images/wf6-studio-shot.jpg)

## Tips

- A storyboard plans shots in **References** mode; the sheet is a plan for H3, not a picture that appears in the video.
- Name the characters in the shot texts (`@Luna`, `@Inferna`) and say who stands where: the order comes from the text.
- Four to six panels for 10–30 seconds; more panels make very short shots.
- The drawn sheet (PNG) carries the whole storyboard. Drag it onto an H3 Storyboard to get every panel and layer back —
  try it with `h3-example-storyboard.png` from the input folder.
