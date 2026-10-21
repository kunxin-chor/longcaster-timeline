# Generation switches and production defaults

## New example

Load `example_workflows/longcaster_timeline_ref2va_dual_switch.json` in ComfyUI, then open LongCaster. Existing example workflows are unchanged.

The generation panel discovers connected, supported switches and renders one dropdown per switch. This example has:

| Switch | A | B | C | D |
| --- | --- | --- | --- | --- |
| Model source | Full native REF2VA | FL2VA + reference patch (experimental) | - | - |
| Acceleration | HyperFlow, 8 steps | PDD ACC, 8 steps | Standard REF2VA, 20 steps (no acceleration) | SMD REF2VA, 8 steps |

The lazy MODEL switch feeds the acceleration branches. Each acceleration branch bundles its matching MODEL, SAMPLER and SIGMAS in a Configuration node. A Configuration Switch selects the complete bundle. Comfy Kitchen runs after the acceleration patch on each branch. Only the chosen branch is submitted; unused model loaders, adapters and schedules are pruned from the queued prompt.

Select the real installed filenames in the loaders and adapter nodes. No weights or node packs are installed automatically. HyperFlow uses the existing full node-build adapter, its native SIGMAS and Euler; its SIGMAS must not be shifted again. PDD uses its own SIGMAS with video/audio shifts 12/3 and Euler. Standard REF2VA uses res_multistep, a simple 20-step scheduler at denoise 1.0, the same 12/3 shifts and Comfy Kitchen, with neither HyperFlow nor PDD in its selected ancestry.

