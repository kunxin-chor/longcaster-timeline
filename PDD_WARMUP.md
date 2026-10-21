# Runtime PDD warmup

Implemented 2026-10-18. Native warmup, combined drift/colour and refinement
comparison results are recorded below and in HANDOFF_REFINE.md.

In Timeline's generation settings choose **PDD warmup: Auto** or **Off**. Off is
the default, including existing drafts. Prepared extensions carry the selection.
Restart ComfyUI after this backend update and reload the app. Auto checks the
backend capability before queueing so new UI code cannot silently request this
feature from an old backend. No workflow edits or additional workflow nodes.

Auto examines the MODEL actually received at execution. It recognizes the
supported PDD pack's `minimax_h3_pdd_acc` runtime wrapper together with its
`pdd_final_forward` object patch and verifies the complete trained 8-step sigma
schedule and plain Euler sampler. It does not identify PDD by configuration
switches, names, filenames or merely counting steps. Non-PDD models use ordinary
generation. Unsupported/incomplete PDD hooks, fused/baked PDD weights, missing
ancestry and incompatible schedules produce an error rather than a guessed base
model or silent untreated fallback.

The adapter walks ModelPatcher clone ancestry to the PDD boundary. It removes
only the exact trunk patch entries introduced there from an isolated clone,
restores the pre-PDD final-layer forward and removes the PDD runtime wrapper.
Earlier subject LoRAs and patches appended after PDD are retained. Attention and
other received options remain on the clone. Input and upstream models are not
mutated. Zero-strength/baked PDD cannot prove base recovery and is rejected.

The installed supported PDD pack's own `warmup_schedule(8, 0.8)` supplies the
schedule. Eight unaccelerated steps establish structure, then two trained PDD
steps finish. Both stages use the same conditioning and native joint AV latent.
The first sampler's nonzero-sigma output feeds the second with DisableNoise;
there is no new noise injection. Original AV context masks carry across phases.
Existing protected-context checks still run after sampling.

The receipt records runtime detection, removed trunk patch count, both schedules,
original incoming sigmas, phase timings and actual diffusion callback counts and
sigma traces. Actual counts must be eight base calls and two PDD calls. The
top-level sigma list describes the combined executed schedule. This recipe is
experimental; it is not guaranteed to prevent identity drift. Test it separately
from Anti-Burn. Warmup plus refinement is supported; see HANDOFF_REFINE.md.
Drift Control/Color Stable can also be combined
experimentally using the two-phase adapter described below.

Supported upstream:
https://github.com/Jalen-Brunson/ComfyUI-MiniMax-H3-PDD-Acc
(`nodes.py` runtime hooks and `pdd_acc_core.py` warmup_schedule). No source files
or dependencies in the upstream extension are modified or automatically updated.

Validation completed: backend suite 106 tests, 103 passed and 3 optional skips;
TypeScript and production frontend build passed. New tests exercise patch
isolation and preservation of subject LoRAs, non-PDD/off bypass, unsafe base
recovery rejection, schedule slicing, no-noise handoff, mask transfer, runtime
counts and cancellation. These do not substitute for native GPU testing.

Planned quality test (not run): reuse native production
`01ad79cd-9d64-4c78-8080-34633e003090`'s selected starting take, generate four
continuations with Auto, 20 continuous queue-idle seconds before each generation,
other treatments off. Reuse the existing pure-PDD outputs as the control. Read
only authorized productions and productions created by automated tests.


## First native smoke test and handoff correction

The first test in production `e3b05d44-151e-40f4-837a-111e65526a66`
successfully detected PDD, removed 308 trunk patch entries, and executed eight
base plus two PDD calls. The saved take failed the independent protected-context
check (video max error 19.1213, audio 3.2518). It was not finalized; no further
continuations were submitted. This is an implementation failure, not evidence
about the recipe's visual effectiveness.

The public sampler returns inverse-noise-scaled output when its schedule ends
at sigma 0.8. That output can resume generated regions but cannot serve as a
fresh clean inpainting reference for protected AV regions. Version 2 preserves
the original clean reference before sampling and restores only zero-mask values
at the stage boundary. Generated regions retain the actual nonzero-sigma resume
state. Nothing is overwritten after the final sample; the independent protected
AV check still gates finalization. A new regression emulates rescaled protected
video/audio prefixes and verifies clean reference recovery, mask retention and
unchanged generated-region handoff. Backend capability version 2 prevents use
of the older handoff through the updated UI. Native retry remains pending a
backend restart. The failed take and its receipt remain available for diagnosis.


