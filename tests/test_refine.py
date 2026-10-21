import sys
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch

from timeline_core.refine import controls, freeze, apply
from timeline_core.vendor.h3_refine import schedule, refine_blend


class Joint:
    def __init__(self, parts): self.parts = list(parts)
    def unbind(self): return self.parts


class Model:
    def __init__(self):self.wrappers={}
    def clone(self):return copy.deepcopy(self)
    def add_wrapper_with_key(self,kind,key,fn):self.wrappers.setdefault(kind,{}).setdefault(key,[]).append(fn)


class RefineTests(unittest.TestCase):
    def test_disabled_is_zero_cost_and_independent_start_is_skipped(self):
        raw = object()
        self.assertIs(apply(raw, None, None, None, 1, 0, freeze(None, None))[0], raw)
        self.assertFalse(freeze({"enabled": True}, None)["applied"])
        for invalid in ({"enabled": 1}, {"steps": True}, {"steps": 0}, {"steps": 5}, "on"):
            with self.assertRaises(ValueError): controls(invalid)

    def run_refine(self, corrupt=None, sigmas=None, setting=None, anchor=None, person_mask=None):
        self.raw = {"samples": Joint((torch.ones(1, 24, 47, 2, 2), torch.ones(1, 32, 2, 263)))}
        vm = torch.ones(1, 1, 47, 2, 2); vm[:, :, :12] = 0
        am = torch.ones(1, 1, 2, 263); am[..., :65] = 0
        self.raw["noise_mask"] = Joint((vm, am))
        self.calls = []
        def sample(noise, guider, sampler, sigmas, latent):
            for sigma in sigmas[:-1]:
                for group in guider.wrappers.values():
                    for functions in group.values():
                        for fn in functions:fn(lambda *a,**k:None,None,torch.tensor([float(sigma)*1000]))
            self.calls.append((noise, sampler, sigmas.clone(), latent))
            video, audio = latent["samples"].unbind()
            mv, ma = latent["noise_mask"].unbind()
            video.add_(mv * 2)  # Exercise an in-place sampler implementation.
            if corrupt == "audio": audio.add_(1)
            if corrupt == "head": video[:, :, 0].add_(1)
            return ({**latent, "samples": Joint((video, audio))},)
        nodes = SimpleNamespace(BasicGuider=SimpleNamespace(execute=lambda *args:(args[0],)),
            RandomNoise=SimpleNamespace(execute=lambda seed:(seed,)),
            KSamplerSelect=SimpleNamespace(execute=lambda name:(name,)),
            BasicScheduler=SimpleNamespace(execute=lambda model,name,steps,denoise:(torch.linspace(.4,0,steps+1),)),
            SamplerCustomAdvanced=SimpleNamespace(execute=sample))
        mods = {"comfy": SimpleNamespace(), "comfy.nested_tensor": SimpleNamespace(NestedTensor=Joint),
            "comfy_extras": SimpleNamespace(), "comfy_extras.nodes_custom_sampler": nodes,
            "comfy.patcher_extension":SimpleNamespace(WrappersMP=SimpleNamespace(DIFFUSION_MODEL='diffusion'))}
        if sigmas is None: sigmas = torch.tensor([1., .98, .95, .9, .85, .8, .7, .5, 0.])
        with patch.dict(sys.modules, mods):
            return apply(self.raw, Model(), [], sigmas, 123, 39, freeze(setting or {"enabled": True}, {"id":"parent"},
                {"id":"anchor","latent_path":"root.mmh3","latent_sha256":"hash","width":32,"height":32} if anchor else None),anchor=anchor,person_mask=person_mask)

    def test_euler_tail_hard_masks_audio_and_original_remain_intact(self):
        result, receipt = self.run_refine()
        noise, sampler, tail, work = self.calls[0]
        self.assertEqual(sampler, "euler")
        self.assertEqual(noise, (123 ^ 0x5EF1) & 0x7fffffff)
        self.assertTrue(torch.equal(tail, torch.tensor([.7, .5, 0.])))
        vm, am = work["noise_mask"].unbind()
        self.assertTrue(torch.all(vm[:, :, :12] == 0))
        self.assertTrue(torch.all(vm[:, :, 12:] == 1))
        self.assertTrue(torch.all(am == 0))
        video, audio = result["samples"].unbind()
        self.assertTrue(torch.equal(video[:, :, :12], self.raw["samples"].unbind()[0][:, :, :12]))
        self.assertTrue(torch.equal(audio, self.raw["samples"].unbind()[1]))
        self.assertTrue(torch.all(self.raw["samples"].unbind()[0] == 1))
        self.assertTrue(torch.all(video[:, :, 20:] == 3))
        self.assertTrue(receipt["output_audio_exact"])
        self.assertEqual(receipt["blend_frames"], "0:0, 39:0, 61:1")

    def test_sampler_mask_violations_fail_instead_of_being_hidden_by_blend(self):
        for corrupt in ("audio", "head"):
            with self.subTest(corrupt=corrupt), self.assertRaises(RuntimeError): self.run_refine(corrupt)

    def test_statistics_anchor_is_required_and_generates_no_sampler_calls(self):
        with self.assertRaises(ValueError):freeze({'enabled':True,'mode':'noembryo_stats'},{'id':'parent'})
        anchor={'samples':Joint((torch.full((1,24,37,2,2),1.2),torch.ones(1,32,2,200)))}
        result,receipt=self.run_refine(setting={'enabled':True,'mode':'noembryo_stats'},anchor=anchor)
        self.assertEqual(len(self.calls),0)
        self.assertEqual(receipt['actual_steps'],0)
        self.assertEqual(receipt['sigma_values'],[])
        self.assertTrue(torch.equal(result['samples'].unbind()[0][:,:,:12],self.raw['samples'].unbind()[0][:,:,:12]))
        self.assertTrue(torch.equal(result['samples'].unbind()[1],self.raw['samples'].unbind()[1]))

    def test_character_mask_keeps_unselected_background_exact(self):
        mask=torch.zeros(1,1,47,2,2);mask[:,:,:,0,0]=1
        result,receipt=self.run_refine(setting={'enabled':True,'mode':'character_masked','steps':3},person_mask=mask)
        v=result['samples'].unbind()[0];original=self.raw['samples'].unbind()[0]
        self.assertTrue(torch.equal(v[:,:,:,:,1],original[:,:,:,:,1]))
        self.assertTrue(torch.all(v[:,:,20:,0,0]>original[:,:,20:,0,0]))
        self.assertEqual(receipt['actual_steps'],3)

    def test_refine_follows_each_supplied_standard_or_accelerated_schedule(self):
        for steps in (4,8,20,30):
            sigmas = torch.linspace(1,0,steps+1)
            _, receipt = self.run_refine(sigmas=sigmas)
            self.assertEqual(receipt["base_steps"],steps)
            self.assertTrue(torch.equal(self.calls[0][2],sigmas[-3:]))

    def test_real_h3_context_token_mapping_and_no_full_schedule_restart(self):
        for context, tokens in ((39, 12), (90, 27), (141, 42)):
            self.assertEqual(refine_blend.whole_steps_for_frames(context), tokens)
            weights = refine_blend.step_weights(tokens+20, refine_blend.parse(refine_blend.auto_ramp(context)))
            self.assertTrue(all(w == 0 for w in weights[:tokens]))
        sigmas = torch.tensor([1., .7, .5, 0.])
        selected, actual, base = schedule.tail(sigmas, 99)
        self.assertEqual((actual, base), (2, 3))
        self.assertEqual(selected.tolist(), sigmas[1:].tolist())
        with self.assertRaises(ValueError): schedule.tail(torch.tensor([1., 0.]), 2)
