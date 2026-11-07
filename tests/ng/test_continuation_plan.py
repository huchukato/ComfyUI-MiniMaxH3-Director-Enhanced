"""A continuation consumes hidden source context, never another copy on the story timeline."""
import unittest
import json
from dataclasses import replace

from _pack import module
from test_shot_scope_contract import plan, shot

ctx, opts = module('ng.core.context'), module('ng.core.context_options')
chunks, project = module('ng.core.chunks'), module('ng.core.project')
continuation = module('ng.core.continuation')


def video(**changes):
    return ctx.ContextItem('v','Singing','video','source.mp4',usage=('continue',),length_s=5.875,
                           options=opts.ContextOptions(video_audio='reference'),**changes)


class ContinuationPlan(unittest.TestCase):
    def test_ref_sound_uses_90_frames_without_changing_delivered_duration(self):
        result = project.plan_project(ctx.DirectorContext(items=(video(),), mode='ref2va', project_seconds=4.25),
                                      6, chunks.ContinuityPlan())
        part, compiled = result.plan.chunks[0], result.compiled[0]
        self.assertEqual((part.head_frames, part.delivered_frames, part.sampled_frames), (90, 102, 192))
        self.assertEqual(chunks.Chunk.from_dict(part.to_dict()), part)
        self.assertEqual([(r.start_f, r.length_f, r.trim_start_f) for r in compiled.of_kind('continue_video')], [(0, 90, 51)])
        self.assertFalse(compiled.of_kind('video'))
        self.assertFalse(compiled.of_kind('audio'))

    def test_ref_sound_short_range_warns_and_ignore_keeps_shorter_prefix(self):
        short = replace(video(), options=opts.ContextOptions(start_s=3., video_audio='reference'))
        result = project.plan_project(ctx.DirectorContext(items=(short,), mode='ref2va', project_seconds=4.25),
                                      6, chunks.ContinuityPlan())
        self.assertEqual(result.plan.chunks[0].head_frames, 56)
        self.assertIn('continue_short', {i.code for i in result.issues})
        silent = replace(video(), options=opts.ContextOptions(video_audio='ignore'))
        result = project.plan_project(ctx.DirectorContext(items=(silent,), mode='ref2va', project_seconds=4.25),
                                      6, chunks.ContinuityPlan())
        self.assertEqual(result.plan.chunks[0].head_frames, 39)

    def test_ref_original_song_keeps_39_frames_and_correct_offset(self):
        song = ctx.ContextItem('song','Song','audio','song.mp3',usage=('lock',),length_s=180,
                               options=opts.ContextOptions(start_s=5.875))
        result = project.plan_project(ctx.DirectorContext(items=(video(),song), mode='ref2va', project_seconds=4.25),
                                      6, chunks.ContinuityPlan())
        self.assertEqual(result.plan.chunks[0].head_frames, 39)
        lock = result.compiled[0].of_kind('lock')[0]
        self.assertEqual((lock.trim_start_f, lock.length_f), (102,141))

    def test_auto_scoped_ref_sound_uses_long_prefix_for_later_source(self):
        other = ctx.ContextItem('person','Singer','image','person.png',usage=('reference',))
        records = [shot('first',0,6,[]),shot('next',6,10,[('v','continue'),('person','reference')])]
        result = plan(records,(other,video()),10,10,chunks.ContinuityPlan())
        part, compiled = next((p,c) for p,c in zip(result.plan.chunks,result.compiled) if p.continuation_id)
        self.assertEqual(part.head_frames,90)
        self.assertEqual(compiled.mode,'ref2va')
        self.assertEqual(compiled.of_kind('continue_video')[0].length_f,90)

    def test_lock_elsewhere_in_project_keeps_existing_source_window_without_false_short_warning(self):
        song = ctx.ContextItem('song','Song','audio','song.mp3',usage=('voice',),length_s=180)
        records = [shot('first',0,6,[('v','continue')]), shot('later',6,10,[('song','lock')])]
        document = json.dumps({'format':'h3-director-shots','schema_version':1,'shots':records})
        result = project.plan_project(ctx.DirectorContext(items=(video(),song),mode='ref2va',shots_text=document,
                                                          project_seconds=10),4,chunks.ContinuityPlan())
        self.assertEqual(result.plan.chunks[0].head_frames,39)
        self.assertNotIn('continue_short',{issue.code for issue in result.issues})

    def test_source_context_is_hidden_and_delivered_duration_is_planned_independently(self):
        result = project.plan_project(ctx.DirectorContext(items=(video(),),project_seconds=4.25),6,chunks.ContinuityPlan())
        part = result.plan.chunks[0]
        self.assertEqual((part.continuation_id,part.head_frames,part.delivered_frames,part.sampled_frames),('v',39,102,141))
        self.assertEqual(result.compiled[0].of_kind('video'),())
        self.assertEqual([(r.start_f,r.length_f,r.trim_start_f) for r in result.compiled[0].of_kind('continue_video')],[(0,39,102)])
        self.assertNotIn('reference_disabled',{i.code for i in result.issues})
        self.assertEqual(chunks.Chunk.from_dict(part.to_dict()),part)

    def test_later_continuation_opens_its_own_part_without_carrying_previous_shot_media(self):
        other = ctx.ContextItem('old','Other subject','image','old.png',usage=('reference',))
        records = [shot('old',0,6,[('old','reference')]),shot('next',6,10,[('v','continue')])]
        result = plan(records,(other,video()),10,10,chunks.ContinuityPlan())
        selected = [(part,compiled) for part,compiled in zip(result.plan.chunks,result.compiled) if part.continuation_id]
        self.assertEqual(len(selected),1)
        part,compiled = selected[0]
        self.assertEqual(part.head_frames,39)
        self.assertEqual(compiled.of_kind('continue_video')[0].start_f,0)
        self.assertNotIn('old',{r.ctx_id for r in compiled.refs})
        self.assertEqual({s.shot_id for s in part.shots},{'next'})

    def test_short_and_selected_source_ranges_use_native_prefix_lengths(self):
        for duration,count in ((.1,1),(.3,5),(1,22),(1.625,39),(4,39)):
            item = ctx.ContextItem('v','Short','video','v.mp4',usage=('continue',),length_s=duration)
            self.assertEqual(continuation.prefix_frames(item),count)

    def test_sound_does_not_make_a_continue_clip_a_general_video_reference(self):
        self.assertFalse(video().uses_video_reference)
        self.assertTrue(ctx.ContextItem('m','Motion','video','v.mp4',usage=('motion','continue')).uses_video_reference)

    def test_original_song_offset_is_kept_with_its_own_hidden_audio_history(self):
        song = ctx.ContextItem('song','Song','audio','song.mp3',usage=('lock',),length_s=180,
                               options=opts.ContextOptions(start_s=5.875))
        result = project.plan_project(ctx.DirectorContext(items=(video(),song),project_seconds=4.25),6,chunks.ContinuityPlan())
        lock = result.compiled[0].of_kind('lock')[0]
        self.assertEqual((lock.start_f,lock.trim_start_f,lock.length_f),(0,102,141))
        self.assertEqual(lock.trim_start_f + result.plan.chunks[0].head_frames,141)

    def test_first_picture_with_separate_locked_sound_keeps_its_existing_fl2va_path(self):
        picture = ctx.ContextItem('image','First','image','first.png',usage=('first_frame',))
        song = ctx.ContextItem('song','Song','audio','song.mp3',usage=('lock',),length_s=180,
                               options=opts.ContextOptions(start_s=5.875))
        result = project.plan_project(ctx.DirectorContext(items=(picture,song),project_seconds=4.25),6,chunks.ContinuityPlan())
        part,compiled = result.plan.chunks[0],result.compiled[0]
        self.assertEqual((part.head_frames,part.continuation_id,compiled.mode),(0,'','fl2va'))
        self.assertEqual(compiled.of_kind('first_frame')[0].start_f,0)
        self.assertEqual(compiled.of_kind('lock')[0].trim_start_f,141)
        self.assertFalse(compiled.of_kind('continue_video'))

    def test_first_picture_anchors_new_footage_after_the_known_video_tail(self):
        picture = ctx.ContextItem('image','First','image','first.png',usage=('first_frame',))
        result = project.plan_project(ctx.DirectorContext(items=(video(),picture),project_seconds=4.25),6,chunks.ContinuityPlan())
        compiled = result.compiled[0]
        self.assertFalse(compiled.of_kind('first_frame'))
        self.assertEqual(compiled.of_kind('keyframe')[0].start_f,39)
        self.assertEqual(compiled.of_kind('continue_video')[0].start_f,0)
