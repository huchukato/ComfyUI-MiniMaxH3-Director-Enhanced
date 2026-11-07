# Story and generation timeline contract

The Director's Studio, in the node or full screen, has a shared timeline with
Shots, independent Audio lanes, Control video and the automatically planned Render parts.
All tracks scroll together; track names remain visible. Add shots and audio lanes
with the buttons above the tracks; drag connected Content onto a shot or track.
Each Audio/Control track header also offers a **+** source picker. It lists only
connected sources suitable for that track and inserts into the next free range.
New Ref2VA audio clips inherit the card's Lock/Copy choice; other audio references
start as Ref. FL2VA clips start as Lock. Existing clip modes remain their own.

Use **+ / −** to zoom, **Fit project** for the whole duration or **Fit selection**
to work on a short selected shot, audio clip or control clip. The horizontal
scrollbar moves through a zoomed project. Selection and incoming plan responses
keep the view in place. Save/Reload preserves zoom and horizontal position in
the Director's workflow properties, separately from the shot/clip data.

Drag a block to move it, or an edge to trim. Left-trimming audio and control
clips advances their source offset so the remaining material stays at the same
story time. Moving a clip keeps its source offset. Aborted pointer gestures
restore their initial position without saving the preview.

The curved arrows undo/redo timeline project edits, including duration changes
and their clipped media. Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) work outside text
fields; text fields retain their normal text undo. History is local to this
open Studio and is cleared after an external project change. Saving stores the
current project, not the undo stack. Undo is disabled during an AI operation.
ComfyUI's deferred graph-undo handler excludes key events already handled by
the Studio through its exported ChangeTracker API. Other graph shortcuts keep
their normal behavior; closing a Studio releases its key listener.

Select a block with the mouse, or Tab to it and press Enter/Space. Left/Right
arrows move the selection by 0.1 s; Shift uses 1 s. Delete/Backspace removes only
that shot or clip. The inspector offers precise times and source offset. Long
shots retain their labels when the view is scrolled into their middle.
Number edits survive asynchronous plan redraws until confirmed by leaving the
field. A changed project clears the old render-part display while replanning.

Control clips use their own lane, not image/video-reference slots.
The description on a Control video card is a saved note about the source;
it does not describe the generated scene. Put the target figure and scene in
the shot text. Ordinary Motion, Camera, Structure and Continue video roles
still contribute their descriptions to the prompt.

For ControlNet, a partially
covered render part holds its nearest control edge frames over uncovered time;
parts with no control clip do not use ControlNet. The selected clip's inspector
and the plan warnings explain this, including when shorter render parts help.

Story shots and generation chunks share one time axis covering both requested
and delivered duration. The requested end remains visible when H3's frame grid
extends or shortens output. Labels derive from integer frame counts at native
24 fps; sampled frames include the pinned head, delivered frames exclude it.
The preceding continuity frames come from the earlier render part or from a
Continue video source; they are not added to the new output duration.
The existing planner remains the authority; this editor does not replan chunks.

Selecting a shot selects its card/bar and highlights chunks containing its stable
ID in the actual compiler preview, including carry/head intersections. Chunk
tooltips describe delivered time, sampled/head frames and participating shots.
After a story/timing edit the prior chunk plan is cleared until a new response
arrives; stale geometry must not look current.

Dragging a story bar moves it; dragging an edge resizes it within project bounds.
A cancelled gesture restores its initial data. Pointer coordinates use the DOM
track width (including ComfyUI zoom). Timeline selection preserves shot identity.
Earlier/later controls swap chronological neighbors, preserving each duration,
their intervening gap and all text/media/dialogue/locks/drafts. Overlapping or
invalid ranges are left unchanged with repair feedback. Manual editing remains
allowed for fields protected from AI. Reordering does not rewrite prose.

Required proofs: real planner frame boundaries for 10 seconds, 5+5 targets and
120 seconds/12 targets; UI geometry, selection/carry membership, stale clearing,
drag/resize/cancel, reorder identity and Save/Reload. Editor geometry is verified
separately from real media rendering. Audio placement/mixing and interior frame
anchors use the existing execution contracts; see [shot audio](NG-shot-audio.md).
