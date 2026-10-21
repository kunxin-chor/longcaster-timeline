import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import torch

from timeline_core.image_continuation import load_frame, validate, compile_with_frame
from timeline_core.store import Store, digest


class ImageSourceTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        state=Store.create(self.temp.name,"Image restart")
        self.store=Store(self.temp.name,state["id"])
        self.path=self.store.asset("takes/source/original.mmh3")
        self.path.parent.mkdir(parents=True);self.path.write_bytes(b"frozen selected take")
        source={"id":"chosen-take","latent_path":"takes/source/original.mmh3","latent_sha256":digest(self.path),
                "latent_resource_id":"resource","plan":{"sampled_frames":22,"delivery":{"start":5,"end":18}}}
        self.snapshot={"source":source,"width":32,"height":32}
        self.api=SimpleNamespace(load_archive=lambda path,verify:object())
        self.frames=torch.arange(22,dtype=torch.float32)[:,None,None,None].expand(22,32,32,3)/22
        self.vae=SimpleNamespace(decode=lambda tensor:self.frames)
        self.latent={"samples":SimpleNamespace(unbind=lambda:(torch.zeros(1,24,7,2,2),torch.zeros(1,32,2,37)))}
        self.primary=patch('timeline_core.engine.primary',return_value=(self.latent,{"id":"resource"},{"origin":"sampler_output"}))
        self.primary.start()

    def tearDown(self):
        self.primary.stop();self.temp.cleanup()

    def test_selected_archive_final_delivered_frame_used_without_preview(self):
        frame,report=load_frame(self.api,self.store,self.snapshot,self.vae,"job")
        self.assertTrue(torch.equal(frame,self.frames[17:18]))
        self.assertEqual(report["source_take_id"],"chosen-take")
        self.assertEqual(report["source_frame_index"],17)
        self.assertEqual(report["source_delivered_frame_index"],12)
        self.assertFalse(report["motion_history"]);self.assertFalse(report["audio_history"])
        self.assertTrue(self.store.asset(report["image_path"]).is_file())

    def test_archive_tampering_and_cancellation_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"cancelled"):
            load_frame(self.api,self.store,self.snapshot,self.vae,"job",lambda:True)
        self.path.write_bytes(b"different take")
        with self.assertRaisesRegex(ValueError,"missing or changed"):
            load_frame(self.api,self.store,self.snapshot,self.vae,"job")

    def test_resource_frame_count_and_nonfinite_decode_are_rejected(self):
        with patch('timeline_core.engine.primary',return_value=(self.latent,{"id":"other"},{})):
            with self.assertRaisesRegex(ValueError,"resource differs"):
                load_frame(self.api,self.store,self.snapshot,self.vae,"job")
        self.frames=self.frames[:21]
        with self.assertRaisesRegex(ValueError,"frame count"):
            load_frame(self.api,self.store,self.snapshot,self.vae,"job")
        self.frames=torch.full((22,32,32,3),float('nan'))
        with self.assertRaisesRegex(ValueError,"pixel values"):
            load_frame(self.api,self.store,self.snapshot,self.vae,"job")

    def test_runtime_validation_accepts_frozen_off_controls_but_rejects_no_source(self):
        validate('ref2va',self.snapshot['source'],{})
        validate('fl2va',self.snapshot['source'],{'continuation_protection':{'mode':'off'},'decode_edge':{'frames':0},'refine':{'enabled':False}})
        with self.assertRaisesRegex(ValueError,'finalized source'):
            validate('fl2va',None,{})


