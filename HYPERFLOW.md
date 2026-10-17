# HyperFlow H3 configuration path

Use the installed node pack at `E:\ComfyUI_windows_portable_38\ComfyUI\custom_nodes\ComfyUI-HyperFlow-H3`. Its native node ID is `ApplyHyperFlowH3`, displayed as **Apply HyperFlow H3 (MiniMax-H3 8-Step)**. The old `ApplyHyperFlow` node ID belongs to a different pack and must not be substituted.

## Connections

```text
REF2VA Load Diffusion Model
  -> ApplyHyperFlowH3 MODEL input
     -> MODEL output -> optional Model Attention Backend -> Configuration MODEL
     -> SIGMAS output ----------------------------------> Configuration SIGMAS
Euler KSamplerSelect -----------------------------------> Configuration SAMPLER
Configuration (profile=ref2va) ---------------------------> Configuration Switch
```

Name the configuration **HyperFlow REF2VA - 8 steps**. The switch bundles the patched model, Euler sampler and matching native sigma grid together. Keep CLIP and both VAEs on the shared Execution inputs. The normal Timeline dropdown discovers this configuration without a special runtime adapter.

Do not route this path through BasicScheduler or PDD_ACC. HyperFlow supplies its trained 9-point grid (8 integration intervals); BasicScheduler would replace that grid. Keep the default video/audio shift pair 12/3; the pack already produces video-shifted sigmas, so do not shift the SIGMAS output a second time. Apply attention backend patches after HyperFlow. Start with dense attention for a clean comparison; sparse attention is a separate experiment.

## Apply node settings

| Input | Value |
| --- | --- |
| strength | 1.0 |
| lora_mode | bypass |
| variant | auto |
| download_if_missing | false |
| verbose | false |
| experimental_curve_refit | true for a pruned-base curve-refit test; false for an explicit LoRA-only comparison |

Select the converted weights that match the base:

- Full base: `custom_node_hyperflow_8step_v1.0_comfyui.safetensors`.
- Pruned base: `custom_node_hyperflow_8step_v1.0_comfyui_pruned.safetensors`.

The installed pack registers these under ComfyUI's `models/hyperflow/`. Weights availability has not been checked outside the authorized repositories, and no automatic downloads are enabled.

On a pruned base, the normal adapter is backbone-only. The pack's experimental curve refit restores an approximation of two-time conditioning for supported checkpoint/adapter pairs. If enabled, name the path **HyperFlow REF2VA - 8 steps (curve refit)**. Its console can report a fallback to backbone-only; the flag alone does not prove that a matching fit was applied. A full base uses the actual two-time conditioning path.

## Timeline behavior

No HyperFlow prompt time offsets, automatic last-frame injection or extra delivery trim are added. The existing selected-take latent continuation and hard AV masks remain in effect. Freeze the complete upstream configuration into each new take; use **Replace tail segment** to compare samplers without changing the continuation source.

The installed node's MODEL/SIGMAS outputs match the existing configuration contract. Native GPU sampling and HyperFlow continuation quality still require testing on the user's ComfyUI instance.

Source: the installed pack's [README](../ComfyUI-HyperFlow-H3/README.md), `hyperflow_h3/nodes.py`, and `hyperflow_h3/schedule.py`.

The configuration-switch example now wires HyperFlow to slot C, using the full adapter for its default full REF2VA loader. Slots A (PDD) and B (the existing 30-step stock comparison) are unchanged. Slots D and E remain available. Select **HyperFlow REF2VA - 8 steps** in Timeline.
