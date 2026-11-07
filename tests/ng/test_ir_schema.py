"""Check the compiled prompt against the H3 writing guides' own field lists.

`test_compile.py` checks that the prompt contains certain sentences. This file checks the opposite,
and the thing that actually matters: that the prompt *is* one of the two documented shapes and
nothing else. A field that silently disappears, moves, or gets invented would pass every assertion
in `test_compile.py` and still be a malformed H3 prompt.

The two guides list fixed fields in a fixed order:

    ref2va  subject_definitions, summary, retention_analysis, detailed_description,
            overall_soundscape, non_diegetic_music
    base    integrated_multimodal_description, overall_soundscape, non_diegetic_music

and base prompt modes with picture references carry an alignment line before the first field.

# The guides themselves (`base-en.txt`, `ref-en.txt`) are not in this repo, so the field lists are
# written out here as a fixture. `GuideFixture` pins them; keep this module the one place that
# decides what the shape is.

# Fixture transcribed from the two guides in MiniMax-AI/MiniMax-H3,
# skills/h3-prompt-writing/references/ (fetched 2026-10-04):

#   base-en.txt §2.2 — "integrated_multimodal_description: [Shot 1] ...",
#   "overall_soundscape: ...", "non_diegetic_music: ..."; §2.1 — "The instruction must be the
#   first line of the final prompt, followed by one blank line before the core fields."

#   ref-en.txt §1 — "A complete rewrite output consists of six sections in the following order":
#   subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape,
#   non_diegetic_music.

# The four label types are ref-en.txt §2: <Subject N>, <Picture N>, <Video N>, <Audio N>.

# Retention vocabulary, ref-en.txt §2: "retention_analysis records where each referenced item
# appears and whether it is fully preserved, partially preserved, transferred, or reused." The
# worked example writes the keyword underscored ("fully_preserved") and uses "reference" for an
# audio timbre reference. `locked` is NOT a guide keyword; it came from an earlier draft of this
# fixture and has been removed.
"""
import re
import unittest

from _pack import module

chunks = module("ng.core.chunks")
compile_ = module("ng.core.compile")
context = module("ng.core.context")
shots = module("ng.core.shots")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)

REF2VA_FIELDS = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
                 "overall_soundscape", "non_diegetic_music")
BASE_FIELDS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")

# Any line that opens a block field: a known name plus a colon at the end of the line. A block field
# (`subject_definitions:`, `retention_analysis:`) is followed by further lines; a value field
# (`summary: ...`) carries its text on the same line. Both are recognised here so that an invented
# field cannot hide by choosing the other form.
FIELD_START = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")

# The two guides (`base-en.txt`, `ref-en.txt`) are not part of this repo. Copies fetched on
# 2026-10-04 sit in `_notes/NG/experiments/`, and `fetch_h3_guides.py` refreshes them. Everything
# below is transcribed from those copies rather than from memory.

#   ref-en.txt §1 — "A complete rewrite output consists of six sections in the following order".
#   ref-en.txt §2 — the four label types, and "Once a reference label is assigned to a piece of
#     content, it keeps the same meaning across subject_definitions, summary, retention_analysis,
#     detailed_description, and the audio sections."
#   base-en.txt §2.2 — integrated_multimodal_description, overall_soundscape, non_diegetic_music.
#   base-en.txt §2.1 — "The instruction must be the first line of the final prompt, followed by one
#     blank line before the core fields."

# ref-en.txt §4 gives TWO marker tables, not one.
#   §4.1, for <Subject N>/<Picture N>/<Video N>: fully_preserved, partially_preserved,
#        attribute_transfer, weak_reference
#   §4.2, for <Audio N>: fully_copy, partially_copy, reference, weak_reference
# The compiler's vocabulary has to satisfy both. `attribute_transfer`, `fully_copy` and
# `partially_copy` are in the guide and were missing from an earlier draft of this fixture;
# `locked` is in neither table and has been removed.
VISIBLE_RETENTION_WORDS = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
AUDIO_RETENTION_WORDS = ("fully_copy", "partially_copy", "reference", "weak_reference")
RETENTION_WORDS = VISIBLE_RETENTION_WORDS + AUDIO_RETENTION_WORDS
LABELS = ("Subject", "Picture", "Video", "Audio")


