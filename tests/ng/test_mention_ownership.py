"""A complete Context name owns its mention even when another role resolves first."""
import unittest

from _pack import module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def item(identity, name, media, role, **changes):
    return ctx.ContextItem(identity, name, media, "same.file", usage=(role,), **changes)


def plan(items, idea, **changes):
    settings = dict(idea=idea, items=tuple(items), project_seconds=12, width=64, height=64,
                    soundscape="Room tone", music="N/A")
    settings.update(changes)
    return project.plan_project(ctx.DirectorContext(**settings), 5, chunks.ContinuityPlan("video_audio", 22, 24))


class MentionOwnership(unittest.TestCase):
    def test_subject_prefix_cannot_take_a_lock_video_voice_or_guide_mention(self):
        root = item("subject", "Rain", "image", "reference", content=("character",))
        cases = (
            (item("long", "Rain Track", "audio", "lock", length_s=12, description="quiet music"), "quiet music"),
            (item("long", "Rain Track", "audio", "voice", length_s=3, speaker="subject"), "<Audio 1>"),
            (item("long", "Rain Track", "video", "motion", length_s=3), "<Video 1>"),
            (item("long", "Rain Track", "image", "keyframe", description="a red door",
                  options=opts.ContextOptions(anchor_s=6)), "a red door"),
        )
        for longer, label in cases:
            for ordered in ((root, longer), (longer, root)):
                with self.subTest(role=longer.usage, order=ordered[0].id):
                    for compiled in plan(ordered, "Use @Rain Track behind @Rain.").compiled:
                        self.assertIn("Use %s behind <Subject 1>." % label, compiled.prompt)
                        self.assertNotIn("<Subject 1> Track", compiled.prompt)

    def test_numbered_audio_prefix_cannot_take_a_timed_guide_even_when_it_is_absent(self):
        audio = item("audio", "Rain", "audio", "sound_reference", length_s=3)
        guide = item("guide", "Rain Door", "image", "keyframe", description="a red doorway",
                     options=opts.ContextOptions(anchor_s=6))
        for compiled in plan([audio, guide], "Use @Rain Door with @Rain.").compiled:
            self.assertIn("Use a red doorway with <Audio 1>.", compiled.prompt)
            self.assertEqual(dict(compiled.prompt_labels), {"<Audio 1>": "audio"})
            expected = "guide_mention_prose" if compiled.of_kind("keyframe") else "guide_mention_unavailable"
            self.assertIn((expected, "Rain Door"), [(i.code, i.ref) for i in compiled.issues])

    def test_linked_asset_prefix_cannot_take_a_lock_name_in_scoped_text(self):
        root = item("subject", "Mage", "image", "reference", content=("character",))
        asset = item("asset", "Rain", "image", "reference", content=("outfit",), subject_ids=("subject",))
        lock = item("lock", "Rain Track", "audio", "lock", description="quiet music", length_s=12)
        text = ctx.ContextItem("note", "Rules", "text", "Keep @Rain Track distinct from @Rain.",
                               usage=("rule",), subject_ids=("subject",))
        for compiled in plan([root, asset, lock, text], "A walk.").compiled:
            self.assertIn("For <Subject 1>: Keep quiet music distinct from <Picture 2>.", compiled.prompt)
            self.assertEqual(dict(compiled.prompt_labels)["<Picture 2>"], "asset")

    def test_multiple_locks_and_guides_use_longest_full_names_in_any_card_order(self):
        items = [item("short", "Rain", "audio", "lock", description="short music", length_s=12),
                 item("long", "Rain Track", "audio", "lock", description="long music", length_s=12),
                 item("guide", "Rain Track Door", "image", "keyframe", description="a red doorway",
                      options=opts.ContextOptions(anchor_s=6)),
                 item("guide2", "Rain Door", "image", "keyframe", description="a blue doorway",
                      options=opts.ContextOptions(anchor_s=8))]
        for ordered in (items, list(reversed(items))):
            for compiled in plan(ordered, "Use @Rain Track Door beside @Rain Door with @Rain Track and @Rain.").compiled:
                self.assertIn("Use a red doorway beside a blue doorway with long music and short music.", compiled.prompt)
                self.assertEqual({i.ref for i in compiled.issues if i.code.startswith("audio_lock_mention")},
                                 {"Rain", "Rain Track"})
                self.assertEqual({i.ref for i in compiled.issues if i.code.startswith("guide_mention")},
                                 {"Rain Door", "Rain Track Door"})
                self.assertFalse(compiled.prompt_labels)

    def test_missing_source_long_name_never_borrows_an_available_short_reference(self):
        subject = item("subject", "Rain", "image", "reference", content=("character",))
        missing = ctx.ContextItem("missing", "Rain Track", "audio", "", usage=("lock",))
        compiled = plan([subject, missing], "Use @Rain Track beside @Rain; leave @Unknown.").compiled[0]
        self.assertIn("Use @Rain Track beside <Subject 1>; leave @Unknown.", compiled.prompt)
        self.assertIn("source_missing", [i.code for i in compiled.issues])
        self.assertFalse(any(i.code.startswith("audio_lock_mention") for i in compiled.issues))

    def test_case_expanded_long_names_keep_ownership_and_subject_dialogue_still_works(self):
        subject = item("subject", "Straße", "image", "reference", content=("character",))
        lock = item("lock", "Straße Track", "audio", "lock", description="quiet music", length_s=12)
        compiled = plan([subject, lock], "Use @STRASSE TRACK with @strasse.").compiled[0]
        self.assertIn("Use quiet music with <Subject 1>.", compiled.prompt)
        longer_subject = item("long_subject", "Rain Voice", "image", "reference", content=("character",))
        audio = item("audio", "Rain", "audio", "voice", speaker="long_subject", length_s=3)
        spoken = plan([audio, longer_subject], "@Rain Voice says: Hello.").compiled[0]
        self.assertIn("<d>", spoken.prompt)
        self.assertIn("Hello", spoken.prompt)
        self.assertEqual(dict(spoken.prompt_labels)["<Subject 1>"], "long_subject")
        self.assertEqual(dict(spoken.prompt_labels)["<Audio 1>"], "audio")

    def test_raw_prompt_override_preserves_both_names(self):
        root = item("subject", "Rain", "image", "reference", content=("character",))
        lock = item("lock", "Rain Track", "audio", "lock", description="quiet music", length_s=12)
        raw = "My raw @Rain Track beside @Rain."
        for compiled in plan([root, lock], "A walk.", prompt_override=raw).compiled:
            self.assertEqual(compiled.prompt, raw)