class ContinuationPromptTests(TestCase):
    def source(self):
        return {'id':'parent','latent_sha256':'archive-hash','plan':{'delivery':{'start':39,'end':158}}}

    def refs(self,count):
        return [{'id':str(i),'kind':'image','token_name':f'asset{i}','scope':'project','owner_id':None,'enabled':True,'role':'picture','asset_path':f'{i}.png','asset_sha256':f'image-hash-{i}'} for i in range(count)]

    def test_actual_number_three_sections_original_timing_and_authored_text_preserved(self):
        fields={'subject_definitions':'<Subject 1> is the person in <picture.asset0>.',
                'detailed_description':'[Shot 1] At 00:01.000 <Subject 1> pulls up.\n[Shot 2] At 00:03.000 The camera cuts.'}
        compiled=compile_with_frame(fields,self.refs(2),self.source())
        self.assertEqual(compiled['continuation_picture']['native_label'],'<Picture 3>')
        self.assertEqual(compiled['authored_fields']['detailed_description'],fields['detailed_description'])
        self.assertIn('<Subject 1> is the person in <Picture 1>.',compiled['resolved_fields']['subject_definitions'])
        self.assertIn('<Picture 3> is the final frame',compiled['resolved_fields']['subject_definitions'])
        self.assertIn('<Picture 3> ([Shot 1] first frame): fully_preserved',compiled['resolved_fields']['retention_analysis'])
        self.assertIn('[Shot 1] The video continues from <Picture 3>',compiled['resolved_fields']['detailed_description'])
        self.assertIn('[Shot 2] At 00:03.000 The camera cuts.',compiled['prompt'])
        self.assertIn('At 00:01.000',compiled['prompt'])
        self.assertEqual(compiled,compile_with_frame(fields,self.refs(2),self.source()))
        self.assertIsNone(compiled['images'][-1]['asset_sha256'])
        self.assertEqual(compiled['images'][-1]['source_archive_sha256'],'archive-hash')
        self.assertTrue(compiled['resolved_fields']['summary'].startswith('[keyframe completion + reference generation]'))

    def test_summary_task_type_merges_without_duplicate_prefix_or_rewriting_authored_fields(self):
        for summary in ('[reference generation] A person exercises.','[keyframe completion + reference generation] A person exercises.'):
            compiled=compile_with_frame({'summary':summary,'detailed_description':'[Shot 1] Exercise.'},self.refs(2),self.source())
            final=compiled['resolved_fields']['summary']
            self.assertTrue(final.startswith('[keyframe completion + reference generation]'))
            self.assertEqual(final.count('keyframe completion'),1)
            self.assertEqual(final.count('A person exercises.'),1)
            self.assertEqual(compiled['authored_fields']['summary'],summary)
        only=compile_with_frame({'detailed_description':'Move.'},[],self.source())
        self.assertTrue(only['resolved_fields']['summary'].startswith('[keyframe completion]'))

    def test_disabled_images_native_limit_missing_source_and_ambiguous_shots(self):
        refs=self.refs(2);refs[0]['enabled']=False
        compiled=compile_with_frame({'detailed_description':'Walking.'},refs,self.source())
        self.assertEqual(compiled['continuation_picture']['native_label'],'<Picture 2>')
        self.assertTrue(compiled['resolved_fields']['detailed_description'].startswith('[Shot 1]'))
        with self.assertRaisesRegex(ValueError,'at most 9'):compile_with_frame({},self.refs(9),self.source())
        with self.assertRaisesRegex(ValueError,'finalized source'):compile_with_frame({},[],None)
        for text in ('[Shot 2] Walking.','[Shot 1] One. [Shot 1] Two.'):
            with self.assertRaises(ValueError):compile_with_frame({'detailed_description':text},[],self.source())

    def test_existing_reference_strength_and_generated_picture_order_are_preserved(self):
        from timeline_core.reference_conditioning import scale_reference_conditioning
        refs=self.refs(1);refs[0].update(conditioning_mode='latent',latent_strength=50)
        compiled=compile_with_frame({'detailed_description':'Walking.'},refs,self.source())
        original=torch.ones(1,24,1,2,2)
        positive=[[None,{'minimax_refs':[{'kind':'image','latent':original},{'kind':'image','latent':original*3}]}]]
        result=scale_reference_conditioning(positive,compiled['images'])
        self.assertTrue(torch.equal(result[0][1]['minimax_refs'][0]['latent'],original*.5))
        self.assertTrue(torch.equal(result[0][1]['minimax_refs'][1]['latent'],original*3))
        self.assertTrue(torch.equal(positive[0][1]['minimax_refs'][0]['latent'],original))


class ShortMotionTests(TestCase):
    def test_video_only_prefix_and_empty_audio_context_checks(self):
        from timeline_core.image_continuation import prepare_motion
        from timeline_core.continuation_evidence import capture_context,check_context
        from timeline_core.store import duration
        class Joint:
            def __init__(self,parts):self.parts=tuple(parts)
            def unbind(self):return self.parts
        with tempfile.TemporaryDirectory() as folder:
            state=Store.create(folder,'Short motion');store=Store(folder,state['id'])
            path=store.asset('source.mmh3');path.write_bytes(b'source')
            source={'id':'parent','latent_path':'source.mmh3','latent_sha256':digest(path),'latent_resource_id':'r','plan':duration(5)}
            plan=duration(5,22,video_only=True)
            self.assertEqual(plan['new_frames'],119);self.assertEqual(plan['audio']['context_steps'],0)
            snapshot={'source':source,'plan':plan,'image_motion_frames':22}
            video=torch.arange(37,dtype=torch.float32)[None,None,:,None,None].expand(1,24,37,2,2).clone()
            original={'samples':Joint((video,torch.ones(1,32,2,207)))}
            target={'samples':Joint((torch.zeros(1,24,42,2,2),torch.zeros(1,32,2,235)))}
            api=SimpleNamespace(load_archive=lambda *args,**kwargs:None,validate_h3_continuation_compatibility=lambda _:None)
            with patch('timeline_core.engine.primary',return_value=(original,{'id':'r'},{'origin':'sampler_output'})):
                prepared,receipt=prepare_motion(api,store,snapshot,target)
            v,a=prepared['samples'].unbind();vm,am=prepared['noise_mask'].unbind()
            self.assertTrue(torch.equal(v[:,:,:7],video[:,:,-7:]))
            self.assertTrue(torch.all(v[:,:,7:]==0));self.assertTrue(torch.all(a==0))
            self.assertTrue(torch.all(vm[:,:,:7]==0));self.assertTrue(torch.all(vm[:,:,7:]==1));self.assertTrue(torch.all(am==1))
            before=capture_context(prepared,receipt)
            v[:,:,7:]=99;a.fill_(9)
            check=check_context(prepared,before,receipt)
            self.assertTrue(check['passed']);self.assertEqual(check['streams']['audio']['protected_values'],0)
            v[:,:,0]+=1
            self.assertFalse(check_context(prepared,before,receipt)['passed'])

