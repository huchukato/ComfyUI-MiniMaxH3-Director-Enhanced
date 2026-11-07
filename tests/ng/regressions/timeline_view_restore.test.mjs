import test from "node:test";
import assert from "node:assert/strict";
import { studio } from "./studio_fixture.mjs";

test("workflow configuration after Studio creation restores saved timeline zoom", (t) => {
  const { node, root, handle, read } = studio(t);
  const before = read();
  // ComfyUI creates the node and its DOM before restoring workflow properties.
  node.properties.ng_timeline = { zoom: 8, scroll: 0.4 };
  handle.refresh();
  assert.equal(root.byTag("output")[0].innerText, "800%");
  assert.deepEqual(read(), before, "restoring a view must not edit shot/media data");
  assert.deepEqual(node.properties.ng_timeline, { zoom: 8, scroll: 0.4 });
});
