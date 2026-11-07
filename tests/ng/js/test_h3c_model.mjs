// The Context cards' rules: valid roles, mode-aware hints and where the Studio uses a card.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as model from "../../../js/ng/h3c_model.js";

// Every content kind and role a card offers is one ng/core/context.py accepts for that medium.
{
  const source = readFileSync(new URL("../../../ng/core/context.py", import.meta.url), "utf8");
  const tuple = (dict, media) => {
    const block = source.slice(source.indexOf(`${dict} = {`)), at = block.indexOf(`"${media}": (`);
    return [...block.slice(at, block.indexOf(")", at)).matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).slice(1);
  };
  for (const media of ["image", "video", "audio"]) for (const [key] of model.CONTENT[media])
    assert.ok(tuple("CONTENT_BY_MEDIA", media).includes(key), `${media} content ${key} is accepted by Python`);
  for (const media of ["image", "video", "audio", "text"]) for (const [key] of model.USAGE[media])
    assert.ok(tuple("USAGE_BY_MEDIA", media).includes(key), `${media} usage ${key} is accepted by Python`);
  for (const media of ["image", "video", "audio", "text"]) assert.deepEqual(model.USAGE[media].map(([key]) => key).sort(), tuple("USAGE_BY_MEDIA", media).sort(),
    `every ${media} role Python accepts can be shown, so a stored role is never left unmarked`);
  for (const [key] of model.INSERTS) assert.ok(tuple("CONTENT_BY_MEDIA", "text").includes(key), `quick insert ${key} is a text content kind`);
}

// Hints warn exactly where the Director's mode ignores the role.
{
  assert.match(model.roleHint("image", "reference", "fl2va").text, /as a reference next to the frames/, "FL2VA keeps a reference a reference (2026-10-12)");
  assert.equal(model.roleHint("image", "keyframe", "fl2va").warn, false);
  assert.match(model.roleHint("image", "keyframe", "ref2va").text, /after the shot's start/);
  assert.match(model.roleHint("image", "storyboard", "ref2va").text, /shot order/);
  assert.equal(model.roleHint("image", "storyboard", "fl2va").warn, true, "no storyboard in First / last frame mode");
  assert.equal(model.roleHint("image", "reference", "ref2va").warn, false);
  assert.equal(model.roleHint("video", "camera", "fl2va").warn, true);
  assert.equal(model.roleHint("video", "continue", "fl2va").warn, false);
  assert.equal(model.roleHint("audio", "voice", "fl2va").warn, true);
  assert.equal(model.roleHint("audio", "lock", "fl2va").warn, false);
  assert.equal(model.roleHint("audio", "copy", "auto").warn, false);
}

// AI Loader: an address that is no HTTP(S) URL is dropped when the source card changes (user workflow had "custom").
{
  const { clearedAddress } = await import("../../../js/ng/ng_widgets.js");
  assert.deepEqual(clearedAddress("custom"), { base_url: "" });
  assert.deepEqual(clearedAddress("http://127.0.0.1:11434"), {});
  assert.deepEqual(clearedAddress("https://openrouter.ai/api/v1"), {});
  assert.deepEqual(clearedAddress(""), {});
}

// An AI suggestion may only write roles the card's medium has; free text ("Establishing shot ...") never reaches a widget.
{
  assert.deepEqual(model.offerFor("image").usage, ["reference", "first_frame", "last_frame", "keyframe", "storyboard"], "the AI may only pick what the card shows");
  assert.deepEqual(model.offerFor("text").content, []);
  assert.deepEqual(model.usableFields("text", { description: "A rule.", usage: "rule" }), { usage: "rule" }, "a Text card has no description to fill");
  assert.deepEqual(model.usableFields("image", { description: "A man.", content: "face", usage: "Establishing shot for character introduction." }),
    { description: "A man.", content: "face" });
  assert.deepEqual(model.usableFields("image", { usage: "Last frame" }), { usage: "last_frame" });
  assert.deepEqual(model.usableFields("audio", { usage: "lock", content: "voice" }), { usage: "lock", content: "voice" });
  assert.deepEqual(model.usableFields("image", { content: "voice" }), {}, "a picture cannot be a voice");
}

console.log("h3c model ok");
