/**
 * BUG-054: relatedContexts collapses all cards with default empty context_id and name into a single card
 *
 * Wo: js/ng/ng_read.js:108-115 (relatedContexts)
 *
 * Im echten Ablauf:
 * 1. Der User baut einen Workflow mit NGContextConnector und schließt mehrere Context-Karten an
 *    (z. B. zwei Bildkarten alice.png und bob.png, plus eine Audiokarte voice.wav).
 * 2. Bei neu angelegten Karten in ComfyUI sind die Widgets context_id und name standardmäßig leer ("").
 * 3. Auf der Audiokarte (oder einer Asset-Karte) ruft load() / assetPanel() relatedContexts(node) auf,
 *    um alle am selben Connector hängenden Karten für "Whose voice" (subjectChoices) bzw.
 *    "Belongs to" (assetChoices) zu ermitteln.
 *
 * Ist:
 *    relatedContexts indiziert die gefundene Map mit:
 *      found.set(entry.widgets.context_id || entry.widgets.name, entry)
 *    Wenn context_id und name leer sind (""), ergibt der Schlüssel den leeren String "".
 *    Jede weitere Karte mit leerer ID/Name überschreibt die vorherige unter dem Schlüssel "".
 *    Von z. B. 3 angeschlossenen Karten bleibt nur eine einzige übrig (die letzte). Alle anderen
 *    Karten werden lautlos gelöscht.
 *    Folglich fehlen die Figuren in "Whose voice" und "Belongs to" vollständig.
 *
 * Soll:
 *    relatedContexts darf verbundene Karten nicht überschreiben, nur weil context_id oder name
 *    leer sind. Wenn context_id leer ist, muss wie im restlichen System (contextId in h3s_content.js
 *    bzw. item_from_widgets in context_build.py) die deterministische Fallback-ID
 *    contextId(entry.widgets, entry.media) bzw. die eindeutige Node-Identität genutzt werden,
 *    sodass alle am Connector hängenden Karten erhalten bleiben.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { relatedContexts } from "../../../js/ng/ng_read.js";

function createMockGraph() {
  const graph = {
    links: {
      1: { origin_id: 10, target_id: 100 },
      2: { origin_id: 20, target_id: 100 },
      3: { origin_id: 30, target_id: 100 },
    },
    getNodeById(id) {
      return this.nodes[id];
    },
  };

  const nodeAlice = {
    id: 10,
    comfyClass: "NGContextImage",
    widgets: [
      { name: "image", value: "alice.png" },
      { name: "name", value: "" },
      { name: "context_id", value: "" },
    ],
  };

  const nodeBob = {
    id: 20,
    comfyClass: "NGContextImage",
    widgets: [
      { name: "image", value: "bob.png" },
      { name: "name", value: "" },
      { name: "context_id", value: "" },
    ],
  };

  const nodeAudio = {
    id: 30,
    comfyClass: "NGContextAudio",
    outputs: [{ links: [3] }],
    widgets: [
      { name: "audio", value: "voice.wav" },
      { name: "name", value: "" },
      { name: "context_id", value: "" },
    ],
    graph,
  };

  const connector = {
    id: 100,
    comfyClass: "NGContextConnector",
    inputs: [
      { name: "context_image.1", link: 1 },
      { name: "context_image.2", link: 2 },
      { name: "context_audio.1", link: 3 },
    ],
    graph,
  };

  graph.nodes = { 10: nodeAlice, 20: nodeBob, 30: nodeAudio, 100: connector };
  return { graph, nodeAlice, nodeBob, nodeAudio, connector };
}

test("BUG-054: relatedContexts must not collapse cards when context_id and name are empty", () => {
  const { nodeAudio } = createMockGraph();

  const related = relatedContexts(nodeAudio);

  // RED: currently related.length is 1 because all 3 cards collide on found.set("", entry)
  assert.equal(
    related.length,
    3,
    `relatedContexts must return all 3 connected cards, but returned ${related.length} (cards collapsed on empty key)`
  );

  const images = related.filter((r) => r.media === "image");
  assert.equal(images.length, 2, "Both image cards (alice.png and bob.png) must be present in relatedContexts");
});

test("BUG-054 (Control): relatedContexts preserves all cards when context_id is explicitly set", () => {
  const { graph, nodeAudio, nodeAlice, nodeBob } = createMockGraph();

  // Set explicit context_id on the cards
  nodeAlice.widgets.find((w) => w.name === "context_id").value = "image_alice";
  nodeBob.widgets.find((w) => w.name === "context_id").value = "image_bob";
  nodeAudio.widgets.find((w) => w.name === "context_id").value = "audio_voice";

  const related = relatedContexts(nodeAudio);

  // GREEN CONTROL: with explicit context_id, all 3 cards are kept
  assert.equal(related.length, 3, "relatedContexts returns all 3 cards when context_id is distinct");
});
