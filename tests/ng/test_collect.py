import unittest

from _pack import comfy_available, module

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor

chunks = module("ng.core.chunks")
pin = module("ng.core.pin")
collect = module("ng.adapters.collect")

RATE = 32000


def fake_latent(frames, marker):
    video = torch.full((1, 24, ((frames - 5) // 17) * 5 + 2, 2, 2), float(marker))
    audio = torch.full((1, 32, 2, round(frames / 24.0 * 40)), float(marker))
    return {"samples": NestedTensor((video, audio))}


def decode_video(video, missing=0):
    """Pixel frames on the VAE's 1-4-4-4-4 grid, each valued by the step it comes from."""
    values = video[0, 0, :, 0, 0]
    steps = [values[k] for k in range(values.shape[0]) for _ in range(pin.FRAMES_PER_STEP[k % 5])]
    return torch.stack(steps[:len(steps) - missing]).view(-1, 1, 1, 1).expand(-1, 4, 4, 3).clone()


def context_decode(video):
    """Each step's pixel frames, valued by the step and the one before it inside the decoded window."""
    values = video[0, 0, :, 0, 0]
    out = []
    for k, offset in enumerate(pin.step_offsets(values.shape[0])):
        before = values[k - 1] if k else values[k]
        out += [values[k] + before / 4096.0] * pin.FRAMES_PER_STEP[k % 5]
    return torch.stack(out).view(-1, 1, 1, 1).expand(-1, 4, 4, 3).clone()


def decode_audio_factory(frames_by_marker, extra_samples=0):
    def decode(audio):
        marker = int(audio.flatten()[0].item())
        samples = int(round(frames_by_marker[marker] / 24.0 * RATE)) + extra_samples
        return {"waveform": torch.full((1, 2, samples), float(marker)), "sample_rate": RATE}
    return decode


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Collect(unittest.TestCase):
    def test_picture_correction_only_visits_external_openings_and_keeps_audio(self):
        parts = (chunks.Chunk(0, 0, 102, 39, continuation_id="a"),
                 chunks.Chunk(1, 102, 102, 22),
                 chunks.Chunk(2, 204, 102, 39, continuation_id="b"))
        plan = chunks.SequencePlan(306, chunks.ContinuityPlan(), parts)
        returned = [fake_latent(part.sampled_frames, n) for n, part in enumerate(parts)]
        decode = decode_audio_factory({part.index: part.sampled_frames for part in parts})
        visits = []
        def correct(index, known, frames):
            visits.append((index, float(known[0, 0, 0])))
            frames[:6].add_(.125)
            return frames
        expected, sound, _ = collect.collect_chunks(returned, plan, decode_video, decode)
        frames, audio, _ = collect.collect_chunks(returned, plan, decode_video, decode, restore_picture=correct)
        self.assertEqual(visits, [(0, 0.), (2, 2.)])
        self.assertTrue(torch.equal(audio["waveform"], sound["waveform"]))
        for index in (0, 204):
            self.assertTrue(torch.equal(frames[index:index + 6], expected[index:index + 6] + .125))
        self.assertTrue(torch.equal(frames[6:204], expected[6:204]))
        self.assertTrue(torch.equal(frames[210:], expected[210:]))

    def test_external_prefix_is_removed_from_first_and_later_independent_runs(self):
        parts = (chunks.Chunk(0,0,102,39,continuation_id='first'),
                 chunks.Chunk(1,102,102,22),
                 chunks.Chunk(2,204,102,39,continuation_id='second'))
        plan = chunks.SequencePlan(306,chunks.ContinuityPlan(),parts)
        values = [fake_latent(part.sampled_frames,n)['samples'].unbind()[0] for n,part in enumerate(parts)]
        pictures = list(collect.delivered_pictures(values,plan,decode_video))
        self.assertEqual([len(frames) for frames in pictures],[102,102,102])
        self.assertEqual([int(frames[20,0,0,0]) for frames in pictures],[0,1,2])
        self.assertEqual(len(collect._joined_runs(values,plan)),2)

    def plan(self, total=600, window=22):
        return chunks.plan_chunks(total, 240, chunks.ContinuityPlan("video_audio", window, 24))

    def run_collect(self, plan, extra_samples=0):
        sizes = {c.index: c.sampled_frames for c in plan.chunks}
        latents = [fake_latent(c.sampled_frames, c.index) for c in plan.chunks]
        return collect.collect_chunks(latents, plan, decode_video, decode_audio_factory(sizes, extra_samples))

    def test_length_equals_the_plan_and_sound_equals_picture(self):
        plan = self.plan()
        frames, audio, issues = self.run_collect(plan)
        self.assertEqual(frames.shape[0], plan.total_frames)
        self.assertEqual(audio["waveform"].shape[-1], round(plan.total_frames / 24.0 * RATE))
        self.assertEqual(issues, ())

    def test_pictures_and_sound_come_from_the_delivered_parts(self):
        plan = self.plan()
        frames, audio, _ = self.run_collect(plan)
        edge = 0
        for chunk in plan.chunks:
            self.assertEqual(int(frames[edge, 0, 0, 0].item()), chunk.index)
            sample = int(round(edge / 24.0 * RATE))
            self.assertEqual(int(audio["waveform"][0, 0, sample].item()), chunk.index)
            edge += chunk.delivered_frames

    def test_audio_rounding_is_applied_once_to_the_whole_sequence(self):
        # Three 107-frame clips each round up at 32 kHz; six 158-frame clips each round down.
        for total, target in ((288, 120), (960, 160)):
            plan = chunks.plan_chunks(total, target, chunks.ContinuityPlan("none", 22, 24))
            frames, audio, issues = self.run_collect(plan)
            self.assertEqual(audio["waveform"].shape[-1], round(frames.shape[0] / 24 * RATE))
            self.assertEqual(issues, ())

    def test_each_chunk_keeps_its_picture_and_sound_when_decoders_reuse_buffers(self):
        plan = chunks.plan_chunks(288, 120, chunks.ContinuityPlan("none", 22, 24))
        size = plan.chunks[0].sampled_frames
        picture_buffer = torch.empty(size, 4, 4, 3)
        sound_buffer = torch.empty(1, 2, round(size / 24 * RATE))
        def picture(video):
            return picture_buffer.fill_(float(video.flatten()[0]))
        def sound(audio):
            return {"waveform": sound_buffer.fill_(float(audio.flatten()[0])), "sample_rate": RATE}
        returned = [fake_latent(c.sampled_frames, c.index) for c in plan.chunks]
        frames, audio, _ = collect.collect_chunks(returned, plan, picture, sound)
        for chunk in plan.chunks:
            self.assertEqual(float(frames[chunk.story_start_f, 0, 0, 0]), chunk.index)
            self.assertEqual(float(audio["waveform"][0, 0, round(chunk.story_start_f / 24 * RATE)]), chunk.index)

    def test_the_last_chunk_is_handed_on_without_a_second_copy(self):
        # A 12 s single part ran out of memory on the copy of its 3.1 GB picture; after the last decode none is needed.
        plan = chunks.plan_chunks(288, 288, chunks.ContinuityPlan("none", 22, 24))
        decoded = []
        def picture(video):
            decoded.append(decode_video(video))
            return decoded[-1]
        latents = [fake_latent(c.sampled_frames, c.index)["samples"].unbind()[0] for c in plan.chunks]
        frames = list(collect.delivered_pictures(latents, plan, picture))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].untyped_storage().data_ptr(), decoded[0].untyped_storage().data_ptr())

    def test_overlong_sound_is_cut_and_short_sound_is_padded_and_reported(self):
        plan = self.plan()
        frames, audio, issues = self.run_collect(plan, extra_samples=300)
        self.assertEqual(audio["waveform"].shape[-1], round(frames.shape[0] / 24.0 * RATE))
        _, audio, issues = self.run_collect(plan, extra_samples=-300)         # 9 ms: the grid's normal rounding, no warning
        self.assertEqual(audio["waveform"].shape[-1], round(plan.total_frames / 24.0 * RATE))
        self.assertEqual(issues, ())
        _, audio, issues = self.run_collect(plan, extra_samples=-1000)        # 31 ms: more than one audio step
        self.assertEqual(audio["waveform"].shape[-1], round(plan.total_frames / 24.0 * RATE))
        self.assertTrue(issues and issues[0].code == "audio_short")

    def test_joins_are_decoded_like_one_continuous_latent(self):
        # Real minute (fixed_minute_ref2va, 2026-10-11): each part decoded alone ended on the VAE's unblended lookahead clip and
        # restarted the decoder on the regenerated head, a one-frame jump at every join (29.958 s: luma +0.0110, contrast +0.0049).
        # A decoder whose frames depend on the step before them stands in for the VAE's clip-to-clip blend.
        plan = self.plan(total=900)
        steps = [pin.steps_for_frames(c.sampled_frames) for c in plan.chunks]
        videos = [torch.arange(n, dtype=torch.float32).add(1000 * c.index).view(1, 1, n, 1, 1).expand(1, 24, n, 2, 2).clone()
                  for n, c in zip(steps, plan.chunks)]
        latents = [{"samples": NestedTensor((v, torch.zeros(1, 32, 2, round(c.sampled_frames / 24.0 * 40))))} for v, c in zip(videos, plan.chunks)]
        head = pin.steps_for_frames(plan.continuity.head)
        joined = torch.cat([videos[0]] + [v[:, :, head:] for v in videos[1:]], 2)
        expected = context_decode(joined)
        sizes = {c.index: c.sampled_frames for c in plan.chunks}
        frames, _, _ = collect.collect_chunks(latents, plan, context_decode, decode_audio_factory(sizes))
        self.assertEqual(frames.shape[0], expected.shape[0])
        self.assertTrue(torch.equal(frames, expected))

    def test_wrong_number_of_chunks_or_frames_is_refused(self):
        plan = self.plan()
        sizes = {c.index: c.sampled_frames for c in plan.chunks}
        with self.assertRaises(ValueError):
            collect.collect_chunks([fake_latent(124, 0)], plan, decode_video, decode_audio_factory(sizes))
        latents = [fake_latent(c.sampled_frames, c.index) for c in plan.chunks]
        with self.assertRaises(ValueError):
            collect.collect_chunks(latents, plan, lambda video: decode_video(video, missing=17), decode_audio_factory(sizes))



@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class JoinSound(unittest.TestCase):
    def test_a_pinned_join_fades_into_the_next_parts_own_take_and_keeps_the_length(self):
        # part 0 hums at phase 0; part 1 (pinned, 22 frames) at another phase: butted together the wave jumps at the join
        parts = (chunks.Chunk(0, 0, 107, 0), chunks.Chunk(1, 107, 102, 22))
        plan = chunks.SequencePlan(209, chunks.ContinuityPlan(), parts)
        returned = [fake_latent(part.sampled_frames, n) for n, part in enumerate(parts)]
        def decode(audio):
            marker = int(audio.flatten()[0].item())
            start = 0 if marker == 0 else round((107 - 22) / 24.0 * RATE)
            t = torch.arange(start, start + round(parts[marker].sampled_frames / 24.0 * RATE)) / float(RATE)
            wave = torch.sin(2 * 3.14159 * 220 * t + (0 if marker == 0 else 2.0))
            return {"waveform": wave.view(1, 1, -1).expand(1, 2, -1).clone(), "sample_rate": RATE}
        _, sound, _ = collect.collect_chunks(returned, plan, decode_video, decode)
        wave = sound["waveform"][0, 0]
        self.assertEqual(wave.shape[-1], round(209 / 24.0 * RATE))
        join = round(107 / 24.0 * RATE)
        steps = (wave[1:] - wave[:-1]).abs()
        normal = steps[:join - 2000].max()
        self.assertLess(steps[join - 400:join + 400].max(), normal * 1.2, "no click at the join")


if __name__ == "__main__":
    unittest.main()
