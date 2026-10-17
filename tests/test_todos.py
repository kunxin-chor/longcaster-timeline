from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from timeline_core.compiler import compile_prompt,effective_references
from timeline_core.project_settings import migrate_legacy_fields,project_resolution
from timeline_core.store import Store,atomic_json,digest,uid,Conflict,active_job


def ref(name='main',kind='image',**values):
    return dict(id=uid(),token_name=name,display_name=name,scope='project',owner_id=None,
        kind=kind,role='picture',enabled=True,asset_path='assets/test.png',asset_sha256='a'*64,**values)


class NamespaceTests(unittest.TestCase):
    def test_subjects_and_assets_are_independent_many_to_many(self):
        references=[ref(),ref('detail')]
        fields={'subject_definitions':'<Subject 1> is the left person in <picture.main>, with clothing from <picture.detail>.\n<Subject 2> is the right person in <picture.main>.\n<Subject 3> is a newly imagined red ball.',
            'retention_analysis':'<Subject 1>: fully_preserved - keep appearance.',
            'detailed_description':'[Shot 1] <Subject 1> passes <Subject 3> to <Subject 2>. <d>[Chinese] 你好</d>'}
        result=compile_prompt(fields,references)
        self.assertEqual(len(result['subjects']),3)
        self.assertTrue(all(set(subject)=={'label','definition'} for subject in result['subjects']))
        self.assertEqual(result['resolved_fields']['subject_definitions'],fields['subject_definitions'].replace('<picture.main>','<Picture 1>').replace('<picture.detail>','<Picture 2>'))
        self.assertEqual(result['resolved_fields']['retention_analysis'],fields['retention_analysis'])
        self.assertEqual(result['resolved_fields']['detailed_description'],fields['detailed_description'])
        self.assertEqual(result['mappings']['picture.main']['label'],'<Picture 1>')
        self.assertNotIn('Referenced appearance',result['prompt'])

    def test_cross_media_names_coexist_and_ambiguous_legacy_names_fail(self):
        references=[ref(),ref(kind='video'),ref(kind='audio')]
        result=compile_prompt({},references)
        self.assertEqual([result['mappings'][name]['label'] for name in ('picture.main','video.main','audio.main')],['<Picture 1>','<Video 1>','<Audio 1>'])
        with self.assertRaisesRegex(ValueError,'Ambiguous legacy'):
            compile_prompt({'summary':'<main>'},references)
        for token in ('video.main','audio.main'):
            with self.subTest(token=token),self.assertRaisesRegex(ValueError,'conditioning is not implemented'):
                compile_prompt({'summary':f'<{token}>'},references)

    def test_case_disabled_wrong_kind_malformed_and_missing_subject(self):
        item=ref()
        self.assertEqual(compile_prompt({'summary':'<PiCtUrE.MAIN>'},[item])['resolved_fields']['summary'],'<Picture 1>')
        for token in ('<picture..main>','<video.main>','<picture.main','<Picture main>','<Subject 1>'):
            with self.subTest(token=token),self.assertRaises(ValueError):compile_prompt({'summary':token},[item])
        item['enabled']=False
        with self.assertRaisesRegex(ValueError,'disabled'):compile_prompt({'summary':'<picture.main>'},[item])
        with self.assertRaisesRegex(ValueError,'Duplicate subject'):
            compile_prompt({'subject_definitions':'<Subject 1> is a man.\n<Subject 1> is a woman.'},[])

    def test_override_kind_cannot_change_and_migration_preserves_authored_actions(self):
        item=ref();override={**item,'id':uid(),'kind':'video','scope':'scene','owner_id':'scene','overrides':item['id']}
        with self.assertRaisesRegex(ValueError,'media kind'):effective_references([item,override],'scene',None)
        item['role']='subject'
        fields={'subject_definitions':'<main> is a person.','detailed_description':'[Shot 1] <main> moves.'}
        with self.assertRaisesRegex(ValueError,'manual correction'):migrate_legacy_fields(fields,[item])
        with self.assertRaisesRegex(ValueError,'Bare reference'):compile_prompt(fields,[item])

    def test_compilation_only_expands_assets_and_canonicalizes_native_labels(self):
        from timeline_core.store import FIELDS
        item=ref();item['role']='subject'
        fields={field:'User-authored text with <subject 7> and <picture.main>.' for field in FIELDS}
        fields['subject_definitions']='<subject 7> is the person in <picture.main>. Preserve only the manually specified clothing.'
        result=compile_prompt(fields,[item])
        expected={field:text.replace('<subject 7>','<Subject 7>').replace('<picture.main>','<Picture 1>') for field,text in fields.items()}
        self.assertEqual(result['authored_fields'],fields)
        self.assertEqual(result['resolved_fields'],expected)
        self.assertEqual(result['prompt'],'\n\n'.join(f'{field}:\n{expected[field]}' for field in FIELDS))
        self.assertEqual(result['version'],4)

    def test_legacy_role_never_creates_subjects_or_links(self):
        item=ref();item['role']='subject'
        result=compile_prompt({'summary':'A landscape from <picture.main>.'},[item])
        self.assertEqual(result['subjects'],[])
        self.assertEqual(result['resolved_fields']['subject_definitions'],'')
        self.assertNotIn('<Subject',result['prompt'])
        self.assertEqual(set(result['mappings']),{'picture.main'})
        fields={'subject_definitions':'<subject 2> is an imagined runner.','detailed_description':'[Shot 1] <subject 2> runs.'}
        result=compile_prompt(fields,[item])
        self.assertEqual(result['resolved_fields']['subject_definitions'],'<Subject 2> is an imagined runner.')
        self.assertNotIn('<Picture',result['prompt'])
        for token in ('<main>','<subject.main>','<Subject 1>'):
            with self.subTest(token=token),self.assertRaises(ValueError):compile_prompt({'summary':token},[item])



class ProjectAndProgressTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.test-tmp';root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.data=Store.create(self.temp.name,'Todo tests');self.store=Store(self.temp.name,self.data['id'])
        self.scene=self.data['scenes'][0]
        self.settings=dict(scene_id=self.scene['id'],segment_id=self.scene['segments'][0]['id'],mode='new',profile='fl2va',
            width=768,height=448,seconds=5,fields={'subject_definitions':'<Subject 1> is a runner.','detailed_description':'[Shot 1] <Subject 1> runs.'})

    def tearDown(self):self.temp.cleanup()
    def command(self,action,**payload):return self.store.command(self.store.load()['revision'],action,payload)
    def queue(self,**values):return self.store.queue(self.store.load()['revision'],{**self.settings,**values})[1]

    def test_queue_freezes_effective_configuration_without_pin_of_inherited_draft(self):
        from timeline_core.configuration import descriptor
        graph={'pack':{'class_type':'LongCasterTimelineConfiguration','inputs':{'name':'Standard','profile':'fl2va','model':['loader',0],'sampler':['sampler',0],'sigmas':['sigmas',0]}},
            'loader':{'class_type':'Loader','inputs':{}},'sampler':{'class_type':'Sampler','inputs':{}},'sigmas':{'class_type':'Schedule','inputs':{'steps':20}}}
        configuration=descriptor(graph,'pack')
        defaults={'configuration_id':'pack','selections':{'model':'A'},'schema':[{'id':'model','name':'Model source','kind':'model','select':'A','options':[{'value':'A','label':'Full REF2VA'}]}]}
        self.command('set_generation_defaults',defaults=defaults)
        wrong=deepcopy(configuration);wrong['id']='old-pack';wrong['upstream']['old-pack']=wrong['upstream'].pop('pack')
        with self.assertRaisesRegex(ValueError,'follow production defaults'):self.queue(configuration=wrong)
        job=self.queue(configuration=configuration,configuration_id='old-materialized-choice',switch_selections={'old-switch':'B'})
        draft=self.store.load()['scenes'][0]['segments'][0]['working_draft']
        self.assertFalse(draft['configuration_override'])
        for key in ('configuration','configuration_id','switch_selections'):self.assertNotIn(key,draft)
        self.assertEqual(job['snapshot']['configuration']['id'],'pack')
        self.store.fail(job['id'],'test cleanup')
        override=self.queue(configuration=configuration,configuration_override=True,configuration_id='pack',switch_selections={'model':'B'})
        draft=self.store.load()['scenes'][0]['segments'][0]['working_draft']
        self.assertTrue(draft['configuration_override']);self.assertEqual(draft['switch_selections'],{'model':'B'})
        self.assertEqual(override['snapshot']['configuration'],job['snapshot']['configuration'])

    def test_defaults_reject_configuration_id_that_disagrees_with_switch(self):
        defaults={'configuration_id':'hyper','selections':{'acceleration':'C'},'schema':[{'id':'acceleration','name':'Acceleration','kind':'configuration','select':'C','options':[{'value':'C','label':'Standard','configuration_id':'standard'}]}]}
        with self.assertRaisesRegex(ValueError,'does not match'):self.command('set_generation_defaults',defaults=defaults)

    def test_production_switch_defaults_persist_and_validate_selected_sources(self):
        defaults={'configuration_id':'pack','selections':{'model':'A'},'schema':[{'id':'model','name':'Model source','kind':'model','select':'A','options':[{'value':'A','label':'Full REF2VA'}]}]}
        self.command('set_generation_defaults',defaults=defaults)
        self.assertEqual(self.store.load()['generation_defaults'],defaults)
        invalid=deepcopy(defaults);invalid['selections']['model']='E'
        with self.assertRaisesRegex(ValueError,'connected source'):self.command('set_generation_defaults',defaults=invalid)
        self.assertEqual(self.store.load()['generation_defaults'],defaults)

    def test_external_interrupt_before_claim_unlocks_generation(self):
        from timeline_core.execution_status import reconcile
        from unittest.mock import Mock
        job=self.queue();self.store.stage(job['id'],'loading_models',prompt_id='ours',dispatch=True)
        queue=Mock();queue.get_current_queue.return_value=([],[])
        queue.get_history.return_value={'ours':{'status':{'status_str':'error','messages':[['execution_interrupted',{'prompt_id':'ours'}]]}}}
        reconcile(self.store,queue)
        saved=self.store.load()['jobs'][job['id']]
        self.assertEqual(saved['status'],'cancelled');self.assertFalse(active_job(saved))
        self.assertEqual(saved['progress']['stage'],'cancelled');self.queue()

    def test_external_interrupt_inside_engine_is_cancelled(self):
        job=self.queue();self.store.claim(job['id']);self.store.fail(job['id'],'Cancelled in ComfyUI',cancelled=True)
        self.assertEqual(self.store.load()['jobs'][job['id']]['status'],'cancelled')

    def test_reconcile_keeps_live_or_new_jobs_and_detects_removed_queue_item(self):
        from timeline_core.execution_status import reconcile
        from unittest.mock import Mock
        job=self.queue();self.store.stage(job['id'],'queued',prompt_id='ours',dispatch=True)
        queue=Mock();queue.get_current_queue.return_value=([],[]);queue.get_history.return_value={}
        reconcile(self.store,queue)
        self.assertEqual(self.store.load()['jobs'][job['id']]['status'],'queued')
        with self.store.locked():
            data=self.store._read();data['jobs'][job['id']]['updated_at']='2000-01-01T00:00:00+00:00';self.store._commit(data)
        queue.get_current_queue.return_value=([],[[0,'ours']])
        reconcile(self.store,queue)
        self.assertEqual(self.store.load()['jobs'][job['id']]['status'],'queued')
        queue.get_current_queue.return_value=([],[])
        reconcile(self.store,queue)
        self.assertEqual(self.store.load()['jobs'][job['id']]['status'],'cancelled')

    def test_terminal_events_validate_prompt_and_preserve_published_take(self):
        job=self.queue();self.store.stage(job['id'],'queued',prompt_id='ours',dispatch=True)
        with self.assertRaises(Conflict):self.store.execution_ended(job['id'],'unrelated','cancelled','Stop')
        self.store.claim(job['id'])
        artifact=self.store.asset('takes/test/original.mmh3');artifact.parent.mkdir(parents=True);artifact.write_bytes(b'latent')
        take=self.store.complete(job['id'],dict(take_id=uid(),latent_path='takes/test/original.mmh3',latent_sha256=digest(artifact),latent_resource_id=uid()),{})
        self.store.execution_ended(job['id'],'ours','cancelled','Preview interrupted')
        saved=self.store.load();self.assertIn(take['id'],saved['takes'])
        self.assertEqual(saved['jobs'][job['id']]['status'],'succeeded')
        self.assertEqual(saved['jobs'][job['id']]['progress']['stage'],'preview_failed')
        self.assertFalse(active_job(saved['jobs'][job['id']]))
        self.store.stage(job['id'],'complete')
        self.store.execution_ended(job['id'],'ours','cancelled','Late duplicate event')
        self.assertEqual(self.store.load()['jobs'][job['id']]['progress']['stage'],'complete')

    def test_reconcile_reports_upstream_error_as_failure(self):
        from timeline_core.execution_status import reconcile
        from unittest.mock import Mock
        job=self.queue();self.store.stage(job['id'],'queued',prompt_id='ours',dispatch=True)
        queue=Mock();queue.get_current_queue.return_value=([],[])
        queue.get_history.return_value={'ours':{'status':{'status_str':'error','messages':[['execution_error',{'exception_message':'Loader failed'}]]}}}
        reconcile(self.store,queue)
        saved=self.store.load()['jobs'][job['id']]
        self.assertEqual(saved['status'],'failed');self.assertEqual(saved['error'],'Loader failed')

    def test_project_resolution_is_authoritative_and_persists(self):
        self.command('set_resolution',width=1024,height=576)
        data=self.store.load();self.assertEqual(project_resolution(data),{'width':1024,'height':576})
        self.assertEqual(data['scenes'][0]['segments'][0]['working_draft']['width'],1024)
        with self.assertRaisesRegex(ValueError,'project resolution'):self.queue()
        job=self.queue(width=1024,height=576)
        self.assertEqual(job['snapshot']['width'],1024)
        with self.assertRaises(Conflict):self.command('set_resolution',width=768,height=448)

    def test_progress_tracks_prompt_and_postprocessing_remains_active(self):
        job=self.queue();self.store.stage(job['id'],'loading_models',prompt_id='ours',dispatch=True)
        self.store.claim(job['id']);self.store.stage(job['id'],'sampling')
        self.store.stage(job['id'],'sampling',prompt_id='ours',value=4,maximum=8,dispatch=True)
        with self.assertRaises(Conflict):self.store.stage(job['id'],'sampling',prompt_id='other',value=8,maximum=8,dispatch=True)
        artifact=self.store.asset('takes/test/original.mmh3');artifact.parent.mkdir(parents=True);artifact.write_bytes(b'latent')
        self.store.complete(job['id'],dict(take_id=uid(),latent_path='takes/test/original.mmh3',latent_sha256=digest(artifact),latent_resource_id=uid()),{})
        self.assertTrue(active_job(self.store.load()['jobs'][job['id']]))
        with self.assertRaises(Conflict):self.queue()
        self.store.stage(job['id'],'building_preview');self.store.stage(job['id'],'preview_failed')
        self.assertFalse(active_job(self.store.load()['jobs'][job['id']]))
        current=self.store.load()['jobs'][job['id']]
        self.assertEqual(current['status'],'succeeded')
        self.assertEqual(current['snapshot'],job['snapshot'])
        self.assertEqual(current['prompt_id'],'ours')

    def test_late_dispatch_cannot_regress_stage_and_zero_cannot_generate(self):
        with self.assertRaises(ValueError):self.queue(seconds=0)
        job=self.queue();self.store.claim(job['id']);self.store.stage(job['id'],'encoding')
        self.store.stage(job['id'],'queued',prompt_id='ours',dispatch=True)
        self.assertEqual(self.store.load()['jobs'][job['id']]['progress']['stage'],'encoding')

    def test_changed_project_resolution_does_not_resize_or_continue_old_latents(self):
        job=self.queue();self.store.claim(job['id'])
        take_id=uid();artifact=self.store.asset(f'takes/{take_id}/original.mmh3')
        artifact.parent.mkdir(parents=True);artifact.write_bytes(b'original latent bytes')
        take=self.store.complete(job['id'],dict(take_id=take_id,latent_path=f'takes/{take_id}/original.mmh3',latent_sha256=digest(artifact),latent_resource_id=uid()),{})
        preview=self.store.asset(f'takes/{take_id}/preview.mp4');preview.write_bytes(b'preview')
        atomic_json(preview.with_suffix('.json'),dict(status='ready',source_sha256=take['latent_sha256'],path=f'takes/{take_id}/preview.mp4'))
        self.store.stage(job['id'],'complete');self.command('finalize',take_id=take_id)
        self.command('set_resolution',width=1024,height=576)
        draft={**self.settings,'mode':'extend','source_take_id':take_id,'width':1024,'height':576,'context':39}
        data=self.command('create_segment',scene_id=self.scene['id'],after_segment_id=take['segment_id'],draft=draft)
        with self.assertRaisesRegex(ValueError,'source resolution'):
            self.queue(**{**draft,'segment_id':data['last_created_segment_id']})
        self.assertEqual(artifact.read_bytes(),b'original latent bytes')
        self.assertEqual(self.store.load()['takes'][take_id],take)

    def test_migration_requires_review_and_never_rewrites_generated_data(self):
        data=self.store.load();item=ref();data['references']=[item]
        draft=data['scenes'][0]['segments'][0]['working_draft']
        draft['fields'].update(subject_definitions='<Subject 1> is the person in <main>.',detailed_description='[Shot 1] <Subject 1> runs.')
        data['takes']={'historic':{'snapshot':{'prompt':'<main> original frozen prompt'}}}
        atomic_json(self.store.manifest,data)
        migrated=migrate_legacy_fields(draft['fields'],[item]);before=deepcopy(data['takes'])
        with self.assertRaises(Conflict):self.command('migrate_prompt',segment_id=draft['segment_id'],reviewed_fields={})
        updated=self.command('migrate_prompt',segment_id=draft['segment_id'],reviewed_fields=migrated)
        self.assertEqual(updated['takes'],before)
        self.assertIn('<picture.main>',updated['scenes'][0]['segments'][0]['working_draft']['fields']['subject_definitions'])
