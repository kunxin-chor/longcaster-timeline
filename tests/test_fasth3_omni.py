import unittest
from unittest.mock import patch
from types import SimpleNamespace, ModuleType
import sys
from timeline_core.fasth3_omni import CHECKPOINTS, ATTACHMENT, LongCasterTimelineFastH3Omni, is_checkpoint, native_sigmas, validate_header


def shapes():
    return {"final_layer.video_out.weight":(3072,5376),"final_layer.video_out.bias":(3072,),
        "final_layer.audio_out.weight":(1024,5376),"final_layer.audio_out.bias":(1024,),
        **{f"blocks.{i}.attn.to_gate_compress.weight":(7168,5376) for i in range(50)}}


class OmniTests(unittest.TestCase):
    def test_only_omniref_native_release_is_selected(self):
        for name in CHECKPOINTS:
            self.assertTrue(is_checkpoint(name));self.assertTrue(is_checkpoint("subfolder/"+name))
        for name in ("fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors","adapter_model.safetensors","minimax_h3_ref2va.safetensors","fasth3_omniref_8step_pruned_int8_convrot.safetensors.bak"):
            self.assertFalse(is_checkpoint(name))

    def test_native_32_head_four_interval_partition(self):
        sigmas=native_sigmas();self.assertEqual(len(sigmas),9)
        self.assertEqual((sigmas[0],sigmas[-1]),(1,0))
        fine=[12*(1-i/32)/(1+11*(1-i/32)) for i in range(33)]
        self.assertEqual(sigmas,fine[::4])
        self.assertTrue(all(a>b for a,b in zip(sigmas,sigmas[1:])))

    def test_complete_heads_and_gates(self):
        validate_header(shapes())
        validate_header({"diffusion_model."+k:v for k,v in shapes().items()})

    def test_partial_or_base_checkpoint_rejected(self):
        for key in shapes():
            data=shapes();data.pop(key)
            with self.assertRaises(ValueError):validate_header(data)
        data=shapes();data["final_layer.video_out.weight"]=(96,5376)
        with self.assertRaises(ValueError):validate_header(data)

    def test_loader_uses_only_native_model_shift_and_euler(self):
        import torch
        data=shapes(); calls=[];attachment={}
        class Header:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def keys(self):return data.keys()
            def get_slice(self,k):return SimpleNamespace(get_shape=lambda:data[k])
        model=SimpleNamespace(get_model_object=lambda _:SimpleNamespace(video_out=SimpleNamespace(weight=SimpleNamespace(shape=(3072,5376))),audio_out=SimpleNamespace(weight=SimpleNamespace(shape=(1024,5376)))))
        shifted=SimpleNamespace(set_attachments=lambda k,v:attachment.update({k:v}))
        def shift(**kwargs):calls.append(kwargs);return (shifted,)
        modules={}
        modules['folder_paths']=SimpleNamespace(get_full_path=lambda *args:'installed-model.safetensors')
        modules['safetensors']=SimpleNamespace(safe_open=lambda *args,**kwargs:Header())
        comfy=ModuleType('comfy');comfy.__path__=[]
        sd=ModuleType('comfy.sd');sd.load_diffusion_model=lambda *args,**kwargs:model;comfy.sd=sd
        modules.update({'comfy':comfy,'comfy.sd':sd,'comfy_extras':ModuleType('comfy_extras'),
            'comfy_extras.nodes_minimax_h3':SimpleNamespace(MiniMaxH3SigmaShift=SimpleNamespace(execute=shift)),
            'comfy_extras.nodes_custom_sampler':SimpleNamespace(KSamplerSelect=SimpleNamespace(execute=lambda name:(name,)))})
        with patch.dict(sys.modules,modules):result=LongCasterTimelineFastH3Omni().load(CHECKPOINTS[0])
        self.assertIs(result[0],shifted);self.assertEqual(result[1],'euler')
        self.assertEqual(calls,[{'model':model,'shift_video':12.0,'shift_audio':3.0}])
        torch.testing.assert_close(result[2],torch.tensor(native_sigmas()))
        self.assertFalse(attachment[ATTACHMENT]['attention_override'])
        self.assertFalse(attachment[ATTACHMENT]['added_loras'])
        self.assertFalse(attachment[ATTACHMENT]['external_pdd_handoff'])

    def test_checkpoint_provenance_through_configuration(self):
        from timeline_core.engine import model_checkpoint_sources
        graph={'exec':{'class_type':'LongCasterTimelineExecute','inputs':{'configuration':['config',0]}},
            'config':{'class_type':'LongCasterTimelineConfiguration','inputs':{'model':['omni',0]}},
            'omni':{'class_type':'LongCasterTimelineFastH3Omni','inputs':{'unet_name':CHECKPOINTS[0]}}}
        self.assertEqual(model_checkpoint_sources(graph),[{'checkpoint':CHECKPOINTS[0],'ref_patch_node':None}])

if __name__=='__main__':unittest.main()
