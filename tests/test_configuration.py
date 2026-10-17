from copy import deepcopy
import ast
import json
from pathlib import Path
import tempfile
import unittest

from timeline_core.configuration import (LongCasterTimelineConfiguration, LongCasterTimelineConfigurationSwitch,
    descriptor, freeze_configuration, verify_configuration)
from timeline_core.engine import model_checkpoint_names
from timeline_core.store import Store


def graph_fixture():
    return {
        'run': {'class_type': 'LongCasterTimelineExecute', 'inputs': {'configuration': ['switch', 0], 'clip': ['clip', 0]}},
        'switch': {'class_type': 'LongCasterTimelineConfigurationSwitch', 'inputs': {'select': 'B', 'source_a': ['a', 0], 'source_b': ['b', 0]}},
        'a': {'class_type': 'LongCasterTimelineConfiguration', 'inputs': {'name': 'Baseline', 'profile': 'ref2va', 'model': ['model-a', 0], 'sampler': ['sampler', 0], 'sigmas': ['sigmas', 0]}},
        'b': {'class_type': 'LongCasterTimelineConfiguration', 'inputs': {'name': 'PDD 8 steps', 'profile': 'fl2va', 'model': ['model-b', 0], 'sampler': ['sampler', 0], 'sigmas': ['sigmas', 0]}},
        'model-a': {'class_type': 'Loader', 'inputs': {'unet_name': 'ref2va.safetensors'}},
        'model-b': {'class_type': 'Loader', 'inputs': {'unet_name': 'fl2va.safetensors', 'token': 'private'}},
        'sampler': {'class_type': 'Sampler', 'inputs': {'sampler_name': 'euler'}},
        'sigmas': {'class_type': 'Schedule', 'inputs': {'steps': 8, 'shift': 1e-7}},
        'clip': {'class_type': 'TextLoader', 'inputs': {'model_name': 'ref2va-text.safetensors'}}}


