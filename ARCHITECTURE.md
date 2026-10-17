# LongCaster — Generation Director Architecture

**Status:** Baseline architecture, agreed for Milestones 1–4  
**Date:** 2026-10-17  
**Product identity:** AI video director's workstation for MiniMax H3, integrated with ComfyUI.

## 1. Product boundary

LongCaster's primary timeline is a **generation timeline**, not a nonlinear video editing timeline. It organizes creative direction, generation inputs, MH3 continuity, outputs and takes. A future editing timeline is a separate feature and must not dictate the generation data model.

A narrow **take-splicing** tool is allowed within the generation workflow to select portions of alternate generations of *one segment*. This is not a general track-based editing system.

### Core invariants

1. Hierarchy: **Project → Scene → Segment → Shot**. A segment represents **one H3 generation unit**, usually 5–15 seconds, and may describe multiple camera shots.
2. A **Take** is the saved result of executing a segment, with immutable generation configuration and independently owned MH3 latent assets.
3. Project, scene and segment configuration supports scoped references and LoRAs; segments inherit higher-level defaults unless overridden/excluded.
4. LongCaster's UI is the source of truth for creative references. Routine workflow edits must not be necessary to swap references.
5. H3 generation depends on an external, user-configurable ComfyUI workflow. LongCaster must not own or hardcode HyperFlow, PDD-Acc, NEAT Turbo or Comfy Kitchen.
6. Saved takes must record enough information to recreate the effective *upstream execution environment*, not just visible LongCaster settings.
7. Original outputs and MH3 latents are not overwritten by take splices or derived processing such as upscaling.
8. Major UI panels and settings groups are independently collapsible; layout is resizable and persisted.
9. No identity checkpoints or automatically injected last-frame images. Continue Latent uses an explicit take/latent boundary; image starts are explicit user-selected operations.
10. No HyperFlow-specific time skip or prompt timestamp compensation until controlled testing and a reviewed specification change justify it.
11. References receive editable names/tokens at definition time; one new H3 Prompt Compiler resolves named prompts and the matching conditioning manifest. Users do not manage numeric H3 labels.

## 2. Domain model

```text
Project
├── project_settings / prompt_fields / references / LoRAs
├── asset_library (immutable asset IDs and versions)
└── Scenes[]
    ├── scene_settings / prompt_fields / references / LoRAs
    ├── start_mode: image | text
    └── Segments[]
        ├── shot_descriptions[] (within a single H3 generation)
        ├── reference/LoRA overrides and local generation settings
        ├── prompt_drafts[] (one active draft)
        ├── continuation_spec (latent | image; source boundary)
        ├── takes[] (one visible take per segment in M1)
        │   ├── immutable generation_snapshot
        │   ├── original outputs and independent MH3 latent assets
        │   └── derived_media[] (schema in M1; upscaling in M5)
        └── active_output
            ├── single_take(take_id)
            └── splice(splice_map_id) [implemented M2]
```

### Entity responsibilities

| Entity | Responsibility |
|---|---|
| Project | Production-wide defaults, assets, scenes and metadata. |
| Scene | Ordered collection of segments, its own references/LoRAs/prompts, start-from-image or start-from-text configuration. |
| Segment | H3 generation intent, shots, prompt drafts, local inputs, continuation mode, take history and selected output. |
| Shot | Description of continuous camera action *within* a segment; not an independent generated asset or editing clip. |
| Take | Immutable record of actual execution inputs and results, including upstream node configuration and provenance. |
| Asset | Reference image/video/audio, LoRA, model, latent, or output artifact, identified by stable ID and verified content/version where feasible. |
| SpliceMap | Ordered source-take portions and frame ranges for one segment's composite output. |
| DerivedMedia | Non-destructive transformation (e.g. future upscaled version) referencing original source and processing provenance. |

## 3. Configuration resolution and inheritance

Project, scene and segment support reference images, reference videos, reference audio, LoRAs and relevant generation settings. Assets are selected in the LongCaster UI and resolved for a generation. Assets can be reused without duplicating physical files.

- **Inherit:** dynamically adopt parent values.
- **Override:** change the effective value locally.
- **Disable/exclude:** suppress an inherited value locally.
- **Add:** introduce additional local assets or LoRAs.
- **Snapshot at generation:** freeze the resolved effective configuration in the resulting take. Later parent edits do not modify earlier take snapshots.

LoRA injection is implemented by **LongCaster custom ComfyUI node(s)** based on the resolved project/scene/segment configuration, with individual model file identity, strengths and ordering preserved. The integration must avoid unintended leakage of applied LoRAs between jobs. Exact model-patching order must be validated against external accelerators.

### Reference latent slider (M1)

For **applicable image references**, expose a latent adherence slider in the UI:

- **100%:** normal supported native image-reference path, which already encodes the image.
- **Below 100%:** apply an explicitly named, validated transformation to its encoded image-reference latent; preserve the reference's text-encoder input and numbering. The slider does not imply that native 100% conditioning bypasses latent encoding.
- The source image, encoded latent or reproducible encoding parameters, slider value, injection strategy, conditioning role, and effective downstream inputs are frozen with the take.
- This is **not** merely an image-opacity or generic reference-weight slider. How to reduce latent adherence (latent scaling, low-pass weakening, noise, etc.) is a backend strategy that must be validated; these operations are not equivalent.
- Latent-as-reference support depends on the relevant H3 conditioning path/custom nodes. Do not silently treat it as universally supported for image-to-video start frames or all video/audio references.
- Preserve reference numbering and text-encoder/conditioning alignment (e.g., `<Picture 1>`); latent injection alone does not guarantee that the prompt encoder sees the source image.

