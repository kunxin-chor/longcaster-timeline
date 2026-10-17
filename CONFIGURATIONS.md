# Named generation configurations

Use one ComfyUI canvas to compare baseline, PDD, HyperFlow, Comfy Kitchen and other upstream setups from the Timeline app. Restart ComfyUI and refresh both its browser tab and the Timeline window after installing these nodes.

## Connect once on the canvas

1. Add **LongCaster Timeline - Configuration** at the end of each model path. Connect that path's final **MODEL**, matching **SAMPLER**, and matching **SIGMAS**. Patches, acceleration and Comfy Kitchen stay upstream, in their usual order.
2. Give each Configuration a descriptive **name**, such as `REF2VA baseline`, `PDD 8 steps`, or `HyperFlow test`. Set **profile** to the actual checkpoint family: `ref2va` or `fl2va`. Acceleration does not itself determine that family.
3. Add **LongCaster Timeline - Configuration Switch**. Connect the configurations to its **source_a** through **source_e** sockets (five paths in this first version).
4. Connect the switch's **configuration** output to **configuration** on **LongCaster Timeline - Execution**. Keep the common **CLIP**, **video_vae** and **audio_vae** connected to Execution. Its direct MODEL/SAMPLER/SIGMAS inputs can be disconnected; when a named configuration is selected, they are ignored.
5. Keep exactly one Execution node. If its new configuration socket is absent after refreshing, recreate that Execution node and reconnect its inputs.

A single Configuration can also connect directly to Execution without a switch. Existing direct-input setups still work and appear as **Direct canvas inputs**. CLIP and the VAEs are shared in this slice; per-path encoder/VAE switching is not implemented.

## Select inside Timeline

In the right inspector, open **Generation settings > Generation configuration** and choose a path by name. Generate a take, then choose another configuration and generate another take in the same unfinished tail segment. For a finalized tail, use **Replace tail segment** to compare replacements. This preserves the existing tail/source rules.

The dropdown discovers connected configurations from the open ComfyUI tab and refreshes approximately every 2.5 seconds. Names live at each Configuration's definition. Duplicate display names include their canvas node ID for disambiguation. Names may change; node IDs bind saved choices, so recreating a Configuration requires selecting its new entry. Missing saved choices never silently fall back to a different path.

Selecting a different profile for an independent first segment updates its generation mode. A continuation or replacement with an existing source must keep the source's profile and geometry; incompatible choices are disabled. REF2VA still requires enabled reference images. FL2VA still requires references to be excluded.

## What is frozen and executed

Generate freezes the chosen Configuration ID, name, profile, switch slot and selected upstream serialized inputs. The backend redacts secret-named inputs and records an SHA-256 fingerprint. These details are stored in the immutable take snapshot and execution receipt; the frozen inspector shows the configuration name.

The bridge overrides selection in the queued prompt, without changing canvas selector widgets. Unselected switch connections and their exclusively unused upstream nodes are omitted from that prompt. The native switch also uses lazy evaluation. An incomplete inactive path does not block a complete selected path. Common dependencies needed by the selected path still run. Switching configurations may load a different model; ComfyUI manages cached models and VRAM residency.

Dispatch rejects a changed/disconnected selected path rather than routing to a fallback. Execution verifies the selected branch and frozen upstream fingerprint before encoding/sampling. Family checks inspect only the selected MODEL ancestry, avoiding false mismatches from other paths. The fingerprint records graph settings, not hashes of checkpoint file contents. It does not promise bit-identical results across different runtime environments.

## Reused code and validation

The typed switch adapter reuses `SimpleSelectorSwitch` from the bundled MIT-licensed [ComfyUI-Lenient-Switch](https://github.com/id-fa/ComfyUI-Lenient-Switch), pinned at `bf859e5f442ec618b3e6e5cc39a39fa2d6207ac7`. The original module is unmodified, with its license and provenance in `timeline_core/vendor/lenient_switch/`. No separate node-pack installation or automatic dependency update is needed.

Validation covers native node lazy-input requests, keeping model/sampler/sigmas together, frozen queue metadata, mode mismatch, model ancestry, branch pruning, missing/edited paths, direct-input compatibility, per-take app selection and the existing Timeline behavior. Actual ComfyUI GPU sampling through these new nodes still needs a native test.


## Numeric validation compatibility

ComfyUI validates numeric widgets before execution and may rewrite JSON `12` as FLOAT `12.0`. Configuration verification accepts exactly equal integer/float values without requiring their raw JSON hashes to match. Booleans and strings remain distinct, and different numeric values are still rejected without an epsilon tolerance. Frozen upstream graphs and their original fingerprints remain unchanged. Switching configuration between new take attempts is supported.

## HyperFlow H3

See [HyperFlow H3 configuration path](HYPERFLOW.md) for the installed `ApplyHyperFlowH3` node, native 8-step SIGMAS wiring, full/pruned weights selection and experimental curve-refit option. No prompt timing compensation is added.

The supplied REF2VA switch example includes HyperFlow in slot C using `ApplyHyperFlowH3`, Euler, and the node's native SIGMAS. PDD remains in A; the existing stock comparison remains in B.


## Dual switches and production defaults

The new `example_workflows/longcaster_timeline_ref2va_dual_switch.json` separates Model source from Acceleration. The UI discovers one dropdown per supported switch. Production settings can save default values and warn when the open workflow no longer matches. See [Generation switches](GENERATION_SWITCHES.md) for setup, validation, provenance and experimental REF-patch limitations. Existing workflows remain unchanged.