The experimental source requires [ComfyUI-MiniMaxH3_Ref-Patch](https://github.com/lihaoyun6/ComfyUI-MiniMaxH3_Ref-Patch) and `minimax_h3_ref_patch.safetensors` in `models/model_patches`. Its author explicitly describes the patch as approximating reference behavior rather than reproducing native REF2VA. The reference-patch node's schema was checked against the author's source. This implementation does not claim equivalent generation quality or proven compatibility of every accelerator/checkpoint pair. GPU generation testing is still required.

## Production defaults

In **Production > Default generation switches**, choose values and save. The production stores the configuration node ID, selections by switch node ID, and switch schema (names, kinds, source slots and labels). Segments follow production defaults unless **Override production defaults** is enabled in Generation settings. Legacy draft switch values without this explicit flag also follow the production defaults. Generating a take freezes its effective settings in the take snapshot without turning inherited settings into draft overrides. A segment can return to inheritance by disabling the override or using **Use production defaults**. Queued takes retain their frozen selections when defaults change.

Opening a production checks its saved schema against the current connected workflow. Missing switches, changed switch kinds/names or removed/renamed sources produce a warning. Additions to the source list are allowed. **Use current workflow switches** resets the editable default selections so the new workflow can be reviewed and explicitly saved. Existing takes and generation artifacts remain unchanged. Full production duplication retains production defaults. Duplicate + Invalidate clears production defaults, per-segment configuration IDs, switch selections and frozen configuration graphs, allowing the copy to use a new generation setup while retaining prompts and reference assets.

## Compatibility checks

- Exactly one Timeline Execution node must be connected.
- Switch discovery follows the Execution configuration ancestry, including available branches; disconnected canvas nodes do not become controls.
- Supported adapters: `LongCasterTimelineModelSwitch` and `LongCasterTimelineConfigurationSwitch`. Any number of MODEL switches can be discovered, including switches upstream of other MODEL switches. The final Configuration Switch accepts Configuration bundles; nested Configuration Switch bundles are rejected.
- Third-party switch/selector nodes require an explicit adapter for their selection semantics. Unknown switch classes are rejected rather than guessed.
- Current ComfyUI `/object_info` definitions validate the selected execution graph: missing node classes, disconnected required inputs, unavailable filename/enum choices and incompatible socket types block generation.
- MODEL switch profile must match the selected Configuration profile. A segment's generation profile must also match.
- Graph cycles, stale selections or source disconnections block generation. Switches and defaults are checked when the controls change and polled every 2.5 seconds; node definitions are cached for 30 seconds. Queue submission revalidates the selection.

These checks establish a valid declared graph, not tensor compatibility or output quality. Runtime model validation still applies. For an explicitly connected `MiniMaxH3RefPatchLoader`, the FL2VA backbone is validated as FL2VA and the experimental patch path is recorded in the execution receipt; it is never relabelled as a native REF2VA checkpoint.

## Freezing and provenance

MODEL selections live in the draft's `switch_selections`. Before queueing, the bridge clones the graph, applies selections and removes inactive MODEL sources. The snapshot's Configuration captures the active upstream graph, model `switch_values`, selected configuration slot and content fingerprint. Backend freeze/verification reconstruct the same selected MODEL ancestry; modifying a chosen switch, model, adapter or schedule after queueing fails verification. Native numeric validation casts remain supported.

Preview-only requests continue to omit model/configuration branches. This change does not alter prompt compilation, reference conditioning, latent continuation, overlap, drift controls or HyperFlow prompt timing.

To add another switch family, implement discovery/selection and pruning rules in `web/extension/switches.js`, add backend ancestry verification and a typed lazy node where needed, and test frozen provenance and inactive-branch pruning. The UI itself renders the returned schema without hard-coded switch counts.


## Reference image sizing

Production > Reference images saves the default **Match** or **Max** policy. Generation settings > Reference image sizing uses that production default unless an explicit segment override is selected. This is independent of the switch-override checkbox. The policy applies to every active image reference in the generation, including references with latent-strength conditioning.

The effective `ref_image_size` is validated and frozen in each take snapshot and execution receipt, and passed directly to native `MiniMaxH3ReferenceToVideo`. Match scales down to the generation pixel area while preserving aspect ratio. Max scales down to a 2048px short edge. Neither upscales; native H3 rounds the result to its canvas multiple. Existing projects and older takes default to Match. Production copies retain the sizing default. Later production changes do not alter saved takes.

Native implementation: https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py


## Generate with the current or a random seed

The main Generate button uses the Seed field as entered. The adjacent **Random seed** action chooses a fresh nonnegative, JavaScript-safe 53-bit seed and immediately generates the same target segment with otherwise identical settings. It updates the visible Seed field and saves the exact value in the job/take snapshot, so the next normal generation can reuse it. Both actions share configuration, prompt, duration and continuation validation, and are unavailable while generation is active.


## SMD REF2VA - added 2026-10-20

The dual-switch workflow adds **Acceleration D: SMD REF2VA - 8 steps** while preserving the original paths and default selection. Reload the updated workflow, then choose this configuration in Timeline. Prefer Model source A (native REF2VA); source B remains experimental with SMD.

Place the native ComfyUI-converted **SMD-MiniMax-H3-Ref2VA-8step.safetensors** in `models/loras` or your configured LoRA directory. It is an adapter, not a complete diffusion model. This branch applies it after SigmaShift 12/3 at strength 1.0, then Comfy Kitchen, Euler and the author's ManualSigmas. Timeline already uses BasicGuider (no CFG). The selected SMD branch contains neither PDD nor HyperFlow. Do not add Lightning/Turbo adapters or apply SMD again through project/scene LoRAs.

The eight raw interval widths are `[1,1,1,1,1,1,1,0.5]`, divided by 7.5 before video shift 12. The exact SIGMAS are:

```
1, 0.9873417721518988, 0.9705882352941178, 0.9473684210526315,
0.9130434782608696, 0.8571428571428573, 0.7500000000000002,
0.4615384615384622, 0
```

Native H3 handles audio shift 3. A generic eight-step simple/PDD schedule is not equivalent. The file must be the ComfyUI conversion, not a renamed Diffusers adapter.

Recipe revision: `fc5f640d0db854cccdcad3b1cdb375458bfaaef4` in zjwfufu/SMD-MiniMax-H3-Ref2VA-8step-ComfyUI. Published adapter SHA256: `89cc678b60b2e85f10cdf69739900d948475fa52512b165b635b8b65aa364a8b`.

Verified JSON/link/socket consistency, unchanged old configurations/default, selected ancestry and frozen switch selections. No model download or GPU generation was performed. SMD continuation/audio quality remains untested. No additional custom nodes are introduced.

Source: https://huggingface.co/zjwfufu/SMD-MiniMax-H3-Ref2VA-8step-ComfyUI
