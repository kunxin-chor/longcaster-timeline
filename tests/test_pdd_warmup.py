import copy
import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import torch

from timeline_core.pdd_warmup import HEAD, KEY, freeze, prepare, sample, for_refinement

CORE = ModuleType('fake_pdd.pdd_acc_core')
exec('''
def warmup_schedule(n, handoff):
    t=handoff/(12-11*handoff)
    head=[12*u/(1+11*u) for u in [1+(t-1)*i/n for i in range(n+1)]]
    return head+[12/19,0.0],n
def make_head(bounds):
    def pdd_final_forward(self):
        return bounds
    return pdd_final_forward
''', CORE.__dict__)
NODES = ModuleType('fake_pdd.nodes')
exec('def pdd_acc_wrapper(executor,*args,**kwargs): return executor(*args,**kwargs)', NODES.__dict__)


class Layer:
    video_out=SimpleNamespace(weight=torch.empty(96,1))
    def forward(self): pass


class Model:
    def __init__(self):
        self.parent=None;self.patches={};self.object_patches={};self.wrappers={};self.model_options={'attention':'kitchen'}
        self.layer=Layer()
    def clone(self):
        result=copy.copy(self);result.parent=self
        result.patches={k:v[:] for k,v in self.patches.items()}
        result.object_patches=dict(self.object_patches)
        result.wrappers={k:{key:v[:] for key,v in group.items()} for k,group in self.wrappers.items()}
        return result
    def get_model_object(self,path): return self.layer
    def add_wrapper_with_key(self,kind,key,fn):self.wrappers.setdefault(kind,{}).setdefault(key,[]).append(fn)


