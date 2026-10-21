import unittest
from timeline_core.continuation_evidence import edge_policy, capture_context, check_context

try:
    import torch
except ImportError:
    torch = None


class PolicyTests(unittest.TestCase):
    def test_bounds_independence_and_no_hidden_timing_changes(self):
        source = {"plan": {"new_frames": 124}}
        plan = {"context_frames": 39, "new_frames": 119}
        self.assertEqual(edge_policy(4, None, plan)["frames"], 0)
        self.assertEqual(edge_policy(4, source, plan)["audio"], "unchanged_delivery")
        self.assertEqual(plan, {"context_frames": 39, "new_frames": 119})
        for value in (True, 1.5, -1, 9, "4", None):
            with self.assertRaises(ValueError): edge_policy(value, source, plan)
        with self.assertRaises(ValueError): edge_policy(4, {"plan": {"new_frames": 3}}, plan)


@unittest.skipIf(torch is None, "Native tensor invariants require PyTorch; not GPU sampling evidence")
class ContextTests(unittest.TestCase):
    def test_in_place_changes_audio_changes_nan_and_valid_context(self):
        class Joint:
            def __init__(self, *streams): self.streams = streams
            def unbind(self): return self.streams
        receipt = {"video_context_steps": 12, "audio_context_steps": 65}
        latent = {"samples": Joint(torch.ones(1, 2, 20, 2, 2), torch.ones(1, 2, 4, 120))}
        expected = capture_context(latent, receipt)
        self.assertTrue(check_context(latent, expected, receipt)["passed"])
        latent["samples"].streams[0][:, :, 12:] = 3  # New footage is free.
        self.assertTrue(check_context(latent, expected, receipt)["passed"])
        latent["samples"].streams[1][..., 64] += 1e-7
        rounded = check_context(latent, expected, receipt)
        self.assertTrue(rounded["passed"])
        self.assertFalse(rounded["streams"]["audio"]["exact"])
        latent["samples"].streams[1][..., 64] = 2
        self.assertFalse(check_context(latent, expected, receipt)["streams"]["audio"]["exact"])
        latent["samples"].streams[0][:, :, 0] = float("nan")
        self.assertFalse(check_context(latent, expected, receipt)["streams"]["video"]["finite"])
