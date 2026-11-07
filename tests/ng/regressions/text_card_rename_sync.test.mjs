// BUG-031: Text-Karte aktualisiert @Name-Referenzen bei Umbenennung nicht:
// 1. node.properties.ng_context_names wird beim Card-Attach nicht initialisiert; der erste Rename wird
//    durch previous = {} vollstaendig verpasst und die Referenz bleibt dauerhaft kaputt.
// 2. followRenames aktualisiert nur values(node).text. node.properties.ng_text_note und ng_text_ai
//    werden nicht aktualisiert; beim Umschalten zwischen "My note" und "AI prompt" wird der veraltete @Name wiederhergestellt.
// Kein Fix, nur rote Regressionstests.
import assert from "node:assert/strict";
import test from "node:test";
import { renameReferences, knownNames, followNoteRenames } from "../../../js/ng/ng_references.js";

test("BUG-031a: text card renameReferences misses first rename when ng_context_names is uninitialized", () => {
  const initialText = "Look at @Alice and keep her calm.";
  const connectedEntries = [
    { widgets: { context_id: "ctx_alice", name: "Bob" } },
  ];

  // h3c_card.js load(): a text card remembers the names of its connected cards (knownNames) before any rename, so
  // the first rename has the old name to replace.
  const remembered = knownNames({}, [{ widgets: { context_id: "ctx_alice", name: "Alice" } }]);
  const renamed = renameReferences(initialText, remembered, connectedEntries);

  // Ist-Zustand (Bug): renamed ist unveraendert "Look at @Alice...", weil previous leer war.
  // Soll-Zustand: Wenn eine Karte mit @Alice verbunden war und Alice zu Bob umbenannt wird,
  // muss der Text auf @Bob aktualisiert werden (d.h. ng_context_names muss vor dem Rename initialisiert sein).
  assert.equal(
    renamed,
    "Look at @Bob and keep her calm.",
    "a renamed context must update @Name in the text card even on the first rename event"
  );
});

test("BUG-031b: followRenames must update both ng_text_note and ng_text_ai so view toggles do not resurrect stale names", () => {
  const node = {
    properties: {
      ng_context_names: { ctx_alice: "Alice" },
      ng_text_note: "Hier ist @Alice im Wald.",
      ng_text_ai: "Encounter with @Alice under the trees.",
      ng_text_view: "ai",
    },
    widgets: [
      { name: "text", value: "Encounter with @Alice under the trees." },
      { name: "name", value: "Notes" },
    ],
  };

  const newEntries = [
    { widgets: { context_id: "ctx_alice", name: "Bob" } },
  ];

  // h3c_card.js followRenames: followNoteRenames renames the shown text and both kept versions.
  const activeText = node.widgets.find((w) => w.name === "text").value;
  node.widgets.find((w) => w.name === "text").value = followNoteRenames(node.properties, activeText, newEntries);

  // Hier zeigt sich BUG-031b:
  // node.properties.ng_text_note wurde NICHT durch renameReferences geschickt!
  // Wenn der Nutzer jetzt auf "My note" umschaltet:
  // actions.textView("note"):
  // applyValues(node, { text: String(node.properties.ng_text_note) })
  // Dann wird widget.value wieder auf den alten Wert mit @Alice gesetzt!
  assert.equal(
    node.properties.ng_text_note,
    "Hier ist @Bob im Wald.",
    "node.properties.ng_text_note must be updated by followRenames to prevent reverting to stale @Name on view switch"
  );

  assert.equal(
    node.properties.ng_text_ai,
    "Encounter with @Bob under the trees.",
    "node.properties.ng_text_ai must be updated by followRenames when in note view"
  );
});
