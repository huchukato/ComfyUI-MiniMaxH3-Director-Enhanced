// H3 Storyboard data: a saved board is read back (and repaired), panels follow each other in time, the sheet's grid and
// geometry, and the hit test of a turned layer.
import assert from "node:assert/strict";

const model = await import("../../../js/ng/h3b_model.js");

// A new board: four 16:9 panels of 2.5 s, as the user's ChatGPT boards.
{
  const board = model.newBoard();
  assert.equal(board.panels.length, 4);
  assert.deepEqual(model.panelTimes(board).at(-1), [7.5, 10]);
  const back = model.readBoard(model.writeBoard(board));
  assert.equal(back.error, "");
  assert.deepEqual(back.board, board);
}

// Saved data is repaired where it can be: unknown layers go, numbers are clamped, a bad aspect is 16:9; bad JSON is said.
{
  const text = JSON.stringify({ format: "h3-storyboard", aspect: "5:2", panels: [{ seconds: -3, layers: [
    { kind: "image", src: { filename: "a.png", type: "evil" }, scale: 99 }, { kind: "video" }, { kind: "text", color: "red" }] }] });
  const { board, error } = model.readBoard(text);
  assert.equal(error, "");
  assert.equal(board.aspect, "16:9");
  assert.equal(board.panels[0].seconds, 0.1);
  assert.deepEqual(board.panels[0].layers.map((l) => l.kind), ["image", "text"]);
  assert.equal(board.panels[0].layers[0].src.type, "input");
  assert.equal(board.panels[0].layers[0].scale, 5);
  assert.equal(board.panels[0].layers[1].color, "#FFFFFF");
  assert.match(model.readBoard("{").error, /not readable/);
  assert.match(model.readBoard('{"format":"x"}').error, /no H3 storyboard/);
}

// The panel count keeps the panels there are and adds new ones with the last one's length.
{
  let board = model.newBoard();
  board.panels[3].seconds = 5;
  board = model.setPanelCount(board, 6);
  assert.deepEqual(board.panels.map((p) => p.seconds), [2.5, 2.5, 2.5, 5, 5, 5]);
  assert.equal(model.setPanelCount(board, 20).panels.length, model.MAX_PANELS);
  assert.equal(model.setPanelCount(board, 0).panels.length, 1);
}

// The grid: landscape 2 x 2 for four, 3 x 3 for nine; portrait in up to two rows.
{
  assert.deepEqual(model.grid(4, "16:9"), { cols: 2, rows: 2 });
  assert.deepEqual(model.grid(6, "16:9"), { cols: 3, rows: 2 });
  assert.deepEqual(model.grid(9, "16:9"), { cols: 3, rows: 3 });
  assert.deepEqual(model.grid(4, "9:16"), { cols: 4, rows: 1 });
  assert.deepEqual(model.grid(6, "9:16"), { cols: 3, rows: 2 });
  assert.deepEqual(model.grid(1, "1:1"), { cols: 1, rows: 1 });
}

// The sheet of four 16:9 panels with a title is about the ChatGPT board's 1672 x 941; panels do not overlap.
{
  const board = { ...model.newBoard(), title: "MINIMAX H3 - STORYBOARD" };
  const layout = model.sheetLayout(board);
  assert.equal(layout.width, 1672);
  assert.ok(Math.abs(layout.height - 1050) < 120, `height ${layout.height}`);
  const [a, b, c] = layout.panels;
  assert.ok(b.x >= a.x + a.w && c.y >= a.y + a.h);
  assert.ok(Math.abs(a.pic.w / a.pic.h - 16 / 9) < 1e-9);
  assert.equal(model.sheetLayout(model.newBoard()).title, 0, "no title line without a title");
  assert.deepEqual(model.pictureSize("16:9"), [1280, 720]);
  assert.deepEqual(model.pictureSize("9:16"), [720, 1280]);
}

// A picture layer is as wide as its scale of the panel; the hit test follows its rotation.
{
  const layer = model.newLayer("image", { x: 0.5, y: 0.5, scale: 0.5, rotation: 90 });
  const box = model.layerBox(layer, 1000, 500, [200, 100]);
  assert.deepEqual([box.w, box.h], [500, 250]);
  assert.ok(model.hits(layer, 500, 480, 1000, 500, [200, 100]), "turned 90°: the long side runs down");
  assert.ok(!model.hits(layer, 700, 250, 1000, 500, [200, 100]));
  assert.equal(model.loadName({ filename: "c.png", subfolder: "h3-storyboard", type: "output" }), "h3-storyboard/c.png [output]");
  assert.match(model.srcUrl({ filename: "a b.png", subfolder: "x", type: "input" }), /^\/view\?filename=a\+b\.png&subfolder=x&type=input$/);
}

// The shots document matches the node's: panel times end to end, shot text before caption.
{
  const board = model.newBoard();
  board.panels[0].caption = "Caption."; board.panels[1].shot = "Shot."; board.panels[1].caption = "Ignored.";
  const shots = model.shotsDocument(board).shots;
  assert.deepEqual(shots.map((s) => [s.start, s.end, s.text]).slice(0, 2), [[0, 2.5, "Caption."], [2.5, 5, "Shot."]]);
}

