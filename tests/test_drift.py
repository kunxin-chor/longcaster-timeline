from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import torch
import torch.nn.functional as F

from timeline_core.drift import freeze, prepare, install_sampling, validate_sampling
from timeline_core.store import Store, digest, uid
from timeline_core.vendor.context_loop.drift_control import (
    apply_dynamic_prefix_mask, temporal_prefix_weights, _DriftControlMaskState)


class Joint:
    def __init__(self,parts): self.parts=list(parts)
    def unbind(self):return self.parts


class VAE:
    def __init__(self):self.decodes=0;self.encodes=0
    def decode(self,video):
        self.decodes+=1
        values=F.interpolate(video[:,:1,:,:1,:1],size=(39,1,1),mode="trilinear",align_corners=True)[0,0,:,0,0]
        return values[:,None,None,None].expand(39,2,2,3).contiguous()
    def encode(self,frames):
        self.encodes+=1
        return F.interpolate(frames.mean(dim=(1,2,3)).view(1,1,39,1,1),size=(12,2,2),mode="trilinear",align_corners=True)


class Model:
    def __init__(self,options=None):
        self.model=SimpleNamespace(model_type=SimpleNamespace(name="FLOW_AV"))
        self.model_options={} if options is None else options;self.wrappers={}
    def clone(self):return Model(self.model_options)
    def set_model_denoise_mask_function(self,fn):self.model_options["denoise_mask_function"]=fn
    def add_wrapper_with_key(self,kind,key,fn):self.wrappers.setdefault(kind,{}).setdefault(key,[]).append(fn)


