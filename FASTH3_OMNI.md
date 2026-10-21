# FastH3 Omni: plain REF2VA configuration

Prepared 2026-10-21. 49 targeted CPU integration/core/last-frame regression checks pass; GPU acceptance is pending.
This is the new full Omni REF2VA checkpoint, separate from the older FastH3 V2
FL2VA recipe in FASTH3.md. No model is downloaded or ComfyUI core updated by Timeline.

## Installation

Use FastVideo/FastH3-Omni-Comfy, reviewed revision
`82eff2a6eee6c962846879f4bab52610a4df24d3`.

For the tested machine's RTX 4090, install
`fasth3_omniref_8step_pruned_int8_convrot.safetensors` in your configured
diffusion-model directory. Publisher size: 22,213,723,064 bytes; SHA256:
`851b2dc9670ed864b7f1e951ac9da047d83b1c04ded9bfcc1a9e5bba0ee33f80`.
The full BF16 Comfy checkpoint is also admitted by the loader. Diffusers/FastVideo
shards, LoRAs and the old V2 checkpoint are rejected.

Keep the existing H3 INT8 text encoder (including reference vision tower),
video VAE and FP32 audio VAE for the first comparison. The publisher lists these
as shared components. NVFP4 text-encoder acceleration requires Blackwell;
it is not the initial RTX 4090 recipe.

Use an updated ComfyUI with native 32-head H3 PDD loading. The announcement
mentions 0.42.2; the server last probed here reported 0.38.0. No core files were
inspected or changed. The loader verifies complete output-head/gate geometry,
then verifies loaded head shapes before returning the model. This is a geometry
check, not proof of full native runtime compatibility or a weight checksum check.

## Configuration

Add **LongCaster Timeline - FastH3 Omni (plain)** after restarting ComfyUI.
Select the installed checkpoint. Connect its MODEL, SAMPLER and SIGMAS outputs
to an ordinary **LongCaster Timeline - Configuration** node, named
**FastH3 Omni - plain 8 steps**, profile **ref2va**. Connect that configuration
to Execution, or a free slot on an existing Configuration Switch.
Keep CLIP and both VAEs connected to Execution.

This node supplies:

- Complete checkpoint with native trained 32-head PDD bank.
- Native Comfy dense attention: no VSA, Kitchen, Sol, Sage or other node override.
  Global ComfyUI launch settings still control the default attention backend.
- Sigma shifts 12 video / 3 audio.
- Plain Euler and eight blocks of four native PDD fine intervals.
- Native shifted sigma nodes: 1, 0.9882352941176471, 0.972972972972973,
  0.9523809523809523, 0.9230769230769231, 0.8780487804878049, 0.8,
  0.631578947368421, 0.
- Timeline's existing BasicGuider, CFG 1.

The complete model already contains its distilled weights and head bank. There
is no external PDD Apply or base-model handoff. Keep PDD warmup **Off**: recovering
the old base from a fused checkpoint is unsupported. Keep additional LoRAs,
Anti-Burn, refinement, continuation protection and edge correction off initially.

The plain dense native recipe is an explicit comparison choice. The FastVideo
source runtime uses VSA and a 0.999 fine-grid maximum; native Comfy uses a unit
fine grid and different head storage. This configuration does not claim output,
speed or numerical parity with FastVideo/UniServe. The old V2 shift-10 recipe
and res_multistep/simple preset must not be silently substituted.

## Pull-up acceptance test

Prepare one fresh root plus three continuations from the authorized pull-up
control's same authored prompts and character/gym assets. Do not reuse a PDD- or
SMD-generated first segment. New production; original tests remain unchanged.

Continuations use REF2VA's last-frame Picture reference plus 22-frame/seven-token
video-only motion context. Audio is generated fresh: no audio history or later
audio-refinement pass. Exact context/source/reference receipts, native recipe,
preview readiness and joined playback are checked. Rest 20 continuous queue-idle
seconds before each generation. Stop on an error or a ten-minute generation
limit; no automatic retry. Three continuations assess the requested case, not
long-chain reliability or seamless audio universally.

No workflow files were inspected or edited for this integration. The test uses
an API execution graph constructed from saved take provenance and the native
configuration node.

## Sources

- https://huggingface.co/FastVideo/FastH3-Omni-Comfy
- https://huggingface.co/FastVideo/FastH3-Omni-Comfy/blob/82eff2a6eee6c962846879f4bab52610a4df24d3/conversion/CONVERSION.md
- https://huggingface.co/FastVideo/FastH3-Omni-Comfy/blob/82eff2a6eee6c962846879f4bab52610a4df24d3/provenance/fastvideo_inference.json
- https://haoailab.com/blogs/fastvideo-omniref-update/

Prepared production: `5042a9d5-1eed-494c-af7c-e6e869d65dc0`, **Pull-ups - FastH3 Omni plain - last frame + 22f motion**. Four planned segments, no generations submitted during preparation.