class ConfigurationTests(unittest.TestCase):
    def test_dual_model_switch_prunes_and_verifies_each_selection(self):
        from timeline_core.configuration import LongCasterTimelineModelSwitch
        graph=graph_fixture()
        graph['model-switch']={'class_type':'LongCasterTimelineModelSwitch','inputs':{'name':'Model source','profile':'ref2va','select':'B','source_a':['model-a',0],'source_b':['model-b',0]}}
        graph['a']['inputs']['model']=['model-switch',0]
        graph['switch']['inputs']['select']='A'
        expected=descriptor(graph,'a','switch','A')
        self.assertNotIn('model-a',expected['upstream'])
        self.assertEqual(expected['switch_values'],{'model-switch':'B'})
        self.assertEqual(freeze_configuration(expected),expected)
        actual={k:expected[k] for k in ('id','name','profile','selector_id','slot')}
        verify_configuration(expected,actual,graph,'run')
        changed=deepcopy(graph);changed['model-switch']['inputs']['select']='A'
        with self.assertRaisesRegex(ValueError,'differs'):verify_configuration(expected,actual,changed,'run')
        graph['model-switch']['inputs']['profile']='fl2va'
        with self.assertRaisesRegex(ValueError,'incompatible'):descriptor(graph,'a','switch','A')
        switch=LongCasterTimelineModelSwitch();model=object()
        self.assertEqual(switch.check_lazy_status('B',source_a=model,source_b=None),['source_b'])
        self.assertIs(switch.run('B','Model source','ref2va',source_a=object(),source_b=model)[0],model)

    def test_selected_patched_model_provenance_does_not_include_other_loader(self):
        from timeline_core.engine import model_checkpoint_sources
        graph=graph_fixture()
        graph['patch']={'class_type':'MiniMaxH3RefPatchLoader','inputs':{'model':['model-b',0],'ref_strength':1.0,'patch_name':'ref.safetensors'}}
        graph['model-switch']={'class_type':'LongCasterTimelineModelSwitch','inputs':{'select':'B','source_a':['model-a',0],'source_b':['patch',0]}}
        graph['b']['inputs']['model']=['model-switch',0]
        sources=model_checkpoint_sources(graph)
        self.assertEqual(sources,[{'checkpoint':'fl2va.safetensors','ref_patch_node':'patch'}])
        graph['model-switch']['inputs']['select']='A'
        self.assertEqual(model_checkpoint_sources(graph),[{'checkpoint':'ref2va.safetensors','ref_patch_node':None}])

    def test_comfy_float_coercion_allows_switching_paths_between_takes(self):
        graph=graph_fixture()
        graph['model-a']['inputs']['shift_video']=12
        graph['model-b']['inputs']['shift_video']=12
        graph['sigmas']['inputs']['denoise']=1
        before=deepcopy(graph)
        for pack_id,slot in [('a','A'),('b','B'),('a','A')]:
            graph['switch']['inputs']['select']=slot
            expected=descriptor(graph,pack_id,'switch',slot)
            frozen=deepcopy(expected)
            validated=deepcopy(graph)
            # execution.py converts FLOAT widgets in place during validation.
            validated['model-a']['inputs']['shift_video']=12.0
            validated['model-b']['inputs']['shift_video']=12.0
            validated['sigmas']['inputs']['denoise']=1.0
            actual={k:expected[k] for k in ('id','name','profile','selector_id','slot')}
            self.assertNotEqual(descriptor(validated,pack_id,'switch',slot)['upstream_sha256'],expected['upstream_sha256'])
            verify_configuration(expected,actual,validated,'run')
            self.assertEqual(expected,frozen)
        self.assertEqual(graph['model-a'],before['model-a'])

    def test_numeric_equivalence_does_not_hide_changed_values_types_or_fingerprints(self):
        graph=graph_fixture();graph['sigmas']['inputs'].update(denoise=1,enabled=True)
        expected=descriptor(graph,'b','switch','B')
        actual={k:expected[k] for k in ('id','name','profile','selector_id','slot')}
        for key,value in [('denoise',.9999999999),('denoise','1'),('enabled',1),('steps',12)]:
            changed=deepcopy(graph);changed['sigmas']['inputs'][key]=value
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'configuration.upstream.sigmas.inputs'):
                verify_configuration(expected,actual,changed,'run')
        invalid=deepcopy(expected);invalid['upstream_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            verify_configuration(invalid,actual,graph,'run')

    def test_execution_requests_only_selected_bundle_or_legacy_inputs(self):
        # Load the real node class without importing ComfyUI server/model modules.
        source=Path(__file__).resolve().parents[1]/'nodes.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        node=next(item for item in tree.body if isinstance(item,ast.ClassDef) and item.name=='LongCasterTimelineExecute')
        namespace={'json':json}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
        execute=namespace['LongCasterTimelineExecute']()
        graph={'run':{'inputs':{'configuration':['switch',0], 'model':['unused',0], 'sampler':['unused',0], 'sigmas':['unused',0]}}}
        token=json.dumps({'operation':'generate'})
        self.assertEqual(execute.check_lazy_status(token,prompt=graph,unique_id='run'),['configuration'])
        self.assertEqual(execute.check_lazy_status(token,configuration={'model':object()},prompt=graph,unique_id='run'),[])
        self.assertEqual(execute.check_lazy_status(json.dumps({'operation':'preview'}),prompt=graph,unique_id='run'),[])
        del graph['run']['inputs']['configuration']
        self.assertEqual(execute.check_lazy_status(token,prompt=graph,unique_id='run'),['model','sampler','sigmas'])

    def test_pack_and_selector_keep_model_sampler_sigmas_together(self):
        a, b, sampler, sigmas = object(), object(), object(), object()
        pack = LongCasterTimelineConfiguration()
        first = pack.pack('Baseline', 'ref2va', a, sampler, sigmas, 'a')[0]
        second = pack.pack('PDD', 'ref2va', b, sampler, sigmas, 'b')[0]
        switch = LongCasterTimelineConfigurationSwitch()
        self.assertEqual(switch.check_lazy_status('B', source_a=None, source_b=None), ['source_b'])
        self.assertEqual(switch.check_lazy_status('C', source_a=None, source_b=None), [])
        result = switch.run('B', 'switch', source_a=first, source_b=second)[0]
        self.assertIs(result['model'], b)
        self.assertIs(result['sampler'], sampler)
        self.assertIs(result['sigmas'], sigmas)
        self.assertEqual(result['metadata']['selector_id'], 'switch')
        self.assertIsNone(second['metadata']['selector_id'])
        self.assertTrue(all(value[1]['lazy'] for value in switch.INPUT_TYPES()['optional'].values()))
        with self.assertRaisesRegex(ValueError, 'not connected'): switch.run('C', 'switch')

    def test_frozen_selection_rejects_branch_and_setting_changes(self):
        graph = graph_fixture()
        expected = descriptor(graph, 'b', 'switch', 'B')
        self.assertNotIn('model-a', expected['upstream'])
        self.assertNotIn('clip', expected['upstream'])
        self.assertEqual(expected['upstream']['model-b']['inputs']['token'], '[redacted]')
        self.assertEqual(freeze_configuration(expected), expected)
        actual = {k:expected[k] for k in ('id', 'name', 'profile', 'selector_id', 'slot')}
        verify_configuration(expected, actual, graph, 'run')
        for record, key, value in [('switch', 'select', 'A'), ('sigmas', 'steps', 12), ('b', 'name', 'Changed')]:
            changed = deepcopy(graph); changed[record]['inputs'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_configuration(expected, actual, changed, 'run')
        with self.assertRaises(ValueError): verify_configuration(expected, None, graph, 'run')
        with self.assertRaises(ValueError): verify_configuration(None, actual, graph, 'run')
        self.assertEqual(model_checkpoint_names(graph), ['fl2va.safetensors'])

    def test_queue_freezes_selected_configuration_and_rejects_mode_mismatch(self):
        root = Path(__file__).resolve().parents[1]/'.test-tmp';root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            data = Store.create(directory, 'Configurations'); store = Store(directory, data['id'])
            scene=data['scenes'][0]
            configuration=descriptor(graph_fixture(), 'b', 'switch', 'B')
            settings = dict(scene_id=scene['id'], segment_id=scene['segments'][0]['id'], mode='new', profile='fl2va',
                width=768, height=448, seconds=5, seed=1, fields={'detailed_description':'[Shot 1] A quiet street.'}, configuration=configuration)
            wrong=descriptor(graph_fixture(), 'a', 'switch', 'A')
            with self.assertRaisesRegex(ValueError, 'configuration mode'):
                store.queue(data['revision'], {**settings, 'configuration':wrong})
            state, job=store.queue(data['revision'], settings)
            configuration['name']='Edited after queue'
            self.assertEqual(job['snapshot']['configuration']['name'], 'PDD 8 steps')
            self.assertEqual(store.claim(job['id'])['snapshot']['configuration']['upstream_sha256'], job['snapshot']['configuration']['upstream_sha256'])

    def test_invalid_definitions_and_cycles_fail(self):
        graph=graph_fixture();graph['a']['inputs']['name']=' '
        with self.assertRaises(ValueError): descriptor(graph,'a')
        graph=graph_fixture();graph['model-b']['inputs']['model']=['b',0]
        with self.assertRaisesRegex(ValueError,'cycle'): descriptor(graph,'b')
