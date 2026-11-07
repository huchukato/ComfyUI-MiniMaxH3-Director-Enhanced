// BUG-035: editSpoken drops language choice on empty or narrator spoken lines.
// When a user selects a language (e.g. "German") for a new spoken line before typing text,
// or clears the text of a narrator line while editing, editSpoken evaluates:
//   next.length === 1 && !next[0].text.trim() && !next[0].speaker_id ? [] : next;
// which immediately discards the line (returning []), causing the Studio UI to revert to "English".
import assert from "node:assert/strict";
import test from "node:test";
import { editSpoken } from "../../../js/ng/h3s_model.js";

test("BUG-035: selecting a language on an initial spoken line must preserve the language choice", () => {
  // User selects "German" from the language dropdown in the Studio before typing dialogue text
  const result = editSpoken([], 0, { language: "German" });

  assert.equal(result.length, 1, "changing language on a new spoken line must create and keep the line");
  assert.equal(result[0].language, "German", "the chosen language must be preserved and not discarded");
});

test("BUG-035: clearing text on a narrator spoken line must preserve the chosen language", () => {
  // User had a narrator line in German and clears the text field to retype the sentence
  const existing = [{ schema_version: 1, text: "Guten Tag", speaker_id: "", voice: "a narrator", language: "German", delivery: "says" }];
  const result = editSpoken(existing, 0, { text: "" });

  assert.equal(result.length, 1, "clearing dialogue text on a narrator line must keep the line");
  assert.equal(result[0].language, "German", "the narrator line must retain its chosen language");
});

test("control: editing text on a spoken line retains both text and language", () => {
  const result = editSpoken([], 0, { text: "Hello world", language: "German" });

  assert.equal(result.length, 1);
  assert.equal(result[0].text, "Hello world");
  assert.equal(result[0].language, "German");
});
