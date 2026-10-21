# Anti-Burn continuation control

Anti-Burn is an optional model-only LoRA treatment for accumulating harshness during latent continuation. It is off by default and is separate from the normal scoped LoRA list. Effectiveness with standard REF2VA 20-step sampling and preservation of identity or body proportions are unverified. Combining it with latent refinement is untested; evaluate each separately before combining them.

## Use

1. Install `h3_antiburn_universal_v1.safetensors` under a configured ComfyUI `models/loras` directory (subfolders are supported). LongCaster does not download it automatically.
2. Open **Scene settings** and enable **Anti-Burn for scene continuations**. Start at strength **0.5**.
3. Under the target segment's **Generation settings**, choose **Inherit scene**, **On**, or **Off**. An optional strength override can be set independently.
4. Use **Refresh Anti-Burn availability** after installing the file. Availability also refreshes periodically.

Independent starts, including replacement of the first independent segment, skip the dedicated treatment even when enabled. New extensions inherit scene settings rather than copying a previous segment's override. Replacement of a tail retains that segment's authored override. Changes affect future generations only.

An unavailable, missing or ambiguous file produces a visible warning. If treatment is enabled for a continuation, both Generate buttons are disabled and the server rejects queueing before sampling. Turning treatment off allows generation. Independent starts remain available. Multiple copies with the expected basename must be resolved by the user. Adding the same Anti-Burn file through the normal LoRA panel while the dedicated treatment is active is rejected to avoid double application.

## Reproducibility and implementation

- Scene defaults are persisted as `scene.anti_burn = {enabled, strength}`.
- Segment overrides are stored in `working_draft.anti_burn = {mode: inherit|on|off, strength?: number}`. Strength must be finite, greater than zero and at most 2.
- Queueing resolves inheritance using the actual source after regeneration source selection. It freezes effective enablement, override mode, strength, applied/skipped reason, relative filename, SHA-256, and application placement into `snapshot.anti_burn`.
- Execution verifies the frozen file hash and applies it through the model-only LoRA loader, after the upstream configuration and ordinary LongCaster LoRAs. It does not modify CLIP or inject prompt text. The resulting record is saved in `receipt.anti_burn`; Frozen settings shows the applied strength or independent-start skip.
- Missing or changed weights never silently fall back to untreated generation. Old snapshots without this setting remain untreated and are labeled as legacy in their execution receipt.
- Prompt-only production copies retain scene defaults and segment overrides, but no generations or frozen execution hashes.

The current placement supports the standard REF2VA experiment. It does not reproduce the Anti-Burn author's before-turbo test ordering. No upstream acceleration nodes or HyperFlow curve-refit behavior are changed by this feature. A later upstream placement option needs separate validation.

## Validation

Backend tests cover inheritance, independent-start skipping, strict settings validation, missing/ambiguous files, duplicate manual entries, queue atomicity, frozen file hashes, model-loader dispatch, and prompt-only copying. Browser coverage checks scene persistence, independent generation, continuation blocking, segment opt-out, availability refresh, and strength overrides. No GPU quality acceptance is claimed.
