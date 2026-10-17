# LongCaster Timeline TODO

## Typed reference namespaces

Status: **Implemented for image references; video/audio conditioning gates remain below**. Updated 2026-10-17. Qualified asset citations and authored subject labels are separate. Legacy bare names remain supported when unambiguous.

Use media-type namespaces in authored prompts:

| Asset type | Example token |
|---|---|
| Image | `<picture.main>` |
| Video | `<video.main>` |
| Audio | `<audio.main>` |

The reference's editable base name remains `main`; the asset type supplies the namespace. A picture and a video can both be called `main`, distinguished by their full tokens. Project/scene/segment are inheritance scopes and remain separate from these media namespaces.

### Required behavior

- [x] Parse a token into its media namespace and editable base name; use consistent case-insensitive lookup while preserving display spelling. Define canonical prefixes as `picture`, `video` and `audio`.
- [x] Enforce uniqueness of `(media namespace, base name)` within the effective inherited reference set. Preserve project -> scene -> segment add/override/exclude behavior. Overrides must retain the inherited media kind; reject mismatched kinds.
- [x] Display the complete token when defining/renaming references and in reference lists, autocomplete, the retention editor, prompt-import previews and compiled mapping previews. Suggestions show thumbnail, media type and scope.
- [x] Resolve available image sources through immutable reference IDs and one ordered manifest. Reserve independent picture/video/audio numbering; unsupported conditioning fails before generation.
- [ ] Activate video/audio payloads and paired-video soundtrack numbering when their actual upload/conditioning paths are implemented. No synthetic soundtrack labels are emitted today.
- [x] Keep media namespace separate from subject semantics. `<picture.main>` always resolves to its source `<Picture N>`; authors explicitly define `<Subject N>` using that source. The old role-driven qualified-token proposal is superseded. A namespace does not imply a keyframe or composition anchor.
- [x] Apply identical resolution in every applicable prompt field, manually pasted prompts and retention-editor output. Reject unknown, disabled, malformed and wrong-kind tokens before generation.
- [x] Preserve valid native numbered H3 labels and control/dialogue tags. `<Picture main>` is not the proposed syntax.
- [x] Support safe reference renaming with a reviewed replacement preview for matching qualified tokens in working drafts. Keep asset display names separate from token names and immutable IDs.

### Compatibility and migration

- [x] During transition, support legacy `<main>` only when its name resolves unambiguously across media kinds. If multiple kinds share it, require a qualified token and identify the alternatives; do not silently choose one.
- [x] Migrate structured working references by ID. Offer a reviewed conversion of freeform legacy tokens in editable project/scene/segment prompt fields.
- [x] Leave existing generated takes, frozen prompts, compiled mappings, reference manifests, hashes and latent/source provenance unchanged. Replaying an old take uses its frozen representation.
- [x] Wire typed video/audio tokens only when their actual upload/conditioning paths exist. Reject unavailable paths clearly; introducing namespaces does not itself implement video/audio references.

### Acceptance checks

- [x] Image/video/audio assets can share a base name in namespace validation, with separate labels and ambiguous bare-name rejection.
- [ ] Demonstrate native mixed-media conditioning with an image `main` and video `main`; video/audio uploads and conditioning remain unavailable in this slice.
- [x] An authored `<Subject N>` definition can cite `<picture.main>` without defining that picture as a keyframe. Qualified tokens never implicitly become subject labels.
- [x] Scoped overrides/exclusions, case handling, rename previews and ambiguous legacy-token errors behave consistently.
- [x] Prompt paste and retention entries compile through the same resolver and preserve authored shots, dialogue and timing.
- [x] Old saved takes remain byte-for-byte unchanged and usable for latent continuation.

## Project resolution and resolution selector

Status: **Implemented**. Updated 2026-10-17.

- [x] Set and persist generation resolution at the project level. Scenes and segments use the project's resolution rather than independent per-segment width/height settings.
- [x] Add a project resolution selector with common aspect-ratio/resolution presets and custom width/height. Display the resulting pixel dimensions and validate them against the active H3 profile.
- [x] Show the effective project resolution in generation settings and freeze the actual dimensions in each generated take.
- [x] Define migration for existing projects and behavior when the project resolution changes after takes exist. Preserve saved artifacts and reject incompatible direct-latent continuation explicitly; do not silently resize source latents or change continuation methods.

## Separate reference assets from subject definitions

Status: **Implemented for authored subject definitions and available image assets**. Updated 2026-10-17. Cross-media conditioning examples remain gated below. Native `<Subject N>` labels are authored semantic identities; source bindings use immutable reference asset IDs.

- [x] Keep a reference-asset registry for named sources such as `<picture.main>`, `<video.main>` and `<audio.voice>`, separate from subject definitions and their immutable IDs.
- [x] Let a subject definition such as `<Subject 1>` cite any applicable source assets and explain what each contributes. For example: `<Subject 1> is the person whose appearance comes from <picture.main> and whose movement comes from <video.main>.`
- [x] Support multiple assets contributing to one subject and multiple subjects drawn from one asset. Do not enforce one asset = one subject, or restrict subjects to image sources.
- [x] Allow explicitly authored subjects without a reference asset. Subject definitions can describe people, objects, environments, clothing or other reusable visible content; avoid a character-only schema.
- [x] Treat reference-asset namespaces as source identifiers. Preserve asset citations as the matching native `<Picture N>`, `<Video N>` or `<Audio N>` labels; resolve subject mentions independently to `<Subject N>`. Do not infer a subject or replace an asset token with a Subject label merely because an asset is marked as a character reference.
- [x] Provide separate asset management and subject-definition editing, with convenient source selection and autocomplete. Keep the subject description and each source's contribution editable rather than forcing a fixed relationship template.
- [x] Compile subject numbering, asset numbering and conditioning order from explicit definitions and source bindings. Validate missing/disabled sources and unresolved subject references without imposing a single-source or single-media restriction.
- [x] Update retention editing and rename/migration handling to distinguish subject references from source-asset references. Preserve existing frozen take prompts, reference manifests and provenance.