// Stage 3: the redraw instruction keeps the collage's composition, names each reference image, and leaves out beat marks
// and @ signs; a redrawn layer and the first-frame mark survive a save.
{
  const board = model.newBoard();
  board.panels[1].caption = "";
  board.panels[1].shot = "0–5s: A full-body shot of @Luna at the altar. 5–10s: She turns.";
  const text = model.redrawPrompt(board, 1, [{ name: "Luna", description: "Violet hair." }, { name: "Inferna", description: "" }]);
  assert.match(text, /^Redraw <image1> as one finished, polished storyboard frame in the art style of the character references\./);
  assert.match(text, /Luna looks exactly as in <image2>: face, hair, outfit and colours \(Violet hair\)\./);
  assert.match(text, /Inferna looks exactly as in <image3>/);
  assert.match(text, /What happens: A full-body shot of Luna at the altar\. She turns\./);
  assert.doesNotMatch(model.redrawPrompt(board, 0), /art style|<image2>/);
  board.panels[0].first_frame = true;
  board.panels[0].layers.push(model.newLayer("image", { src: { filename: "r.png", subfolder: "h3-storyboard", type: "output" }, redrawn: true }));
  const back = model.readBoard(model.writeBoard(board)).board;
  assert.equal(back.panels[0].first_frame, true);
  assert.equal(back.panels[0].layers[0].redrawn, true);
}

// Stage 4: the Director's shots carry the storyboard card on every shot and a panel's card as its first frame.
{
  const board = model.newBoard();
  const shots = model.directorShots(board, { storyboard: "ctx_sheet", frames: { 2: "ctx_p3" } });
  assert.equal(shots.length, 4);
  assert.deepEqual(shots[0].media, [{ schema_version: 1, context_id: "ctx_sheet", role: "storyboard" }]);
  assert.deepEqual(shots[2].media.map((m) => m.role), ["storyboard", "first_frame"]);
  assert.deepEqual(model.directorShots(board)[0].media, []);
}

// End pictures survive save/reload and use their own explicit role, including both roles on one panel.
{
  const board = model.newBoard();
  board.panels[1].last_frame = true;
  board.panels[2].first_frame = board.panels[2].last_frame = true;
  const saved = model.readBoard(model.writeBoard(board)).board;
  assert.equal(saved.panels[1].last_frame, true);
  assert.equal(saved.panels[1].first_frame, false);
  const shots = model.directorShots(saved, { frames: { 2: "both" }, lastFrames: { 1: "end", 2: "both" } });
  assert.deepEqual(shots[1].media, [{ schema_version: 1, context_id: "end", role: "last_frame" }]);
  assert.deepEqual(shots[2].media.map((item) => [item.context_id, item.role]), [["both", "first_frame"], ["both", "last_frame"]]);
  const old = JSON.parse(model.writeBoard(board));
  delete old.panels[1].last_frame;
  assert.equal(model.readBoard(JSON.stringify(old)).board.panels[1].last_frame, false);
}

// Pictures made with Qwen Image 2.1: a figure from a sheet in the template's RGBA wording, an empty background, about a
// megapixel in the panel format; the board's library and every picture on a panel are offered on all panels, once each.
{
  const figure = model.figurePrompt("Luna", "raising her staff.");
  assert.match(figure, /^This is an RGBA format image with transparency\. A single full-body figure of Luna as shown in <image1>/);
  assert.match(figure, /props: raising her staff\. Only this one figure/);
  assert.match(figure, /The image has an alpha channel and a transparent background\.$/);
  assert.equal(model.backgroundPrompt("A gothic hall."), "A gothic hall. An empty scene for a storyboard panel: no people, no characters, no text.");
  assert.deepEqual(model.makeSize("16:9"), [1376, 768]);
  assert.deepEqual(model.makeSize("1:1"), [1024, 1024]);
  const board = model.newBoard();
  const bg = { filename: "background_00001_.png", subfolder: "h3-storyboard", type: "output" };
  const cut = { filename: "cut.png", subfolder: "h3-storyboard", type: "output" };
  board.library = [{ id: "a1", name: "Hall", kind: "background", src: bg }];
  board.panels[0].layers.push(model.newLayer("image", { src: bg }), model.newLayer("image", { src: cut, name: "Luna" }),
    model.newLayer("image", { src: { filename: "r.png", subfolder: "", type: "output" }, redrawn: true }));
  board.panels[2].layers.push(model.newLayer("image", { src: cut, name: "Luna" }));
  assert.deepEqual(model.libraryItems(board).map((item) => [item.kind, item.src.filename]), [["background", "background_00001_.png"], ["picture", "cut.png"]],
    "each picture once, a redraw is no picture to reuse");
  const back = model.readBoard(model.writeBoard(board)).board;
  assert.deepEqual(back.library, board.library);
  assert.deepEqual(model.readBoard(JSON.stringify({ ...board, library: [{ name: "broken" }, { kind: "figure", src: bg }] })).board.library.map((i) => i.kind), ["figure"]);
}

