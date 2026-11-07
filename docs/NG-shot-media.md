# Shot media display contract

> **Studio (2026-10-04):** shots and Content cards are now shown in the Studio ([guide](NG.md#the-studio)); the
> old shot cards, their media marks and **Refresh previews** are gone. Previews still come from `/ng/media`.

Shots show the material the user assigned, mentioned or selected as a dialogue
speaker. This display does not assert that an asset is present in a generated
frame; the compiler Inspector describes the actual chunk conditioning.

Each assigned context retains its ID, name, role and card color. Mixed shots can
show several marks. Audio marks follow explicitly selected content: voice/speech,
singing, music, ambience or sound effect. Unclassified audio uses a generic audio
mark. `singing` is an additive audio content choice; no API or recognition is
needed. Action text and original dialogue also have distinct marks. Disconnected
bindings remain visible. Text mentions use the same Unicode/name-boundary parser
as highlighted references, so @Bob does not match @Bobby.

Image/video previews use only their connected input file, through the existing
local `/ng/media` endpoint. Video displays the first decoded input frame, even
when a different source interval is selected for generation; the caption says
which frame is shown. All visual contexts can be previewed. No generated preview
or embedded thumbnail is stored in the workflow. Loading, missing sources and
decode failures retain the type mark and display a readable status.

Preview requests are shared per file/media within an editor and aborted when it
is removed. Refresh previews reloads an overwritten file at the same path.
Source changes cannot apply an old response to a new preview. Text edits update
marks and mentions without replacing the focused text control. IDs, media roles,
dialogue, locks, active text and saved node size remain unchanged by previewing.

Verification requires content/identity and async lifecycle tests, actual file
decoding, missing-file/error responses and browser assignment/refresh/reload.
The existing compiler/sampler stays unchanged; GPU generation is unnecessary
for this display behavior. Overall visual design and render quality acceptance
remain separate.