Acceptance examples:

- [ ] Native mixed-media example: one subject uses an image for appearance and a video for motion. Gated on the media paths above; the authored schema does not impose a single-source restriction.
- [x] Two subjects use different people from the same picture.
- [x] One subject uses multiple pictures for complementary appearance details.
- [x] A new authored subject has no source asset, while other subjects in the same prompt use references.

This supersedes any earlier TODO wording that would always resolve `<picture.main>` directly to `<Subject N>`. An asset citation and a subject mention must remain independently expressible.

## Show generation progress in the UI

Status: **Implemented**. Updated 2026-10-17. Sampling uses real step events; phases and history are persisted independently of frozen take snapshots.

- [x] Show the active stage: queued, loading models, preparing references/continuation, encoding prompt/references, sampling, decoding, saving artifacts, building preview, and completed/failed/cancelled.
- [x] Display real sampling step progress and elapsed time when available. Distinguish stages with measurable progress from stages that need an indeterminate indicator; do not invent percentages or ETA values.
- [x] Associate progress with the correct project, scene, segment, take attempt and ComfyUI prompt/job. Unrelated executions must not update this generation's progress.
- [x] Keep status visible in the generation workspace and pending timeline segment while the user browses source footage. Preserve the source preview and editable-state boundaries.
- [x] Show when sampling has finished but decoding, saving or preview preparation is still running. Distinguish a saved take with a failed preview from a failed generation, and expose the relevant recovery action.
- [x] Present actionable failure/cancellation details and retain useful status after reconnecting or reopening the project. Keep detailed technical logs available in an expandable view.

Exact placement and presentation remain open to UI implementation and user feedback.


## Duration beside Extend scene

Status: **Implemented**. Updated 2026-10-17.

- [x] Add a duration control directly beside the **Extend scene** button, with a displayed range of **0-15 seconds**.
- [x] Use the chosen duration for the new segment created by Extend scene and keep it synchronized with the generation settings duration.
- [x] Treat this as requested new-footage duration; show the actual duration after H3 frame-grid rounding. Zero disables Extend and Generate. No segment or minimum-length clip is generated. Values 1-15 seconds remain subject to the native sampled-window/context limit.


## 2026-10-17 implementation evidence

- Namespaced image sources, explicit subject definitions, legacy conversion review, project resolution presets/custom dimensions, persisted generation phases and extension duration are implemented.
- Video/audio namespace validation is available; upload/conditioning and mixed-media/soundtrack acceptance checks are explicitly still gated, consistent with the original instruction not to pretend an unavailable path exists.
- Backend regression suite: 42 checks, including a real FFmpeg preview assembly check. Browser coverage includes the new controls and existing configuration/preview behavior. GPU generation and model-produced seam quality still require native testing.
- The explicitly authorized saved test project is migrated separately with a manifest backup; no take snapshots, job snapshots, latent references, media files or selected outputs are rewritten.


## Audio-only regeneration and refinement

Status: **Pending**. Added 2026-10-18. Planning only; no generation action is implemented yet.

- [ ] Add **Regenerate audio** and **Refine audio** actions for a selected generated take. Reuse its saved original joint video/audio latent instead of re-encoding the preview.
- [ ] Freeze the complete video stream with the native H3 per-stream nested noise mask. Regeneration re-noises audio for a fresh soundtrack; refinement exposes partial audio denoise to try to reduce artifacts while retaining content.
- [ ] For continuation takes, preserve their original context overlap and audio alignment; modify only the segment's delivered audio. Keep the source take, original latent and existing finalized selection unchanged until the user accepts the new result.
- [ ] Save the result as a derived take with explicit source provenance, authored sound/dialogue instructions, seed, denoise strength, selected configuration, timings and the resulting joint latent. Reuse the original encoded video when muxing the new audio, avoiding unnecessary video re-encoding.
- [ ] Verify that the output video latent is identical to the selected source, the protected audio overlap is unchanged, delivered frame/sample counts match, and scene preview can audition the audio variant across adjacent segments before finalizing.
- [ ] Expose that frozen mouth movements cannot adapt to changed dialogue, so replacing speech may affect lip-sync. Do not promise audio-only sampling is inexpensive: H3 still processes frozen video context in the baseline path.
- [ ] Evaluate [ComfyUI-H3-AudioRefine](https://github.com/Adudeguyman/ComfyUI-H3-AudioRefine) as an implementation reference or optional integration. Start by validating the native masked baseline; assess its optional approximate frozen-video cache separately for quality, compatibility, compute and memory tradeoffs.

Native masking reference: [ComfyUI MiniMax H3 documentation](https://github.com/Comfy-Org/docs/blob/main/tutorials/video/minimax/minimax-h3-native.mdx). Acceptance requires real GPU tests with LongCaster's supported model/configuration paths, especially accelerated first-pass takes and continuation seams.