// Multi-storyboard scenes and Studio <-> Storyboard sync: Scene 2 appends after Scene 1 with unique IDs; editing Scene 1
// updates its slice in-place (preserving spoken lines and locked text) and shifts Scene 2's times; syncFromDirector pulls
// edited durations and shot texts back into the matching board's panels.
{
  const scene1 = model.newBoard(), scene2 = structuredClone(scene1);
  scene1.panels = scene1.panels.slice(0, 2); scene2.panels = scene2.panels.slice(0, 2);
  scene1.panels[0].shot = "Scene 1 A"; scene1.panels[1].shot = "Scene 1 B";
  scene2.panels[0].shot = "Scene 2 A"; scene2.panels[1].shot = "Scene 2 B";
  let shots = model.mergeDirectorShots([], scene1, { storyboard: "ctx_sb1" });
  assert.deepEqual(shots.map((s) => [s.id, s.start, s.end]), [[`sb-${scene1.panels[0].id}`, 0, 2.5], [`sb-${scene1.panels[1].id}`, 2.5, 5]]);
  // Scene 2 (cloned panel IDs) appends at 5..10 s with disambiguated shot IDs.
  shots = model.mergeDirectorShots(shots, scene2, { storyboard: "ctx_sb2" });
  assert.equal(shots.length, 4);
  assert.equal(new Set(shots.map((s) => s.id)).size, 4, "all shot IDs remain unique across cloned boards");
  assert.deepEqual(shots.slice(2).map((s) => [s.start, s.end, s.text]), [[5, 7.5, "Scene 2 A"], [7.5, 10, "Scene 2 B"]]);
  // Studio edits: add spoken line + lock text on shot 0, resize shot 2 (Scene 2 panel 1) to 4 s and edit its text.
  shots[0].spoken = [{ schema_version: 1, speaker_id: "luna", text: "Hello" }];
  shots[0].locked_fields = ["text"];
  shots[0].media.push({ schema_version: 1, context_id: "ctx_luna", role: "subject" });
  scene1.panels[0].seconds = 4; scene1.panels[0].shot = "Should not overwrite locked text";
  shots = model.mergeDirectorShots(shots, scene1, { storyboard: "ctx_sb1", frames: { 0: "ctx_f1" } });
  assert.deepEqual(shots.map((s) => [s.start, s.end]), [[0, 4], [4, 6.5], [6.5, 9], [9, 11.5]], "Scene 2 shifted by +1.5 s");
  assert.equal(shots[0].text, "Scene 1 A", "locked text preserved");
  assert.equal(shots[0].spoken.length, 1, "spoken lines preserved");
  assert.deepEqual(shots[0].media.map((m) => m.role), ["storyboard", "first_frame", "subject"]);
  // Studio resizes Scene 2's first shot from 2.5 s to 5 s (6.5..11.5) and edits its text; syncFromDirector pulls it back.
  shots[2].end = 11.5; shots[2].text = "Scene 2 A edited in Studio";
  shots[3].start = 11.5; shots[3].end = 14;
  const res = model.syncFromDirector(scene2, shots, "ctx_sb2");
  assert.deepEqual(res, { updated: 1, matched: 2 });
  assert.equal(scene2.panels[0].seconds, 5);
  assert.equal(scene2.panels[0].shot, "Scene 2 A edited in Studio");
  assert.equal(scene2.panels[1].seconds, 2.5);
}

// Character bar (Figurenleiste) on the sheet and PNG tEXt project roundtrip (embedBoardPng -> extractBoardPng).
{
  const board = { ...model.newBoard(), title: "CAST TEST" };
  const baseLayout = model.sheetLayout(board);
  const cast = [
    { name: "Luna", src: { filename: "luna.png", subfolder: "", type: "input" } },
    { name: "Inferna", src: { filename: "inferna.png", subfolder: "", type: "input" } },
  ];
  const castLayout = model.sheetLayout(board, model.SHEET_WIDTH, cast);
  assert.equal(castLayout.cast.length, 2);
  assert.deepEqual(castLayout.cast.map((c) => c.name), ["Luna", "Inferna"]);
  assert.ok(castLayout.panels[0].y > baseLayout.panels[0].y, "panels shift down below the character bar");
  assert.equal(castLayout.height - baseLayout.height, castLayout.panels[0].y - baseLayout.panels[0].y);

  // Minimal valid PNG: 8-byte signature + 13-byte IHDR + 0-byte IEND.
  const minimalPng = new Uint8Array([
    137, 80, 78, 71, 13, 10, 26, 10,
    0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137,
    0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130,
  ]);
  assert.equal(model.extractBoardPng(minimalPng), null, "plain PNG has no storyboard chunk");
  board.panels[0].caption = "Luna — 0–2.5 s: Grüße im Saal.";
  const embedded = model.embedBoardPng(minimalPng, board);
  assert.ok(embedded.length > minimalPng.length);
  const restored = model.extractBoardPng(embedded);
  assert.deepEqual(restored, board);
}

console.log("h3b model ok");