class DriftTests(unittest.TestCase):
    def setUp(self):
        directory=Path(__file__).resolve().parents[1]/".test-tmp";directory.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory)
        self.store=Store(self.temp.name,uid());self.store.path.mkdir()
        path=self.store.asset("anchor.mmh3");path.write_bytes(b"anchor")
        self.anchor={"id":"anchor","latent_path":"anchor.mmh3","latent_sha256":digest(path),"width":2,"height":2}
        self.source={"id":"parent","latent_sha256":"different"}
        self.video=torch.full((1,1,47,2,2),.25);self.audio=torch.randn(1,2,2,263)
        self.latent={"samples":Joint((self.video,self.audio))}
    def tearDown(self):self.temp.cleanup()

    def snapshot(self,mode):return {"source":self.source,"width":2,"height":2,
        "continuation_protection":freeze(mode,self.source,{"context_frames":39},self.anchor)}

    def test_independent_off_context_and_refiner_combination_contracts(self):
        self.assertFalse(freeze("drift_color",None,{"context_frames":0})["applied"])
        self.assertFalse(freeze(None,self.source,{"context_frames":39})["applied"])
        for mode in ("drift_control","color_stable","drift_color"):
            with self.assertRaises(ValueError):freeze(mode,self.source,{"context_frames":90},self.anchor)
            with self.assertRaises(ValueError):freeze(mode,self.source,{"context_frames":39},self.anchor,True)
        validate_sampling({"applied":False})
        with self.assertRaises(RuntimeError):validate_sampling({"drift_control":True,"mask_calls":0})

    def test_pdd_schedule_matched_mask_audio_and_new_video_unchanged(self):
        sigmas=[1,.9882352948,.9729729891,.9523809552,.9230769277,.8780487776,.8000000119,.6315789223,0]
        state=_DriftControlMaskState((1,2,15,1,1),12,sigmas)
        original=torch.full((1,1,35),.42)
        for current,next_sigma in zip(sigmas,sigmas[1:]):
            packed=state.denoise_mask_function(torch.tensor(current),original)
            video=packed[...,:30].reshape(1,2,15,1,1)
            expected=torch.tensor(temporal_prefix_weights(12,4))*next_sigma/current
            self.assertTrue(torch.allclose(video[0,0,:12,0,0],expected,atol=1e-6))
            self.assertTrue(torch.equal(packed[...,30:],original[...,30:]))
            self.assertTrue(torch.equal(video[:,:,12:],original[...,:30].reshape(1,2,15,1,1)[:,:,12:]))
        self.assertTrue(torch.all(video[:,:,:12]==0))
        self.assertTrue(torch.all(original==.42))

    def test_sigma_split_update_preserves_starting_state_and_clean_reference(self):
        reference=torch.full((1,1,35),.25)
        state=_DriftControlMaskState((1,2,15,1,1),12,[1,.8,.5,0],reference)
        guider=SimpleNamespace(inner_model=SimpleNamespace(process_latent_in=lambda x:x,model_sampling=SimpleNamespace(noise_scale=1)))
        stage=torch.full_like(reference,.75);noise=torch.full_like(reference,.1)
        expected=.5*noise+.5*stage;calls=[]
        state.sampler_sample_wrapper(lambda *args:calls.append(args),guider,torch.tensor([.5,0]),{},None,noise,stage,torch.ones_like(reference),False)
        self.assertTrue(torch.allclose(.5*calls[0][4]+.5*calls[0][5],expected))
        self.assertTrue(torch.equal(calls[0][5],reference))

    def test_latest_model_hooks_are_isolated_and_execution_is_recorded(self):
        model=Model();modules={"comfy":SimpleNamespace(),"comfy.patcher_extension":SimpleNamespace(WrappersMP=SimpleNamespace(APPLY_MODEL="apply",SAMPLER_SAMPLE="sample"))}
        with patch.dict(sys.modules,modules):
            _,patched,report=prepare(None,self.store,self.snapshot("drift_control"),self.latent,model,torch.tensor([1.,.8,0]),None)
        self.assertEqual(model.model_options,{})
        self.assertEqual(len(patched.wrappers),2)
        mask=torch.ones(1,1,self.video.numel()+self.audio.numel())
        patched.model_options["denoise_mask_function"](torch.tensor(1.),mask)
        self.assertEqual(report["mask_calls"],1)
        self.assertAlmostEqual(report["sigma_trace"][0]["ratio"],.8,places=6)
        validate_sampling(report)

    def test_color_only_changes_disposable_video_prefix_and_retains_audio(self):
        vae=VAE();before=self.video.clone()
        anchor_latent={"samples":Joint((torch.full((1,1,12,2,2),.75),self.audio))}
        with patch("timeline_core.engine.primary",return_value=(anchor_latent,None,None)):
            output,model,report=prepare(SimpleNamespace(load_archive=lambda *args,**kw:None),self.store,self.snapshot("color_stable"),self.latent,None,None,vae)
        video,audio=output["samples"].unbind()
        self.assertTrue(torch.equal(self.video,before))
        self.assertTrue(torch.equal(video[:,:,0],self.video[:,:,0]))
        self.assertFalse(torch.equal(video[:,:,11],self.video[:,:,11]))
        self.assertTrue(torch.equal(video[:,:,12:],self.video[:,:,12:]))
        self.assertTrue(torch.equal(audio,self.audio))
        self.assertTrue(report["color"]["applied"])
        self.assertFalse(report["drift_control"])
        self.assertIsNone(model)
        self.assertEqual(vae.encodes,2)
        self.assertEqual(vae.decodes,2)  # Anchor + source, without decoding source twice.

    def test_warmup_both_phases_share_full_schedule_and_restore_split_reference(self):
        sigmas=torch.tensor([1.,.995,.988,.979,.966,.946,.914,.875,.8,12/19,0])
        snap=self.snapshot('drift_color')
        snap['source']={**self.source,'latent_sha256':self.anchor['latent_sha256']}
        modules={'comfy':SimpleNamespace(),'comfy.patcher_extension':SimpleNamespace(
            WrappersMP=SimpleNamespace(APPLY_MODEL='apply',SAMPLER_SAMPLE='sample'))}
        with patch.dict(sys.modules,modules):
            latent,base,report=prepare(None,self.store,snap,self.latent,Model(),sigmas,VAE(),phase='base')
            pdd=install_sampling(Model(),latent,sigmas,report,phase='pdd')
        n=self.video.numel()+self.audio.numel();mask=torch.ones(1,1,n)
        for model,schedule in ((base,sigmas[:8]),(pdd,sigmas[8:-1])):
            for sigma in schedule:model.model_options['denoise_mask_function'](sigma,mask)
        self.assertEqual(report['phase_mask_calls'],{'base':8,'pdd':2})
        self.assertAlmostEqual(report['sigma_trace'][8]['ratio'],(12/19)/.8,places=6)
        self.assertEqual(report['sigma_trace'][-1]['ratio'],0)
        self.assertTrue(report['color']['neutral'])
        state=pdd.model_options['h3_context_loop_drift_control_av']
        reference=torch.full((1,1,n),.25);state.reference_samples=reference
        stage=torch.full_like(reference,3.);noise=torch.zeros_like(reference);calls=[]
        guider=SimpleNamespace(inner_model=SimpleNamespace(process_latent_in=lambda x:x,model_sampling=SimpleNamespace(noise_scale=1)))
        fn=pdd.wrappers['sample']['h3_context_loop_drift_control_split_handoff'][0]
        fn(lambda *args:calls.append(args),guider,sigmas[8:],{},None,noise,stage,mask,False)
        torch.testing.assert_close(.8*calls[0][4]+.2*calls[0][5],.2*stage)
        torch.testing.assert_close(calls[0][5],reference)
        self.assertEqual(report['split_handoff_calls'],1)

    def test_first_color_continuation_is_neutral_and_anchor_tampering_fails(self):
        snap=self.snapshot("color_stable");snap["source"]={**self.source,"latent_sha256":self.anchor["latent_sha256"]}
        vae=VAE();out,_,report=prepare(None,self.store,snap,self.latent,None,None,vae)
        self.assertIs(out,self.latent)
        self.assertEqual((vae.decodes,vae.encodes),(0,0))
        self.assertEqual(report["color"]["reason"],"first_continuation_from_anchor")
        self.store.asset("anchor.mmh3").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"anchor archive"):
            prepare(None,self.store,self.snapshot("color_stable"),self.latent,None,None,vae)
