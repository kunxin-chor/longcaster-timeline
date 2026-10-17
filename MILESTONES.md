# LongCaster — Delivery Milestones

**Date:** 2026-10-17  
**Roadmap status:** Milestones **1–4 locked**; Milestone **5 provisional**.  
**Follow-up plans:** [TODO.md](TODO.md)  
**Architecture reference:** [ARCHITECTURE.md](ARCHITECTURE.md)  
**UI baseline:** [UI_UX_SPEC.md](UI_UX_SPEC.md); implementation judgment and later user feedback may override UI details.

## Guiding scope

LongCaster is a **director's generation timeline**, not a video editing timeline. **Project → Scene → Segment → Shot** structures creative generation; each segment corresponds to an H3 generation. Each saved take freezes its actual references, upstream node settings and MH3 continuity inputs. LongCaster manages creative references in the UI and runs on customizable external ComfyUI workflows with `MODEL`, `SAMPLER`, `SIGMAS` and related interfaces.

## M1 — Core Generation Timeline (LOCKED)

### Deliverables

1. **Project system:** create/open/save projects, project manager, settings, persistent project/scene/segment hierarchy.
2. **Scene and segment creation:** basic scene creation/management and segment creation; scenes start from user-uploaded image or text, configurable in scene settings. Advanced cursor-aware New Scene placement and bridging remain M4.
3. **Scoped references:** project, scene and segment images, videos, audio, LoRAs and associated inheritance/add/override/exclusion rules. Manage them in LongCaster UI, not routine ComfyUI workflow rewiring.
4. **Reference latent slider:** for supported image-reference conditioning, **100% normal native image reference** and **below 100% a named transformation of its encoded reference latent**; retain text-encoder image input and reference numbering. Capture the exact method/settings in each generated take and validate supported paths and visual behavior.
5. **Prompt editor and new H3 Prompt Compiler:** editable H3 prompt fields; project base, scene Inherit/Edit/Disable (**Edit = modify copied inherited field**), segment append text; named reference tokens in every applicable field, autocomplete, final compiled prompt/mapping preview and historical per-segment drafts. The compiler produces the matching conditioning manifest; users never manage numeric H3 labels.
6. **Extend Scene / new continuation engine:** original saved H3 AV latent continuation with hard native denoise masks, explicit source take/resource/hash and 39/90/141-frame context (default 39), or separately selected **Extend from Image**. Separate resolver/planner/preparation/sampling/handover/diagnostics and preserve original takes. No automatic last-frame image injection, identity checkpoints or HyperFlow timing compensation.
7. **Continuation quality / drift:** hard masked extension is the default control. Implement AV phase bookkeeping, seam diagnostics and independently testable experimental decode-edge correction (initially off); inherited/scoped policies and exact masks/ownership are frozen per take. No automatic fractional departure ramp, Level Lock, crossfade or color repair; additional techniques require evidence.
8. **Upstream freezing:** preserve entire effective upstream ComfyUI submitted workflow/settings, model/sampler/sigma configuration, patches, references, LoRAs, versions and output/latent provenance for each take.
9. **Unified generation workspace:** three columns, frozen finalized-source inspector, central side-by-side source/new monitors with permanently present corresponding prompt editors, scene header/settings and timeline. The right inspector stacks References & Misc, Takes (Finalize), and Generation Settings (Generate) vertically. Compact vertical take rows, conditional fields, named retention editing, keyboard/navigation, resizable persistent layout and honest milestone gating follow UI_UX_SPEC.md, with permitted implementation/user-feedback adjustments.
10. **Keyboard controls:** `Space` play/pause; `Alt + +` / `Alt + -` zoom; `Left`/`Right` single-frame cursor navigation, respecting text-input focus.
11. **LongCaster ComfyUI node contract:** accept externally supplied `MODEL`, `SAMPLER`, `SIGMAS`, and relevant VAE/conditioning inputs; expose compatible outputs/pass-through or resolved types; inject inherited LoRAs and references through LongCaster-controlled custom node(s). External HyperFlow, PDD-Acc, NEAT Turbo and Comfy Kitchen are integration compatibility targets, **not features hosted inside LongCaster**.
12. **Future-ready storage:** define Take and selected-output types immediately (M1 may expose only one take); define derived-media/artifact relationships for M5 upscaling without implementing upscaling yet. Reserve splice-map variant in schema, but do not build splice UI.
13. **Persistence and recovery:** save/reopen without losing prompt drafts, references, generation snapshots, source linkage or layout state; baseline error/status handling.
14. **Named reference definitions and renaming:** editable reference/token names at definition time, separate immutable reference IDs and asset bindings; renamable asset display names, scoped uniqueness/override rules, structured-reference updates and reviewed freeform token replacement. Frozen takes retain original names/mappings.
15. **Retention Analysis Editor:** ID-backed reference/use-case/marker/description rows, named-token editable output, profile-valid markers and compilation through the same new H3 Prompt Compiler used for manual prompt text.

