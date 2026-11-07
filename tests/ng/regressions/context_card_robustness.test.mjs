// BUG-029: wirePlayback darf audio.volume nicht auf NaN setzen (wirft TypeError im Browser).
// BUG-030: selectedRoles und contextOptions duerfen bei nicht-JSON-Strings (z. B. "image" aus aelteren Workflows) keinen SyntaxError werfen.
// Kein Fix, nur rote Regressionstests.
import assert from "node:assert/strict";
import test from "node:test";
import { wirePlayback } from "../../../js/ng/h3c_media.js";
import { selectedRoles, contextOptions } from "../../../js/ng/ng_context_controls.js";

test("BUG-029: wirePlayback must not set audio.volume to NaN when duration is not yet loaded and fade_out is active", () => {
  let volumeSet = null;
  const audio = {
    currentTime: 0,
    duration: NaN,
    paused: false,
    pause() { this.paused = true; },
    get volume() { return volumeSet; },
    set volume(v) {
      if (!Number.isFinite(v)) {
        throw new TypeError("The provided double value is non-finite");
      }
      volumeSet = v;
    },
  };
  const S = {
    els: { audio },
    opts: { start_s: 0, end_s: 0 },
    listen: { volume: 0.8, fade_in: 0, fade_out: 1.0 },
  };

  wirePlayback(S, () => {}, audio, () => {});

  // Simulate ontimeupdate before metadata is loaded
  assert.doesNotThrow(() => {
    audio.ontimeupdate();
  }, "ontimeupdate must not throw TypeError when volume is updated with unready duration");

  assert.ok(Number.isFinite(volumeSet), `volume must be a finite number, got ${volumeSet}`);
});

test("BUG-030: selectedRoles must not throw SyntaxError when content_roles contains non-JSON text from older workflows", () => {
  const node = {
    widgets: [
      { name: "content_roles", value: "image" },
      { name: "content", value: "character" },
    ],
  };

  assert.doesNotThrow(() => {
    const roles = selectedRoles(node, "content");
    assert.ok(Array.isArray(roles), "should return an array fallback");
  }, "selectedRoles must safely handle non-JSON string without throwing SyntaxError");
});

test("BUG-030: contextOptions must not throw SyntaxError when context_options contains malformed text", () => {
  const node = {
    widgets: [
      { name: "context_options", value: "{ broken json" },
    ],
  };

  assert.doesNotThrow(() => {
    const opts = contextOptions(node);
    assert.ok(opts && typeof opts === "object", "should return fallback options object");
  }, "contextOptions must safely handle malformed JSON without throwing SyntaxError");
});
