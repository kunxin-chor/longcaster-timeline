"""Plain native FastH3 Omni checkpoint and 8-step PDD recipe.

No LoRA, external PDD Apply, VSA, attention override or base warmup is installed.
This is a native Comfy sampling recipe, not FastVideo runtime parity.
"""
from pathlib import PurePosixPath

SOURCE = "https://huggingface.co/FastVideo/FastH3-Omni-Comfy"
REVISION = "82eff2a6eee6c962846879f4bab52610a4df24d3"
CHECKPOINTS = (
    "fasth3_omniref_8step_pruned_int8_convrot.safetensors",
    "fasth3_omniref_8step_pruned_bf16.safetensors",
)
ATTACHMENT = "longcaster_fasth3_omni_plain"


def is_checkpoint(name):
    return PurePosixPath(str(name).replace(chr(92), "/")).name in CHECKPOINTS


def native_sigmas():
    # Native Comfy's PDD fine grid is [1,0], partitioned into eight blocks of four.
    # The publisher explicitly distinguishes this from FastVideo's 0.999 grid.
    return [12 * t / (1 + 11 * t) for t in (1 - i / 8 for i in range(9))]


def validate_header(shapes):
    prefix = "diffusion_model." if "diffusion_model.final_layer.video_out.weight" in shapes else ""
    expected = {
        "final_layer.video_out.weight": (3072, 5376),
        "final_layer.video_out.bias": (3072,),
        "final_layer.audio_out.weight": (1024, 5376),
        "final_layer.audio_out.bias": (1024,),
    }
    for key, shape in expected.items():
        if tuple(shapes.get(prefix + key, ())) != shape:
            raise ValueError("FastH3 Omni requires the complete native checkpoint with 32 PDD heads; incompatible " + key)
    gates = {prefix + f"blocks.{i}.attn.to_gate_compress.weight" for i in range(50)}
    if any(tuple(shapes.get(key, ())) != (7168, 5376) for key in gates):
        raise ValueError("FastH3 Omni requires all 50 native gate-compression weights. Select the Comfy checkpoint, not a LoRA or FastVideo shard.")


class LongCasterTimelineFastH3Omni:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [n for n in folder_paths.get_filename_list("diffusion_models") if is_checkpoint(n)]
        return {"required": {"unet_name": (names or ["(install FastH3 Omni Comfy checkpoint)"],)}}

    RETURN_TYPES = ("MODEL", "SAMPLER", "SIGMAS")
    RETURN_NAMES = ("model", "sampler", "sigmas")
    FUNCTION = "load"
    CATEGORY = "LongCaster Timeline"
    DESCRIPTION = "Full FastH3 Omni REF2VA checkpoint, dense native attention, Euler 8 steps, shifts 12/3. Connect all three outputs to a REF2VA Configuration. No added LoRA, attention patch or PDD handoff."

    def load(self, unet_name):
        if not is_checkpoint(unet_name):
            raise ValueError("Install/select fasth3_omniref_8step_pruned_int8_convrot.safetensors or the BF16 Comfy checkpoint.")
        import folder_paths
        import torch
        from safetensors import safe_open
        import comfy.sd
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3SigmaShift
        from comfy_extras.nodes_custom_sampler import KSamplerSelect
        path = folder_paths.get_full_path("diffusion_models", unet_name)
        if not path:
            raise ValueError("FastH3 Omni checkpoint is not installed. Install it and refresh ComfyUI's model list.")
        with safe_open(path, framework="pt", device="cpu") as handle:
            shapes = {k: handle.get_slice(k).get_shape() for k in handle.keys()}
        validate_header(shapes)
        model = comfy.sd.load_diffusion_model(path, model_options={})
        if model is None:
            raise ValueError("ComfyUI could not load FastH3 Omni. Update ComfyUI for native H3/PDD support; do not substitute the older FastH3 V2 recipe.")
        layer = model.get_model_object("diffusion_model.final_layer")
        if tuple(layer.video_out.weight.shape) != (3072, 5376) or tuple(layer.audio_out.weight.shape) != (1024, 5376):
            raise ValueError("Installed ComfyUI did not detect FastH3 Omni's 32 PDD heads. Update ComfyUI before generating.")
        shifted = MiniMaxH3SigmaShift.execute(model=model, shift_video=12.0, shift_audio=3.0)[0]
        shifted.set_attachments(ATTACHMENT, {
            "checkpoint": unet_name, "source": SOURCE, "reviewed_revision": REVISION,
            "profile": "ref2va", "steps": 8, "sampler": "euler", "cfg": 1,
            "video_shift": 12, "audio_shift": 3, "sigma_values": native_sigmas(),
            "attention_override": False, "added_loras": False, "external_pdd_handoff": False,
            "runtime": "native_comfy_pdd_unit_grid", "gpu_acceptance": "pending",
        })
        return shifted, KSamplerSelect.execute("euler")[0], torch.tensor(native_sigmas(), dtype=torch.float32)
