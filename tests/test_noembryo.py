import unittest
import torch
from timeline_core.vendor.noembryo.core import refine,_band_split,_AVStreamPair


class NoEmbryoTests(unittest.TestCase):
    def test_statistics_do_not_mutate_source_or_audio(self):
        generator=torch.Generator().manual_seed(124)
        video=torch.randn((1,24,47,16,16),generator=generator)*1.15+.12
        audio=torch.randn((1,32,2,263),generator=generator)
        anchor=torch.randn((1,24,37,16,16),generator=generator)
        original=video.clone()
        result,report=refine({'samples':_AVStreamPair(video,audio)},1.,39,
                            reference_latent={'samples':_AVStreamPair(anchor,audio)})
        corrected,returned_audio=result['samples'].unbind()
        self.assertTrue(torch.equal(original,video))
        self.assertTrue(torch.equal(returned_audio,audio))
        self.assertTrue(torch.isfinite(corrected).all())
        self.assertLess(abs(float(corrected.mean())),abs(float(video.mean())))
        self.assertIn('CORRECTED',report)

    def test_detail_transfer_uses_original_low_band_and_donor_high_band(self):
        generator=torch.Generator().manual_seed(75)
        video=torch.randn((1,24,47,16,16),generator=generator)
        donor=torch.randn(video.shape,generator=generator)
        audio=torch.ones(1,32,2,263)
        result,report=refine({'samples':_AVStreamPair(video,audio)},0.,39,detail_donor=donor)
        body=video[0,:,12:-12];detail=donor[0,:,12:-12]
        lo,_=_band_split(body.reshape(-1,16,16));_,hi=_band_split(detail.reshape(-1,16,16))
        torch.testing.assert_close(result['samples'].unbind()[0][0,:,12:-12],(lo+hi).reshape_as(body))
        self.assertIn('refine+detail',report)
