# M1 first slice — implementation and evidence

Status: implemented for local testing; **not full M1 completion**. The approved architecture/milestone/UI documents remain the broader specification. This report records the delivered subset and does not quietly replace the remaining gates.

## Technical design and source findings

The independently written engine uses native ComfyUI conditioning/sampling and the selected MH3 continuation/archive APIs. Legacy LongCaster controller/state-anchor/drift code is not a runtime dependency. OBVPM informed the investigation; its implementation was not copied into this project.

Reviewed sources:

- [Pinned MH3 continuation](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/continuation.py): original tail extraction into a fresh joint AV target, nested per-stream noise masks, exact shared context boundaries. Native output grid `N=17k+5`; exact AV context `C=39+51j`.
- [Pinned MH3 latent contract](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/h3_contract.py): `sampler_output` origin, batch 1, bound geometry/time, explicit absolute start, joint AV layout. The public API module does not re-export archive I/O or these contract helpers; the local adapter imports their owning modules explicitly.
- [Pinned MH3 generation contract](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/generation_contract.py): REF2VA continuation can use normal reference conditioning while the original joint latent supplies the temporal start. FL2VA uses text conditioning without a keyframe requirement. Reference conditioning and continuation state are separate.
- [Pinned MH3 decoded continuation](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/decoded_continuation.py), [AV bridge](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/av_bridge.py), [latent stitch](https://github.com/einhorn13/mmh3_media/blob/86b96deb52ed3c753789b5bf846f58e0b0c2feba/mmh3_media/latent_stitch.py): different tools for decoded-source operations/dual-source processing/provenance-aware assembly. None justifies concatenating unrelated full generation latents or silently replacing original latent continuation with decoded frames.
- [ComfyUI v0.38.0 H3 nodes](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy_extras/nodes_minimax_h3.py), [model base](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy/model_base.py), [custom samplers](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/comfy_extras/nodes_custom_sampler.py): ordered reference payloads, native video/audio mask conditioning and standard external SAMPLER/SIGMAS execution. Runtime masking overrides can invalidate baseline assumptions.
- [OBVPM masked pins](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/nodes_masked.py) and [handover](https://github.com/chanon/comfyui-obvpm-timeline/blob/main/web/h3_handover.js): concept comparison for hard/fractional masks and decoded handover ownership. No GPL source was incorporated. Its edge policies remain research rather than claims of measured LongCaster parity.

An upstream GitHub API check during this session found the selected MH3 revision still at the repository head, with no tags/releases indicating a newer release. No installed dependency was changed. Source findings are **source-confirmed**, not proof that this machine's live patched runtime behaves identically.

## Modules

| Module | Responsibility |
|---|---|
| `timeline_core/store.py` | UUID projects, optimistic revisions, OS/thread locks, atomic manifests, immutable queue snapshots and take records, publication journals/restart recovery, source integrity, authoritative duration/delivery planning. |
| `timeline_core/compiler.py` | Scoped reference resolution and explicit overrides; case-insensitive named tokens across six fields; independent Subject/Picture numbering; prompt/conditioning order from one manifest. |
| `timeline_core/engine.py` | Capability-checked adapter facade, source resource/hash/contract checks, original tail preparation, pre-sampling tensor/mask assertions, checkpoint-family diagnostics, native sampling, original archive publication and execution receipt. |
| `timeline_core/preview.py` | Decode the saved sampled archive; retain full AV outputs and generate a separate delivery preview. Preview failure cannot roll back successful sampling. |
| `timeline_core/routes.py` | Local project/command/job/reference/media APIs and built app assets. Adapter preflight runs before queueing costly upstream model execution. |
| `nodes.py` | Narrow execution node with externally connected MODEL/CLIP/VAEs/SAMPLER/SIGMAS; no replacement model loader/sampler implementation. |
| `web/extension/launcher.js` | ComfyUI launcher and same-origin opener bridge; queues only the execution node's upstream closure, maps progress/errors and cancels only its queued/running prompt. |
| `frontend/src/` | React/TypeScript app, timeline, monitors, prompt editors, inspector state, reference management and generation/finalization flow. |

React + Vite provides the app bundle, Radix Dialog provides accessible dialogs, react-resizable-panels provides persistent split layouts, and Lucide provides icons. The initial generation timeline is small custom React/CSS geometry driven by backend take plans. A multitrack editor library is not needed for this slice's Generate/Extend interactions; later trim/splice operations can evaluate one against the actual data contracts. The app ships with its production bundle.

## Delivered behavior

- New project and basic scene creation/renaming; numbering is scene-local.
- Timeline scene track with draft/finalized segment blocks, playhead, ruler scrub, zoom, selection and transport shortcuts. Internal scrolling and resizable/resettable layout.
- Dual monitors and prompt regions; read-only frozen source and separately editable generation target. Right inspector has references/miscellaneous, takes and generation settings; Generate stays visible while settings scroll.
- REF2VA uploaded image references at project, scene and segment scope, explicit narrower-scope image overrides, exclusions, role overrides, reviewed renaming, autocomplete and editable retention entries. All six fields pass through the same compiler.
- Generate → review → Finalize → Extend → review → Finalize, plus same-segment tail replacement. Each new project/scene has its first segment immediately. Only a finalized tail can be extended; non-tail replacement/finalization is rejected by the backend. Browsing takes differs from finalizing. A prepared/queued extension is not rebound by browsing another source take.
- External SAMPLER/SIGMAS/MODEL execution with captured upstream configuration, exact sigma list, input/reference IDs/hashes and lineage. LoRAs on the external MODEL remain applied; there is no internal accelerator path.
- Continue from the exact finalized original latent/resource, not a thumbnail or selected preview. Default 39-frame hard AV context; 90/141 supported by the planner when valid. Archive verification at queue/execute/publication.
- Preserve raw latent/full MP4/WAV and delivery preview separately. Sidecar preview errors support a no-resampling rebuild. Finalize is gated by preview readiness in the UI.
- One active sampling job per project, duplicate-claim rejection, targeted cancellation, dispatch/upstream-error recovery, restart recovery and a publication journal.

Authored timing remains unchanged. There is no identity-checkpoint system, automatic last-frame guide, HyperFlow timing offset, fractional mask, automatic color repair, or alternate-take fallback.

## Continuation details and limits

The source freeze records take/scene/segment IDs, archive path/hash, primary resource ID, dimensions and source plan. The adapter reopens with full verification, validates the source contract and builds a fresh target via `build_h3_continuation_handover`. Both copied prefix masks must equal 0, both new masks must equal 1, and both copied tensor prefixes must equal the source tails before sampling. Effective H3 model masking support is checked before sampling. The standard sampler consumes the external sampler object and exact sigma tensor. Completed operation masks are removed only when saving the finished sampled master; receipt diagnostics retain the applied policy/ranges.

The take-local original archive starts at frame 0. Its delivered range is `[C,N)`, while the original full sampled run is retained. The timeline uses the take's actual `N-C` duration. Default 5 seconds resolves to 124 independent frames, and approximately 5 seconds plus 39 context frames resolves to 158 sampled frames / 119 delivered frames. The total sampled window is capped at 362 frames pending longer-window tests.

At 24 FPS and 40 Hz, 39/90/141 contexts are exact shared boundaries, but arbitrary `17k+5` full lengths may require rounded audio-latent lengths. The plan records that rounding residual; PCM preview trims use the actual decoded sample rate and integer sample boundaries. This does **not** establish repeated-extension audio seam/phase parity. No speculative phase correction has been applied.

Model/VAE context can make decoded pixels at the edge differ despite correct original latent preservation. Experimental decoded-edge correction remains **off and unimplemented in this first slice**, although the full M1 amendment requires its later implementation/evaluation. Video playback currently advances between finalized scene segments using browser media elements; it is not a sample-accurate, gapless export renderer.

The source/code audit confirms the selected API contracts. It cannot prove sampler-side protected-output fidelity, composition continuity, audio seam quality or accelerator compatibility without native model execution.

## Verification evidence

- `python -m unittest discover -s tests -v`: **24 passed**. Covers independent reference numbering, retention tokens, authored timing, scoped override isolation, compiler preflight failures, actual adapter-module boundaries and compatibility checks, MODEL-branch checkpoint identification, frozen source/hash/reference bindings, finalized-take selection, geometry rejection, duplicate claim and snapshot tampering, queued/running cancellation, preview failure persistence, recovery and revision/path boundaries.
- `npm run build`: TypeScript checks and production Vite build passed. Radix's ignored `use client` bundle messages are non-failing bundler notices.
- Playwright: **12 passed** (8 browser scenarios plus 4 prompt/timeline checks) against a simulated API/execution bridge. Covers Generate/Finalize/Extend source binding, queued cancellation, both monitors, all three image-reference scopes, expanded prompt editing, reviewed reference renaming, and desktop layouts at 1920×1080, 1366×768 and 2560×1440.
- Browser screenshots: [1920](docs/screenshots/first-slice-1920.png), [1366](docs/screenshots/first-slice-1366.png), [2560](docs/screenshots/first-slice-2560.png). These show fixture data, not GPU-generated evidence.
- Python compilation passed. No saved user workflows were inspected or executed.

## Outstanding first native test and later gates

Next native test: connect the matching REF2VA model with ordinary character-sheet references; generate A; finalize A; extend into B; verify source resource/hash and hard masks in B's receipt; review the seam and audible transition; restart and extend B. This development Python lacks the running ComfyUI/PyTorch model environment, so **no actual GPU generation or measured quality result is claimed**.

Before calling M1 complete: native AV mask/output fidelity tests and saved-take reopen continuation; controlled accelerator/stock comparisons; repeated-extension audio phase/seam checks; measured decoded-edge policy and ownership tests; broader scoped audio/video references and scoped LoRA management; remaining inheritance/project management requirements from the milestone document. Splicing/Split belongs to M2, operation-level Prepend/Bridge to M3, and advanced scene insertion to M4.


## 2026-10-17 scene flow and editing correction

The user clarified that scenes own ordered segments. New projects now contain Scene 01 with Segment 01 ready for references/prompt input and independent generation. New scenes likewise contain their first segment. Existing empty scenes are initialized idempotently on entry; existing segments and saved takes are retained.

The normal directing sequence is **Generate first segment -> Review/Finalize -> Extend scene -> Generate next segment**. **Replace tail segment** generates a new take for the same final segment. For a first segment its source remains independent; for a continuation it restores the original frozen parent source and motion context. No sampled take is overwritten. Queueing, execution claims and changing a finalized output enforce the tail-only rule. Adding segments during a running scene job or ahead of an unfinished tail is rejected. The internal operation value `regenerate` is retained for compatibility; the user-facing action is Replace.

The timeline supports pointer capture for ruler/clip-lane dragging and a larger playhead hit area. A frame-rounded scene position resolves to one segment and a local preview time. A pending seek is applied after metadata loads when the selected source changes. This replaces fixed-delay seek/play callbacks. Focused timeline arrow keys move one frame; scrubbing leaves the generation target and authored draft intact. Ungenerated draft placeholders have no playable frame. Playback remains browser media playback rather than a gapless scene export engine.

A shared prompt importer supports plain/markdown six-section headings and matching XML field sections. Both the Paste prompt dialog and direct textarea paste use it. Partial imports keep omitted fields; duplicates and unassigned preamble/outside text are rejected to prevent silent loss. No timestamp compensation or shot rewriting is performed.

Additional evidence: Python tests exercise auto-initialized scene/segment ownership, idempotent empty-scene initialization, unfinished-tail guards, independent first-segment replacement, original-parent continuation replacement, and non-tail queue/finalization rejection. Browser tests cover fresh project/scene entry, sectioned prompt import and clipboard paste, tail-only replacement and real preview seeking across finalized segment boundaries. The seek test uses a small seekable WebM fixture with HTTP byte-range responses matching the saved-file endpoint; it checks actual video currentTime, playhead dragging and one-frame steps. It does not use model-generated footage or claim GPU quality validation.


## 2026-10-17 MH3 compatibility and latest-version preference

The exact-checkout gate was too restrictive: an installed `386980fc2dfddfebcf77cec43782eca2f351e4ae` was rejected before capability checks. The latest official upstream check still resolves to `86b96deb52ed3c753789b5bf846f58e0b0c2feba`, two commits ahead. Source hashes for public_api.py, h3_contract.py, continuation.py, archive.py and process_result.py match between these revisions. Both declare adapter API 1 and latent contract 2. generation_contract.py differs, so runtime checks still validate the needed callable/signature surface.

Policy now prefers the latest compatible upstream dependency without automatically upgrading it. Compatibility requires API v1, latent contract v2, required callable exports, the archive/continuation/packing/family-validation keyword contracts, and packet create/primary/extension methods. Preflight binds signatures without executing dependency functions, allocating model tensors or loading weights. A different Git hash is not an error. An unavailable Git revision is recorded as null and does not by itself reject a compatible ZIP installation.

Generation receipts now record the detected dependency Git revision and compatibility metadata instead of always reporting the reviewed baseline hash. New snapshots label the constant as `mh3_reviewed_revision`; historical frozen snapshots/takes are retained unchanged. Revision metadata records the checkout observed at execution; after updating installed Python code, restart ComfyUI so its loaded modules reflect that checkout.

The 24 backend tests include the reported older hash, the reviewed baseline, another compatible hash, missing Git, incompatible API/latent versions, missing exports, and an incompatible continuation signature. Latest-version installation is a separate action requiring the exact authorized dependency directory; no installed MH3 checkout was changed by this compatibility fix.


## 2026-10-17 Project preview beside the timeline

A collapsible monitor now reviews all scenes in project order using one cached H.264/AAC MP4. The timeline retains its left-hand lane, zoom and scrubbing. Visibility persists; the initial small-screen layout keeps the monitor closed. Project playback never changes the active generation target or inspected scene. Timeline seeking resolves the matching take into the assembled movie's project frame range.

`timeline_core/project_preview.py` resolves finalized outputs and optional ready draft takes, then assembles the already-trimmed delivery previews on a single background worker. The selected tail take can audition a replacement without publishing it. The manifest records scene/segment/take IDs, draft flags, global and scene-local frame ranges, source fingerprint and output hash. Content keys include source file identity and delivered frame counts; display-name changes reuse the movie. Endpoints POST `projects/{project}/preview` and GET `projects/{project}/preview/{key}` expose build state and byte-range playback. Failed builds expose retry; publication uses atomic replacement. No sampler, latent decode, source mutation, double context trim or GPU allocation is involved.

Evidence: 28 backend checks pass, including actual FFmpeg assembly of red/blue clips with audio, exact 72 decoded video frames, the color transition at frame 24, three seconds of decoded stereo audio, asynchronous build/cache reuse, project ordering, draft inclusion, missing preview rejection and unchanged source/project bytes. Browser checks use simulated project APIs with real seekable media; they cover playback across the finalized/draft boundary, project seeking from the ruler, draft exclusion, no accidental finalization, and persisted visibility at 1920 and 1366 pixels. Production TypeScript/Vite build also passes. GPU generation and model-produced seam quality still require the user's native test.


## 2026-10-17 Named upstream configurations

Added Configuration and Configuration Switch nodes, an optional lazy configuration input on Execution, the app's named selector, and a bridge that freezes/prunes the queued branch. MODEL/SAMPLER/SIGMAS travel as one typed bundle; CLIP and VAEs remain shared. Existing direct inputs retain their behavior. The switch adapter reuses the MIT SimpleSelectorSwitch from the pinned, unmodified bundled Lenient Switch module; its license and provenance are included.

The queue snapshot records the configuration identity, name, mode, slot, redacted selected upstream inputs and their fingerprint. Dispatch and execution check the frozen selection; family preflight follows only the selected MODEL root. Inactive branches are excluded before ComfyUI validation as well as protected by lazy evaluation. The dropdown uses canvas node IDs for bindings and refreshes the connected options while retaining missing saved choices as unavailable. Per-take metadata stays frozen when later takes select another path.

Targeted validation: 33 backend checks and 19 Playwright checks, including pure dispatch graph tests and app selection between two takes; TypeScript/Vite production build. Model objects are fakes in adapter tests and the execution bridge is simulated in app tests. No actual GPU sampling through the new configurations has been claimed. See CONFIGURATIONS.md for the native wiring/acceptance procedure.


## 2026-10-17 TODO implementation and editable-project migration

Compiler v2 separates typed source citations from authored Subject labels. It preserves unambiguous legacy bare-name behavior but injects no definitions for qualified citations. Effective scoped assets enforce namespace uniqueness and media-kind-preserving overrides. Compiled subjects expose explicit source IDs, including multiple sources/subjects and subjects without assets. Unknown, disabled, malformed, unsupported and undefined tokens fail before sampling. Images are the active conditioning path; mixed video/audio payloads remain gated and are not marked complete in TODO.md.

Project dimensions are authoritative at queue time, persist through the project selector, propagate into scene/segment drafts and freeze into each take. Existing projects infer geometry from saved media. A changed project size cannot resize or silently continue an incompatible source. Extension duration is adjacent to Extend, synchronized with settings, and zero disables creation/generation.

Jobs now persist progress separately from immutable snapshots. The execution bridge binds an actual prompt ID and filters unrelated or unidentifiable progress. Native execution records preparation, encoding, continuation, sampling, archive saving, decoding, AV saving and preview phases. Saved jobs remain active during preview preparation, preventing another generation from racing postprocessing. Preview failures retain the sampled take and an actionable message; rebuilds update phases without resampling. Restart recovery terminates orphaned preparation states.

Validation: 42 backend checks cover namespace/subject semantics, legacy migration review, frozen-data preservation, project geometry, continuation rejection, prompt-scoped progress and postprocessing guards, in addition to existing configuration/state/preview tests. Browser checks cover the corresponding controls and existing app behavior with simulated APIs and real seekable fixture media. Production build passes. No model/GPU generation result is claimed.

The authorized project migration preserves all existing take/job snapshots, selected outputs, source IDs/hashes, asset paths and files. It rewrites only editable working prompt fields and reference role metadata, records project resolution, and creates an exact original-manifest backup under the project's backups directory. Its detailed report is stored beside that backup.


## 2026-10-17 Fix configuration rejection after ComfyUI input validation

The runtime guard compared whole descriptors including raw JSON fingerprints. ComfyUI execution.py casts FLOAT inputs in place, so browser numbers such as shifts 12/3, denoise 1 and PDD strengths 1 became 12.0/3.0/1.0. Python graph equality accepted those values, but JSON fingerprints differed, causing both stock and PDD paths to fail before sampling.

The guard now validates the saved fingerprint against its saved graph, then compares executed settings structurally with exact numeric equivalence. It ignores only the current representation-dependent fingerprint during that comparison. Booleans remain distinct from numbers; strings, keys, connections, names, modes and non-equal floats still fail. Mismatch errors identify the differing field path. No frozen snapshot or saved project was rewritten.

Validation: 44 backend checks pass, including A/B/A switching with ComfyUI-style FLOAT casts, immutable snapshots, genuine numeric changes, boolean/type differences and fingerprint corruption. Three saved failed job snapshots from the authorized test project reproduced the previous hash mismatch and passed the corrected guard with the validation casts applied. GPU generation was not run.


## 2026-10-17 Prompt-only project duplication

Added a project-manager action and POST `projects/{project}/duplicate`. A new project copies scene/segment draft prompts and settings, remaps all owner/reference/override IDs, and copies only referenced source assets with hash verification. It publishes its manifest after assets are ready and cleans its own partial files on failure. It never copies takes, jobs, archives, AV previews, preview caches, transactions or frozen configuration graphs. The original remains unchanged.

Copied segment placeholders are planned prompts. The generation-tail guard permits only empty planned placeholders after the current segment; generated downstream footage still blocks historical generation. The backend rejects future copied segments before predecessors are finalized. Planned state is consumed at queue time. The UI opens the first unfinished copied segment, rebinds continuation to the newly finalized preceding take, and advances to the next copied prompt after finalization. Future prompts may be edited while generation remains blocked.

Validation includes independent asset copies and remapped scopes/overrides, original manifest preservation, no generated artifacts, selected-take prompt fallback, failed-copy cleanup and complete sequential generation/publication using new take IDs. Browser coverage duplicates a two-segment project, checks its prompts and empty take/job lists, blocks out-of-order generation and verifies the second generation uses the first new take rather than the original source. GPU sampling is simulated in these checks.