### M1 acceptance demonstration

- Create a project and scene from image; alternatively start a scene from text.
- Add project references and LoRAs, override them at scene and segment scope; demonstrate direct-image and validated latent-reference conditioning.
- Define named references/assets, author named tokens throughout project/scene/segment prompt fields, save/switch drafts and inspect the compiled H3 prompt plus actual conditioning manifest. Use autocomplete and the Retention Analysis Editor; rename a reference and asset without changing a saved take.
- Generate one segment and extend its original saved H3 AV latents using hard masks; demonstrate supported 39/90/141-frame contexts, explicit image extension, AV synchronization and independently switchable decode-edge correction with its default off. Record seam evidence and effective policies.
- Save, close, reopen and inspect immutable take provenance; restore/replay effective configuration as dependencies permit.
- Connect an externally configured ComfyUI model/sampler/sigma path; verify outputs and upstream snapshot fidelity.
- Navigate/playback and zoom the generation timeline; panels collapse and persist.

**Explicitly deferred:** multiple visible takes and finalized-segment splicing (M2); split+bridge/prepend (M3); advanced cursor-aware New Scene placement and Bridge Scene (M4); upscaling execution (M5). Basic scene creation/management is included in M1 per the UI specification; later operations are not presented as functional before their milestone.

## M2 — Multiple Takes & Splicing (LOCKED)

### Deliverables

1. Generate and retain **multiple independent takes per segment**, with full settings/reference/upstream snapshots for each.
2. Review, switch, shortlist and compare takes without destructive replacement.
3. Show Selected Take 1 / Selected Take 2 temporary splice rows only for the selected finalized segment with an active inspected/edited splice, directly beneath and restricted to its horizontal span. Splice controls are left-side only; the unfinished generation target has no splice editor.
4. Select source ranges and finalize a non-destructive composite output for that segment, preserving all original takes.
5. Persist a **SpliceMap** with ordered source take IDs and precise frame ranges.
6. Preserve **independent source MH3 latents**; expose first/last boundary source resolution for prepend/extend and reject incompatible latent contexts.
7. Preserve splice provenance and selected active output through save/reload.

### Acceptance demonstration

Create at least two takes of one segment, splice selected portions, save/reopen, identify the original take providing each boundary and confirm that none of the source MH3 latents has been merged or overwritten.

## M3 — Split + Bridge and Prepend (LOCKED)

### Deliverables

1. Split segment at selected timeline cursor location and create a generated bridge across the split.
2. Prepend video generation before an existing segment/scene sequence.
3. For normal or spliced active outputs, resolve the **actual boundary source take** and validate available latent/frame context.
4. Keep all operations non-destructive; retain input take snapshots and lineage.
5. Expose **Prepend, Split, Extend** where cursor is inside a scene, with contextual toolbar/right-click actions.

### Acceptance demonstration

Use both operations on an ordinary segment and on a segment with a spliced active output; verify correct source provenance and no loss of original generation assets.

## M4 — New Scene and Bridge Scene (LOCKED)

### Deliverables

1. **New Scene** when the cursor is after the final scene.
2. **Bridge Scene** when the cursor is between two existing scenes.
3. Source continuity from appropriate outgoing/incoming selected take boundaries; preserve independent scene settings, references and prompts.
4. Scene boundary targeting and validation; contextual toolbar and right-click menus.
5. Playback of selected generation outputs across scene boundaries, with source/continuity lineage intact.

