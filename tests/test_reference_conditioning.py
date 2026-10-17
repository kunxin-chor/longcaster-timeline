import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from timeline_core.reference_conditioning import reference_controls,scale_reference_conditioning
from timeline_core.compiler import compile_prompt
from timeline_core.store import Store,uid,digest,atomic_json,Conflict
from timeline_core.loras import effective_loras
from timeline_core.production import duplicate_complete,delete_production
from timeline_core.duplicate import duplicate_without_generations

class Tensor:
    def __init__(self,values):self.values=values
    def __mul__(self,value):return Tensor([item*value for item in self.values])

class ConditioningTests(unittest.TestCase):
    def reference(self,number,mode='image',strength=100):return {'kind':'image','native_label':f'<Picture {number}>','conditioning_mode':mode,'latent_strength':strength}
    def test_only_selected_diffusion_latent_changes_and_text_embedding_is_identical(self):
        embedding=object();first=Tensor([4,8]);second=Tensor([10,20]);meta={'minimax_refs':[{'kind':'image','latent':first},{'kind':'image','latent':second}],'text_images':['original-one','original-two']}
        original=[[embedding,meta]]
        output=scale_reference_conditioning(original,[self.reference(1),self.reference(2,'latent',35)])
        self.assertIs(output[0][0],embedding);self.assertIs(output[0][1]['text_images'],meta['text_images'])
        self.assertIs(output[0][1]['minimax_refs'][0]['latent'],first)
        self.assertEqual(output[0][1]['minimax_refs'][1]['latent'].values,[3.5,7])
        self.assertEqual(second.values,[10,20]);self.assertIs(original[0][1],meta)
    def test_normal_mode_is_identity_and_zero_is_scaling_not_random_noise(self):
        positive=[[object(),{'minimax_refs':[{'kind':'image','latent':Tensor([2,5])}]}]]
        self.assertIs(scale_reference_conditioning(positive,[self.reference(1)]),positive)
        self.assertEqual(scale_reference_conditioning(positive,[self.reference(1,'latent',0)])[0][1]['minimax_refs'][0]['latent'].values,[0,0])
        self.assertIs(scale_reference_conditioning(positive,[self.reference(1,'latent')])[0][1]['minimax_refs'][0]['latent'],positive[0][1]['minimax_refs'][0]['latent'])
    def test_rejects_invalid_controls_and_unrecognized_native_payload(self):
        for value in (-1,101,float('nan'),True,'35'):
            with self.subTest(value=value),self.assertRaises(ValueError):reference_controls(self.reference(1,'latent',value))
        with self.assertRaises(ValueError):reference_controls(self.reference(1,'noise'))
        with self.assertRaisesRegex(ValueError,'payload changed'):scale_reference_conditioning([[None,{}]],[self.reference(1,'latent',35)])
        with self.assertRaisesRegex(ValueError,'order'):scale_reference_conditioning([[None,{'minimax_refs':[{'kind':'image','latent':Tensor([2])}]}]],[self.reference(2,'latent',35)])

class ScopedProductionTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.test-tmp';root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.data=Store.create(self.temp.name,'Test');self.store=Store(self.temp.name,self.data['id'])
        self.scene=self.data['scenes'][0];self.segment=self.scene['segments'][0]
        source=self.store.asset('assets/main.png');source.parent.mkdir();source.write_bytes(b'image')
        self.ref=dict(id=uid(),token_name='main',kind='image',scope='project',owner_id=None,enabled=True,asset_path='assets/main.png',asset_sha256=digest(source))
        self.data['references']=[self.ref];atomic_json(self.store.manifest,self.data)
    def tearDown(self):self.temp.cleanup()
    def command(self,action,**payload):return self.store.command(self.store.load()['revision'],action,payload)
    def test_scoped_reference_control_preserves_parent_and_frozen_snapshot(self):
        self.command('reference',reference_id=self.ref['id'],scope='segment',owner_id=self.segment['id'],conditioning_mode='latent',latent_strength=35)
        settings=dict(scene_id=self.scene['id'],segment_id=self.segment['id'],mode='new',profile='ref2va',seconds=5,width=768,height=448,seed=1,fields={'subject_definitions':'<Subject 1> is the person in <picture.main>.','detailed_description':'[Shot 1] <Subject 1> moves.'})
        state,job=self.store.queue(self.store.load()['revision'],settings)
        reference=job['snapshot']['compiled']['images'][0]
        self.assertEqual(reference['latent_strength'],35);self.assertEqual(reference['conditioning_mode'],'latent')
        self.command('reference',reference_id=reference['id'],latent_strength=70)
        self.assertEqual(self.store.load()['jobs'][job['id']]['snapshot'],job['snapshot'])
        self.assertNotIn('conditioning_mode',self.store.load()['references'][0])
        self.assertIn('<Subject 1> is the person in <Picture 1>.',job['snapshot']['compiled']['prompt'])
    def test_reference_size_inheritance_override_and_frozen_snapshot(self):
        settings=dict(scene_id=self.scene['id'],segment_id=self.segment['id'],mode='new',profile='ref2va',seconds=5,width=768,height=448,seed=1,fields={'detailed_description':'[Shot 1] The subject exercises.'})
        _,legacy=self.store.queue(self.store.load()['revision'],settings)
        self.assertEqual(legacy['snapshot']['ref_image_size'],'match')
        self.store.fail(legacy['id'],'test cleanup')
        self.command('set_reference_image_size',ref_image_size='max')
        _,inherited=self.store.queue(self.store.load()['revision'],settings)
        self.assertEqual(inherited['snapshot']['ref_image_size'],'max')
        self.assertNotIn('ref_image_size',self.store.load()['scenes'][0]['segments'][0]['working_draft'])
        frozen=deepcopy(inherited['snapshot'])
        self.command('set_reference_image_size',ref_image_size='match')
        self.assertEqual(self.store.load()['jobs'][inherited['id']]['snapshot'],frozen)
        self.store.fail(inherited['id'],'test cleanup')
        _,override=self.store.queue(self.store.load()['revision'],{**settings,'ref_image_size':'max'})
        self.assertEqual(override['snapshot']['ref_image_size'],'max')
        self.assertEqual(self.store.load()['scenes'][0]['segments'][0]['working_draft']['ref_image_size'],'max')
        self.store.fail(override['id'],'test cleanup')
        for invalid in ('largest','',False,42):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(ValueError,'match or max'):
                self.store.queue(self.store.load()['revision'],{**settings,'ref_image_size':invalid})
            with self.assertRaisesRegex(ValueError,'match or max'):self.command('set_reference_image_size',ref_image_size=invalid)

    def test_loras_use_explicit_scope_and_frozen_model_settings(self):
        self.command('set_loras',scope='project',owner_id=None,entries=[dict(filename='style.safetensors',strength=.7)])
        self.command('set_loras',scope='scene',owner_id=self.scene['id'],entries=[dict(filename='style.safetensors',strength=.4)])
        self.assertEqual(effective_loras(self.store.load(),self.scene['id'],self.segment['id'])[0]['strength'],.4)
        self.command('set_loras',scope='segment',owner_id=self.segment['id'],entries=[dict(filename='style.safetensors',strength=.4,enabled=False)])
        self.assertEqual(effective_loras(self.store.load(),self.scene['id'],self.segment['id']),[])
        with self.assertRaises(ValueError):self.command('set_loras',scope='project',owner_id=None,entries=[dict(filename='../outside.safetensors')])
    def test_duplicate_full_and_invalidate_have_distinct_artifact_semantics(self):
        data=self.store.load();data['ref_image_size']='max';take_id=uid();data['takes'][take_id]={'id':take_id,'snapshot':{}};data['scenes'][0]['segments'][0]['takes']=[take_id]
        artifact=self.store.asset(f'takes/{take_id}/original.mmh3');artifact.parent.mkdir(parents=True);artifact.write_bytes(b'latent')
        atomic_json(self.store.manifest,data);before=self.store.manifest.read_bytes()
        copied=duplicate_complete(self.store,'Full copy');target=Store(self.temp.name,copied['id'])
        self.assertEqual(target.asset(f'takes/{take_id}/original.mmh3').read_bytes(),b'latent');self.assertEqual(copied['takes'],data['takes']);self.assertEqual(copied['ref_image_size'],'max')
        empty=duplicate_without_generations(self.store,'Prompts only');self.assertEqual(empty['takes'],{});self.assertEqual(empty['jobs'],{});self.assertEqual(empty['ref_image_size'],'max')
        self.assertFalse((Store(self.temp.name,empty['id']).path/'takes').exists());self.assertTrue(empty['references'])
        self.assertEqual(before,self.store.manifest.read_bytes())
    def test_delete_is_reversible_and_active_generations_are_protected(self):
        data=self.store.load();data['jobs']['active']={'status':'running'};atomic_json(self.store.manifest,data)
        with self.assertRaises(Conflict):delete_production(self.store,data['revision'])
        data['jobs']={};atomic_json(self.store.manifest,data)
        result=delete_production(self.store,data['revision']);self.assertTrue(result['deleted']);self.assertFalse(self.store.path.exists())
        self.assertEqual(len(list((Path(self.temp.name)/'.trash').glob('*/project.json'))),1)
