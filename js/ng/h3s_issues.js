// Short headings for the plan's notes. The detail stays the planner's own sentence.
const TITLES = {
  anchor_multiple: "Several first/last frames", voice_unbound: "Voice without character", voice_extra_take: "Extra voice take",
  usage_unknown: "Unknown use", usage_pending: "Time missing", text_empty: "Empty text card",
  subject_target_invalid: "Invalid assignment", subject_look_alike: "Same figure twice?", part_capped: "Render part shortened", speaker_unknown: "Unknown speaker", source_shared: "File used several times",
  source_missing: "File missing", shots_preamble: "Text without time", shot_speaker_unknown: "Speaker not connected",
  shot_speaker_unbound: "Speaker without picture", shot_role_unknown: "Role does not fit", shot_overlap: "Shots overlap",
  shot_gap: "Gap between shots", shot_empty_range: "Shot without length", shot_context_unknown: "Content not connected",
  shot_clipped: "Shot shortened", shot_after_end: "Shot after project end", reference_disabled: "Not used in First/last frame mode",
  prompt_override: "Manual prompt active", planner: "Compiler note", no_text: "No text", no_continuity: "Hard cuts",
  length_snapped: "Length fitted to H3 grid", late_change: "Change just after a seam", guide_outside_project: "Time outside project",
  content_unknown: "Unknown content", canvas_snapped: "Size on 32 grid", canvas_from_image: "Size from picture",
  canvas_default: "Default size", audio_short: "Audio too short", audio_roles: "Several audio roles", audio_dulling: "Audio gets duller",
  audio_clip_unknown: "Audio clip without audio Content", audio_clip_clipped: "Audio clip shortened", audio_clip_after_end: "Audio clip after project end", audio_clip_past_file: "Audio clip past file end",
  asset_relation_unavailable: "Assignment not possible",
};

export function issueLine(issue) {
  const title = TITLES[issue.code] || "Note";
  return `${title}${issue.ref ? ` (${issue.ref})` : ""}: ${issue.text}`;
}
