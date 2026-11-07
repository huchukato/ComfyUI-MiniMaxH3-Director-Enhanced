# Structured shot contract · E43a

The existing `shots` String input accepts old timed text or a JSON document:

```json
{
  "format": "h3-director-shots",
  "schema_version": 1,
  "shots": [{
    "id": "shot-example",
    "start": 0,
    "end": 8,
    "text": "The woman enters the room.",
    "media": [{"schema_version": 1, "context_id": "ctx-woman", "role": "context"}],
    "spoken": [{"schema_version": 1, "speaker_id": "ctx-woman", "voice": "a calm narrator", "language": "German", "delivery": "says", "text": "Guten Morgen!"}],
    "locked_fields": ["spoken"],
    "draft": null
  }]
}
```

`start` and `end` are finite, nonnegative story seconds, converted to 24 fps
at compilation. IDs must be nonempty and unique. Editing, serialization, time
sorting and splitting a shot across chunks retain its ID. Old timed text receives
`legacy-shot-N` IDs in source order and is stored as JSON after its first edit;
an untouched old workflow keeps its original text. An empty widget uses the Idea.
An explicit JSON document with no shots describes no shots.

Media bindings contain Context IDs, never filenames or display names. `context`
inherits the card's usage in its original order; an explicit role overrides it for the intersecting
chunks. A context assigned anywhere is scoped to those shots; contexts with no
shot assignment remain global for backward compatibility. Intersections include
the pinned head and any extension of the chunk to H3's frame grid. Subject and
voice dependencies remain present. Reconnecting the same ID restores a binding;
unknown IDs and unsupported roles produce visible compiler issues. Unbinding the
last use makes that context global again. Overlapping bindings keep roles in story
time order and remove duplicates without alphabetic sorting. Conflicting audio
roles are diagnosed; the first supported role remains the compiler's choice.

Bound First/Last frames target the normalized Shot start/final frame. Video Continue
places the selected source's final frame at that Shot start. Each occurrence owns
one delivered chunk, without repeating the boundary in carried heads. Unbound
Contexts retain project-boundary behavior. See [Shot guides](NG-shot-guides.md) for
native frame slots, exact offsets and conflict priority. Audio Copy/Lock
separates the selected source window from Shot placement: each binding starts at
the normalized Shot start and carried chunks advance the source. Locks add before
encoding; Copy supplies a timed reference instruction. See [Shot audio](NG-shot-audio.md)
for intervals, clipping, carry priority and the distinction between guidance and a lock.

Spoken entries are separate from action text and media. The existing H3 compiler
receives their exact words, language and delivery, bound to the Subject owning
the image or a described narrator. Missing/non-Subject speakers use the described
narrator and produce an issue without losing the words. A carried shot retains
its action but does not repeat its dialogue. One entry represents one spoken
line. Voice/language/delivery fields cannot contain grammar delimiters or newlines.
Old inline dialogue still works. Avoid writing the same line in both places.

`locked_fields` protects `timing`, `text`, `media` and/or `spoken` from AI, while
manual editing stays possible. `draft` is a separate object and never compiles.
E46 offers ID-addressed proposals and selected-field Apply for existing Shots,
including legacy timed text. Unselected fields and protected fields survive;
own dialogue is preserved. Pending review is separate workflow state, while
the existing Shot `draft` metadata remains inactive and untouched. See
[Shot drafts](NG-shot-drafts.md) for validation, conflicts, stale/cancel and reload.
Scenes without existing Shots still accept the original scene proposal workflow.

The live preview and execution use the same parser/compiler. Chunk serialization
includes `shot_id`, media, dialogue and locks as additive v1 fields; older saves
without them remain readable. Invalid JSON/version/field types never silently
fall back to legacy timed text. The editor retains the original data for repair.

E43b validates the foundation with native Ref2VA → T2VA → Ref2VA renders through
both the external sampler loop and H3 Render Sequence. Actual model selection,
reference/Subject labels, exact prompt equality, AV shapes, per-chunk seeds and
copied carry-conditioning tails are observed. Scoped video/soundtrack/source-window
presentation is also checked against the installed native H3 tokenizer.
This is a three-step, 256-pixel function smoke test, not quality acceptance.
E44 adds mixed media indicators, explicit audio kinds and actual image/input-video
previews, with refresh, cancellation and missing-file feedback. See [shot media](NG-shot-media.md).
E45a adds timeline reorder and honest shared axes. E45b adds Shot audio placement
and lock mixing. E45c adds actual interior First/Last/Continue guides with native
conditioning and render checks. E46 adds ID-addressed drafts/Apply with field review,
protection and request lifecycle checks. Inspector provenance remains for E47.
Existing native sampler and Legacy paths
are preserved; the Director as a whole is unfinished.
