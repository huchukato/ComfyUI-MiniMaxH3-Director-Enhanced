"""Named context mentions must resolve consistently across Unicode, media and chunk boundaries."""
import unittest

from _pack import module

ctx = module("ng.core.context")
chunks = module("ng.core.chunks")
project = module("ng.core.project")


class NamedMentions(unittest.TestCase):
    def compile(self, items, text):
        context = ctx.DirectorContext(idea=text, project_seconds=8, width=64, height=64,
                                      items=tuple(items), soundscape="Room", music="N/A")
        return project.plan_project(context, 5, chunks.ContinuityPlan("video_audio", 22, 24))

    def test_regex_only_unicode_aliases_do_not_crash_or_claim_an_unknown_image_name(self):
        image = ctx.ContextItem("figure", "İris", "image", "mage.png", usage=("reference",))
        for compiled in self.compile([image], "@iris waits.").compiled:
            self.assertIn("@iris waits.", compiled.prompt)

    def test_regex_only_unicode_aliases_do_not_crash_audio_or_video_mentions(self):
        for media, usage, label in [("video", "motion", "Video"), ("audio", "sound_reference", "Audio")]:
            with self.subTest(media=media):
                item = ctx.ContextItem("medium", "İris", media, "ref.file", usage=(usage,), length_s=2)
                for compiled in self.compile([item], "Follow @iris.").compiled:
                    self.assertIn("Follow @iris.", compiled.prompt)
                    self.assertNotIn("Follow <%s 1>." % label, compiled.prompt)

    def test_full_unicode_casefold_resolves_image_video_audio_and_text_in_every_chunk(self):
        items = [ctx.ContextItem("figure", "Straße", "image", "mage.png", usage=("reference",)),
                 ctx.ContextItem("move", "İzmir", "video", "video.mp4", usage=("motion",), length_s=2),
                 ctx.ContextItem("voice", "Große Musik", "audio", "voice.wav", usage=("voice",),
                                 speaker="figure", length_s=2),
                 ctx.ContextItem("rules", "Rules", "text", "Use @GROSSE MUSIK and follow @i\u0307zmir.",
                                 usage=("rule",))]
        for compiled in self.compile(items, "@STRASSE moves.").compiled:
            self.assertIn("<Subject 1> moves.", compiled.prompt)
            self.assertIn("Use <Audio 1> and follow <Video 1>.", compiled.prompt)
            self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>", compiled.prompt)
            self.assertEqual(compiled.of_kind("audio")[0].ctx_id, "voice")

    def test_distinct_dotted_and_ascii_names_remain_distinct_despite_regex_aliases(self):
        items = [ctx.ContextItem("dotted", "İris", "image", "first.png", usage=("reference",)),
                 ctx.ContextItem("ascii", "Iris", "image", "second.png", usage=("reference",))]
        ctx.require_unique(items)
        for compiled in self.compile(items, "@İris greets @IRIS.").compiled:
            self.assertIn("<Subject 1> greets <Subject 2>.", compiled.prompt)
