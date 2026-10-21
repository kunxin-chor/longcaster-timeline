import copy
from types import SimpleNamespace, ModuleType
from unittest import TestCase
from unittest.mock import patch
import torch
from timeline_core.video_continuation import compile_with_video, validate, slice_tail, condition, load_reference
from timeline_core.reference_conditioning import scale_reference_conditioning
import test_core
import test_image_continuation


def parent():
    return dict(id='parent',latent_sha256='archive',plan=dict(sampled_frames=175,delivery=dict(start=39,end=158)))


class VideoPromptTests(TestCase):
    def test_preserves_subjects_summary_timing_and_image_numbering(self):
        ref=dict(id='image',token_name='main',kind='image',enabled=True,asset_sha256='imagehash')
        fields=dict(subject_definitions='<Subject 1> is the man in <picture.main>.',
                    summary='[reference generation] A man exercises.',detailed_description='[Shot 1] <Subject 1> moves.\n[Shot 2] At 00:03.000 A cut.')
        original=copy.deepcopy(fields)
        compiled=compile_with_video(fields,[ref],parent())
        self.assertEqual(fields,original)
        self.assertEqual(compiled['authored_fields']['summary'],fields['summary'])
        self.assertIn('[video continuation + audio reference + reference generation]',compiled['prompt'])
        self.assertEqual(compiled['prompt'].count('A man exercises.'),1)
        self.assertEqual(compiled['subjects'],[{'label':'<Subject 1>','definition':'<Subject 1> is the man in <Picture 1>.'}])
        self.assertEqual(compiled['images'][0]['native_label'],'<Picture 1>')
        self.assertIn('<Audio 1>: reference -',compiled['prompt'])
        self.assertIn('[Shot 2] At 00:03.000 A cut.',compiled['prompt'])
        self.assertNotIn('keyframe completion',compiled['prompt'])
        self.assertEqual(compiled,compile_with_video(fields,[ref],parent()))
        self.assertEqual(compiled['continuation_video']['source_frame_start'],68)
        self.assertEqual(compiled['continuation_video']['source_frame_end'],158)

    def test_plain_summary_and_existing_task_types(self):
        for summary in ('A man exercises.','[video continuation + audio reference] A man exercises.'):
            compiled=compile_with_video({'summary':summary,'detailed_description':'Move.'},[],parent())
            self.assertEqual(compiled['resolved_fields']['summary'].count('video continuation'),1)
            self.assertTrue(compiled['resolved_fields']['detailed_description'].startswith('[Shot 1]'))

    def test_rejects_ambiguous_shots_other_media_and_short_source(self):
        for detail in ('[Shot 2] Missing opening.','[Shot 1] Move. [Shot 1] Move.'):
            with self.assertRaises(ValueError):compile_with_video({'detailed_description':detail},[],parent())
        with self.assertRaisesRegex(ValueError,'disable other'):
            compile_with_video({},[{'kind':'video','token_name':'other','enabled':True}],parent())
        source=parent();source['plan']['delivery']['start']=100
        with self.assertRaisesRegex(ValueError,'90 delivered'):compile_with_video({},[],source)

    def test_user_video_assets_remain_gated_outside_generated_continuation(self):
        from timeline_core.compiler import compile_prompt
        fake=dict(id='fake',kind='video',token_name='source',asset_sha256=None,generated_role='continuation_video')
        with self.assertRaisesRegex(ValueError,'not implemented'):
            compile_prompt({'summary':'<video.source>'},[fake])

    def test_native_pairing_and_image_strength_preserve_av_block(self):
        captured={}
        def native(clip,prompt,width,height,length,ref_images,audio_vae,ref_image_size,ref_videos,ref_video_audios):
            captured.update(locals());return ('positive','latent')
        frames=object();sound=object()
        self.assertEqual(condition(native,dict(clip='clip',prompt='prompt',width=32,height=32,length=124),{'picture':'image'},'audioVAE',frames,sound,'match'),('positive','latent'))
        self.assertIs(captured['ref_videos']['ref_video_1'],frames)
        self.assertIs(captured['ref_video_audios']['ref_video_audio_1'],sound)
        image=torch.ones(2);block={'kind':'video_audio','latent':torch.ones(3),'audio_latent':torch.ones(4)}
        refs=[{'kind':'image','native_label':'<Picture 1>','conditioning_mode':'latent','latent_strength':50}]
        cond=[['embed',{'minimax_refs':[{'kind':'image','latent':image},block]}]]
        scaled=scale_reference_conditioning(cond,refs)
        self.assertTrue(torch.equal(scaled[0][1]['minimax_refs'][0]['latent'],image*.5))
        self.assertIs(scaled[0][1]['minimax_refs'][1],block)
        self.assertTrue(torch.equal(image,torch.ones(2)))
        def old_native(clip,prompt,width,height,length):raise AssertionError('must not run')
        with self.assertRaises(RuntimeError):
            condition(old_native,dict(clip='clip',prompt='prompt',width=32,height=32,length=124),{},None,frames,sound,'match')


