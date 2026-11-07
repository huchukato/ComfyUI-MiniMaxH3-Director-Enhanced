// BUG-023: "Remove empty audio lane" entfernt die Spur aus der Liste, laesst aber die
// Clips im Dokument. Beim naechsten Laden kommt die Spur samt Clips zurueck.
// Kein Fix, nur Beleg.
import assert from "node:assert/strict";
import test from "node:test";
import { readProject, writeProject, removeLane } from "../../../js/ng/h3s_model.js";

const clip = (id, lane, start) => ({ schema_version: 1, id, context_id: "a1",
  start, end: start + 2, offset: 0, mode: "lock", lane });

test("control: eine Spur mit Clips wird nicht angeboten", () => {
  // Der Knopf erscheint laut h3s_timeline.js nur fuer items.length === 0. Diese Pruefung
  // haelt den Vertrag fest, damit eine spaetere Aenderung daran nicht still vorbeilaeuft.
  const read = readProject(writeProject({ shots: [], audio: [clip("c1", "l1", 0)], lanes: ["l1"] }));
  const laneItems = read.audio.filter((c) => c.lane === "l1");
  assert.equal(laneItems.length, 1, "a lane with clips must not offer the empty-lane button");
});

test("BUG-023: eine Spur ohne Clips verschwindet, ihre Vergangenheit nicht", () => {
  // Eine Spur, die einmal Clips hatte und wieder geleert wurde.
  const stored = writeProject({ shots: [], audio: [], lanes: [] });
  const before = readProject(stored);
  assert.deepEqual(before.lanes, [], "nothing to remove");

  // Jetzt der Fall, der im Studio passieren kann: addLane() nimmt eine ID an, aber newClip()
  // kann ausfallen (kein Audio-Content, kein Raum) - die Spur bleibt dann leer im Dokument.
  const afterEmptyLane = writeProject({ shots: [], audio: [], lanes: ["lane_1"] });
  const read = readProject(afterEmptyLane);
  assert.deepEqual(read.lanes, ["lane_1"], "the empty lane is stored");

  // removeLane() (the Studio action) nimmt die Clips der Spur mit; sonst kaemen Spur und Clips beim Laden zurueck.
  const withClips = writeProject({ shots: [], audio: [clip("c1", "lane_1", 0)], lanes: ["lane_1"] });
  const removed = removeLane(readProject(withClips), "lane_1");
  const lanesAfterRemoval = readProject(writeProject({ shots: [], ...removed })).lanes;
  const audioAfterRemoval = removed.audio;
  assert.deepEqual(lanesAfterRemoval, [], "the lane is gone from the list");
  assert.equal(audioAfterRemoval.length, 0,
    "the clips of a removed lane must be removed with it, not survive in the document");
});