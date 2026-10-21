# Automatic continuation comparisons and drift treatments

Implemented 2026-10-18. The PDD H3 Refine run was executed by the user and showed no clear torso-drift benefit. Native Drift Control / Color Stable quality and AV acceptance is pending.

## Launch a comparison

1. Restart ComfyUI after installing this update, then reopen or reload the Timeline app from ComfyUI.
2. Open the baseline production and select its scene. For the initial pull-up baseline, use production `61095971-2651-4673-b374-5de917e8ed2b`.
3. Click **Drift comparison** in the app header.
4. Select the treatments to compare. The dialog initially selects **Drift Control**, **Color Stable only**, and **Drift Control + Color Stable**. H3 Refine remains an optional separate arm. Leave **Saved baseline configuration** selected for the initial controlled test. To test another standard or accelerated path, choose its generation switches in the normal panel and select **Current generation switches** in the comparison dialog.
5. Optionally check **Reuse existing control** to generate only the selected treatment chains. It is unchecked by default. Reuse requires matching generation settings and enough finalized control continuations; checking it initially selects up to four available continuations (three for the initial baseline).
6. Click **Check baseline and configuration**, review the common starting take and configuration, then **Run selected treatments**. H3-Refine-only selections retain their existing button labels.

Without control reuse, the runner creates separate control and selected treatment productions. With reuse enabled it creates only the selected treatment productions and records the existing control project, scene, selected take IDs and latent hashes; it neither copies nor queues new control generations. Selected control artifacts/previews are rechecked before dispatch and at completion. A changed configuration or a requested chain longer than the saved control requires explicitly turning reuse off; there is no automatic regeneration fallback. It copies only the explicitly finalized first take, its files and the references needed by the scene, not a newer unselected root take or the baseline's later generations. The baseline remains untouched. Generated, finalized take snapshots supply the continuation prompts, seeds, duration and context. Planned-only segment prompts and edited working drafts are not used by this test runner. When generating a fresh control, if more continuations are requested than were recorded, the last saved continuation template repeats; the dialog states this explicitly. The initial baseline has three continuation templates; the default four-continuation test repeats the last one once.

Default: four continuations per treatment, 20 uninterrupted idle seconds before every generation and 60 uninterrupted idle seconds between treatments. Idle time starts only when ComfyUI's running and pending queues are empty and resets if other work appears. This does not unload models or actively cool the GPU. ComfyUI's queue is shared: another client can still submit work after an idle check.

Keep the Timeline and its originating ComfyUI tab open. This first slice is browser-orchestrated, not a background server daemon. Reloading/closing stops further orchestration; a generation already submitted may finish as an unaccepted draft. There is no automatic resume. **Stop comparison** cancels the runner's active job or removes its queued prompt, preserves completed takes and prevents dispatching the next segment or treatment. No unrelated prompt is interrupted.

## Acceptance and configuration integrity

The runner accepts a take only after the job and preview complete, the frozen source matches its expected parent, and protected AV context checks pass. Refinement also requires head/audio preservation evidence. Normal finalization additionally verifies the saved latent hash and matching preview. Failed previews, mask violations, cancellation, lost bridge connections and changed generation configurations stop the chain.

Automatic acceptance checks technical integrity; it does not certify identity, anatomy, lighting, sound quality or a visually seamless join. Review both generated productions afterward. Compare matched body poses, skin tone, torso geometry, texture, gym/background stability and seams through segment five.

Both treatment arms use the same checked generation configuration. The comparison can use standard REF2VA, PDD or HyperFlow; it is not hardcoded to an eight-step path. Selecting another path records that difference from the historical baseline explicitly, keeps the identical saved first take, and generates a fresh untreated control on the new path. This isolates refinement within that continuation configuration; it is not an entirely regenerated chain on the new model. FL2VA/REF2VA profile changes across the common starting take are rejected. All selected switch values and upstream definitions are checked before each dispatch and again by execution. Unsupported/missing inputs remain errors, never silent substitutions.

## H3 Refine adapter

The normal generation panel has an **H3 Refine (experimental)** segment checkbox, off by default. Independent starts skip refinement. Extending a segment carries the chosen setting into the next prepared draft; it can be changed for that draft. The comparison sets it explicitly per arm.

