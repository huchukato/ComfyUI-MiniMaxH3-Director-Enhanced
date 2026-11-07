/**
 * A copied Context card (or a preset loaded onto a second card) kept the first card's context_id and name; the
 * Context Connector then stopped the run: "context.ctx_e15_mage: id used twice (Mage and Mage)" (user workflow,
 * 2026-10-11, nodes 474 and 504 with two different pictures). The later card must get its own ID and name.
 */
import assert from "node:assert/strict";
import { ownIdentity } from "../../../js/ng/ng_widgets.js";

const mage = { context_id: "ctx_e15_mage", name: "Mage" };

assert.deepEqual(ownIdentity({ ...mage }, [mage], () => "ctx_new"), { context_id: "ctx_new", name: "Mage 2" });
assert.deepEqual(ownIdentity({ ...mage }, [mage, { context_id: "ctx_x", name: "mage 2" }], () => "ctx_new"),
  { context_id: "ctx_new", name: "Mage 3" }, "names compare without case, as the Connector does");
assert.deepEqual(ownIdentity({ ...mage }, [{ context_id: "ctx_other", name: "Alice" }]), {}, "a unique card is left alone");
assert.deepEqual(ownIdentity({ context_id: "", name: "" }, [{ context_id: "", name: "" }]), {}, "a fresh empty card is not renamed");
assert.deepEqual(ownIdentity({ context_id: "ctx_e15_mage", name: "Mage 2" }, [mage], () => "ctx_new"), { context_id: "ctx_new" },
  "an already renamed card only needs its own ID");
console.log("card_copied_identity: ok");