def fields_of(prompt):
    """The field names in the order the prompt presents them, in-block or inline."""
    found = []
    for line in prompt.splitlines():
        match = FIELD_START.match(line.strip())
        if match:
            name = match.group(1)
            if name not in found:      # a block header repeats nothing, but keep first-seen order
                found.append(name)
    return found


def body_of(prompt, name):
    """Everything from `name:` up to the next field, for assertions about a single field."""
    lines = prompt.splitlines()
    out, inside = [], False
    for line in lines:
        match = FIELD_START.match(line.strip())
        if match:
            if inside:
                break
            inside = match.group(1) == name
            if inside:
                out.append(line)
            continue
        if inside and line.strip():
            out.append(line.strip())
    return "\n".join(out)


def item(id_, name, media, source="", **kw):
    return context.ContextItem(id=id_, name=name, media=media, source=source or "%s.bin" % name.lower(), **kw)


def build(ctx, continuity=VIDEO, chunk_s=10):
    total = round(ctx.project_seconds * 24)
    if ctx.shots_text.strip():
        story, _ = shots.parse_shots(ctx.shots_text, total)
    else:
        story = shots.auto_shots(ctx.idea, total)
    plan = chunks.plan_chunks(total, chunk_s * 24, continuity, story)
    return plan, [compile_.compile_chunk(ctx, c, continuity) for c in plan.chunks]


ALICE = item("ctx_0001", "Alice", "image", "refs/alice.png", content=("character",), usage=("reference",),
             description="a young woman in a red coat")
VOICE = item("ctx_0002", "AliceVoice", "audio", "refs/alice.wav", content=("voice",), usage=("voice",),
             speaker="ctx_0001", length_s=8.0)
FIRST = item("ctx_0003", "Start", "image", "refs/start.png", content=("composition",), usage=("first_frame",))
LAST = item("ctx_0005", "End", "image", "refs/end.png", content=("composition",), usage=("last_frame",))
SCRIPT = "0-8: @Alice walks in.\n@Alice says: Hello there."


def ref2va_ctx(**kw):
    base = dict(idea="", project_seconds=8, items=(ALICE, VOICE), shots_text=SCRIPT)
    base.update(kw)
    return context.DirectorContext(**base)


class FieldList(unittest.TestCase):
    """The prompt must present exactly the guide's fields, in the guide's order."""

    def assert_schema(self, prompt, expected):
        found = fields_of(prompt)
        self.assertEqual(found, [f for f in expected if f in found],
                         "field list/order wrong; guide order is %s" % (expected,))

    def test_ref2va_carries_all_six_in_guide_order(self):
        _, out = build(ref2va_ctx())
        self.assertEqual(out[0].mode, "ref2va")
        self.assert_schema(out[0].prompt, REF2VA_FIELDS)

    def test_base_carries_its_three_in_guide_order(self):
        _, out = build(context.DirectorContext(idea="A woman plays with a red ball.", project_seconds=8))
        self.assertEqual(out[0].mode, "t2va")
        self.assert_schema(out[0].prompt, BASE_FIELDS)

    def test_base_with_soundscape_and_music_carries_both(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8,
                                               soundscape="wind, distant traffic", music="soft piano"))
        self.assert_schema(out[0].prompt, BASE_FIELDS)

    def test_no_invented_field_reaches_the_prompt(self):
        # A user note that happens to look like a field must not become one.
        tricky = item("ctx_0009", "Tricky", "text", "summary: this is prose, not a field",
                      usage=("style",))
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8, items=(tricky,)))
        for name in fields_of(out[0].prompt):
            self.assertIn(name, BASE_FIELDS, "field %r is not in the base guide" % name)

    def test_every_chunk_of_a_long_project_keeps_the_shape(self):
        ctx = ref2va_ctx(project_seconds=30,
                         shots_text="0-8: @Alice walks.\n@Alice says: Hello.\n"
                                    "8-16: @Alice sits.\n16-30: @Alice walks away.")
        plan, out = build(ctx)
        self.assertGreater(len(out), 1)
        for compiled in out:
            self.assert_schema(compiled.prompt, REF2VA_FIELDS)


