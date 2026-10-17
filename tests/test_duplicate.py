from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from timeline_core.compiler import compile_prompt,effective_references
from timeline_core.duplicate import duplicate_without_generations
from timeline_core.store import Store,atomic_json,digest,new_scene,uid,blank_segment


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.test-tmp';root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.data=Store.create(self.temp.name,'Source');self.store=Store(self.temp.name,self.data['id'])
        scene=self.data['scenes'][0];scene['segments']+=[blank_segment(scene['id'],2),blank_segment(scene['id'],3)]
        self.data['scenes'].append(new_scene('Independent scene'))
        asset=self.store.asset('assets/main.png');asset.parent.mkdir();asset.write_bytes(b'original reference image')
        reference=dict(id=uid(),token_name='main',display_name='Character sheet',kind='image',role='picture',scope='project',owner_id=None,enabled=True,asset_path='assets/main.png',asset_sha256=digest(asset))
        override={**reference,'id':uid(),'scope':'scene','owner_id':scene['id'],'overrides':reference['id']}
        self.data['references']=[reference,override]
        for index,segment in enumerate(scene['segments']):
            segment['working_draft'].update(mode='regenerate',source_take_id='old',configuration={'upstream':{'old':'frozen'}},configuration_id='config-A',switch_selections={'old-switch':'B'},configuration_override=True)
            segment['working_draft']['fields'].update(subject_definitions='<Subject 1> is the person in <picture.main>.',detailed_description=f'[Shot 1] <Subject 1> performs action {index+1}.')
            segment['takes']=['old'];segment['active_output']={'kind':'single_take','take_id':'old'}
        self.data['takes']={'old':{'snapshot':{'seed':9,'profile':'ref2va','compiled':{'authored_fields':{'detailed_description':'Fallback prompt'}},'plan':{'requested_seconds':7}}}}
        self.data['generation_defaults']={'configuration_id':'config-A','selections':{'old-switch':'B'},'schema':[]}
        self.data['jobs']={'old-job':{'status':'succeeded','snapshot':{'unchanged':True}}}
        atomic_json(self.store.manifest,self.data)

    def tearDown(self):self.temp.cleanup()

    def duplicate(self):
        result=duplicate_without_generations(self.store,'Prompts only')
        return result,Store(self.temp.name,result['id'])

    def test_copy_is_independent_and_has_no_generation_artifacts(self):
        original=self.store.manifest.read_bytes();data,target=self.duplicate()
        self.assertEqual(self.store.manifest.read_bytes(),original)
        self.assertEqual(data['takes'],{});self.assertEqual(data['jobs'],{})
        self.assertNotIn('generation_defaults',data)
        self.assertFalse((target.path/'takes').exists());self.assertFalse((target.path/'project_previews').exists())
        self.assertNotEqual(data['scenes'][0]['id'],self.data['scenes'][0]['id'])
        root,override=data['references']
        self.assertEqual(override['overrides'],root['id'])
        self.assertEqual(override['owner_id'],data['scenes'][0]['id'])
        self.assertEqual(target.asset(root['asset_path']).read_bytes(),b'original reference image')
        self.assertEqual(root['asset_path'],override['asset_path'])
        for scene in data['scenes']:
            for index,segment in enumerate(scene['segments']):
                draft=segment['working_draft']
                self.assertEqual(segment['takes'],[]);self.assertIsNone(segment['active_output'])
                self.assertNotIn('source_take_id',draft);self.assertNotIn('configuration',draft)
                self.assertNotIn('configuration_id',draft);self.assertNotIn('switch_selections',draft);self.assertNotIn('configuration_override',draft)
                self.assertEqual(draft['mode'],'new' if index==0 else 'extend')
                if index:self.assertEqual(draft['source_segment_id'],scene['segments'][index-1]['id'])
                compile_prompt(draft['fields'],effective_references(data['references'],scene['id'],segment['id']))

    def test_full_duplicate_retains_switches_and_invalidation_ignores_snapshot_configuration(self):
        from timeline_core.production import duplicate_complete
        full=duplicate_complete(self.store,'Full copy')
        self.assertEqual(full['generation_defaults'],self.data['generation_defaults'])
        self.assertEqual(full['scenes'][0]['segments'][0]['working_draft']['switch_selections'],{'old-switch':'B'})
        self.data['takes']['old']['snapshot']['configuration']={'id':'snapshot-config','switch_values':{'snapshot-switch':'A'}}
        draft=self.data['scenes'][0]['segments'][0]['working_draft']
        draft.pop('configuration_id');draft.pop('switch_selections')
        atomic_json(self.store.manifest,self.data)
        data,_=self.duplicate()
        for scene in data['scenes']:
            for segment in scene['segments']:
                self.assertNotIn('configuration_id',segment['working_draft'])
                self.assertNotIn('switch_selections',segment['working_draft'])

    def test_copied_segments_generate_in_order_using_only_new_takes(self):
        data,target=self.duplicate();scene=data['scenes'][0]
        future=scene['segments'][1]
        with self.assertRaisesRegex(ValueError,'in order'):
            target.queue(target.load()['revision'],future['working_draft'])
        previous=None
        for index,segment in enumerate(scene['segments']):
            draft=deepcopy(segment['working_draft'])
            if previous:draft['source_take_id']=previous['id']
            state,job=target.queue(target.load()['revision'],draft)
            if previous:self.assertEqual(job['snapshot']['source']['id'],previous['id'])
            else:self.assertIsNone(job['snapshot']['source'])
            self.assertIn(f'action {index+1}',job['snapshot']['compiled']['prompt'])
            target.claim(job['id']);take_id=uid();relative=f'takes/{take_id}/original.mmh3'
            artifact=target.asset(relative);artifact.parent.mkdir(parents=True);artifact.write_bytes(b'new latent')
            previous=target.complete(job['id'],dict(take_id=take_id,latent_path=relative,latent_sha256=digest(artifact),latent_resource_id=uid()),{})
            preview=target.asset(f'takes/{take_id}/preview.mp4');preview.write_bytes(b'preview')
            atomic_json(preview.with_suffix('.json'),dict(status='ready',source_sha256=previous['latent_sha256'],path=f'takes/{take_id}/preview.mp4'))
            target.stage(job['id'],'complete')
            target.command(target.load()['revision'],'finalize',{'take_id':take_id})
        with self.assertRaisesRegex(ValueError,'tail'):
            target.queue(target.load()['revision'],{**scene['segments'][0]['working_draft'],'mode':'regenerate'})

    def test_missing_draft_uses_selected_take_authored_prompt(self):
        del self.data['scenes'][0]['segments'][0]['working_draft'];atomic_json(self.store.manifest,self.data)
        data,target=self.duplicate();draft=data['scenes'][0]['segments'][0]['working_draft']
        self.assertEqual(draft['fields']['detailed_description'],'Fallback prompt')
        self.assertEqual(draft['seconds'],7);self.assertEqual(draft['seed'],9)

    def test_missing_reference_fails_without_publishing_partial_copy(self):
        self.store.asset('assets/main.png').unlink()
        before={p.name for p in Path(self.temp.name).iterdir()}
        with self.assertRaisesRegex(ValueError,'missing or corrupt'):self.duplicate()
        self.assertEqual({p.name for p in Path(self.temp.name).iterdir()},before)