The adapter reuses unmodified MIT-licensed `schedule.py` and `refine_blend.py` from [dntpi/ComfyUI-H3-Refine](https://github.com/dntpi/ComfyUI-H3-Refine), revision `903e66219569eef22d46f81ec478f7556b0b9ab3`. See `timeline_core/vendor/h3_refine/NOTICE.md` and `LICENSE`. Installing the upstream extension separately is unnecessary.

Timeline-specific choices:

- Same selected, patched MODEL and authored text/reference conditioning as the main pass. No last-frame injection, new subject links or prompt timestamp changes.
- Plain Euler refinement using the last two intervals of the actual main SIGMAS tensor (`hop_tail`), not an independently constructed schedule or upstream's `res_multistep` default. At least one base interval remains excluded; an insufficient schedule fails. Other selected configurations supply their own actual schedule.
- Deterministic upstream-style independent refine seed: `(seed ^ 0x5EF1) & 0x7fffffff`.
- Hard-zero video mask throughout the actual continuation prefix; entire audio stream masked to zero. Existing masks are intersected. Unlike upstream's optional fractional head ramp, Timeline protects the entire source head.
- Video-only blend from raw throughout the prefix to fully refined 22 video frames afterward, using H3's real `(1,4,4,4,4)` token mapping. A 39-frame context resolves to `0:0, 39:0, 61:1`. Contexts 90 and 141 map to 27 and 42 protected video tokens.
- Verify donor head/audio preservation within the existing FP32 tolerance before blending. Restore the output head and full audio exactly from the original sampled tensors. Nonfinite streams, shape changes and meaningful mask violations fail instead of falling back.

The PDD source requires plain Euler on trained block boundaries. The initial baseline's recorded eight-step schedule ends in `[0.800000011920929, 0.6315789222717285, 0]`; those starts select PDD blocks 6 and 7 under the upstream strict boundary function. This verifies schedule arithmetic, not generated image quality or native compatibility of every possible model patch. Standard/HyperFlow support likewise needs native A/B evidence; correctness tests are not that evidence.

## Artifacts and timings

For a successful refined take:

- `takes/<take>/original.mmh3`: original main-pass sampled latent, with an explicit before-refine receipt.
- `takes/<take>/refined.mmh3`: derived, blended latent; this is the take's canonical `latent_path`, preview source, hash and next continuation source.
- Existing untrimmed media and trimmed previews decode the canonical take latent. Media filenames such as `original.mp4` mean the untrimmed canonical decode; they do not mean a separate decode of the before-refine archive.
- Receipt includes upstream helper revision, main sigma values, refine sigma tail, sampler, blend, seed, head/audio checks and both archive hashes. `sampling_seconds` keeps its existing main-pass meaning; `refinement_seconds` and `total_sampling_seconds` record the additional cost. Idle rest is excluded.
- `project.json` carries `experiment`: shared comparison ID, treatment, baseline revision/selected seed hash, exact prompt templates, configuration, accepted take IDs and latest runner status. This is provenance, not a resume instruction. Browser disappearance can leave the last runner status stale.

Successful original archives remain available for diagnostics. A failed refinement is a failed job and cannot be silently treated as a successful untreated result; previous accepted segments remain available.

## Verification delivered

- Backend suite: 102 tests, 99 passed and 3 existing optional checks skipped.
- New tensor tests: source immutability under an in-place sampler, protected masks, exact output audio/head, donor violations, frame mapping and actual schedule tails across 4/8/20/30-step inputs.
- New experiment tests: selected root versus newer unused take, verified isolated copies, repeated templates, corrupt/mismatched baselines and standard/accelerated configuration selection.
- Seven browser comparison tests: multi-segment parent chaining, idle/rest timing, cancellation, upstream edits, selecting current standard REF2VA switches, and optional existing-control reuse without control dispatch.
- Four normal-generation/configuration/protection browser checks passed in this update; TypeScript and production build passed.
- Native Drift Control/Color Stable runs and quality/AV comparisons have not yet been performed. The earlier H3 Refine PDD run completed, but sampled frames still showed torso/shading drift.

## Next treatments

Keep Anti-Burn excluded from this PDD comparison. Drift Control, Color Stable and their combination are now implemented. Future arms: noEmbryo statistics-only, noEmbryo detail refinement, character-masked refinement, Pull-Forward and its masked-refinement combination. Seam Restore belongs in a separate standard H3 round given the author's warning about turbo/low-step runs. Last-frame restart with and without motion is a separate continuation-strategy experiment.


## Drift Control and Color Stable implementation / upstream audit

Upstream checked 2026-10-18: [ethanfel/ComfyUI-MiniMaxH3-Context-Loop](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop), pinned to `43afeffcc570beb5f7382593e79e4b211c7e02f6` (2026-10-14). Drift Control's latest file commit is `04af3a6d4a15e5830dc21392b5287b84b472bd2d` (2026-08-21, clean-reference preservation across sigma splits); color carry's latest file commit is `5459f26b1fd3342fc5603752066c03a49987f4f5` (2026-08-22). Later repository changes did not replace these core recipes. Upstream describes the 20-step path as the initial validated baseline; schedule compatibility does not establish quality on PDD.

The current modules and two recipe constants are bundled under `timeline_core/vendor/context_loop`, with upstream GPL-3.0 license and NOTICE. They require no separate Context Loop install. Adapter changes: detach options when a custom MODEL clone shares its model_options dictionary; an optional decoded_current argument in color carry avoids decoding the same prefix twice. Colour mathematics is unchanged. Versioned source modules are not updated automatically.

Normal generation has **Continuation protection**: Off (default), Drift Control, Color Stable only, and Drift Control + Color Stable. It applies only to continuations, currently with exactly 39 frames / 12 video tokens. Independent starts record a skip. Prepared extensions carry the chosen setting. H3 Refine and these protections are mutually exclusive within a take until a separately tested combined sampling lifecycle is implemented.

- **Drift Control:** clone the selected external model, keep its patches and original SIGMAS, install the upstream paired sampler/H3 row-mask hooks, and use `next_sigma/current_sigma` on the eight oldest carried video tokens. Four tokens taper .75/.50/.25/0 toward the seam. Audio mask and new video mask remain unchanged. The final schedule interval resolves to zero prefix noise. Retained clean-reference hooks also handle upstream sigma-split handoffs; Timeline's main pass remains one sampler call. The receipt records actual hook calls and sigma/ratio trace; zero calls fails rather than publishing an untreated take.
- **Color Stable only:** apply the upstream paired-encode delta to the disposable video prefix, retain ordinary hard sampling masks, and do not install Drift Control. The first finalized take's delivered tail is the fixed anchor. The first continuation is neutral because source and anchor coincide. Later continuations measure robust centre-weighted luma/saturation, apply bounded strength .5 (maximum 6/255 brightness and 6% saturation adjustment), low-pass the latent delta and smoothstep it from zero to full strength across the prefix. Neutral corrections skip encode work. Stats caching stores CPU scalars and a weak VAE identity, not model/tensor references.
- **Combined:** color preparation first, then dynamic Drift Control during the original sampling pass. No extra diffusion pass or alternate schedule is constructed.

Color carry intentionally changes the disposable video prefix. The archived source and audio are never edited; preservation checks compare sampling output against the **prepared treated prefix** and state that reference explicitly. Snapshot mask_profile records `drift_control_av_v1` or `hard_av_color_prefix_v1`, not a misleading untouched-source claim. The source archive hash is rechecked as usual. Color anchor ID/path/hash, recipes, measured colour stats, actual correction/neutral status, upstream revision, preparation time and runtime mask calls enter the take receipt.

The runner creates separate arms, retains 20s/60s idle rests and optional existing-control reuse, and rejects a take with missing or mismatched protection evidence before automatic acceptance. Tests cover PDD sigma ratios, untouched audio/new-video mask regions, model isolation, the upstream split-reference fix, original prefix immutability, paired encode output, neutral first continuation, anchor tampering, frozen queue policies and separate browser treatment dispatch. These are integration/arithmetic checks, not a native PDD drift-quality result.


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