class WarmupTests(TestCase):
    def setUp(self):
        self.modules=patch.dict(sys.modules,{CORE.__name__:CORE,NODES.__name__:NODES});self.modules.start();self.addCleanup(self.modules.stop)
        self.bounds=[12*t/(1+11*t) for t in [1-i/8 for i in range(9)]]
        self.sigmas=torch.tensor(self.bounds)
        self.base=Model();self.subject=('subject_lora',);self.base.patches={'weight':[self.subject]}
        self.pdd=self.base.clone();self.distill=('pdd_lora',)
        self.pdd.patches['weight'].append(self.distill)
        self.pdd.object_patches[HEAD]=CORE.make_head(self.bounds).__get__(self.pdd.layer,Layer)
        self.pdd.add_wrapper_with_key('diffusion_model',KEY,NODES.pdd_acc_wrapper)
        self.downstream=self.pdd.clone();self.later=('later_subject_lora',)
        self.downstream.patches['weight'].append(self.later)

    def run_prepare(self,model=None,sigmas=None,**kwargs):
        return prepare(model or self.downstream,self.sigmas if sigmas is None else sigmas,freeze('auto'),**kwargs)

    def test_off_and_non_pdd_never_touch_sampler_or_schedule(self):
        self.assertEqual(prepare(self.downstream,None)[1]['reason'],'disabled')
        self.assertEqual(self.run_prepare(self.base)[1]['reason'],'non_pdd_model')
        for invalid in (True,'yes',{}):
            with self.assertRaises(ValueError):freeze(invalid)

    def test_recover_only_pdd_delta_preserve_other_patches_and_input(self):
        (base,pdd,sigmas,split),report=self.run_prepare()
        self.assertIs(base.patches['weight'][0],self.subject)
        self.assertIs(base.patches['weight'][1],self.later)
        self.assertEqual(len(self.downstream.patches['weight']),3)
        self.assertEqual(len(pdd.patches['weight']),3)
        self.assertNotIn(KEY,base.wrappers['diffusion_model'])
        self.assertIs(base.object_patches[HEAD].__func__,Layer.forward)
        self.assertIsNot(base.model_options,self.downstream.model_options)
        self.assertEqual(split,8);self.assertEqual(len(sigmas),11)
        torch.testing.assert_close(sigmas[-3:],self.sigmas[-3:])
        self.assertEqual(report['removed_trunk_patch_entries'],1)

    def test_refuse_unsafe_base_recovery_and_other_treatments(self):
        for modify in ('missing_parent','baked','rewritten','incomplete','cycle'):
            with self.subTest(modify=modify):
                self.setUp()
                if modify=='missing_parent':self.pdd.parent=None
                if modify=='baked':self.pdd.patches['weight']=[self.subject];self.downstream.patches['weight']=[self.subject,self.later]
                if modify=='rewritten':self.downstream.patches['weight']=[('different',)]
                if modify=='incomplete':self.downstream.object_patches={}
                if modify=='cycle':self.pdd.parent=self.downstream
                with self.assertRaises(ValueError):self.run_prepare()
        with self.assertRaises(ValueError):self.run_prepare(incompatible=True)
        with self.assertRaises(ValueError):self.run_prepare(sigmas=self.sigmas[::2])

    def test_two_phases_handoff_without_new_noise_keep_masks_and_cancel(self):
        prepared,report=self.run_prepare()
        calls=[]
        def execute(noise,guider,sampler,sigmas,latent):
            model=guider
            wrappers=[fn for group in model.wrappers.values() for group_fns in group.values() for fn in group_fns]
            for sigma in sigmas[:-1]:
                for fn in wrappers:fn(lambda *a,**k:None,None,torch.tensor([float(sigma)*1000]))
            calls.append((noise,sigmas.clone(),latent))
            return ({'samples':latent['samples']+1},None)
        fake=SimpleNamespace(BasicGuider=SimpleNamespace(execute=lambda m,c:(m,)),
            RandomNoise=SimpleNamespace(execute=lambda seed:('initial_noise',)),
            DisableNoise=SimpleNamespace(execute=lambda:('zero_noise',)),
            SamplerCustomAdvanced=SimpleNamespace(execute=execute))
        raw={'samples':torch.ones(1),'noise_mask':torch.ones(1)};stages=[]
        with patch.dict(sys.modules,{'comfy_extras.nodes_custom_sampler':fake}):
            result=sample(prepared,report,None,None,raw,123,stage=stages.append)
            self.assertEqual([c[0] for c in calls],['initial_noise','zero_noise'])
            torch.testing.assert_close(calls[1][2]['samples'],raw['samples']+1)
            torch.testing.assert_close(calls[1][2]['noise_mask'],raw['noise_mask'])
            self.assertEqual(report['base_calls'],8);self.assertEqual(report['pdd_calls'],2)
            self.assertEqual(stages,['warming_up','sampling'])
            torch.testing.assert_close(result['samples'],raw['samples']+2)
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                sample(prepared,report,None,None,raw,123,cancelled=lambda:True)

    def test_refine_model_does_not_reuse_warmup_counters_or_modify_upstream(self):
        prepared,report=self.run_prepare()
        base=for_refinement(prepared,self.downstream,True)
        pdd=for_refinement(prepared,self.downstream,False)
        self.assertNotIn(KEY,base.wrappers['diffusion_model'])
        self.assertIn(KEY,pdd.wrappers['diffusion_model'])
        for group in base.wrappers.values():self.assertNotIn('longcaster_pdd_warmup_trace',group)
        base.add_wrapper_with_key('diffusion_model','refine_only',lambda:None)
        self.assertNotIn('refine_only',prepared[0].wrappers['diffusion_model'])
        self.assertEqual(report['base_calls'],0)
        with self.assertRaises(ValueError):for_refinement(None,self.downstream,True)
        with self.assertRaises(ValueError):for_refinement(None,self.base,True)

    def test_nonzero_sigma_handoff_preserves_clean_av_reference_only(self):
        class Joint:
            def __init__(self,parts):self.parts=list(parts)
            def unbind(self):return self.parts
        prepared,report=self.run_prepare()
        video=torch.tensor([[[[[2.]],[[3.]],[[0.]]]]])
        audio=torch.tensor([[[[4.,5.,0.]]]])
        mask=Joint((torch.tensor([[[[[0.]],[[0.]],[[1.]]]]]),torch.tensor([[[[0.,0.,1.]]]])))
        latent={'samples':Joint((video,audio)),'noise_mask':mask}
        calls=[]
        def execute(noise,model,sampler,sigmas,work):
            for sigma in sigmas[:-1]:
                for group in model.wrappers.values():
                    for functions in group.values():
                        for fn in functions:fn(lambda *a,**k:None,None,torch.tensor([float(sigma)*1000]))
            calls.append(work)
            if len(calls)==1:
                # Reproduce nonzero-sigma public sampler output: protected
                # reference inflated, generated region is valid resume state.
                parts=[torch.where(m==0,p*5,p+7) for p,m in zip(work['samples'].unbind(),mask.unbind())]
                return ({'samples':Joint(parts)},None)
            for p,original,m in zip(work['samples'].unbind(),(video,audio),mask.unbind()):
                torch.testing.assert_close(p[m==0],original[m==0])
                torch.testing.assert_close(p[m==1],original[m==1]+7)
            return (work,None)
        fake=SimpleNamespace(BasicGuider=SimpleNamespace(execute=lambda m,c:(m,)),
            RandomNoise=SimpleNamespace(execute=lambda seed:('noise',)),DisableNoise=SimpleNamespace(execute=lambda:('zero',)),
            SamplerCustomAdvanced=SimpleNamespace(execute=execute))
        with patch.dict(sys.modules,{'comfy_extras.nodes_custom_sampler':fake}):
            result=sample(prepared,report,None,None,latent,123)
        self.assertEqual(report['handoff_protected_values'],[2,2])
        self.assertTrue(report['handoff_clean_context_restored'])
        for p,original,m in zip(result['samples'].unbind(),(video,audio),mask.unbind()):
            torch.testing.assert_close(p[m==0],original[m==0])
            torch.testing.assert_close(p[m==1],original[m==1]+7)
        torch.testing.assert_close(video,torch.tensor([[[[[2.]],[[3.]],[[0.]]]]]))

    def test_drift_combination_preserves_partial_prefix_for_upstream_handoff(self):
        # The dynamic mask leaves a meaningful partial prefix, unlike hard
        # context. Do not erase it with the ordinary zero-mask restoration.
        prepared,report=self.run_prepare()
        prepared[1].model_options['h3_context_loop_drift_control_av']=object()
        calls=[]
        def execute(noise,model,sampler,sigmas,work):
            for sigma in sigmas[:-1]:
                for group in model.wrappers.values():
                    for functions in group.values():
                        for fn in functions:fn(lambda *a,**k:None,None,torch.tensor([float(sigma)*1000]))
            calls.append(work)
            return ({'samples':work['samples']+7},None)
        fake=SimpleNamespace(BasicGuider=SimpleNamespace(execute=lambda m,c:(m,)),
            RandomNoise=SimpleNamespace(execute=lambda seed:('noise',)),DisableNoise=SimpleNamespace(execute=lambda:('zero',)),
            SamplerCustomAdvanced=SimpleNamespace(execute=execute))
        latent={'samples':torch.tensor([2.,3.,0.]),'noise_mask':torch.tensor([0.,0.,1.])}
        with patch.dict(sys.modules,{'comfy_extras.nodes_custom_sampler':fake}):
            sample(prepared,report,None,None,latent,123)
        torch.testing.assert_close(calls[1]['samples'],latent['samples']+7)
        self.assertEqual(report['handoff_policy'],'drift_control_preserve_boundary_state_and_restore_reference')