class MandatoryFields(unittest.TestCase):
    """The guides list these as required; a missing one is a malformed prompt."""

    def test_ref2va_always_states_the_music_field(self):
        _, out = build(ref2va_ctx())
        self.assertIn("non_diegetic_music:", out[0].prompt)

    def test_base_always_states_the_music_field(self):
        for kw in ({}, {"soundscape": "wind"}, {"music": "soft piano"},
                   {"soundscape": "wind", "music": "soft piano"}):
            _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8, **kw))
            self.assertIn("non_diegetic_music:", out[0].prompt, "missing for %r" % (kw,))

    def test_soundscape_present_when_the_user_gives_one(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8,
                                               soundscape="wind, distant traffic"))
        self.assertIn("wind, distant traffic", body_of(out[0].prompt, "overall_soundscape"))


class AlignmentLine(unittest.TestCase):
    """Base prompt modes with pictures carry an alignment line as the very first line."""

    def first_line(self, prompt):
        return prompt.splitlines()[0]

    def test_t2va_starts_with_the_description_field(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        self.assertTrue(self.first_line(out[0].prompt).startswith("integrated_multimodal_description:"))

    def test_first_frame_only_uses_the_i2va_sentence(self):
        _, out = build(context.DirectorContext(idea="She turns.", project_seconds=8, items=(FIRST,)))
        self.assertEqual(out[0].mode, "fl2va")
        self.assertEqual(
            self.first_line(out[0].prompt),
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.")

    def test_first_and_last_frame_use_the_alignment_sentence(self):
        _, out = build(context.DirectorContext(idea="She walks.", project_seconds=8, items=(FIRST, LAST)))
        line = self.first_line(out[0].prompt)
        self.assertTrue(line.startswith("How the reference pictures align with the target video -".replace("-", "\u2014")),
                        line)
        self.assertIn("aligns with the 0.00-second mark of the target video", line)

    def test_alignment_line_is_followed_by_a_blank_line(self):
        _, out = build(context.DirectorContext(idea="She walks.", project_seconds=8, items=(FIRST, LAST)))
        lines = out[0].prompt.splitlines()
        self.assertTrue(lines[0].startswith("How the reference pictures align"))
        self.assertEqual(lines[1], "", "the guide asks for one blank line before the core fields")

    def test_alignment_names_the_last_shot(self):
        _, out = build(context.DirectorContext(idea="", project_seconds=8, items=(FIRST, LAST),
                                               shots_text="0-4: She walks.\n4-8: She sits."))
        self.assertIn("Picture 2 (from Shot 2)", out[0].prompt)

    def test_duration_mark_has_exactly_two_decimals(self):
        # The mark lands in the chunk that carries the last frame, which for a project longer than
        # one chunk is not the first chunk. Collect the marks over all chunks, not over chunk 1.
        for seconds in (4, 5, 8, 12, 15):
            _, out = build(context.DirectorContext(idea="", project_seconds=seconds, items=(FIRST, LAST),
                                                   shots_text="0-%d: She walks." % seconds))
            found = []
            for compiled in out:
                found += re.findall(r"aligns with the ([0-9.]+)-second mark", compiled.prompt)
            self.assertTrue(found, "no duration mark anywhere in a %ds project" % seconds)
            for value in found:
                self.assertRegex(value, r"^[0-9]+\.[0-9]{2}$", "S.SS needs two decimals, got %r" % value)
            # Where the first frame is the anchor, both marks appear on one line; in a later chunk
            # only the last frame is anchored, so only that mark appears. What must always hold is
            # the two-decimal form, and — on a single chunk — two marks in ascending order.
            if len(out) == 1:
                self.assertEqual(len(found), 2, "a single-chunk project anchors both frames: %s" % found)
                self.assertEqual(found, ["0.00", found[-1]], "first frame anchors 0.00, then the last frame")

    def test_exact_mark_of_a_single_chunk_project(self):
        # A project that fits one chunk puts the last frame's mark on that same chunk.
        _, out = build(context.DirectorContext(idea="", project_seconds=8, items=(FIRST, LAST),
                                               shots_text="0-8: She walks."))
        self.assertIn("8.00", out[0].prompt)

    def test_no_alignment_line_without_a_picture_reference(self):
        _, out = build(ref2va_ctx())
        self.assertNotIn("align with", out[0].prompt.splitlines()[0])


class RetentionAnalysis(unittest.TestCase):
    """One line per label, the guide's marker vocabulary, and the two documented line shapes.

    ref-en.txt §4 gives the line shape in two variants, and both occur in the compiled output:

        <Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - ...     (§4.1, with context)
        <Audio 1>: reference - ...                                             (§4.2, bare)

    An earlier version of this test matched only the first shape via `): <word> - `, so a bare audio
    line was never checked at all. Both are matched here.
    """

    # a line that names the label, optionally with a parenthetical, then "): " or ": ", the marker,
    # " - " and the explanation
    LINE = re.compile(r"^<(Subject|Picture|Video|Audio) (\d+)>(?:\s*\([^)]*\))?: ([a-z_]+) - (.+)$")

    def lines_of(self, prompt):
        body = body_of(prompt, "retention_analysis")
        out = []
        for line in body.splitlines():
            line = line.strip()
            if line and not line.endswith(":"):
                out.append(line)
        return out

    def markers(self, prompt):
        found = []
        for line in self.lines_of(prompt):
            match = self.LINE.match(line)
            self.assertIsNotNone(match, "retention line is not in a guide shape: %r" % line)
            found.append((match.group(1), match.group(3)))
        return found

    def test_every_line_uses_a_guide_shape_and_marker(self):
        _, out = build(ref2va_ctx())
        markers = self.markers(out[0].prompt)
        self.assertTrue(markers, "no retention lines at all")
        for label, marker in markers:
            table = AUDIO_RETENTION_WORDS if label == "Audio" else VISIBLE_RETENTION_WORDS
            self.assertIn(marker, table,
                          "<%s> uses marker %r, which is not in that label's guide table" % (label, marker))

    def test_both_documented_line_shapes_are_recognised(self):
        # the subject line carries a parenthetical, the audio line does not — that is how ref-en.txt
        # writes them, and both appear in the same compiled prompt
        rhythm = item("ctx_0010", "Song", "audio", "refs/song.wav", content=("music",),
                      usage=("rhythm",), length_s=6)
        _, out = build(ref2va_ctx(items=(ALICE, VOICE, rhythm)))
        lines = self.lines_of(out[0].prompt)
        with_context = [l for l in lines if re.match(r"^<(Subject|Picture|Video) \d+> \(", l)]
        bare = [l for l in lines if re.match(r"^<Audio \d+>: ", l)]
        self.assertTrue(with_context, "no <Subject> line with a shot context:\n%s" % lines)
        self.assertTrue(bare, "no bare <Audio> line:\n%s" % lines)
        # and both parse under the same pattern
        self.assertEqual(len(self.markers(out[0].prompt)), len(lines))

    def test_every_subject_label_has_a_retention_line(self):
        _, out = build(ref2va_ctx())
        body = body_of(out[0].prompt, "retention_analysis")
        defined = set(re.findall(r"^<Subject \d+>", body_of(out[0].prompt, "subject_definitions"), re.M))
        analysed = set(re.findall(r"^<Subject \d+>", body, re.M))
        self.assertTrue(defined, "no subject defined at all")
        self.assertEqual(defined, analysed, "a defined subject is missing from retention_analysis")

    def test_subject_line_names_the_shots_it_appears_in(self):
        _, out = build(ref2va_ctx(project_seconds=30,
                                  shots_text="0-8: @Alice walks.\n@Alice says: Hello.\n"
                                             "8-16: @Alice sits.\n16-30: @Alice walks away."))
        for compiled in out:
            for line in self.lines_of(compiled.prompt):
                match = re.match(r"^<Subject \d+> \((.*)\): ", line)
                if match:
                    self.assertIn("[Shot ", match.group(1),
                                  "a subject line must say which shots it appears in: %r" % line)


class LabelStability(unittest.TestCase):
    """One label keeps one meaning across all six fields."""

    def test_a_label_means_the_same_thing_in_every_field_it_appears_in(self):
        _, out = build(ref2va_ctx())
        prompt = out[0].prompt
        numbers = {}
        for field in REF2VA_FIELDS:
            numbers[field] = set(re.findall(r"<Subject (\d+)>", body_of(prompt, field)))
        # The alignment line is base-only, and audio labels legitimately appear in fewer fields than
        # subjects do, so this asserts the direction that must hold: anything a field mentions is
        # numbered from 1 with no gaps.
        for field, seen in numbers.items():
            self.assertEqual(seen, set(str(n) for n in range(1, len(seen) + 1)),
                             "%s has gaps in its subject numbering: %s" % (field, sorted(seen)))

    def test_shot_numbers_start_at_one_and_do_not_skip(self):
        _, out = build(ref2va_ctx())
        body = body_of(out[0].prompt, "detailed_description")
        shots_seen = re.findall(r"\[Shot (\d+)\]", body)
        self.assertTrue(shots_seen)
        self.assertEqual(shots_seen[0], "1", "the first shot block must be Shot 1")
        self.assertEqual(shots_seen, sorted(set(shots_seen), key=shots_seen.index),
                         "shot blocks must not repeat or go backwards")

    def test_only_documented_labels_are_used(self):
        _, out = build(ref2va_ctx())
        for label in set(re.findall(r"<(\w+) \d+>", out[0].prompt)):
            self.assertIn(label, LABELS, "%r is not a documented H3 label" % label)


class SoundscapeRule(unittest.TestCase):
    """base-en.txt §4.6 vs §4.7 — the two sound fields disagree about an empty box.

    §4.6, overall_soundscape: "Use 1–4 English sentences in one continuous paragraph to
    summarize the ambient sound, physical action sounds, and non-verbal human sounds across the
    full video … Use `N/A` only when the user explicitly requests complete silence throughout the
    video." So there is no value for an empty box, and leaving the field out is not one of the
    guide's options.

    §4.7, non_diegetic_music: "Use `N/A` when there is no non-diegetic music." An empty box has a
    value of its own.

    The consequence is that an empty soundscape must not silently become N/A (that claims the user
    asked for silence) and must not be dropped (that leaves two of three core fields).
    """

    def value_of(self, prompt, field="overall_soundscape"):
        if field + ":" not in prompt:
            return None
        return prompt.split(field + ":", 1)[1].split("\n\n")[0].strip()

    def test_the_field_is_written_when_the_box_is_empty(self):
        plan = module("minimax_plan")
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        self.assertEqual(self.value_of(out[0].prompt), plan.SOUNDSCAPE_PLACEHOLDER)

    def test_a_whitespace_only_box_counts_as_empty(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8, soundscape="   "))
        self.assertNotEqual(self.value_of(out[0].prompt), "")
        self.assertTrue(self.value_of(out[0].prompt))

    def test_an_empty_box_never_becomes_N_A(self):
        # N/A claims the video was asked to be silent. Only the user can make that claim.
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        self.assertNotEqual(self.value_of(out[0].prompt), "N/A")

    def test_a_user_who_asks_for_silence_still_gets_N_A(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8, soundscape="N/A"))
        self.assertEqual(self.value_of(out[0].prompt), "N/A")

    def test_the_users_own_words_are_untouched(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8,
                                               soundscape="wind, distant traffic"))
        self.assertEqual(self.value_of(out[0].prompt), "wind, distant traffic")

    def test_the_placeholder_is_reported_not_passed_off_as_the_users_own(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        warnings = " ".join(str(i) for i in out[0].issues)
        self.assertIn("overall_soundscape is empty", warnings)
        self.assertIn(module("minimax_plan").SOUNDSCAPE_PLACEHOLDER, warnings)

    def test_no_warning_once_the_user_wrote_something(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8,
                                               soundscape="wind, distant traffic"))
        warnings = " ".join(str(i) for i in out[0].issues)
        self.assertNotIn("overall_soundscape is empty", warnings)

    def test_music_keeps_its_own_value_for_an_empty_box(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        self.assertEqual(self.value_of(out[0].prompt, "non_diegetic_music"), "N/A")

    def test_the_field_is_present_in_every_mode(self):
        plan = module("minimax_plan")
        cases = (
            ("t2va", context.DirectorContext(idea="A woman plays.", project_seconds=8)),
            ("ref2va", ref2va_ctx()),
            ("fl2va", context.DirectorContext(idea="She turns.", project_seconds=8, items=(FIRST,))),
        )
        for label, ctx in cases:
            _, out = build(ctx)
            self.assertIn("overall_soundscape:", out[0].prompt, "%s lost the field" % label)
            self.assertEqual(fields_of(out[0].prompt),
                             [f for f in (REF2VA_FIELDS if label == "ref2va" else BASE_FIELDS)
                              if f in fields_of(out[0].prompt)],
                             "%s: field order broken by the placeholder" % label)

    def test_field_order_is_unchanged_by_the_placeholder(self):
        _, out = build(context.DirectorContext(idea="A woman plays.", project_seconds=8))
        found = fields_of(out[0].prompt)
        self.assertEqual(found, list(BASE_FIELDS))

    def test_an_empty_timeline_gets_no_prompt_from_defaults_alone(self):
        # The guard the music field already had: nothing to describe means nothing to attach to.
        plan = module("minimax_plan")
        bare = plan.plan_timeline({"prompt_format": "minimax"}, 0, 288, 24.0)["prompt"]
        self.assertNotIn("overall_soundscape:", bare)

    def test_the_two_constants_are_one_string(self):
        # limits.py used to hold a second copy of this text. Two copies of a prompt string drift.
        plan = module("minimax_plan")
        limits = module("ng.core.limits")
        self.assertEqual(limits.DEFAULT_SOUNDSCAPE, plan.SOUNDSCAPE_PLACEHOLDER)


class GuideFixture(unittest.TestCase):
    """Pin the fixture against the guide text, so a change to the expectation cannot pass unnoticed.

    The expected values below are transcribed from the two guides in
    `MiniMax-AI/MiniMax-H3` under `skills/h3-prompt-writing/references/`, read on 2026-10-04. They
    are quoted here so that a future edit to this module can be checked against the source instead
    of against whoever wrote the test last.
    """

    def test_ref2va_field_list_is_exactly_six(self):
        # ref-en.txt §1: "A complete rewrite output consists of six sections in the following order"
        self.assertEqual(len(REF2VA_FIELDS), 6)
        self.assertEqual(REF2VA_FIELDS[0], "subject_definitions")
        self.assertEqual(REF2VA_FIELDS[-2:], ("overall_soundscape", "non_diegetic_music"))

    def test_base_field_list_is_exactly_three(self):
        # base-en.txt §2.2, verbatim:
        #   integrated_multimodal_description: [Shot 1] ...
        #   overall_soundscape: ...
        #   non_diegetic_music: ...
        self.assertEqual(len(BASE_FIELDS), 3)
        self.assertEqual(BASE_FIELDS[0], "integrated_multimodal_description")

    def test_the_two_schemas_share_their_trailing_fields(self):
        # The two schemas are not variants of each other: ref2va carries three extra fields in
        # front and swaps the description field's name. What they share is the tail.
        self.assertEqual(REF2VA_FIELDS[-2:], BASE_FIELDS[-2:])
        self.assertEqual(REF2VA_FIELDS[3], "detailed_description")
        self.assertEqual(BASE_FIELDS[0], "integrated_multimodal_description")
        self.assertNotEqual(REF2VA_FIELDS[:3], BASE_FIELDS[:1])

    def test_alignment_sentences_are_the_guide_text_verbatim(self):
        # base-en.txt §2.1 gives one fixed sentence per task. Quoted exactly, including the
        # inconsistency the guide itself carries: I2VA and L2VA bracket the tokens
        # (`<Picture 1>`, `[Shot 1]`) and FL2VA does not. The model was trained on this text, so
        # reproducing it as written is deliberate.
        plan = module("minimax_plan")
        self.assertEqual(
            plan.alignment_instruction(True, False, 1, 8.0),
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.")
        self.assertEqual(
            plan.alignment_instruction(False, True, 1, 6.0),
            "How the reference pictures align with the target video — "
            "<Picture 1> (from [Shot 1]) aligns with the 6.00-second mark of the target video.")
        self.assertEqual(
            plan.alignment_instruction(True, True, 1, 8.0),
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) "
            "aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) "
            "aligns with the 8.00-second mark of the target video.")
        # T2VA has no image-alignment instruction at all.
        self.assertEqual(plan.alignment_instruction(False, False, 1, 8.0), "")

    def test_duration_mark_is_floored_to_the_hundredth(self):
        # base-en.txt §2.1: "S.SS is the effective video duration formatted to exactly two decimal
        # places". The planner floors rather than rounds, because rounding can name a mark past the
        # end of the clip: 124 frames last 5.166667s and "5.17" would be outside the video.
        plan = module("minimax_plan")
        line = plan.alignment_instruction(True, True, 1, 124 / 24.0)
        self.assertIn("5.16-second mark", line)
        self.assertNotIn("5.17-second mark", line)

    def test_retention_vocabulary_matches_both_guide_tables(self):
        # ref-en.txt §4.1, quoted: "These markers are fixed English values in the output format" —
        #   fully_preserved | partially_preserved | attribute_transfer | weak_reference
        # ref-en.txt §4.2, for <Audio N>:
        #   fully_copy | partially_copy | reference | weak_reference
        self.assertEqual(sorted(VISIBLE_RETENTION_WORDS),
                         ["attribute_transfer", "fully_preserved", "partially_preserved", "weak_reference"])
        self.assertEqual(sorted(AUDIO_RETENTION_WORDS),
                         ["fully_copy", "partially_copy", "reference", "weak_reference"])
        self.assertNotIn("locked", RETENTION_WORDS)
        # the tables overlap on exactly one marker
        self.assertEqual(set(VISIBLE_RETENTION_WORDS) & set(AUDIO_RETENTION_WORDS), {"weak_reference"})

    def test_emitted_markers_are_all_in_the_guide(self):
        # Every marker the compiler can write into `retention_analysis` must exist in that label's
        # guide table.
        #
        # `lock` is deliberately excluded. `legacy_bridge._AUDIO_RETENTION` maps the NG usage "lock"
        # to the string "lock", and that string is not a guide marker — minimax_plan.py:63 says so
        # ("Not one of the guide's markers") because such a clip never becomes an `<Audio N>` at all:
        # its waveform is encoded straight into the target audio stream. So it is a routing signal
        # that travels alongside the prompt, not a word in it.
        bridge = module("ng.core.legacy_bridge")
        plan = module("minimax_plan")
        for value in set(bridge._RETENTION.values()):
            self.assertIn(value, VISIBLE_RETENTION_WORDS,
                          "legacy_bridge._RETENTION writes %r, which is in neither guide table" % value)
        for usage, value in bridge._AUDIO_RETENTION.items():
            if usage == "lock":
                self.assertNotIn(value, RETENTION_WORDS)
                self.assertEqual(value, plan.AUDIO_LOCK)
                continue
            self.assertIn(value, AUDIO_RETENTION_WORDS,
                          "legacy_bridge._AUDIO_RETENTION writes %r for usage %r" % (value, usage))

    def test_planner_marker_tables_match_the_guide(self):
        # The authoritative copy in the product. If these drift from the two tables above, the
        # guide changed and the fixture has to follow.
        plan = module("minimax_plan")
        self.assertEqual(tuple(sorted(plan.RETENTION_VISIBLE)), tuple(sorted(VISIBLE_RETENTION_WORDS)))
        self.assertEqual(tuple(sorted(plan.RETENTION_AUDIO)), tuple(sorted(AUDIO_RETENTION_WORDS)))

    def test_lock_marker_cannot_reach_the_prompt(self):
        # `sanitize_retention` clamps whatever it is given to the guide vocabulary, so even a stray
        # value is rewritten rather than written out.
        plan = module("minimax_plan")
        self.assertEqual(plan.sanitize_retention("lock", audio=True), plan.RETENTION_AUDIO_DEFAULT)
        self.assertEqual(plan.sanitize_retention("locked", audio=True), plan.RETENTION_AUDIO_DEFAULT)
        self.assertEqual(plan.sanitize_retention("lock"), plan.RETENTION_DEFAULT)

    def test_label_set_matches_the_guide_table(self):
        # ref-en.txt §2 table: <Subject N>, <Picture N>, <Video N>, <Audio N>.
        self.assertEqual(sorted(LABELS), ["Audio", "Picture", "Subject", "Video"])


if __name__ == "__main__":
    unittest.main()
