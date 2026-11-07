/**
 * BUG-051: Context cards hide their figures from the "Whose voice" and "Belongs to" dropdowns
 * when the context_id widget is empty (the ComfyUI default for a newly placed card).
 *
 * Wo:
 *   js/ng/ng_asset_relations.js:17-23  (assetChoices)
 *   js/ng/ng_subjects.js:22-34          (subjectChoices -> isSubject -> referenceSubject)
 *
 * User flow (supported, no crash, no data loss -> P2):
 *   1. The user places a NGContextConnector and wires an NGContextImage card (e.g. alice.png)
 *      with content_roles "character" and usage "reference".
 *   2. A newly created card's widgets context_id and name default to "" (advanced widgets).
 *   3. On the card (or an audio/voice card next to it) the panel builds the "Belongs to"
 *      (assetChoices) and "Whose voice" (subjectChoices) dropdowns from relatedContexts(node).
 *
 * Backend truth: item_from_widgets (ng/core/context_build.py:28) injects the deterministic
 * fallback id  str(widgets.get("context_id") or "%s_%s" % (media, slug(label)))  for a card
 * with an empty context_id, so the compiled plan DOES contain a real figure id such as
 * "image_alice". require_unique (context.py) uses that same id.
 *
 * Ist: assetChoices keeps only entries with a truthy context_id (`entry.widgets.context_id`),
 *   and subjectChoices skips an entry whose id is empty (`if (!id ...) continue`). So the
 *   default figure card is never offered: the "Belongs to" list is empty and the "Whose voice"
 *   dropdown has no entry, even though the same card is a live figure in the plan.
 * Soll: the dropdowns must offer the card under the same id the backend assigns (media_slug),
 *   so a stored choice resolves to that figure.
 *
 * This is not a crash or data loss: it is a supported option (assign a voice / link an asset
 * to a Subject) that silently has no effect for default cards. It differs from BUG-054, which
 * collapses cards inside relatedContexts itself; here relatedContexts is bypassed by feeding
 * the choices functions entries directly, so the missing-figure behaviour is proven on its own.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { assetChoices, referenceSubject } from "../../../js/ng/ng_asset_relations.js";
import { subjectChoices, isSubject } from "../../../js/ng/ng_subjects.js";

// Two figure image cards exactly as a freshly placed node reports its widgets: context_id "".
function defaultCards() {
  return [
    {
      media: "image",
      widgets: {
        image: "alice.png",
        name: "Alice",
        context_id: "", // ComfyUI default for a newly placed card
        usage: "reference",
        content: "character",
      },
    },
    {
      media: "image",
      widgets: {
        image: "bob.png",
        name: "Bob",
        context_id: "",
        usage: "reference",
        content: "character",
      },
    },
  ];
}

// The backend ids item_from_widgets assigns to those same two cards.
const EXPECTED_IDS = ["image_alice", "image_bob"];

test("BUG-051: assetChoices offers a default (empty context_id) figure card under its fallback id", () => {
  const choices = assetChoices(defaultCards(), [], "");
  const ids = choices.map((choice) => choice.id);
  for (const expected of EXPECTED_IDS) {
    assert.ok(
      ids.includes(expected),
      `"Belongs to" must offer the default figure as '${expected}' (the id the plan assigns), got [${ids.join(", ")}]`,
    );
  }
});

test("BUG-051: subjectChoices offers a default (empty context_id) figure card under its fallback id", () => {
  const list = subjectChoices(defaultCards(), "");
  const ids = list.map((entry) => entry.id);
  for (const expected of EXPECTED_IDS) {
    assert.ok(
      ids.includes(expected),
      `"Whose voice" must offer the default figure as '${expected}', got [${ids.join(", ")}]`,
    );
  }
  assert.equal(isSubject(defaultCards()[0]), true, "a default character image card is a Subject");
  assert.equal(referenceSubject(defaultCards()[0]), true, "a default character image card is a reference Subject");
});

test("BUG-051 (control): an explicit context_id figure is offered under exactly that id", () => {
  const cards = [
    {
      media: "image",
      widgets: { image: "alice.png", name: "Alice", context_id: "alice_explicit", usage: "reference", content: "character" },
    },
  ];
  const ids = assetChoices(cards, [], "").map((choice) => choice.id);
  assert.ok(ids.includes("alice_explicit"), "an explicit context_id figure is offered unchanged");
  const subjectIds = subjectChoices(cards, "").map((entry) => entry.id);
  assert.ok(subjectIds.includes("alice_explicit"), "an explicit context_id figure appears in Whose voice");
});