class VideoTailTests(TestCase):
    def test_source_delivery_bounds_and_exact_av_samples(self):
        source=parent();frames=torch.arange(175)[:,None,None,None].expand(175,2,2,3).float()/175
        wave=torch.arange(175*1000).reshape(1,1,-1).float()
        video,sound,bounds=slice_tail(frames,{'waveform':wave,'sample_rate':24000},source,2,2)
        self.assertTrue(torch.equal(video,frames[68:158]))
        self.assertTrue(torch.equal(sound['waveform'],wave[...,68000:158000]))
        self.assertEqual(bounds['audio_start_sample'],68000)
        self.assertEqual(sound['waveform'].shape[-1],90000)
        with self.assertRaisesRegex(ValueError,'does not cover'):
            slice_tail(frames,{'waveform':wave[...,:1000],'sample_rate':24000},source,2,2)
        with self.assertRaisesRegex(ValueError,'pixel values'):
            slice_tail(frames*float('nan'),{'waveform':wave,'sample_rate':24000},source,2,2)

    def test_validation_keeps_pdd_independent_and_blocks_overlap_controls(self):
        validate('ref2va',parent(),{'pdd_warmup':'auto'},{'context_frames':0,'sampled_frames':124})
        for settings in ({'image_motion_frames':22},{'decode_edge_frames':1},{'refine':{'enabled':True}},{'continuation_protection':'color_stable'}):
            with self.assertRaises(ValueError):validate('ref2va',parent(),settings)
        with self.assertRaisesRegex(ValueError,'REF2VA'):validate('fl2va',parent(),{})
        with self.assertRaisesRegex(ValueError,'90 target'):validate('ref2va',parent(),{},{'context_frames':0,'sampled_frames':73})


class VideoArchiveTests(TestCase):
    setUp = test_image_continuation.ImageSourceTests.setUp
    tearDown = test_image_continuation.ImageSourceTests.tearDown
    # Reuse only the safe in-memory setup; no native ComfyUI or GPU work.
    def test_frozen_source_provenance_cancellation_and_audio_binding(self):
        self.snapshot['source']['plan']={'sampled_frames':124,'delivery':{'start':0,'end':124}}
        self.snapshot.update(profile='ref2va',plan={'context_frames':0,'sampled_frames':124})
        self.snapshot['compiled']=compile_with_video({'detailed_description':'Move.'},[],self.snapshot['source'])
        self.frames=torch.zeros(124,32,32,3)
        audio_module=ModuleType('comfy_extras.nodes_audio')
        audio_module.vae_decode_audio=lambda vae,latent:{'waveform':torch.ones(1,2,166000),'sample_rate':32000}
        with patch.dict('sys.modules',{'comfy_extras.nodes_audio':audio_module}):
            frames,sound,receipt=load_reference(self.api,self.store,self.snapshot,self.vae,None,'job')
            self.assertEqual(len(frames),90)
            self.assertEqual(sound['waveform'].shape[-1],120000)
            self.assertEqual(receipt['start'],34)
            self.assertFalse(receipt['hard_latent_pin'])
            self.assertTrue(self.store.asset('diagnostics/job/video-continuation.json').exists())
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                load_reference(self.api,self.store,self.snapshot,self.vae,None,'job',lambda:True)
            self.snapshot['compiled']['continuation_video']['source_frame_end']-=1
            with self.assertRaisesRegex(ValueError,'binding'):
                load_reference(self.api,self.store,self.snapshot,self.vae,None,'job')
            self.path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):
                load_reference(self.api,self.store,self.snapshot,self.vae,None,'job')


class VideoStoreTests(TestCase):
    setUp = test_core.StoreTests.setUp
    tearDown = test_core.StoreTests.tearDown
    queue = test_core.StoreTests.queue
    finish = test_core.StoreTests.finish
    ready_preview = test_core.StoreTests.ready_preview
    command = test_core.StoreTests.command
    image_source = test_core.StoreTests.image_source
    def test_queued_video_prompt_and_regeneration_use_original_parent(self):
        parent=self.image_source()
        settings=dict(mode='extend',profile='ref2va',continuation_method='video_reference',source_take_id=parent['id'],
                      fields={'summary':'A man exercises.','detailed_description':'[Shot 1] Continue moving.'},pdd_warmup='auto')
        _,job=self.queue(**settings);snap=job['snapshot']
        self.assertEqual(snap['plan']['context_frames'],0)
        self.assertEqual(snap['plan']['delivery'],{'start':0,'end':124})
        self.assertEqual(snap['pdd_warmup']['mode'],'auto')
        self.assertEqual(snap['compiled']['continuation_video']['source_take_id'],parent['id'])
        self.assertIn('[video continuation + audio reference]',snap['compiled']['prompt'])
        child=self.finish(job);self.ready_preview(child);self.command('finalize',take_id=child['id'])
        _,replacement=self.queue(**{**settings,'mode':'regenerate','segment_id':child['segment_id'],'source_take_id':child['id']})
        self.assertEqual(replacement['snapshot']['source']['id'],parent['id'])
        self.assertEqual(replacement['snapshot']['compiled']['continuation_video']['source_take_id'],parent['id'])
        self.finish(replacement)
        with self.assertRaisesRegex(ValueError,'90 target'):
            self.queue(**{**settings,'mode':'regenerate','segment_id':child['segment_id'],'seconds':2})
