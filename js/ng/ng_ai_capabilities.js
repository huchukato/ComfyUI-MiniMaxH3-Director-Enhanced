// What a provider can and cannot read, and what the panel says about it - kept out of the panel
// itself so the AI Loader and any future context card answer the same question the same way.
//
// The two checkboxes this replaces were a promise the panel could not keep: a user ticked "vision"
// for a text-only model and only learned it from an error thrown at the far end of the request.
// A capability is a fact about the provider, so the registry decides it and the panel states it.

// The CLIP / Encoder card is the one honest exception. There the model is whatever the user
// connected, and nothing in the registry knows whether it takes pictures or sound - so the switch
// stays, and it stays a promise the user makes rather than a fact we invented.
const NATIVE_CARD = "clip";

// Why one medium cannot be read. The sentence names the way out - a Text card needs no provider at
// all - because "this provider cannot read audio" alone leaves the user with nothing to do. The card
// that holds the medium shows this, so it is read there and not composed here.
export function mediaHint(entry, media) {
  return entry?.media?.[media]?.hint || "";
}

// Whether this provider accepts one field. An absent entry means "assume everything", because a
// field that turns out to be unsupported is a smaller problem than one the user cannot find at all.
export function accepts(entry, name) {
  if (!entry || !Array.isArray(entry.fields)) return true;
  return entry.fields.includes(name);
}

// The name a field carries on the wire. It only differs for Ollama, which nests and renames; shown
// on the tile because a user reading "Max tokens" and searching their own request log for
// max_tokens would otherwise not find it.
export function wireName(entry, name) {
  return entry?.wire?.[name] || name;
}

// The help text for one field, from the registry. Empty means no "?" marker: a field this provider
// does not have should not carry a question mark pointing at a sentence about another provider.
export function fieldHelp(entry, name) {
  return entry?.help?.[name] || "";
}

// Whether the key tile belongs on screen at all. A provider that authenticates with nothing has no
// key to store, and offering the field would be one more thing for the user to wonder about.
export function wantsKey(entry) {
  return !!entry && entry.auth !== "none";
}

export function isNative(sourceId) {
  return sourceId === NATIVE_CARD;
}