**Research origin:** [MiniMax H3 — Latents as reference](https://www.reddit.com/r/StableDiffusion/comments/1whbdje/minimax_h3_latents_as_reference/) and [community custom node](https://github.com/neph1/comfyui-minimaxh3-condition-latent). Treat observed quality/strength settings as experimental, not guaranteed defaults.

## 4. Hierarchical prompt system

Prompt editor operates **per H3 prompt field**, not on a mandatory rigid taxonomy. Initial fields can include `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`; the implementation must be flexible about model/workflow-specific field sets.

- **Project:** editable base value per field.
- **Scene:** `Inherit`, `Edit` or `Disable` per field. **Edit** starts from a copy of the inherited effective field, then changes it as a self-contained local override (**not append**). Inherit remains dynamically linked; edited overrides do not silently change after upstream edits.
- **Segment:** always-available optional **append text** per field, applied after the effective scene/project text. This is where users add instructions rather than editing the inherited base.
- **Drafts:** each segment maintains multiple past prompt drafts and an active draft, independent of take history. Drafts may retain dynamic inheritance until generation.
- **Take snapshot:** save original draft ID, resolved values, and exact compiled prompt sent to H3. Restoring take settings creates/updates working state without altering the frozen take.

The new H3 Prompt Compiler preserves deterministic prompt-field ordering, resolves named reference definitions and produces both the final prompt and its matching conditioning manifest. Named tokens work in every applicable field and in editable Retention Analysis Editor output. Show a readable final compiled preview and mapping inspector. Reference/asset names are editable without changing their internal IDs or historical snapshots; see section 18.

## 5. Continuation, continuity and drift control

Two per-segment continuation strategies are required:

| Strategy | Source | Notes |
|---|---|---|
| Continue Latent | Original sampled H3 joint AV latents from an exact source take/resource/boundary | Modular hard-masked forward extension; selectable 39/90/141-frame context, default 39. No source pixel decode/re-encode or automatic image guide. |
| Extend from Image | Explicitly selected/confirmed uploaded image or frozen extracted source frame and source boundary | An explicit image restart; no hidden final-frame injection in Continue Latent. Motion continuity is not guaranteed. |

The continuation record must include explicit source scene, segment, take, and boundary/frame identifiers. Continuation relationships are **generation dependencies**, not editing-track links. Project-wide, scene and segment drift-control choices can be inherited/overridden and must be captured in takes.

Continuation is a **modular strategy family** with separate source resolution, planning, latent preparation, native sampling, handover and diagnostics. M1's required baseline is hard masked forward AV continuation; implement experimental decode-edge ownership correction separately and leave it off until validated. Additional drift/color techniques are research candidates, not automatic default treatments. Store strategy/mask/ownership versions, parameters and applied order. Section 20 supplies the M1 engine contract and research gate; the old LongCaster controller is not a required foundation.

### Spliced outputs (M2)

Each source take has **independent MH3 latents**. A splice never fabricates one unified latent sequence. A splice map stores, for each selected portion, source take ID, start/end frames, and position in composite. It also permits resolving:

- **Prepend:** the original take providing the composite's first relevant boundary.
- **Extend:** the original take providing the composite's last relevant boundary.

**Validate boundary compatibility.** A portion ending before its source take's actual endpoint is not automatically eligible for using that take's final latent context; missing context must be surfaced, not silently guessed. A spliced composite video's frames are distinct from the original source latent context.

## 6. LongCaster ↔ ComfyUI node contract

LongCaster is a **ComfyUI-integrated director/controller**, not a replacement accelerator or an all-in-one hardcoded graph. One user-facing LongCaster node may be implemented through several cooperating custom nodes if that is more reliable.

### Conceptual sockets

| Direction | Contract | Purpose |
|---|---|---|
| Input | `MODEL` | Externally loaded/patched H3 model; LongCaster may resolve/inject local LoRAs. |
| Input | `SAMPLER` | External custom sampler override where required. |
| Input | `SIGMAS` | External custom sigma schedule where required. |
| Input | `VAE` and supported conditioning inputs | External encoding/decoding/conditioning as workflow demands. |
| Output | `MODEL` | Resolved model, possibly with scoped LoRAs applied. |
| Output | `SAMPLER` | Compatible resolved/pass-through sampler, if used downstream. |
| Output | `SIGMAS` | Compatible resolved/pass-through sigmas, if used downstream. |
| Output | Conditioning / reference payloads | UI-resolved image, video, audio and latent-reference conditioning in validated ComfyUI types. |
| Output | Continuation latents / relevant generation outputs | Provide to downstream H3 sampling and persistence paths as appropriate. |

**These are conceptual integration contracts**, not a claim that one physical ComfyUI node should simultaneously perform all steps or that every port will be both input and output. Exact nodes, ComfyUI types, scheduling/execution path and socket direction must be decided against working workflows.

**External compatibility targets:** HyperFlow, PDD-Acc, NEAT Turbo and Comfy Kitchen. These live in user-supplied upstream/external graphs; LongCaster must accept their compatible model/sampler/sigma outputs and preserve their exact upstream settings. Do **not** assume arbitrary stacking is valid. Any external workflow-specific constraints must be validated and displayed.

### Upstream freezing / take replication (M1)

For each generation capture a **resolved execution snapshot**, including:

1. Final compiled prompts, effective references, assets, roles, LoRAs and strengths.
2. All effective upstream nodes affecting output: node class/type, identifiers, widget/parameter values, connections and execution order (as supported by ComfyUI's submitted workflow representation).
3. Model/VAE/LoRA filenames and hashes or immutable versions where possible; extension versions and key runtime/library versions.
4. Actual seed, steps, CFG, sampler, sigma values/schedule, accelerator/patch configurations, resolution, frame count and settings for every applicable conditioning or drift-control step.
5. Source take IDs, exact latent files or reference frames, latent-reference methodology and parameters.
6. Generated video/audio, MH3 latents, thumbnails, logs, hashes and timestamps.

Prefer storing the **full submitted workflow/API graph plus structured resolved manifest**, not relying only on a graph hash. Replication may still depend on external model files, custom-node versions and nondeterministic kernels; report unavailable dependencies and distinguish **configuration replication** from guaranteed bit-identical output.

## 7. UI architecture

The detailed baseline is [UI_UX_SPEC.md](UI_UX_SPEC.md), including the user's permission to adapt UI details during implementation and based on later feedback. Its preferred one-screen layout guides implementation; material deviations should be explained rather than treated as automatically requiring a new approval.

- Default workspace: three columns (frozen finalized-source inspector, central dual monitors with corresponding prompt editors, editable generation-target inspector) above a substantial scene/segment timeline. Suggested starting widths are 19% / 59% / 22%; they are resizable targets, not fixed dimensions.
- Major regions/settings groups are resizable/collapsible with persistent layout and Reset Layout. The default desktop workspace keeps both monitors and both prompt editors visible together. Inspector lists scroll internally; avoid page-level vertical scrolling. Compact collapsed groups retain useful summaries.
- A scene header above the center shows the scene name and Settings button plus project/scene/segment timecodes. The top-level Project control opens project management. Optional sidebar navigation must not replace the frozen-source inspector or dual-editor workspace.
- Source prompt read-only by default; unlocking creates editable working state, never modifies historical take snapshot.
- Prompt editors can expand into a dialog.
- Timeline transport located in timeline toolbar.
- Timeline is **generation-first**, with scene blocks and segment units, not a general audio/video multitrack editor.
- Take lists are vertical compact rows. The right inspector has three vertically stacked primary panels: References & Miscellaneous Settings, Takes (including Finalize), and Generation Settings (including Generate). Generate never auto-finalizes.
- **M2 splice controls are on the left for finalized segments only.** Selected Take rows appear only for an active inspected/edited splice and are restricted to that selected segment's horizontal span; no permanent empty/project-wide splice tracks.
- Context-sensitive right-click menu uses clicked position/object and execution state; right-click does not need to move playhead.

### Default keyboard controls

| Shortcut | Function |
|---|---|
| `Space` | Timeline playback/pause |
| `Alt + +` / `Alt + -` | Zoom timeline in/out, centered on cursor |
| `Left` / `Right` | Move cursor backward/forward one frame (repeat on hold) |

Avoid intercepting normal keystrokes when editing prompts or form controls.

### Cursor-aware operations

| Cursor target | Available generation commands |
|---|---|
| Inside a scene | Prepend, Split, Extend (depending on milestone and valid sources) |
| Between two scenes | Bridge Scene (M4) |
| After the final scene | New Scene (M4) |

Segment and scene context menus also provide appropriate settings, draft, take and management commands. Scene boundaries must be discrete targets, not ambiguous pixels.

## 8. Future-proof processing and upscaling (M5)

Create the **derived-media relationship in M1's schema**, even though upscaling execution is deferred to M5:

```text
Take
├── original_video (source of truth)
├── original_audio / MH3 latents
├── generation_snapshot
└── derived_media[]
    ├── source_artifact_id
    ├── processing_type (e.g. upscale)
    ├── produced_artifact_id
    └── processing_snapshot (workflow, parameters, models, versions)
```

Upscaled assets never replace original take media or latent files. Each derived output retains its parent and processing provenance. Allow different media resolutions and, where future transforms require it, differing frame rates. Continuation from the original MH3 generation remains explicit rather than implicitly switching to upscaled media.

M5 may add take/scene/project upscaling, external upscaling workflows, batch processing, visual comparisons and export, but none of these requires M1 to execute upscaling.

## 9. Non-goals and engineering guardrails

- No full nonlinear editor, multitrack audio mixing, effects timeline or general clip trimming in M1–M4.
- No mandatory built-in HyperFlow/PDD-Acc/NEAT Turbo/Comfy Kitchen UI presets or engine logic; compatibility through external ComfyUI graphs.
- No assuming every latent-reference strength corresponds linearly to perceptual similarity.
- No implicit merging of latents after splicing.
- No overwriting prior generated takes or asset versions on regeneration.
- No guarantee of pixel-identical regeneration across changed runtime environments.

## 10. Open implementation choices (not product decisions)

- Exact physical custom-node boundaries and ComfyUI data types.
- Which H3 Motion drift-control techniques are validated in M1 and their parameters.
- Latent-reference weakening method and text-encoder integration with supported reference conditioning paths.
- Splice frame boundary semantics and validity tests for MH3 continuation.
- Video container/codec and preview caching; storage retention and missing dependency UX.
- UI toolkit / timeline library selection and project file format.

These are engineering investigations, not reasons to reopen the locked product scope. Sections 11–17 provide source-informed implementation contracts and distinguish reusable evidence, rewrite decisions and unresolved validation work.

## 11. Implementation baseline and terminology

This section supplements the locked product scope with implementation contracts learned from the existing LongCaster node. It is a specification for the rewrite, not a claim that the rewrite is implemented. Source inspection used the existing node's working tree on 2026-10-17; that tree contains uncommitted and unvalidated changes. Reuse algorithms and contracts only after the milestone gates below pass.

| Existing implementation term | Rewrite term | Important distinction |
|---|---|---|
| generation folder | Scene | Scene numbering and settings are local; cross-scene dependencies must be explicit. |
| card | Segment | One generation unit; never use its display number as a source identifier. |
| draft take / accepted master | Take / selected output | Selection binds a specific immutable take, not a mutable segment filename. |
| card-local edit | Segment take splice | A composite references source portions; it does not own a newly merged latent. |
| generation parent | Continuation source boundary | References an exact take/artifact/frame, not merely a preceding segment. |

The old node's organization window and proposed general editing sequences are **not** the product architecture for this project. The generation-first scope in sections 1–10 and the milestone allocation remain authoritative.

### Removed mechanisms and deferred behavior

- **No identity checkpoint subsystem.** Do not port checkpoint records, automatic subject definitions, identity-scope instructions, checkpoint UI, or implicit subject appearance overrides. Users express character references and appearance updates through ordinary authored prompts and explicitly selected reference assets.
- **No automatically injected previous/final-frame image.** Continue Latent must not decode the source ending to add an extra reference or `MiniMaxH3AddGuide` constraint. No hidden previous-frame reference slot, image-index increment, or authoritative continuation-image instruction is permitted.
- **Extend from Image is an explicit operation.** The user selects/confirms an image or an extracted frame and its source boundary. This explicit start image is allowed; it is not a side effect of Continue Latent. An image restart must be labelled as such and must not claim to carry the original motion latent.
- **No HyperFlow-specific time skip, timestamp shift, opening hold, or compensation toggle in the initial implementation.** Do not port `hyperflow.py`'s automatic 1.625-second shift or instruction to delay new actions. Any such treatment requires subsequent controlled tests and a reviewed specification change.
- Latent overlap remains an encoding/continuation requirement. Removing prompt compensation does **not** mean dropping the context latent or trimming generated output twice.

## 12. Persistence, identity and immutable records

### Minimum schema

Use versioned manifests and UUIDs for project, scene, segment, prompt draft, take, artifact, reference binding, splice map, and job identities. Display segment numbers restart within each scene and are derived from presentation order. Reordering/renaming a scene or segment never changes an ID, an archive hash, or a historical dependency.

| Record | Required implementation fields |
|---|---|
| Project | `schema_version`, `project_id`, monotonic `revision`, ordered scene IDs, asset index, scoped configuration, layout state/version, job index. |
| Scene | `scene_id`, name/order, `start_mode`, scoped reference/LoRA bindings and prompt-field policies, ordered segment IDs. |
| Segment | `segment_id`, `scene_id`, shot descriptions, working prompt drafts, configuration overrides, continuation intent, take IDs, `active_output`. |
| Take | `take_id`, `segment_id`, attempt/job IDs, immutable generation snapshot/fingerprint, original artifact IDs/hashes, measured timing, source boundaries, nullable preview metadata, creation time. |
| Artifact | `artifact_id`, kind, project-relative path, SHA-256, byte size, media/latent properties, parent processing provenance where applicable. |
| Job | `job_id`, request/command ID, target segment, frozen resolved inputs, input revision/fingerprint, execution association, status, staged artifact IDs, diagnostics and timestamps. |
| Reference definition / binding | immutable reference ID, definition version, editable display/token names, explicit H3 role, versioned asset bindings, scope/override ancestry, enabled policy, purpose, order and supported latent transformation parameters. |

Store filenames independently of mutable display numbers. Proposed storage layout: `project.json`, immutable `assets/`, `takes/<take_id>/` snapshots and `.mmh3` archives, disposable `previews/`, `derived/`, and recoverable `transactions/`. Layout is an engineering proposal; the logical relationships are required. Paths resolve beneath the project storage root; browser clients use authenticated project/asset routes, not arbitrary filesystem paths.

Take snapshots never change when working prompts, scene references, LoRAs, selection, or layout change. Preview availability and processing state may live in separate metadata keyed to the immutable take hash. Missing previews are a supported state, not evidence that a latent is missing.

### Output selection is separate from browsing

`viewed_take_id` is UI review state. `active_output = {kind: single_take, take_id: ...}` is the saved output choice. A source job references the latter's resolved immutable artifact, frozen at queue time. Changing the monitor or playhead does not change the source. Selecting a different output must be an explicit persisted command and display which existing dependent results still reference the earlier take.

The existing implementation's `_apply_take_to_card` restores archive path/hash on selection, and `accept` copies that selected archive into a master; its regression test verifies that selecting an older take publishes the older bytes. Preserve that correctness, but remove the need to infer a source from mutable segment/master fields. If the rewrite retains a review/accept step, it publishes a take selection; it must not rewrite the take or silently select the newest attempt.

### Asset ownership and deletion

Reference media may reuse immutable files while each scope owns its binding/settings. Removing a binding does not remove an asset still used by another scene, take, job, splice, derived artifact, or retained history. Garbage collection requires a reference graph including queued/in-flight work. Existing invalidation/deletion routines that assume a global suffix of cards must not be transplanted as segment regeneration commands.

## 13. Exact continuation-source and timing contract

### Resolve once, use everywhere

Implement one pure `resolve_source_boundary(project, output, boundary_request)` service. Its result is consumed by generation preflight, source monitor, frame extraction, latent preparation, diagnostics and provenance. Never independently resolve a segment's preferred take in different consumers.

Illustrative descriptor (field names can be adapted without weakening the contract):

```json
{
  "scene_id": "uuid",
  "segment_id": "uuid",
  "take_id": "uuid",
  "artifact_id": "uuid",
  "artifact_sha256": "sha256",
  "source_kind": "original_take",
  "boundary": "out",
  "source_frame_exclusive": 124,
  "source_context_frames": 0,
  "visible_range": {"start": 0, "end": 124},
  "source_fps": {"numerator": 24, "denominator": 1}
}
```

For a splice, resolve the last portion's exact source-in/source-out for Extend and the first portion for Prepend. Source positions refer to the original take's decoded frame coordinates; composite timeline positions require a separate mapping. Freeze both mappings and IDs. An explicit derived source requires its own artifact ID/hash and compatibility validation; never silently replace an original latent with a refinement or upscale because it is the newest asset. If a selected source is unavailable, stop and identify it rather than silently falling back.

### Frame domains and overlap

- All intervals use integer, zero-based **half-open** ranges `[start, end)`. The last included frame is `end - 1`.
- Distinguish **source decoded frames**, **sampled-run frames including context**, **delivered segment frames**, and **generation-timeline frames**. Every boundary conversion names its source and destination domain.
- The standard H3 profile uses **24 fps**, valid sampled lengths `N = 17k + 5` and exact shared context lengths `C = 39 + 51j`. M1 exposes **39/90/141 frames** (1.625/3.75/5.875 seconds), default 39, subject to capability/source validation. These are versioned capabilities; no silent context shortening or prompt time skip. Do not confuse 1.625 seconds with 0.1625 seconds.
- With leading context `C`, baseline forward delivery is `[C, N)`; delivered frame `v` maps to sampled frame `C + v`. Store actual `N`, `C`, delivered frame count and duration, not only requested seconds. An experimental decode-edge policy may redistribute decoded source/child ownership inside preserved context without changing logical new footage or total timeline duration; see section 20. The old nearest-valid duration planner is a reference, not a mandatory new-engine implementation.
- Decode with the temporal context present, then trim delivered video/audio consistently **once**. Preserve the raw joint latent archive independently of the trimmed preview. Preview metadata declares whether context has already been trimmed; consumers must not infer this from filename or duration.
- For future Prepend/Bridge, represent leading and trailing context separately plus explicit delivery intervals. A single `context_frame_count` is insufficient for a suffix pin or two-ended generation.

### Shortened source endpoints

The existing `trim.py` supports exact joint AV prefix cropping only at endpoints `E = 39 + 51k` in physical decoded-source frames. It derives video-latent length `2 + 5 * ((E - 5) / 17)` and audio-latent length `E * 40 / 24`; both must fit the stored streams. For `C` inherited frames and visible endpoint `v`, the old snap rule is `E = 39 + 51 * floor((C + v - 39) / 51)`, with sufficient nonempty context checked afterwards.

This is a restriction of the inspected adapter, not permission to move a user's splice silently. Any decoded frame may be chosen for viewing or a splice; generation preflight must report whether that edge supports exact latent continuation. Offer a reviewed compatible endpoint or explicit Extend from Image. The original full-take ending remains a separate valid handover path and must not be rejected merely for failing the cropped-prefix grid. Do not invent arbitrary incoming-window/suffix support from this prefix-only algorithm.

### Scene independence

Scene order does not establish cross-scene generation ancestry. The first segment has an explicit scene start (text/image) or an explicit source boundary if the operation permits cross-scene continuation. Later Extend commands capture their chosen boundary; moving a segment does not rewrite that relationship. Validate source existence, compatible geometry/latent origin, available AV context and dependency cycles before model work starts.

## 14. Prompt compilation and reference allocation

### Deterministic compilation pipeline

1. Freeze the target segment and working prompt draft for the job.
2. Resolve project → scene field policies and apply segment append text as defined in section 4; retain each layer's authored text and resolution provenance.
3. Resolve scoped asset bindings: inherited order, explicit exclusions, versioned replacements and local additions. A local disable remains distinct from deleting an inherited binding.
4. Allocate native reference indices once for the actual enabled payloads. Use the same ordered plan to compile labels and build text-encoder/latent conditioning.
5. Resolve named reference tokens through ID-backed definitions and optional non-conflicting prompt templates. Allocate semantic Subject labels separately from source Picture/Video/Audio labels, bind subject sources and compile structured retention rows. Validate missing/disabled references, reserved model tags and mapping consistency before encoding.
6. Apply only explicitly configured LoRA activation text or other approved compiler rules, recording each transformation. No identity checkpoint rewrite, automatic previous-frame instruction, hardcoded `<Subject 1>`, or HyperFlow timing shift.
7. Save/show the exact final string passed to the text encoder and a hash, alongside the authored/resolved field values. Historical takes display their frozen prompt, not a recompilation from current scene defaults.

Initial H3 profiles support the six REF2VA fields in section 4 in their canonical order. Keep field definitions profile-driven for other modes. Parse legacy XML and labelled forms at the boundary rather than mixing headings/tags in one compiled prompt. Unknown/malformed aliases generate a useful preflight error. Do not silently rewrite dialogue, camera cuts, shot numbers or timed actions.

**Prompt clocks:** authors use segment-local timing. `[Shot 1]` remains the untimed opening shot; later shot cut timestamps remain authored segment-local values in the initial rewrite. Record any ambiguity between this convention and sampled context as a validation item. Do not imply a timing translation has been proven, or automatically delay all actions. Explicit HyperFlow timing experiments are a later gate, not initial runtime behavior.

### Reference roles and labels

Use MiniMax's [REF2VA guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md) as the H3 profile's source. Subject definitions associate reusable content with its assets. Picture retention can describe partial image reuse; mentioning a picture in retention does not by itself make it a keyframe. Roles must remain consistent across fields. Preserve authored character-sheet bindings and scene/appearance updates; do not substitute generated checkpoint definitions.

Named tokens such as `<hero>`, `<house>`, `<red_jacket>` and `<walking_motion>` are the M1 authoring interface. Assign each editable token name at reference-definition time and resolve it through the effective ID-backed scope configuration. Case-insensitive uniqueness, explicit overrides, renaming and semantic/source label allocation are specified in section 18. Users do not manage native reference numbering. Earlier numeric Project/Scene/Segment alias proposals are superseded; any later legacy-alias import is an explicit migration, not a competing M1 token resolver.

The inspected native path has individual limits of **9 images, 3 reference videos and 3 standalone audio references**; paired soundtracks need separate accounting. Validate these alongside the official mixed-input and duration constraints in section 19, using an explicit capability profile. Image order is deterministic: project → scene → segment under the new scope resolver, with no hidden identity/previous-frame slots. Preserve soundtrack pairing IDs separately from audio/video ordinals. Validate actual payload order rather than assuming equal category indices imply a pairing.

### Latent adherence implementation lesson

The existing `adjust_image_latents` and `substitute_card_latent` operate on H3 conditioning metadata `minimax_refs` after native image encoding, cloning the selected metadata and multiplying an image latent by a configured strength. The text encoder still receives the source image. Thus even **100% native image reference already involves image encoding**; the slider's below-100% path must name the additional transformation, not pretend that image references only become latent at 99%.

If scalar scaling is selected as the first experimental backend, freeze `method=latent_scale`, version, strength, reference binding/native index, resize parameters, VAE identity and resulting tensor properties. Assert that the intended image block exists before replacement. A latent value of zero does not prove that all image influence is disabled because the text encoder still saw the image. Low-pass/noise methods require separate identifiers and validation. Preserve the original image and all other conditioning blocks unchanged.

## 15. Runtime integration, LoRAs and drift methods

### Proposed service boundaries

| Service | Responsibility / lesson from existing code |
|---|---|
| Project store | Revision-checked commands, immutable take/artifact records, migrations, journals. Avoid a monolithic mutable active-segment execution state. |
| New H3 Prompt Compiler / resolver | Pure scoped-input and named-definition resolution, exact source-boundary descriptors, semantic/source mapping, retention compilation, matching conditioning manifest and job fingerprint; separate from the legacy assembler. |
| Execution adapter | Convert a frozen job into supported external ComfyUI input/output contracts; return execution receipts. |
| MH3 adapter | Archive load/verify, primary joint latent/contract extraction, compatibility preflight, continuation handover, pack/save. |
| Conditioning adapter | Native text/image/reference preparation and explicitly selected image-start semantics; verify reference-plan alignment. |
| Preview/processing service | Decode, audio alignment, encode/register, context-aware caching and non-destructive derivatives. |
| UI transport | Query immutable jobs/takes and issue revision-checked commands; never target a running job via current browser selection. |

The existing MH3 wrapper calls `load_archive(..., verify="on_access")`, obtains the primary latent descriptor/payload and H3 contract, validates continuation compatibility, optionally crops a supported prefix, then calls `build_h3_continuation_handover` with source origin, target geometry, target frames and video/audio handover counts. The rewrite should depend on an explicit supported API/version, feature-probe signatures, and fail with dependency-specific errors. Do not copy sibling-directory auto-discovery or assume all installed libraries have identical contracts.

The current sampler uses `RandomNoise` → `BasicGuider` → `KSamplerSelect` → `SamplerCustomAdvanced`, forwarding the actual incoming SIGMAS. It accepts a sampler name, **not an external SAMPLER object**, and uses BasicGuider rather than an arbitrary CFG interface. This is a useful baseline, not fulfillment of the rewrite's external sampler contract. Add and validate the external SAMPLER path without substituting a default sampler or rebuilding a supplied sigma schedule. Preserve supplied MODEL patches and exact sigma values/order; fingerprint configuration without mutating the inputs.

### LoRA application receipt

Resolve an ordered project/scene/segment stack before queueing. Record binding ID, model-file identity/hash, enabled state, model/CLIP strengths where supported, activation words and order. The existing node supports **model-only** LoRAs and applies them through `comfy.sd.load_lora_for_models(model, None, lora, strength_model, 0.0)` before model-sampling/PDD patches; its receipt checks project/segment-equivalent identity and stack consistency. This ordering is a tested-in-code precedent, not a universal accelerator rule.

The rewrite receipt must bind to the **job/snapshot**, not a subsequently active segment. Use ComfyUI's non-destructive patching semantics and verify the upstream model remains reusable between jobs. Reject a stale or mismatched receipt. Trigger words are exact authored strings, not automatic `<Subject N>` bindings; show their location in the compiled prompt. Test ordered stacks, disabled/zero-strength entries, repeated use and accelerator ordering separately. If external graphs already apply the same LoRA, surface the duplicate rather than silently stacking it twice.

### Drift control: reuse candidates, not defaults

- M1 defaults to original-context hard masked AV continuation (context 0, new region 1). No fractional departure ramps or automatic pixel repairs. Record experimental decode-edge ownership separately, initially off; see section 20.
- Legacy drift control's **39-frame-specific** disposable video prefix uses 12 latent video steps (8 matched + 4 taper), a next-lower/current-sigma ratio and 256 mask quantization; audio masking is unchanged. This is historical research evidence, not the default M1 mask or a correct template for all context lengths. Any later optional reuse needs capability, schedule, AV and visual validation.
- Existing color-stable treatment compares context color statistics to a selected baseline, applies a bounded low-frequency `E(graded D(z)) - E(D(z))` delta, and leaves audio unchanged. It can require decoding plus two encodes and has process-local stats caching. It is not free, and it does not establish reference identity or scene composition correctness.
- Do not carry a baseline automatically across scene changes. Freeze an explicit baseline artifact/endpoint when a method requires one. Different current-source and baseline roles must remain distinguishable.
- Port only methods that pass visual, tensor, AV and accelerator validation. Report unsupported combinations before sampling. Do not equate a drift-mask unit test with proof that the next segment starts correctly.

## 16. Job lifecycle, transactions and preview recovery

### Command and execution protocol

Proposed commands include create/edit project/scene/segment, save prompt draft, select output, resolve/preflight job, submit/cancel job, register take artifacts, request preview and finalize splice. Every mutation carries `expected_revision` and a command/idempotency ID; every completion carries `job_id` plus an execution association. Stale writes return a conflict and current revision, not last-writer-wins changes to another segment.

Use separate job states such as `queued → running → persisting → succeeded`, with `failed`, `cancel_requested` and `cancelled` outcomes. Keep generation result, review selection and preview state separate. A successful latent save followed by a preview failure remains a successful take with a recoverable preview error. Do not report the whole generation as failed because an unrelated inspection/UI node encounters `preview: null`.

At queue time freeze target IDs, source IDs/hashes, exact prompt/reference/LoRA plans, seed, actual duration plan and execution inputs. Recheck them at submission; on completion verify source hashes and write to the job's target even if the user navigated to another scene. Preflight must be side-effect-free with respect to model loading and project artifacts.

### Durable commit and interruption

The old store demonstrates per-project locking, expected revision checks, SHA-256 validation, temporary-file writes, flush/fsync, atomic replace, and an acceptance journal that can finish a publication after interruption. Use those patterns for job/artifact publication. Cross-process execution requires a lock with matching cross-process guarantees; an in-process lock alone is insufficient if multiple writers are supported.

Stage outputs under a job-specific location, verify files and metadata, then atomically publish references to completed immutable artifacts. Cancellation/failure must preserve previously successful takes. Startup recovery reconciles journal/job state against actual hashes and running executions before releasing a lock; elapsed time alone does not authorize accepting an unknown result. A late completion must not attach to a different request. Browser reload must not be the only way to recover a finished take or release an interrupted job.

### Preview contract

Register preview against `take_id`, source artifact hash, encoding settings, FPS, source/delivered frame intervals, audio properties and context-trim state. Validate `(preview or {})`/nullable metadata consistently in all status routes and node callbacks. An MP4 visible in an external node is not necessarily registered in the project; show those as separate states with a retryable registration action.

Generate/rebuild preview from the saved take without resampling. Use one AV trim/mapping service for monitors, splices and export; use integer/rational conversions rather than successive rounded time offsets. Acceptance/selection policy regarding absent previews must be explicit in the UI; persistence can retain valid latents even when encoding fails. If an external video-combine node supplies the MP4, its completion receipt must name the exact take/job, not the current segment.

VAE encode/decode calls may occur once per reference and during preview/processing. A repeated dynamic-VRAM preparation message alone does not establish full unloading or duplicate model copies. Instrument operation counts/times and available residency metrics before diagnosing reloads. Optional clean-reference caches must be bounded and keyed by asset hash, preprocessing/geometry, VAE/model identity/version and transformation version; retain immutable CPU data and define invalidation rather than keeping unbounded GPU references.

## 17. Diagnostics and acceptance evidence

Every take inspector should answer, without inspecting an external graph manually:

- Which scene/segment/prompt draft and immutable take/artifact supplied this generation?
- Which exact source frame/range and latent handover were used? Which source was shown in the monitor?
- What was the final model prompt, allocated picture/video/audio mapping and explicit reference role?
- Which LoRAs, MODEL patches, SAMPLER and SIGMAS reached execution, and which drift treatments ran?
- Which raw/delivered frame counts and audio trims produced this preview? Was preview creation successful?
- Were configuration snapshots complete, redacted, truncated, or missing dependencies?

Store job-correlated structured events for source resolution, conditioning, sampling, latent persistence and preview registration. Include IDs, hashes, modes and timing; do not flood logs with image tensors or secret values. A compact source receipt should compare the requested, resolved and consumed artifact hashes. Fail before sampling when these disagree.

The existing provenance capture walks upstream submitted API nodes from MODEL, text encoder, video/audio VAE, SIGMAS and reference inputs. It records bounded, redacted node/configuration summaries; it is **not** a complete replay snapshot. The rewrite must extend roots to external SAMPLER and every executed stage, retain dependency/connection structure and sanitized submitted execution data, and flag omissions. Topological order is not proof of observed scheduler execution order. Runtime tensor hash/shape receipts can supplement configuration evidence where practical; filesystem mtime or a graph hash alone is insufficient identity.

### Evidence levels and carry-forward decisions

| Existing behavior | Evidence available | Rewrite decision |
|---|---|---|
| Select older take → accept its archive | Source trace and storage regression tests comparing bytes | Preserve explicit take binding; additionally verify runtime consumption. |
| Exact joint-AV prefix trimming | Implemented formulas and validation | Port behind an adapter capability; GPU/AV seam tests still required. |
| Native reference ordering and per-image scaling | Source trace and mocked conditioning tests | Reuse alignment checks; actual influence/adherence requires visual tests. |
| Automatic final-frame image + keyframe + authoritative prompt | Implemented; real continuity behavior disputed | Remove completely from Continue Latent. |
| Identity checkpoint instructions | Multiple prompt revisions; composition behavior disputed | Remove subsystem; retain normal authored reference roles. |
| HyperFlow automatic timestamp offset | Implemented locally; timing behavior inconsistent | Do not port; deferred controlled research only. |
| Refined latent source with original-master final-frame guide | Separate source-resolution paths exist; causal effect unproven | Eliminate hidden guide and require a single exact source descriptor. |
| Preview status `.get` on null | Reproduced storage/status regression; local fix | Specify nullable preview handling and independent generation success. |

Passing storage, schema, mocked-node or prompt-string tests does not establish generation quality. M1 must include real two-segment continuation, actual source-consumption receipts and AV seam review before layering drift techniques or later operations. M2–M4 extend the same gates to each boundary of a splice, prepend or bridge. Preserve a small reproducible diagnostic case and compare one variable at a time.

### Source map for implementation work

The following are inspection references in the sibling legacy project, **not dependencies to import wholesale**:

- [Project store](../ComfyUI-MinimaxH3-Longcaster/longcaster/project.py): `begin_generation`, `finish_generation`, `_take_from_card`, `_apply_take_to_card`, `select_draft_take`, `accept`, `continuation_artifact`, revision/commit/journal handling.
- [MH3 adapter](../ComfyUI-MinimaxH3-Longcaster/longcaster/mmh3_adapter.py): `primary_latent`, `prepare_continuation`, archive save/load contracts.
- [Duration](../ComfyUI-MinimaxH3-Longcaster/longcaster/duration.py) and [trim](../ComfyUI-MinimaxH3-Longcaster/longcaster/trim.py): frame planning, exact AV endpoint cropping.
- [Conditioning/sampling](../ComfyUI-MinimaxH3-Longcaster/longcaster/h3_runtime.py) and [image latent transformations](../ComfyUI-MinimaxH3-Longcaster/longcaster/card_reference.py): reference payload ordering, guarded metadata replacement, external sigma forwarding.
- [Reference media](../ComfyUI-MinimaxH3-Longcaster/longcaster/reference_media.py) and [prompt fields](../ComfyUI-MinimaxH3-Longcaster/longcaster/prompt_sections.py): bindings/aliases, six-section parsing, exact activation-word injection.
- [Drift](../ComfyUI-MinimaxH3-Longcaster/longcaster/drift_control.py), [color treatment](../ComfyUI-MinimaxH3-Longcaster/longcaster/color_stable.py), [continuation policy](../ComfyUI-MinimaxH3-Longcaster/longcaster/continuation.py): candidate algorithms and explicit recipes.
- [Splice model](../ComfyUI-MinimaxH3-Longcaster/longcaster/card_edit.py): range validation, independent take preservation and final-source resolution.
- [Provenance](../ComfyUI-MinimaxH3-Longcaster/longcaster/provenance.py), [compatibility probes](../ComfyUI-MinimaxH3-Longcaster/longcaster/comfy_compat.py), [routes](../ComfyUI-MinimaxH3-Longcaster/longcaster/routes.py), [node integration](../ComfyUI-MinimaxH3-Longcaster/nodes.py): execution receipts, errors, status/preview and LoRA wiring lessons.

No saved external graphs were inspected or executed to write this specification. Accelerator compatibility, incoming/suffix pinning and actual generation seam quality remain validation work rather than implied capabilities.

## 18. M1 amendment: named reference definitions and H3 Prompt Compiler

This amendment is part of M1. It supersedes numeric scoped aliases as the primary authoring interface. The implementation belongs to a **new H3 Prompt Compiler**, separate from the legacy prompt assembler. Browser editors and individual ComfyUI nodes must not implement independent token-substitution or reference-allocation logic.

### Definition-owned names and renamable assets

Every reference definition created at project, scene or segment scope owns its name at definition time. Require an editable, unique token-friendly name such as `hero`, `house`, `red_jacket` or `walking_motion`, an explicit H3 classification/role, and an asset binding. The UI may suggest a name, but the definition saves the chosen name explicitly; no runtime name is guessed from a filename, display order or subject number.

Minimum reference definition:

```json
{
  "reference_id": "immutable-uuid",
  "definition_version": 1,
  "display_name": "Hero character sheet",
  "token_name": "hero",
  "scope": "scene",
  "h3_classification": "subject",
  "asset_bindings": [{"asset_id": "immutable-uuid", "asset_version": "immutable-version", "provides": "facial appearance"}],
  "enabled_policy": "enabled",
  "order": 0
}
```

Supported classifications are subject, picture, video and audio, subject to the selected H3 path. Classification is the reference's intended semantic role, not merely its file extension. An image may supply reusable subject content or serve as a picture/composition reference. A subject may draw different attributes from multiple explicitly bound assets; one asset may supply multiple named subjects. This is normal authored reference configuration, not a restored identity checkpoint mechanism.

Asset library entries also have editable display names independent of their immutable asset IDs/content versions. Asset display name, reference display name, prompt token name and disk filename are separate fields. Renaming a library asset does not move its immutable bytes or silently rename every reference token using it. A combined rename command may update explicitly selected fields in one reviewed transaction; the UI must show which names change.

For M1, token names use `[A-Za-z_][A-Za-z0-9_]*`, with case-insensitive ASCII lookup and original spelling retained for display. Effective names are unique after case folding. Reserve native H3 labels, supported control/section tags and any enabled template names so `<d>`, `</d>`, `<scenetrans>`, `<cutoff>`, `<Subject 1>`, `<Picture 1>`, `<Video 1>` and `<Audio 1>` are not misclassified as user tokens. Other profile-specific supported syntax is likewise registered explicitly. Tokenization must respect whole angle-bracket tokens, not replace substrings of ordinary prose.

### Effective scope and override semantics

Resolve Project → Scene → Segment definitions using immutable reference IDs and explicit inheritance policies. Add, override, disable and exclude preserve the behavior specified in section 3. A local override references the inherited logical definition/ID and records its overridden version/asset/role/name; an unrelated new definition with the same effective case-folded name is a conflict, not implicit shadowing.

Two definitions may reuse one asset, but two different effective definitions may not claim the same token. Disabled definitions keep their metadata/identity and show as unavailable in diagnostics; they are not silently replaced by a similarly named reference in another scope. Resolve against the target job's scene/segment, never whichever scope happens to be open in the UI. An asset reassignment is a new binding version; already queued jobs and historical takes retain their frozen version.

### Compiler result and native label allocation

Compile every applicable field, including `subject_definitions`, `summary`, `retention_analysis`, `detailed_description` and supported audio fields, using one resolved reference plan. Both hand-authored text and text generated by the Retention Analysis Editor use named tokens. The compiler returns:

- Authored prompt fields/draft ID, resolved inheritance/appends and source locations.
- Effective named reference definitions with IDs/versions, roles, asset IDs/hashes and conditioning parameters.
- Named-token → native semantic-label mapping and subject → source-asset/native-label relationships.
- Ordered image/video/audio conditioning manifest, native indices, soundtrack associations and supported latent-reference transformations.
- Final H3 prompt, compiler/profile versions, validation diagnostics, transformation trace and compiled-result fingerprint.

**Subject numbering and image numbering are independent.** A subject label is a semantic content label, not an image socket. Its source portrait still occupies a `<Picture N>` slot in the native image payload, even though the author writes `<hero>` and the scene text compiles to `<Subject 1>`. Allocate image/video/audio indices from actual supplied payloads and subject indices from resolved subject definitions. Both mappings must remain linked and frozen. The illustrative numbering in the amendment is not a fixed index assignment.

For example, when the enabled image order is hero portrait, house photograph, jacket photograph, followed by a walking video:

| Named token | Semantic H3 label | Source conditioning binding |
|---|---|---|
| `<hero>` | `<Subject 1>` | Hero portrait is native `<Picture 1>`. |
| `<house>` | `<Picture 2>` | House image is the second enabled image. |
| `<red_jacket>` | `<Picture 3>` | Jacket image is the third enabled image. |
| `<walking_motion>` | `<Video 1>` | Walking video is the first enabled video. |

The compiler must supply the matching image/video bytes and encoded conditioning, not just replace strings. A source binding explicitly authored/configured for a subject supplies a source clause in its compiled definition when required, without replacing the user's character description or inventing traits. Multiple source bindings name what each provides. Do not insert another subject definition with the same ID when one already exists.

Illustrative authoring:

```text
subject_definitions:
<hero> is a young woman with short black hair.
<house> is a composition reference showing a traditional wooden house.

detailed_description:
[Shot 1] <hero> approaches <house>.
```

Illustrative compilation with the table's ordering and an explicit facial-appearance binding:

```text
subject_definitions:
<Subject 1> is a young woman with short black hair. Her facial appearance comes from <Picture 1>.
<Picture 2> is a composition reference showing a traditional wooden house.

detailed_description:
[Shot 1] <Subject 1> approaches <Picture 2>.
```

The source-clause wording is illustrative; its relationship must come from the reference definition. No undocumented role inference or image-based prompt replacement is allowed. A clothing/scene image used as reusable content can instead be explicitly classified as a subject; the compiler validates the chosen use without treating every picture in retention as a keyframe.

Identical source assets with identical preprocessing/conditioning may share one native payload slot and expose multiple named content bindings. Different crops, transforms or conditioning roles that require distinct payloads remain distinct. Deduplication and order are deterministic and recorded. Optional manually authored native numeric labels remain valid syntax, but must resolve to the actual frozen manifest; they are not an exemption from range/consistency checks.

### Retention Analysis Editor and autocomplete

M1 includes a Retention Analysis Editor that selects a reference by ID and shows its name, thumbnail, type and scope. Each structured row stores reference ID, use case, relationship marker, optional shot/appearance locations and editable description. It renders named tokens, never requires manual numeric H3 labels, and passes through the same compiler as manual text.

For example, reference `hero`, use case **Establish Identity**, marker `fully_preserved`, description **Preserve facial identity, hairstyle and distinguishing characteristics** produces:

```text
<hero>: fully_preserved - Preserve facial identity, hairstyle and distinguishing characteristics.
```

Reference `house` may produce:

```text
<house>: weak_reference - Preserve the general architectural composition and atmosphere without copying exact details.
```

With the example manifest these compile to `<Subject 1>` and `<Picture 2>` entries respectively. The use case is an authored reference role; it does not create identity checkpoints or automatic state injection. Marker validation follows the selected profile/category: visual relationship markers and audio relationship markers have distinct allowed sets. Retention text remains editable and is not regenerated over subsequent manual edits without an explicit user action.

Typing `<` in any applicable prompt field opens autocomplete for the target segment's effective named references. Show token, display name, thumbnail where available, media type, H3 role and originating scope. Inserting a suggestion writes the named token or an ID-backed structured token node; numeric output is shown only in compiled preview. Disabled/unavailable definitions may be shown for diagnosis but must not be inserted as usable assets. Autocomplete and compiler diagnostics use the same server-resolved definition set/version.

### Rename and reassignment transactions

Renaming a reference preserves its immutable reference ID and source asset bindings. Update ID-linked structured definitions and retention rows to render the new token name; invalidate their compiled preview/cache. Offer a reviewed, whole-token replacement in affected freeform working drafts, showing changed occurrences and scopes. Do not silently rewrite archived drafts or generated takes. If the user declines a freeform replacement, retain that text and surface an unresolved-token error rather than silently aliasing the old name to a different asset.

Rename preflight checks effective-scope collisions, inherited uses and reserved names. Make rename plus accepted working-text changes a single expected-revision transaction; stale edits conflict. An explicit name override can be scene/segment-local without renaming the project definition. UI selection remains ID-based. Restoring a take shows its frozen names/mapping; applying it to current working state requires reconciliation if the live names/assets have changed.

### Validation and immutable snapshots

Fail before encoding/sampling for unknown names, missing assets, disabled/unavailable definitions, effective-name collisions, invalid classifications, incompatible generation paths, unbound subject sources, bad native label indices, conflicting mappings and unsupported asset limits. Diagnostics identify the prompt field, character span/token, reference ID and originating scope with a specific remedy. Do not convert an unresolved token into an unbound `<Subject N>` and continue.

Save in every take: original named-token prompt and draft/definition versions; resolved fields; final compiled H3 prompt; complete semantic-token and source-asset mappings; actual asset versions/hashes; conditioning payload order/preprocessing; latent-reference modes; compiler/profile version and fingerprint; full available upstream execution snapshot. Reference or asset renames/reassignments do not rewrite these records.

The serialized compiled result is also the conditioning adapter's input contract. Native preparation returns a receipt of consumed asset hashes/indices. Compare that receipt to the compiled manifest before sampling. The browser and downstream nodes consume this contract; they do not recalculate token numbers independently.

## 19. Selected MH3 upstream baseline and pre-implementation gate

The selected rewrite dependency is [einhorn13/mmh3_media](https://github.com/einhorn13/mmh3_media) at commit **`86b96deb52ed3c753789b5bf846f58e0b0c2feba`**, dated **2026-10-09**. The user selected this upstream revision on 2026-10-17 after the compatibility review. It is a commit pin, not a release tag; no tags or published releases were returned by the upstream release queries at review time. Do not silently track moving `main` or upgrade dependencies during a generation.

Verified source-level contracts at that pin:

| Contract | Verified value / consequence |
|---|---|
| Public adapter API | `MMH3_ADAPTER_API_VERSION = 1` in `public_api.py`; check required exported functions as well as this version. |
| H3 latent contract | `H3_LATENT_CONTRACT_VERSION = 2`; this is separate from archive schema and adapter API. |
| Continuation eligibility | `sampler_output` origin, batch 1, stock `17k+5` grid, bound geometry/time, explicit `absolute_start_frame`. |
| Forward continuation | `build_h3_continuation_handover` still accepts source origin, target frames/geometry, separate video/audio handover counts and optional audio feathering; default context remains 39 frames. |
| Archive loading | `load_archive(path, verify="on_access")`; packing and full archive verification must still be exercised end to end. The upstream README states schema-2 archive support and no conversion of pre-v0.3 files. |
| Reference resolution/cache | `resolve_reference_set` and `build_reference_cache_spec` expose ordered reference/preprocessing and exact VAE/native-contract cache identities; assess reuse behind our compiler/adapter. |
| Model-family resolution | FL2VA versus Ref2VA is explicit; auto family uses active-reference presence. Do not choose checkpoints implicitly in the UI merely because a library can infer a family. |

Source references: [public API](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/public_api.py), [latent contract](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/h3_contract.py), [continuation](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/continuation.py), [reference cache](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/reference_cache.py).

Before implementation integration, record/verify the installed package commit and required symbols, then exercise archive pack/save/load, original-take continuation and reference-manifest consumption against that pin. Source-compatible signatures do not certify runtime/model output. Do not import the dependency's project/Studio/controller features as a replacement for LongCaster's agreed generation model. Incoming/suffix pin capabilities still require their own M3 validation.

The official MiniMaxAI/MiniMax-H3 repository checked during the review was revision `42ed227ee7df40d41602854ae760620d6eb651fe`, last changed on 2026-08-13 by a README update; this is not a newly verified weight release. Record actual model-file hashes used at execution. The [official input specifications](https://huggingface.co/MiniMaxAI/MiniMax-H3#model-variants-and-input-specifications) additionally require mixed-reference and duration validation: at most 12 mixed input files, up to 9 images / 3 videos / 3 audios, video/audio clips of 2–15 seconds and respective total duration limits of 15 seconds. Freeze a capability profile, account for soundtrack pairing explicitly, and surface any backend-only extension as experimental rather than silently accepting it as official support.

The selected dependency changes no product exclusions: no identity checkpoints, no automatically injected final frame, and no HyperFlow skip/compensation until a separate reviewed test result warrants it. Selecting this revision in the specification does not upgrade the legacy LongCaster installation.

## 20. M1 amendment: modular latent continuation engine

This amendment specifies the new Timeline continuation engine. It takes precedence over legacy-code reuse suggestions and any implication that schedule-matched fractional masks or color repair are the default M1 extension. The selected MH3 revision in section 19, named-reference compiler in section 18 and previously recorded product exclusions remain in force. No legacy LongCaster node, adapter or controller is a required implementation foundation.

### Research and design gate before major implementation

Study and document the listed source-level concepts before finalizing the engine. **OBVPM is the primary technical reference**; original LongCaster is evidence to investigate and compare, not a control flow to transplant. Source links below are research targets from the amendment, not a declaration that those paths or quality observations have already been runtime-validated for LongCaster Timeline. Pin reviewed source revisions in the design report.

| Reference | Research targets and required findings |
|---|---|
| [OBVPM H3 documentation](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/docs/h3.md) | Motion context, extend/prepend/bridge semantics, latent-grid rules, lineage, handover and seam diagnostics. |
| [OBVPM masked pins](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/nodes_masked.py) | `apply_masked_pins`, `mask_profile`, `handover_frames`, `core_masks_available`; source insertion, per-stream masks and fractional-mask timestep behavior. |
| [OBVPM pin definitions](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/nodes_pins.py) | `H3MCtxPinSpec`, `H3MCtxApplyPins`, source-window extraction, native keyframe conditioning, masked/guided/combined modes and audio alignment. |
| [OBVPM assembly](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/nodes_assemble.py) and [frontend handover](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/web/h3_handover.js) | Source/generated cuts and join positions; Python/JavaScript mirror agreement. Prefer one authoritative backend plan consumed by the UI. |
| OBVPM tests: [handover edge](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/tests/test_handover_edge.py), [handover mirror](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/tests/test_handover_mirror.py), [audio phase](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/tests/test_audio_phase.py), [joint bridge layout](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/tests/test_joint_bridge_layout.py) | Required invariants for edge ownership, mirrored calculations, audio phase and future dual-source layout. |
| [OBVPM seam report](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/seam_report.py) | Separate latent fidelity from motion, pixel, color and audio discontinuities. |
| Selected MH3: [continuation](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/continuation.py), [joint AV structure](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/h3.py), [latent contracts](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/h3_contract.py) | Original joint tensors, nested `noise_mask`, source origin/geometry/time compatibility and exact shared AV contexts including 39/90/141 frames. Verify actual capabilities on the pin. |
| Selected MH3: [decoded AV bridge](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/av_bridge.py), [latent stitch](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/latent_stitch.py) | Distinguish decoded two-source processing from original latent preservation; study supported provenance-aware stitching without assuming arbitrary concatenation. |
| ComfyUI 0.38.0: [model base](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy/model_base.py), [H3 model](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy/ldm/minimax/model.py), [custom samplers](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy_extras/nodes_custom_sampler.py), [H3 conditioning nodes](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy_extras/nodes_minimax_h3.py) | Native per-stream denoise-mask consumption/timestep mapping, sampling lifecycle, externally supplied SAMPLER/SIGMAS and compatible conditioning. |

ComfyUI **0.38.0 is the user-declared baseline**, not a substitute for capability checks against the actual runtime. Investigate third-party patches that replace native H3 masking functions; check effective patched behavior, not just the package version. Local runtime inspection remains subject to the user's filesystem permissions; this amendment does not authorize scanning unrelated directories or saved workflows.

OBVPM is identified in the amendment as GPL-3.0. Prefer an independently written engine. Direct incorporation or adaptation of its code requires a deliberate licensing review and approved reuse decision; recording concepts/tests as research is distinct from copying implementation. MH3 functionality may be reused where correct and compatible without inheriting the old LongCaster architecture.

Before major implementation, provide a short technical design stating module boundaries, actual native masking APIs, differences from OBVPM, archive/latent assumptions, authoritative handover/audio contracts and identified risks. Record which findings are source-confirmed, runtime-confirmed, experimental or unresolved.

### Components and execution contract

| Component | Required behavior |
|---|---|
| Continuation Source Resolver | Resolve exact source take and original sampled latent artifact/resource ID/hash, verify origin/integrity/availability, read geometry/timebase and determine the valid context range. Ordinarily M1 uses the accepted take ending the preceding segment, but this is an explicit saved source selection. Future splices supply a boundary-specific take, not a fictitious composite latent. |
| Continuation Planner | Produce an immutable versioned plan before large target allocation/queueing: source identities, context ranges, strategy, requested/resolved context, target/new frame counts, per-stream latent indices, mask profile, handover/ownership ranges, AV phase and lineage. |
| Latent Preparation Engine | Read original video/audio latent context; allocate new compatible target streams; copy the valid tail context into the prefix; construct per-stream masks. Avoid source pixel decode/re-encode when original compatible latents exist. Never mutate source tensors or concatenate complete unrelated generation latents. |
| Sampling Execution | Consume externally prepared MODEL/SAMPLER/SIGMAS and compatible conditioning through normal ComfyUI sampling. Preserve upstream patches and exact sampler/sigma configuration. Apply inherited LoRAs without discarding upstream patches. Require effective native mask support and reject unsupported combinations. |
| Handover and Timeline Mapper | Produce one authoritative source/child frame-ownership and audio-delivery plan used by timeline playback, previews, full render and export. Keep original full generated latent and delivered ranges distinct. |
| Continuation Diagnostics | Report requested/resolved context, source/target dimensions, per-stream masks/capabilities, handover position, AV phase/alignment, edge policy, warnings and reference/upstream hashes. Errors identify the failed preflight contract. |

Exact module names and physical sockets remain implementation choices. Cooperating nodes may expose resolved MODEL, SAMPLER/SIGMAS pass-through, conditioning, prepared `LATENT`, lineage/plan metadata and saved-result/status receipts. No accelerator implementation belongs inside this engine. Missing/incompatible latents fail explicitly; do not fall back to Extend from Image, a fresh generation or another take silently.

### Configurable motion context and duration planning

| M1 selection | Frames | Context at 24 fps |
|---|---:|---:|
| Standard — default | 39 | 1.625 seconds |
| Extended | 90 | 3.75 seconds |
| Long | 141 | 5.875 seconds |

Freeze the requested and resolved context separately. For the standard H3 profile, sampled video length is `N = 5 + 17k`; exact shared video/audio context boundaries are `C = 39 + 51j`. The source must supply the whole chosen context, and `N > C` must leave actual newly generated frames. Convert the requested duration of **new footage** to a valid total sampled `N` including context, then display the actual new count `N - C` and duration. Longer context consumes more of the sampled temporal window and may increase cost; it does not justify silently reducing requested new footage or exceeding a backend limit.

If a source/model/target cannot support 90 or 141 frames of context, disable that option with an actionable reason. Never silently shorten a context or switch methods. A reviewed alternative selection is a new plan. Choosing exact AV-grid target lengths is a separate evaluated duration policy; do not equate the shared-context grid with a compulsory restriction on every full output length or conceal large duration changes.

### M1 baseline: hard masked forward continuation

Protect copied source video **and** audio context with mask value **0**. Mark the new video/audio generation regions with **1**. Pass the nested `noise_mask` through preparation, guider/model conditioning and sampling until completion; verify native H3 actually consumes the per-stream masks. Do not discard masks while converting between nodes or serializers.

Use the sampler's completed joint output as the new take's raw latent master. Preserve original source arrays/archive bytes and take snapshots. Operation-specific masks may be omitted from the finished source archive only after recording the exact applied policy/values, ranges, shapes and implementation version in its immutable generation snapshot.

Do not add fractional video ramps, schedule-matched softening, Level Lock, crossfades or picture-level color correction to ordinary extensions automatically. The amendment cites OBVPM observations favoring hard departure context and warning of repair-induced flicker; reproduce these comparisons rather than presenting them as universal quality guarantees. Existing legacy drift/color algorithms remain research candidates, not defaults or required engine dependencies. Reference-image latent adherence is a separate input transformation, not the continuation mask.

### Experimental decode-edge correction — implemented in M1, initially off

Investigate the difference between decoding a latent at the source clip's edge and decoding the same preserved latent inside the child's longer run. A latent-identical context can still produce different edge pixels. The proposed correction changes **decoded frame ownership**, not source latent values, mask preservation, prompt clocks or generation timestamps.

The amendment reports OBVPM handing over one latent step earlier, covering four video frames. Treat four frames as a research candidate, not an assumed universal correction across model/VAE versions, geometry, codecs or decode pathways. Implement a deterministic, independently enabled/disabled experimental policy with an explicitly validated offset; keep the default off until measured LongCaster results justify changing it.

For illustration, if the source output ends at exclusive frame `E`, child context has `C` frames and validated ownership correction is `d` frames, replace the source delivery tail with the child's decode of those preserved frames:

```text
Normal assembly:     source [start, E)     + child [C, N)
Corrected assembly:  source [start, E-d)   + child [C-d, N)
```

These ownership intervals preserve total timeline duration and add no new sampled frames. Validate coordinate compatibility, available preserved context, `d` bounds and temporal alignment before using the illustrative mapping. Store ownership separately from the logical `N-C` newly generated duration: borrowed child-context frames are not newly generated footage. Never trim `[C,N)` first and then try to recover an earlier child's decode from that already-trimmed preview.

Keep both original takes unchanged. Persist original and corrected handover plans so preview/render/export use the same policy. Audio timing must remain continuous under a documented per-stream ownership policy; a video-only ownership adjustment is not permission to shift audio arbitrarily. This is **not** a HyperFlow time skip and must not alter authored prompt timestamps.

### Audio phase and seam diagnostics

H3 uses 24-fps video and a 40-Hz audio latent grid, so not every video frame is an exact audio-latent boundary. Track source/child audio latent offsets, phase, decoded sample positions and delivery boundaries with integer/rational arithmetic. Respect actual decoded audio sample-rate metadata; do not confuse latent rate with PCM sample rate. Test repeated extensions for cumulative drift, duplicate/skipped samples and clicks. Preserve source audio latents where the selected policy requires it and keep audio/video masks consistent with that policy.

Investigate OBVPM's audio-phase correction and exact AV target-duration options. Apply only justified deterministic bookkeeping; no arbitrary audio offsets to disguise decoder-edge artifacts, and no hidden large duration adjustment for grid alignment. Surface resolved duration and tradeoffs before queueing.

Seam diagnostics distinguish latent-context fidelity, motion discontinuity, decoded visual discontinuity, brightness/color discontinuity and audio discontinuity. A mathematically correct mask/latent join is not proof of perceptual continuity. Do not automatically repair a latent-identical join; any later correction must be relevant to the measured failure and be individually testable.

### Inspector and immutable plan/snapshot fields

The selected segment inspector exposes **Continuation Method** (Continue Latent / Extend from Image) and, for latent mode, **Motion Context** (39 Standard / 90 Extended / 141 Long). Advanced controls show experimental decode-edge correction, continuation diagnostics, effective source take/latent status, resolved context and visible frame counts. Keep internal tensor controls out of the ordinary directing UI. Explicit image continuation remains a different user-selected or inherited method, with no silent fallback from latent mode.

Each completed take freezes source scene/segment/take, original latent artifact/resource ID/version/hash, source context/stream ranges, requested/resolved method/context, requested new duration, total sampled/newly visible counts, per-stream mask profile/parameters, handover/ownership policy, audio phase/sample boundaries, compiled named prompt/reference manifest, effective model/sampler/sigma/LoRA/upstream snapshot and runtime/custom-node versions. Save completed raw joint latents and original video/audio as distinct artifacts; previews, export and later upscale never replace them. These links must resolve after restart without browser or ComfyUI in-memory state.

### Future contexts without premature M3 execution

Design context descriptors with target placement **before** (prefix for Extend), **after** (suffix for Prepend), or **both** (two-ended Bridge), each bound to independent source resources/ranges. Store before/after stream coordinates rather than assuming every plan has one generation parent or one scalar prefix count.

The amendment's research baseline is masked Extend, guided+masked Prepend, masked Bridge departure and guided+masked Bridge arrival. Future arrival mask parameters include `mask_ramp_frames`, `mask_ramp_edge` and `mask_hold`; reported OBVPM starting values around 10 frames / 0.40 / 0.0 require independent study. These are **not** default M1 controls, automatically injected final-frame guides, or universal quality guarantees. M1 executes forward extension only; guided arrival and dual-source sampling remain M3 implementation work.

### Completion evidence

Use the M1 continuation gates in MILESTONES.md for targeted unit, native runtime integration and controlled A/B tests. At completion report files changed, strategies implemented, test results and generated evidence, measured decode-edge improvement or lack of it, limitations, and which storage/interfaces are ready for M3/M4. Do not call this amendment implemented merely because the architecture or research notes were updated.


## 21. UI source/target state and implementation feedback

The full UI baseline is preserved in [UI_UX_SPEC.md](UI_UX_SPEC.md). Maintain two independently addressed contexts:

- **Current Segment Context:** finalized segment ID, finalized output ID, separately viewed immutable take/composition ID, frozen snapshot/prompt and source-monitor state. Browsing an alternate take updates its preview and inspected settings, not the saved finalized output or an already queued continuation source.
- **Generation Target Context:** operation/placement intent, destination segment or same-segment regeneration target, explicit source-boundary descriptor, editable draft/effective settings, job IDs, generated takes, right-monitor review choice and pending Finalize state. Navigation on the left must not silently retarget this working context or an executing job.

Extend creates a right-side target after the explicit source; Regenerate/Unlock creates a right-side draft targeting the same segment without mutating source data. Generate creates an immutable reviewable take. Finalize persists the chosen output at the intended placement and retains alternatives. Changing a finalized output is an explicit versioned command; descendants retain their frozen source lineage. Discard Extension identifies exactly which pending draft/placement is discarded and preserves finalized source takes and completed referenced artifacts; cancellation of running work is a separate job command.

Both center prompt regions remain useful at normal size, with field selection and optional expansion. The left shows the viewed take's exact effective frozen prompt and captured inheritance; the right edits the agreed hierarchy and uses named-reference autocomplete. Selecting retention_analysis swaps only the field's editing controls to the Retention Analysis Editor, not the whole workspace. Source prompts do not recompile from current scene defaults. Composite inspection exposes source-part prompts/configurations rather than inventing one sampled-generation prompt for a multi-take output.

Latent continuation shows implemented method, separately labelled available drift policy, valid motion contexts and appropriate advanced diagnostics. Off is a truthful drift-policy value when no optional technique is validated; do not invent working algorithms to fill a selector. Image continuation hides latent controls and may suggest the selected source ending, but the source image/frame and actual coordinates require explicit confirmation. Initial independent text/image scene starts remain distinct from continuing a prior segment.

The operation toolbar prepares identifiable right-side generation intents; it does not execute automatically or mutate the left source. Gate Split + Bridge/Prepend to M3 and advanced New Scene placement/Bridge Scene to M4. Basic scene creation and settings are available in M1 under the UI clarification; M4 completes cursor-aware placement and bridging. Disabled/unimplemented operations never masquerade as working controls.

At implementation time inspect the actual target branch and available approved mockup within authorized access. Retain useful existing components, introduce a UI dependency only for a concrete need, establish correct layout and real state transitions before cosmetic polish. Verify 1920×1080, 2560×1440 and 1366×768 with internal scrolling, resizing, keyboard text-focus guards and persisted/resettable layout. Provide screenshots, changed-file/test summaries, milestone-gated limitations and explanations of material UI deviations. No mockup or frontend implementation was verified by this documentation update.


## 22. Scene ownership, tail replacement and editing correction

The 2026-10-17 user feedback makes Project > Scene > Segment the initial creation flow: a new project/scene contains its first editable segment immediately. Independent first-segment generation, extending the finalized scene tail, and replacing that tail are separate actions. Replacement creates another immutable take using the original parent source; earlier segments cannot be replaced or have their finalized output changed. The timeline supports continuous scene scrubbing, and full prompt paste distributes authored text into the six prompt fields. See [the flow amendment](docs/scene-flow-amendment.md) and [implementation evidence](IMPLEMENTATION_NOTES.md) for precedence, delivered behavior, tests and remaining native runtime gates.


## 23. MH3 dependency compatibility policy

The 2026-10-17 user preference is to use the latest compatible upstream MH3 version. The reviewed revision is a research/provenance baseline, not an exact-hash runtime gate. Validate adapter API v1, H3 latent contract v2, required callables and their keyword signatures before execution; preserve source-resource integrity and native AV-mask checks. Record detected dependency revision and validation metadata in each execution receipt. Compatible ZIP installs may have unknown Git provenance. Preserve frozen historical take metadata. Updating an installed dependency remains explicit and requires a ComfyUI restart; the application does not perform automatic background upgrades or sibling-directory discovery. See IMPLEMENTATION_NOTES.md for the source comparison and tests.