### Acceptance demonstration

Create a multi-scene project, insert a bridge scene between two scenes, and verify inheritance, independent scenes, saved take provenance, and coherent preview across scene boundaries.

## M5 — Upscaling and Production Tools (PROVISIONAL)

**Upscaling is a required M5 direction; exact secondary features remain open.** Candidate M5 scope:

- Upscale original takes, composite takes, scenes and/or project outputs through external ComfyUI upscaling workflows.
- Store non-destructive derived video artifacts with source references, output properties and full processing snapshots.
- Preview/compare original and upscaled variants, choose outputs and export.
- Batch queue, retry/recovery, missing-dependency diagnostics and production review tools as capacity permits.

### Architectural commitment in M1

Original generated media and MH3 latents are immutable; each take can own derived outputs with lineage and processing metadata. Do not make video resolution or artifacts assume one fixed file per take. Continuation source selection must not silently switch from original to upscaled footage.

## Dependency and delivery notes

| Foundation | Needed by |
|---|---|
| Versioned assets + complete generation manifests | M1, M2 take history, M3/M4 reliable source lineage, M5 processing provenance |
| Single-take `active_output` with future splice variant | M2 and M3 |
| Explicit continuity source take/boundary | M1 extend, M2 splice, M3 prepend/bridge, M4 scene bridge |
| Modular external ComfyUI execution adapter | Every milestone, including M5 upscaling |
| Derived media schema (execution deferred) | M5 |

**Milestone gates:** a milestone is complete only after repeatable end-to-end demonstrations, save/reload tests and correct provenance/latent preservation. Keep external workflow compatibility verified against actual installed custom nodes rather than assuming arbitrary combinations work.

## Technical delivery gates learned from the existing node

