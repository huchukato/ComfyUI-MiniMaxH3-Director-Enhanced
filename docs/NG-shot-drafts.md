# Shot AI drafts and selective Apply

> **Studio (2026-10-04):** the Studio shows AI proposals as dashed shots (**AI: split into shots**) or as a
> suggestion in the shot panel (**AI: suggest / improve text**) with Accept/Discard, both over the same
> `/ng/direct` route. The field-by-field review list described below is no longer shown; stored `locked_fields`
> still protect fields in the draft contract.

Auto Direct uses the existing optional AI Loader. With existing Shots it asks for
an ID-addressed draft instead of a replacement scene. A separate Idea is optional
when Shots already exist. With no Shots it keeps the original scene proposal path.
Manual work and compilation never require a provider or apply a pending draft.

The result is `h3-director-draft`, schema version 1, with `patches` containing
`shot_id` and `fields`. Offered fields are `text`, `timing` (`start`/`end` seconds),
`media` and `spoken`; optional project fields are `soundscape` and `music`.
IDs must exist and occur once; unknown fields, invalid times, bindings and speakers
are rejected. Drafts cannot insert/delete/reorder Shots. Manual editor operations
remain available. Legacy timed Shots use their existing `legacy-shot-N` IDs.

Review compares current and proposed values. Only unprotected text fields start
selected; timing, media, dialogue and project sound remain explicit choices.
Apply resolves by ID, preserves every unselected field and skips protected fields.
Timing conflicts are checked across the resulting scene before any widget changes.
Project-only Apply does not rewrite the Shot document. Old whole-scene replacement
is refused when existing Shots need an ID-addressed draft.

Existing structured dialogue retains its exact words, fields and order; proposals
may append reviewed new lines. Existing inline `@...: ...` lines stay in their
original Shot when action prose changes. Such lines are conservatively preserved
as written, including described-voice and native reference syntax. Proposed inline
dialogue is omitted when these existing lines are present. Manual edits can still
change any dialogue or protected field.

A pending review is stored separately in the Director's workflow properties as
`ng_direction_draft`, version 1, with suggestion, selected fields and the input
snapshot. It never contributes to compiler or sampling inputs. The existing Shot
`draft` metadata stays untouched. Save/Reload restores the review; project, Context,
provider or native loader changes make it stale and block Apply. Cancel/Discard
leave active inputs unchanged. Late responses after Cancel/removal are ignored.

Both HTTP and native CLIP/Encoder routes use the same validation. AI receives
descriptions, bindings and Shot text, not local media files or resolved API keys.
Passing this contract does not establish AI prompt quality or H3 video quality.
The encoder must support useful text generation: malformed JSON or unsupported
fields produce an error and leave active Shots unchanged. A local conditioning
encoder is not automatically a suitable generative AI model.
