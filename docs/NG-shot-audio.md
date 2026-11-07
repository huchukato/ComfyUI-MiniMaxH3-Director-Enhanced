# Shot audio placement

Copy/Lock source start/end select samples from the input file. For a Context
bound to a structured Shot, that selection starts at the normalized Shot start,
stops at the Shot end or source end, and restarts for each subsequent binding.
The original Context options and Shot IDs remain unchanged. Chunk intersections
include the pinned head; a carried clip advances its source trim instead of
restarting. Gaps and the extra frames beyond the final Shot remain generated.
Unbound Contexts and legacy timed text retain their project-origin behavior.
Existing conflicting-role diagnostics and first-supported-role priority remain.

Copy passes the selected waveform to native H3 as a reference, with
`partially_copy` and an explicit target interval in the compiled retention note.
Its MediaRef `start_f` reports that interval's sampled-clip offset. Copy is model
guidance and does not promise exact sample placement or an identical soundtrack.
Manual prompt override replaces those generated timing instructions. Overlapping
Copy guidance yields to Lock in its held intervals.
Lock places and adds the selected waveforms before the native audio VAE encode,
clamps the summed track to [-1, 1], and holds the union of their latent intervals
with the native sampling noise mask. Input mono is duplicated to stereo.
Lock preserves encoded sound through sampling; VAE decode is lossy and latent
intervals round outward, so it is not a lossless PCM splice.

Video continuity stays enabled. Audio carry stays enabled when locks begin
outside the pinned audio head; a lock intersecting that head takes priority and
suppresses its audio carry conditioning. When there are no more locks, normal
audio carry resumes. No custom sampler or output audio replacement is added.

Interior First/Last/Continue bindings use normalized Shot boundaries and native
guide frame indices. See [Shot guides](NG-shot-guides.md) for their separate contract.

Validation: compiler/source-window/serialization tests, actual native audio
reference presentation, PCM mix/carry/mask tests and native GPU sampling through
both external Loop and Render Sequence. Synthetic tones verify placement and
mixing, not speech, music quality or subjective continuity.

## Audio lane clips (Studio, 2026-10-04)

A shot-bound Context restarts at every shot, which suits a voice line but not a song. For audio that should run
through the project, the Studio places **clips on audio lanes**. A clip is stored in the shot document's `audio`
list with `id`, `context_id`, story `start`/`end`, `offset` (seconds into the file), `mode` (`lock`, `copy`, `ref`)
and `lane`. Clip ranges are independent of shots and of render parts: each part receives the slice of the clip that
falls into its window (including the pinned head), with the source trim advanced by the clip's offset, so the sound
continues across the seam. A clip that runs past the project end is cut there and reported; one that starts after the end is not played and
reported. Past the end of its file a clip simply has no more sound.
`ref` clips are sent once as a reference to every part they touch. In FL2VA only `lock` is offered.
The offset is a second of the file itself, independent of the card's own Start/End; a clip dropped on a lane starts
at the card's Start and runs for its selected length. An offset past the end of the file plays nothing and is reported
(`audio_clip_past_file`). A Subject's voice card keeps its lane locks and copies; its voice reference is sent as before.
A document without `audio` behaves exactly as before.
The same audio card may lie on a lane and be bound to shots. Where its lane clips play, they win; for the rest of each
bound shot the binding plays with the card's own role (lock, copy or a reference sent once), continuing at the place in
the file its shot has reached, so the same sound is never laid twice over the same time.

Validation: core tests in `tests/ng/test_audio_clips.py`; a GPU run (FL2VA Turbo, two parts, song locked at story
1–7 s from file second 20) measured envelope correlation 0.97 at the intended place, best lag 1.00 s and 0.97 on
each side of the seam. No listening assessment.