These gates flesh out the locked deliverables; they do not move M2–M5 features into M1. The implementation contracts and source evidence are in [ARCHITECTURE.md, sections 11–17](ARCHITECTURE.md#11-implementation-baseline-and-terminology). A gate needs recorded evidence, not merely a checklist marked complete.

### Cross-milestone constraints

- No identity checkpoints, automatically injected last-frame images, hidden previous-frame reference slots, or authoritative-image prompt injection.
- Explicit image starts and user-confirmed Extend from Image remain supported. Continue Latent must not silently become an image restart.
- No HyperFlow-specific time skip, prompt timestamp compensation, automatic opening hold or compensation switch until separate testing and specification review establish the behavior.
- Keep all take artifacts and snapshots immutable. No runtime operation infers a source from whichever segment happens to be selected in the browser at completion.
- Scope inheritance resolves before queueing and freezes into the job. Display numbers are scene-local; dependencies use IDs and hashes.

### M1 implementation sequence and gates

Implement the following slices in order, while retaining the milestone's complete deliverables:

1. **Store and resolver:** versioned project/scene/segment/take/artifact/job schemas, UUIDs, revision-checked commands, immutable assets, exact source-boundary descriptor and atomic journalled publication. Define `active_output` now with a reserved splice variant; one visible take is sufficient for M1.
2. **New H3 Prompt Compiler:** field inheritance/overrides/appends, named reference definitions, independent semantic/source allocation, role/mapping validation, autocomplete and Retention Analysis Editor integration, compiled prompt/conditioning inspection, rename safety, LoRA receipt and no removed implicit mechanisms.
3. **External execution adapter:** supported H3/MH3 dependency probes, external MODEL/SAMPLER/SIGMAS/VAEs and required text encoder/conditioning inputs, job-bound submit/complete receipts, source-hash validation and reproducible snapshots.
4. **New hard-masked continuation engine:** complete the source audit/design gate, then implement resolver, immutable planner, original AV latent preparation, external sampling, authoritative handover and diagnostics. Validate 39/90/141-frame contexts and actual consumed-source/AV identity before additional treatments; no dependency on legacy controller nodes.
5. **Explicit image path and supported adherence slider:** user-confirmed frame/image source, named latent transformation, aligned text-encoder/reference-latent inputs, independent source/preview storage.
6. **Boundary/AV quality and experiments:** implement deterministic preview/export ownership and audio-phase bookkeeping; add experimental decode-edge correction as an independent off-by-default policy. Run controlled comparisons and a repeated extension chain. Additional drift methods must not replace the hard-mask baseline automatically.
7. **UI and recovery completion:** generation timeline, source/new monitors, resolved prompt inspector, layout/keyboard/context-menu behavior and project reopen/recovery. UI work may proceed independently, but does not substitute for the generation gates.

| Gate | Required demonstration / evidence |
|---|---|
| Exact source binding | Compare requested, resolved and consumed take/artifact IDs and SHA-256. Reloading/browsing another segment during a job does not retarget it. Wrong/missing/corrupt sources fail before sampling. |
| Basic continuation | Actual H3 generation of two segments with no identity checkpoint, no auto final-frame injection, no timing compensation and no drift treatment. Review the source ending and delivered beginning for unintended pose/composition jumps; record runtime/settings, frames and output. |
| Frame domains | Record sampled `N`, requested/resolved `C`, logical new frames and source/child ownership; overlap is delivered once. Test 39/90/141-frame context, duration tradeoffs, full-source endings and experimental ownership redistribution without changing total timeline duration. |
| Endpoint compatibility | Compatible cropped-source endpoint accepted; off-grid/too-short endpoint rejected or offered a reviewed explicit alternative. No silent snapping of visible splice ranges. |
| Explicit image start | The source image/frame is selected/confirmed and frozen. Latent mode contains no automatically extracted image or guide; image mode is visibly labelled and has truthful motion-continuity limitations. |
| Scoped references | Project/scene/segment named additions, explicit override, exclusion and disabled definitions produce the same asset/label mapping and payload order in prompt encoder and latent conditioning. Save/reload, renaming and multiple-scene isolation pass. |
| Prompt fidelity | Preserve authored shots, dialogue, timestamps and character-sheet roles after inheritance/append/alias resolution. Inspector shows exact final string and compiler trace. No hardcoded subject or deferred HyperFlow offset appears. |
| LoRA isolation | Ordered effective stack matches execution receipt. Disabled/zero-strength handling, stale receipt rejection, repeat jobs and upstream accelerator order validated. A trigger does not claim an automatic subject binding. |
| Slider semantics | 100% matches normal supported native reference path. Below 100% changes only the intended latent block with a recorded method/version. Text-encoder image input persists; zero is not advertised as all-reference-off. Include a visual comparison, not just scaled-tensor assertions. |
| External interface | Supplied SAMPLER and SIGMAS actually reach execution; no sampler-name substitution or schedule rebuild. Capture settings/versions of each tested accelerator configuration separately; do not assume stacking. |
| Preview recovery | Persist latent successfully, force preview/registration failure, reopen and rebuild preview without resampling. Null/missing preview status never crashes unrelated inspection. Source and delivered previews remain distinguishable. |
| Job recovery | Cancel/fail/restart at sampling, output staging and publication. Previous successful takes survive; late results cannot attach to another segment; journal replay is idempotent. |
| Replay fidelity | Snapshot includes exact final prompt, resolved inputs, upstream submitted execution data, actual seed/sigma values and dependency versions. Missing/truncated/redacted information is visible. Claim configuration reproduction only to the demonstrated degree. |

Core video correctness must be shown with real sampling/decode/preview, alongside storage/schema/unit tests. Store a small diagnostic project and test notes for each gate. Record unsuccessful experiments too; do not change several prompt/continuation/patch variables between comparisons and then attribute an improvement to one of them.

### M2 additional gates

- Generate independent A/B takes, explicitly select A after generating B, and prove the active output and a subsequent continuation consume A's archive/latent. Merely displaying A in the monitor must not change selection.
- Verify immutable take snapshots while working prompts, scene settings and selected outputs change. Restoring settings creates working state without editing the saved take.
- Split/splice portions using source-take-local half-open ranges; preserve linked audio and source hashes. Composite duration is the sum of delivered portions, not the length of any single latent.
- Resolve first/last splice boundaries to the actual source take/range. Test a last portion ending before the original take ending and one containing too little latent context. Surface incompatibility before queueing.
- Rebuild composite preview from originals, save/reopen, and verify source/delivery/composite coordinate mappings and active-output selection. Preserve all referenced source assets during deletion/retention commands.

### M3 additional gates

- Implement and capability-test explicit departure/incoming pin descriptors; a prefix-only Extend helper is not a Prepend or Bridge implementation.
- Record both source take/artifact hashes for Bridge, independent latent windows, target placement, leading/trailing context and delivered range. Reject overlapping pins, unsupported temporal phase, insufficient context and incompatible geometry.
- Prepend samples new content before future context; it does not reverse playback or simply regenerate a first frame. Decode with context and trim scaffolding once with aligned audio.
- Split itself preserves source bytes and requires no model work. A generation operation at the split separately validates its source boundary; no hidden change of split location to satisfy latent constraints.
- Demonstrate visual/audio joins on normal and spliced outputs and with explicit incoming/outgoing endpoints. Verify save/reload and provenance, not just command availability.

### M4 additional gates

- First segments of newly created scenes use their explicit text/image start or chosen bridge sources. Neighboring scene order alone never creates a generation source.
- Bridge Scene resolves two immutable boundaries while inheriting its own chosen scene configuration. No scene's asset bindings, LoRA selections or prompts are overwritten by the bridge.
- Reordering/renaming scenes changes presentation only. Frozen jobs/takes retain their original lineage, and scene-local segment numbering remains correct.
- Cross-scene playback applies preview intervals once, preserves audio timing, and handles missing media as a recoverable condition without resampling unrelated scenes.

### M5 implementation notes and gates (provisional)

- Derived processing has a separate snapshot/job and artifact chain: exact source take/splice IDs, processing MODEL/VAE/upscaler identity, target geometry, precision, temporal chunking, context policy and output timing.
- Never reuse a first-pass reference latent at a new geometry without validating/re-encoding its original frozen reference assets and preserving reference-plan identity. Separate first-pass and processing-stage provenance.
- Original joint AV latents and source artifacts remain unchanged. Upscaled video is not silently eligible as an H3 latent continuation source. Original audio reuse versus processed audio is an explicit policy with timing checks.
- Interrupt/retry a processing job without invalidating the original take. Compare/export chosen variants using their actual dimensions/FPS and lineage.

### HyperFlow timing research (deferred; not initial runtime behavior)

After untreated continuation is understood, design a separate controlled comparison of authored local timestamps against observed action/cut onset. Record accelerator version/settings, seed, source take/hash, overlap, prompt and delivered frame coordinates. Change one variable at a time and compare against an unpatched/native control where available. A cut being more consistent in Shot 2 is an observation to measure, not proof that a fixed 1-second or 1.625-second skip is correct. Do not implement a timing treatment until the evidence, user-facing semantics and acceptance criteria are reviewed.

### Completion record

Each milestone closes with a short evidence record: implementation revision, tested runtime/dependency versions, passing automated checks, actual generated artifacts and frame/source receipts, save/recovery results, known limitations and deferred capabilities. Mocked native-node tests, prompt-string assertions and storage byte-copy tests must be labelled as such; they cannot certify seam quality or external accelerator compatibility.

## M1 amendment gates: named references and selected MH3 dependency

These requirements apply to M1, including the Retention Analysis Editor; they are not postponed to multiple takes or splicing. See [ARCHITECTURE.md, section 18](ARCHITECTURE.md#18-m1-amendment-named-reference-definitions-and-h3-prompt-compiler) and [section 19](ARCHITECTURE.md#19-selected-mh3-upstream-baseline-and-pre-implementation-gate).

### Named-reference implementation slices

1. Define reference records with immutable IDs and explicit editable names/tokens, role/classification, scope, versioned asset bindings and inheritance policies at definition time. Asset library display names are independently editable; neither asset nor reference renames require renaming immutable files.
2. Implement the new H3 Prompt Compiler as one backend service: prompt inheritance, effective reference resolution, semantic/source label allocation, structured retention compilation, final prompt assembly, conditioning manifest, validation and snapshot freezing. Do not reuse the legacy assembler as the authoritative compiler or duplicate replacement logic in the frontend/nodes.
3. Add autocomplete on `<` in every applicable prompt field, using the effective scoped definition set; display name/token, thumbnail, media type, role and scope.
4. Add ID-backed structured Retention Analysis Editor rows with named-token editable text, profile-valid use cases/markers and a reviewed transition to/from manual text. Preserve manual changes.
5. Implement reference/asset rename and asset-reassignment commands with revision/collision checks, structured-reference updates, freeform replacement preview and immutable historical take mappings.
6. Bind the compiled prompt and ordered conditioning manifest to the same frozen job/snapshot and verify actual consumed asset hashes/indices before sampling.

### Acceptance matrix

| Case | Required result |
|---|---|
| Name at definition | Create references named `hero`, `house`, `red_jacket` and `walking_motion`, with explicit assets/roles. Names persist across save/reopen and retain immutable IDs. |
| Every prompt field | Write `<hero>` in subject definitions, summary, retention and shot text; applicable audio-field tokens likewise compile. The author never assigns numeric H3 indices. |
| Subject/image distinction | `<hero>` compiles to a Subject label whose source portrait still consumes a native Picture slot. Other images receive indices consistent with the actual payload order. Real H3 conditioning receives the correct assets. |
| Structured/manual parity | Equivalent Retention Analysis Editor and manually typed named-token text produce consistent semantic mappings and valid compiled retention entries. No standalone numeric-label editing is required. |
| Scope inheritance | Inherit/add/override/disable at project/scene/segment scope; resolve only the target segment's effective configuration. Explicit ID-based overrides work; unrelated duplicate names fail. |
| Case and reserved syntax | `<hero>` and `<Hero>` use the same definition; duplicate names differing only in case fail. Native H3 tags and supported dialogue/control syntax survive token parsing and receive appropriate validation. |
| Validation failures | Unknown, disabled, missing-asset, ambiguous, misclassified, incompatible-path and conflicting-mapping cases fail before VAE/model work with field/token/scope diagnostics. |
| Rename reference | Rename `hero` to `protagonist`, retain its reference ID/asset binding, update structured references and offer exact-token freeform replacements. Declined replacements remain visible as errors, never silently retarget. |
| Rename asset | Change the library asset's display name without altering its bytes/hash or unexpectedly changing reference token names. Explicit combined rename affects only reviewed fields. |
| Reassign asset / change scope | New working compilations reflect the reviewed assignment/scope while queued jobs and historical takes retain frozen names, versions, mappings and hashes. |
| Historical fidelity | Save/reopen a take after live renames/reassignments; show its original named prompt, final compiled prompt, semantic/source mappings, actual asset order, latent modes and upstream snapshot unchanged. |

### Dependency gate

Use **`einhorn13/mmh3_media@86b96deb52ed3c753789b5bf846f58e0b0c2feba`** as the selected baseline. Verify the installed revision plus adapter API v1 and H3 latent contract v2 capabilities; fail clearly for an incompatible package instead of implicitly upgrading or falling back. Exercise archive round-trip, original-source latent continuation, named-reference conditioning receipts and exact source-boundary checks on that pin. Record runtime/dependency/model hashes with the demonstration.

Add mixed input count, video/audio duration and soundtrack-pairing cases to preflight acceptance. A source signature check is not a passing GPU integration test. No package installation or legacy-node upgrade is implied by this documentation amendment, and all previously recorded exclusions remain in force.

## M1 amendment gates: modular latent continuation

This amendment adds a clean, independently testable continuation engine to M1; it does not require the original LongCaster controller/nodes as a foundation. [ARCHITECTURE.md, section 20](ARCHITECTURE.md#20-m1-amendment-modular-latent-continuation-engine) specifies research targets, component contracts, mask policy and handover semantics. The selected MH3 commit, named references and product exclusions remain unchanged.

### Delivery phases

| Phase | Required deliverable |
|---|---|
| A — Technical audit/design | Study OBVPM as the primary reference, pinned MH3 and native ComfyUI 0.38.0/runtime capability differences. Before major code implementation provide a short design: module boundaries, masking APIs, differences from OBVPM, archive/latent assumptions, handover/audio contracts, unverified assumptions, risks and licensing considerations. |
| B — New continuation engine | Implement source resolver, immutable planner, original-AV latent tail extraction, hard masked target creation, external MODEL/SAMPLER/SIGMAS integration, authoritative mapping and immutable take persistence. |
| C — Boundary/AV correctness | Implement context-aware preview/export ownership, integer/rational audio bookkeeping and deterministic experimental decode-edge correction, off by default. |
| D — Diagnostics/comparison | Compare new engine, OBVPM and legacy LongCaster under controlled compatible inputs. Fix demonstrated issues before adding strategies; report actual evidence rather than assuming legacy behavior is correct. |
| E — Future interfaces | Confirm storage/plans can represent independently owned sources and prefix/suffix/two-ended context for later splicing, prepend and bridge without executing M3 early. |

### M1 inspector requirements

- **Continuation Method:** Continue Latent or explicit Extend from Image; user selection or scoped inheritance is visible.
- **Motion Context:** 39 frames Standard (default, 1.625 s), 90 Extended (3.75 s), 141 Long (5.875 s) at 24 fps. Disable unsupported options with reasons; never silently reduce context.
- Show requested **new footage** duration separately from resolved sampled duration including context and actual newly visible frame count.
- **Advanced:** independently switchable experimental decode-edge correction, continuation diagnostics, effective source take/latent status and resolved context/frame counts.
- Reference-image latent slider remains independent of continuation masking. No internal mask tensor controls, accelerator management, identity checkpoints or automatic last-frame image injection in the ordinary interface.

### Targeted unit and native integration gates

| Gate | Required result |
|---|---|
| Source contract/integrity | Exact original take/resource/hash, sampler-output origin, geometry/timebase and source availability are checked. Original source tensors and archive bytes remain unchanged. Missing/incompatible source does not cause an image/fresh-generation fallback. |
| Context validation | Valid 39/90/141-frame contexts work when supported. Reject invalid grid, too-short source, incompatible geometry and `N <= C`; requested context is never silently truncated. |
| Tail preparation | Exact source video/audio latent indices copied into the target prefix. New regions allocated separately. Test shape/dtype/device handling without mutating source or naively concatenating unrelated full latents. |
| Hard masks | Copied video/audio context is 0; new regions are 1. Nested mask reaches the actual native sampler/model path and is not stripped before sampling. Missing/unsupported masks cause actionable preflight failure. No fractional ramp is added by default. |
| Runtime patch compatibility | Test effective native H3 per-stream mask/timestep behavior, including representative external patches. Preserve MODEL patch state and inherited LoRAs; reject patches that bypass required masking. |
| External sampling | Supplied SAMPLER and exact SIGMAS are used through normal ComfyUI lifecycle. No continuation-driven schedule rewrite, sampler substitution or built-in accelerator implementation. Completed sampler output is saved as the latent master. |
| Duration and ownership | Sampled `N=5+17k`, context `C=39+51j`, `N-C` new frames and source/delivery coordinates agree. Baseline assembly omits duplicated context exactly once. Preview/render/export use the same plan; resolved duration is visible. |
| Decode-edge experiment | Correction off/on is independently reproducible. Validate candidate offsets against the actual VAE/path; do not assume four frames universally. Corrected source/child ownership preserves total duration, source takes, AV timing and new-frame accounting. |
| Audio phase | Verify integer/rational latent-to-video-to-sample mapping, source offsets, shared boundaries and join ownership. No repeated/skipped samples or cumulative phase drift over repeated extensions; no arbitrary audio shift to hide video-edge differences. |
| References/compiler | Named references and supported latent adherence remain aligned with conditioning during masked generation. No hidden reference, checkpoint instruction or incompatible keyframe guidance is injected. |
| Snapshot/restart | Freeze exact masks/ranges/context/ownership/audio phase plus source lineage and upstream inputs. Save/reopen/restart and continue again from original saved latents without browser-session dependence. |
| Diagnostics | Separately report latent fidelity, motion, decoded pixels, brightness/color and audio seam behavior, dimensions, capability warnings and chosen edge policy. Valid tensor joins do not automatically pass perceptual review. |

Do not automatically apply Level Lock, crossfade or color repair to hard-masked, latent-identical joins. Evaluate additional repairs only against a diagnosed failure; the required default is original-context hard masking. Source decode for preview/comparison is allowed, but direct latent preparation must not require pixel decode/re-encode.

### Controlled A/B and repeated-extension evaluation

Use the same original source, prompt, compatible model/runtime settings and seed whenever possible. Record unavoidable differences between engines or presets instead of claiming an uncontrolled comparison is equivalent.

| Test | Configuration |
|---|---|
| A | New M1 hard-masked extension, 39 frames, decode-edge correction off. |
| B | OBVPM masked extension, 39 frames, with its effective settings and handover policy recorded. |
| C | New M1 hard-masked extension, 90 frames. |
| D | New M1 hard-masked extension, 141 frames. |
| E | New M1 masked extension with experimental decode-edge correction; compare to A with other settings fixed. |
| F | Repeated extension chain, 5–10 segments; record per-join and cumulative AV timing/drift. |

Also compare the original LongCaster output as a diagnostic reference with its actual masks, hidden guides, prompt transforms and timing disclosed; do not import those mechanisms into the rewrite. External acceleration configurations are tested independently through supported interfaces; they do not introduce accelerator-specific engine behavior. Research/test access must respect existing filesystem and saved-workflow boundaries.

For each run record generation time, peak VRAM, source/take hashes, exact context/mask/ownership policy, motion consistency, decoded join quality, brightness/color stability, audio continuity and character-appearance drift across the chain. Appearance drift is an output evaluation metric, not permission to restore identity checkpoints. No faster/better-quality claim without measured evidence.

### Amendment completion criteria and report

M1 continuation is complete when original saved H3 AV latents can be extended through external ComfyUI sampling with verified hard context preservation; only intended delivered frames enter playback; AV synchronization holds; supported contexts are selectable; save/restart and further continuation work; takes freeze sufficient mask/source/phase/handover/runtime provenance and remain immutable; decode-edge correction is independently testable and stays off until validated; and interfaces represent future suffix/dual-source contexts without dependence on old LongCaster control flow.

The completion report lists files created/modified, implemented strategies, targeted/unit/native/A-B results, evidence of whether decode-edge correction improves joins, remaining limitations and M3/M4 readiness. Experimental correction is an M1 deliverable, but enabling it by default requires evidence. Prepend, guided arrival, dual-ended bridge execution and arrival soft-mask controls remain M3; HyperFlow timing compensation remains separately deferred.


## UI baseline and feedback gates

[UI_UX_SPEC.md](UI_UX_SPEC.md) preserves the supplied UI requirements, with the user's explicit permission to adapt them during implementation and based on later feedback. Explain material deviations in the review/completion report; do not require approval for each routine layout decision. Preserve exact source/target identities and immutable take behavior while adjusting presentation.

M1 verification covers the default three-column layout, simultaneous side-by-side monitors and corresponding prompt regions, frozen source settings, vertically stacked right panels, separate Generate/Finalize actions, explicit Latent/Image paths, named references/retention editing, recoverable empty/loading/error states, scene settings and usable timeline. Browsing a take must not silently finalize it or retarget a queued job. Regenerate/Unlock creates right-side working state; Discard Extension never deletes the finalized source.

Verify at 1920×1080, 2560×1440 and 1366×768, including resizing and internal scroll accessibility. Check text-input keyboard guards, monitor independent/optional synchronized playback, prompt-field switching, compiled/frozen prompt inspection, source-frame confirmation, progress, finalization and save/reload/layout reset. M1 can expose its single visible take without fabricating future history/splice UI.

M2 adds vertical multiple-take management/shortlisting and finalized-only left-side splice editing. Conditional rows appear only for an active splice and track that segment's screen span under zoom/resize; original latents remain independently owned. Basic scene creation is M1; M4 adds advanced New Scene placement and cross-scene bridges. M3/M4/M5 controls activate only when their backend operations exist.

At delivery include screenshots, files changed, functional/viewport test results, material deviations and remaining milestone-gated functionality. A written UI specification or static mockup is not evidence that the live interactions are implemented.