## Combined warmup / Drift Control / Color Stable experiment

The combination is now supported experimentally. Color Stable prepares the disposable
39-frame video prefix once, anchored to the original scene take. Drift Control is
installed on both the recovered base and PDD models using the complete 10-step
sigma schedule. Its upstream split-sampler wrapper preserves the partial boundary
state while restoring the clean inpaint reference; ordinary hard-mask handoff
restoration is bypassed for this combination. Receipts must verify eight base
mask calls, two PDD mask calls and one split-reference handoff, followed by the
independent AV context check before finalization. Audio remains hard context.
Anti-Burn and H3 Refine combinations remain blocked. Quality has not yet been
established. The native pure-PDD root/control and warmup-only control are reused;
four new continuations run with at least 20 seconds of continuous queue idle
between generations. No workflow changes are needed.


### Combined treatment result (2026-10-19)

Production `7672af07-3c10-411a-8a98-2353d54c8809` completed four continuations
from the same native PDD root/control used by warmup-only. All five selected
takes passed verification; each new take recorded base=8, PDD=2, phase masks=8+2,
one split-reference correction, ready preview and preserved prepared AV context.
Color Stable was neutral for S2-S4 and corrected S5 by about -0.69/255 brightness
and -2.34% saturation. The fixed wall patch's S5 brightness shift was +0.53%,
versus +1.75% warmup-only and +1.91% pure PDD. This patch is not an identity or
skin-colour metric. Sampled pose comparisons still show appearance changes;
no clear identity/body-preservation win is established. Sampling averaged 87.41 s
versus 85.93 s warmup-only and 66.82 s pure PDD. All four idle rests exceeded
20 s. Controls were reused; no extra arm/retry was generated. Local evidence:
`.test-tmp/pdd-warmup-drift-color-test/review/REPORT.md` in the legacy workspace.
Non-PDD generation still uses its normal single pass and external sigmas with
Drift Control/Color Stable; the new combined adapter is specific to PDD warmup.

## Completed handoff/refinement comparison, 2026-10-19

All five four-continuation arms are complete: twenty accepted new takes. The
earlier twelve were retained; after explicit resume only detail and masked arms
ran. Native pure-PDD and handoff-only controls were reused. Every generation
received at least twenty seconds of continuous queue-idle rest. No failed,
cancelled or retried generation; no more generation is scheduled.

| Added to handoff | Mean extra time | S5 fixed-wall luma change |
| --- | ---: | ---: |
| Handoff-only control | 0 | +1.75% |
| H3 Refine / PDD | 16.34 s | +1.47% |
| H3 Refine / recovered base | 17.29 s | +1.94% |
| noEmbryo statistics only | 0.19 s | -0.27% |
| noEmbryo statistics + detail | 26.49 s | +0.80% |
| Character-masked / recovered base | 52.73 s | +1.75% |

The wall metric is a fixed background patch, not identity accuracy. Statistics
only remains the most promising cheap colour-stability addition in this small
test. Sampled pose comparisons show no clear face-preservation win from any
refinement arm. Detail makes modest texture changes; masked refinement also
adds CPU segmentation cost. Neither establishes an identity fix.

All twenty takes passed source/prompt/seed/reference/configuration, archive
hashes, previews and protected AV context. Each records eight base plus two PDD
handoff calls and separate refine counts (2/2/0/3/3). Base-refine runtime hooks
exclude PDD. Audio/head remain exact; raw and refined archives are retained and
the next segment uses refined.mmh3. Character masks and overlays are saved;
all four masked sampler runs preserved latent background outside support.
Nearby decoded RGB pixels may still change through the VAE receptive field.

Evidence, all production IDs and playable comparisons:
legacy workspace `.test-tmp/handoff-refine-test/review/REPORT.md`.
Backend regressions: 114 tests, 111 passed, three skipped. Earlier frontend build
passed. No workflows inspected/changed; no MMH3/upstream upgrade.

Recovered-base refinement requires an actually applied PDD warmup; non-PDD
configurations use the received model. Statistics-only performs no refinement
sampling. Person-model weights are explicitly installed and verified; missing
or corrupt weights are rejected before main generation, with no auto-download.
