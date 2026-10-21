# FastVideo FastH3 V2 in LongCaster Timeline

Prepared 2026-10-20. Integration checks passed; no model download or GPU generation
was performed. This is an additional FL2VA configuration, not REF2VA acceleration.

## Requirements and limits

The official guide requires ComfyUI >=0.36.0. The last local test startup log
reported 0.38.0; this is evidence from that startup, not a probe of a running
server. Existing H3 CLIP, video VAE and audio VAE are reused.

Install the complete checkpoint through your normal model installation process:
`fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors` under your configured
diffusion-model directory. It is a complete distilled checkpoint with VSA gates,
not a LoRA to apply to the base or PDD model. Installation was not performed here.

Supported official tasks: text-to-video and first/last-frame image-to-video.
REF2VA multi-reference conditioning is not distilled/supported in this recipe.
Do not apply a REF patch to silently pretend it supports named references.

## Connect an external generation configuration

The installed MMH3 Media code already contains **H3 FastH3 V2 Model** and the
**H3 Sampling → FastH3 V2 - 8 steps** preset. Timeline uses their ordinary MODEL
output; it does not invoke MMH3 Generate or replace Timeline's archive handling.

1. **H3 FastH3 V2 Model**: select the complete FastH3 V2 checkpoint.
2. Feed MODEL into **H3 Sampling**, preset **FastH3 V2 - 8 steps**, task family
   **fl2va**. Leave its LoRAs input at automatic/default. That preset installs
   its matching native VSA configuration; do not apply VSA a second time.
3. Feed its MODEL into **MiniMaxH3SigmaShift**. Connect/set its video/audio
   shift outputs: **10 / 3**. The Sampling preset outputs these values; it does
   not itself apply the shift node.
4. Feed the shifted MODEL to **BasicScheduler** and to **LongCaster Timeline –
   Configuration → model**. BasicScheduler uses **simple**, **8 steps**,
   **denoise 1.0**. The Sampling node's scheduler/steps outputs can drive these.
5. **KSamplerSelect** uses **res_multistep** (or connect Sampling's sampler_name).
   Connect its SAMPLER and BasicScheduler's SIGMAS to the Configuration node.
6. Name the configuration **FastH3 V2 - 8 steps**, profile **fl2va**. Connect it
   into a free input on your Configuration Switch, whose output goes to Timeline
   Execution's configuration input. Keep the existing CLIP and VAEs connected.

Alternatively construct the official native chain directly: Load Diffusion Model
with the complete checkpoint -> BlockSparseAttention (VSA keep 10%, start 20%
through the schedule) -> SigmaShift 10/3 -> Configuration MODEL. Pair it with
res_multistep/simple/8 as above. Use one construction, not both VSA paths.

The external configuration switch remains responsible for the selected model,
sampler and sigmas. Timeline now recognizes `MMH3FastH3V2Model.checkpoint` in
selected model ancestry, so its checkpoint is recorded and the installed MMH3
family contract can reject a mistaken REF2VA declaration. This does not certify
arbitrary sampling settings; use the exact recipe above.

## In Timeline

For the cleanest first check, use a separate production with no named media
references and choose FL2VA mode / the FastH3 configuration. Write a normal
text-to-video description. Existing REF2VA prompts containing Picture aliases
must be rewritten or excluded for this path; changing the model does not make
those reference assets available to FL2VA.

For extension from an existing finalized take, select **Last frame - image
restart**, then **FL2VA** and the matching FastH3 configuration. Disable inherited
image references for this target and remove reference labels from its authored
prompt. Timeline can decode the selected preceding take's final delivered frame
and supply it to native `first_frame`; this pathway is implemented but has not
been GPU validated with FastH3. The source resolution must match the production.

The optional **22-frame motion context is REF2VA-only in the current Timeline
implementation** and is unavailable here. Full latent continuation is a separate,
unvalidated experiment for FastH3, not an official FastH3 quality guarantee.

Begin with PDD warmup, Anti-Burn, refinement and continuation protection off.
FastH3 is its own acceleration path; do not stack PDD or HyperFlow onto it.
FastH3 itself can trade motion/audio fidelity for speed, so this is not a promised
fix for the robotic sound observed in PDD continuation.

## Validation and remaining work

- Backend checks: 139 tests, 136 passed and 3 skipped. Added selected FastH3
  loader provenance coverage, including exclusion of an unselected switch path.
- Existing MMH3 source recognizes the V2 checkpoint family as FL2VA and provides
  its native VSA/sampling preset. No MMH3 files were changed or upgraded.
- GPU/model loading, 5s text-to-video, final-frame extension and audio/seam
  acceptance remain untested. No generation is queued and ComfyUI was not started.
- No workflow files were inspected or edited.

Primary source:
https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fastvideo
