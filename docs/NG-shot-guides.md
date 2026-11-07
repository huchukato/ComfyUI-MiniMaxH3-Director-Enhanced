# Shot boundary guides

A bound First frame anchors the normalized Shot start; Last frame anchors its
exclusive end minus one frame. Continue anchors the last frame of the selected
input-video window at the Shot start. The source window is independent of target
time. Reusing a Context in later Shots creates distinct boundary guides.
Unbound Contexts and legacy timed text retain their project boundary behavior.

Every guide belongs to the chunk delivering its target frame. It is not repeated
in the following chunk's pinned head. Native H3 Add Guide accepts that exact local
pixel-frame index; the 17k+5 sampling grid does not round the guide's position.
The previous output's pins retain priority inside the head. Guides at the first
delivered frame start at `head_frames`, outside that protected interval.

First/Last at a sampled clip edge can use native frame slots on the Base path.
Interior guides and guides combined with Ref2VA use native Add Guide and have no
numbered Picture token. Existing reference labels remain owned by their actual
inputs; named guide mentions use prose. Timed Keyframe/Storyboard keeps its
explicit absolute scene time, rather than becoming a Shot-relative offset.

For conflicting Shot boundary bindings at one target frame, the first binding in
story/binding order wins and a compiler issue names the selected and skipped
Contexts. Existing global frame slots take priority at their shared edge. Global
explicit timed guides retain the existing native chaining behavior.

Continue supplies one boundary frame. Motion/Camera can independently provide a
video reference. Continue does not replay source-video history or copy its audio;
native Loop continuity from the previous generated output remains separate.
Raw prompt override changes written instructions, while guides still condition
the native model. Image resemblance and transition quality need render review.
