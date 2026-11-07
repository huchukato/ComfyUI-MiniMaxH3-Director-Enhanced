"""Context cards include unnumbered guides/locks as well as capped native references."""
import unittest
import importlib

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class ConnectorContextCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pack = load_full_pack()
        cls.connector = pack.NODE_CLASS_MAPPINGS["NGContextConnector"]
        for name in ("context", "context_options", "project", "chunks"):
            setattr(cls, name, importlib.import_module(pack.__name__ + ".ng.core." + name))

    def test_native_input_expansion_keeps_guides_and_locks_beyond_reference_counts(self):
        from execution import get_input_data
        for media, count in (("audio", 4), ("video", 4), ("image", 10)):
            cards = [self.context.ContextItem(str(i), "%s%d" % (media, i), media, "same.file") for i in range(count)]
            ports = {"context_%s.%s_%d" % (media, media, i): card for i, card in enumerate(cards)}
            expanded, missing, data = get_input_data(ports, self.connector, "connector")
            self.assertFalse(missing)
            self.assertEqual({name:values[0] for name, values in expanded.items()}, ports)
            self.assertTrue(set(ports) <= set(data["dynamic_paths"]))

    def test_two_voices_and_two_locks_are_collected_without_inflating_native_audio_numbers(self):
        ctx, opts, project, chunks = self.context, self.context_options, self.project, self.chunks
        subject = ctx.ContextItem("subject", "Rain", "image", "same.png", usage=("reference",))
        video = ctx.ContextItem("video", "Move", "video", "same.mp4", usage=("motion",), length_s=3,
                                options=opts.ContextOptions(video_audio="reference"))
        audio = [ctx.ContextItem("voice%d" % i, "Voice%d" % i, "audio", "same.wav", usage=("voice",),
                                 speaker="subject" if i == 0 else "", length_s=3) for i in range(2)]
        audio += [ctx.ContextItem("lock%d" % i, "Lock%d" % i, "audio", "same.wav", usage=("lock",),
                                  length_s=8) for i in range(2)]
        packet = self.connector.execute(clip=["clip", 0], vae=["vae", 0], audio_vae=["audio", 0],
                                        model_ref2va=["model", 0], context_image={"image_0":subject},
                                        context_video={"video_0":video},
                                        context_audio={"audio_%d" % i:card for i, card in enumerate(audio)}).args[0]
        compiled = project.plan_project(ctx.DirectorContext(idea="A walk.", items=packet.contexts, project_seconds=4),
                                        5, chunks.ContinuityPlan("video_audio", 22, 24)).compiled[0]
        self.assertEqual(len(packet.contexts), 6)
        self.assertEqual({ref.ctx_id for ref in compiled.of_kind("lock")}, {"lock0", "lock1"})
        self.assertEqual({label:identity for label, identity in compiled.prompt_labels if label.startswith("<Audio ")},
                         {"<Audio 1>": "video", "<Audio 2>": "voice0", "<Audio 3>": "voice1"})
