# LongCaster Timeline

An app interface for directing MiniMax H3 generations. This is the **first M1 slice**, with a generation timeline, three preview monitors across four workspace columns, REF2VA image references and saved-latent forward extension. The full M1 acceptance gates are not yet complete.

## Open and test

For standard REF2VA without PDD, load [longcaster_timeline_standard_ref2va.json](example_workflows/longcaster_timeline_standard_ref2va.json). It uses the stock REF2VA loader, Sigma Shift 12/3, an external BasicScheduler (simple, 20 steps, full denoise) and Euler sampler. Adjust the model filenames to your installation; author references and prompts in the app. Connections were structurally validated; GPU execution is still untested.

Load [longcaster_timeline_pdd_ref2va.json](example_workflows/longcaster_timeline_pdd_ref2va.json) for a prewired PDD + REF2VA setup based on the original LongCaster example. Select your installed loader/PDD filenames, then open the LongCaster app. References, prompts, resolution and previews are managed in the app. The sample preserves the original Sigma Shift 12/3, REF2VA 8-step PDD settings, strict partition checks and explicit attention backend, and adds an external Euler sampler. The JSON connections were structurally validated; this sample has not been GPU-tested.

1. Restart ComfyUI after installing this directory under `custom_nodes`.
2. Add **LongCaster Timeline — Execution** once. Connect your existing **MODEL**, **CLIP**, **video VAE**, **audio VAE**, **SAMPLER** and **SIGMAS** outputs. Select `ref2va` on that execution node and connect the matching REF2VA checkpoint. The externally supplied model patches, sampler and sigma schedule remain in use.
3. Click **LongCaster** at the bottom right of ComfyUI. Keep that ComfyUI tab open: it supplies the app's execution connection. The app opens in its own tab.
4. Create a production. **Scene 01 and its editable Segment 01 are created and selected automatically**. Creating another scene also gives it its own independent Segment 01. Open **Timeline > References**, choose Project, Scene or Segment, give an image a base name such as `hero`, and add the file.
5. Define subjects manually with `<Subject 1>`, `<Subject 2>`, etc. Only references have aliases: write `<Subject 1> is the person in <picture.hero>.` when that relationship is intended. The **H3** button shows the exact resolved model prompt. The compiler only expands media aliases and validates native labels; it never creates subjects or adds reference relationships.
6. **Generate first segment**, review its preview, then **Finalize selected take**. Click **Extend scene** to add Segment 02 to that scene, write the next action and generate again. Finalize the tail before adding another segment. The finalized take's saved original joint AV latent is the source. The left monitor stays available while reviewing the extension on the right.

Use **Replace tail segment** to generate another take in the same segment. Only the scene tail can be replaced or have its finalized take changed; earlier segments stay read-only. Replacing the independent first segment stays independent. Replacing a later tail reuses that segment's original parent latent, rather than continuing from its own ending. The existing take remains finalized until you review and finalize its replacement. Browsing older takes never changes an output or an already prepared continuation source.


## Timeline and prompt input

Drag the timeline ruler, clip lane or playhead to scrub the current scene. Scrubbing switches to the appropriate finalized segment and seeks its preview to the local frame. It waits for video metadata when switching files, rather than relying on a fixed delay. Left/Right while the scene timeline is focused step one frame. Draft generation inputs stay intact while scrubbing; a draft without generated video has no footage to show.

Use **Paste prompt** (the clipboard button beside the prompt-field selector) to import a full H3 prompt. It detects all six `section_name:` headings and previews the detected sections before applying them. Markdown headings and matching XML sections are also supported. Matching fields are replaced, omitted fields stay unchanged, and plain text goes into Detailed description. Pasting a sectioned document directly into either editable prompt textarea also distributes it into its fields. Shot text, named references, dialogue and authored timestamps are preserved. Duplicate headings or text outside section boundaries fail visibly instead of being discarded.

## Dependencies

- ComfyUI with native MiniMax H3 conditioning and joint video/audio masking. The reviewed baseline is v0.38.0; effective runtime capabilities are checked.
- [MMH3 Media](https://github.com/einhorn13/mmh3_media): use the latest compatible upstream version. The latest checked revision is **`86b96deb52ed3c753789b5bf846f58e0b0c2feba`**. LongCaster requires adapter API v1 / latent contract v2 and validates the function signatures it actually uses; it does not require an exact Git hash. Git revision, when available, is recorded in the execution receipt. Compatible ZIP installations are accepted with unknown Git revision. LongCaster does not auto-update this dependency or search sibling directories; update it explicitly and restart ComfyUI.
- FFmpeg with H.264/AAC encoding, available through PATH or `imageio-ffmpeg`. If needed, install [requirements.txt](requirements.txt) using the Python environment that runs ComfyUI. Pillow, NumPy and PyTorch are supplied by ComfyUI.

The built frontend is included. Node/npm is needed only when changing frontend sources:

```powershell
cd frontend
npm ci
npm run build
```

## Named generation configurations

Choose complete upstream MODEL/SAMPLER/SIGMAS setups from **Generation settings > Generation configuration** in the app. Connect named **Configuration** nodes through a **Configuration Switch** to Execution; keep CLIP and the VAEs shared. Five paths are supported, with the chosen setup frozen into each take. Existing direct-input setups remain available. See [CONFIGURATIONS.md](CONFIGURATIONS.md) for wiring and testing instructions.

## References and subject definitions

Define source images by an editable base name such as `main`; prompts cite them as `<picture.main>`. Project references inherit into scenes and segments; scene references inherit into their segments; segment overrides/exclusions remain local and keep the inherited media kind. Names are case-insensitive within a media namespace. Immutable IDs bind sources separately from their names.

Choose **Subject definitions** in the main prompt editor for reusable content. For example, `<Subject 1> is the person in <picture.main>. Preserve their facial identity and clothing.` Then refer to `<Subject 1>` in the shots and retention analysis. Qualified image citations compile to `<Picture N>`; they never implicitly turn into a subject or a keyframe. A subject can cite multiple images, several subjects can come from one image, and an authored subject can have no reference asset. Nothing is automatically injected for qualified source citations.

The compiler uses one ordered asset manifest for native numbering and conditioning. Only qualified media aliases such as `<picture.main>` resolve to native `<Picture 1>` labels. Subjects always use authored native `<Subject N>` labels. Legacy reference role metadata does not create subjects or links. Bare aliases and subject aliases are rejected and must be corrected manually. Existing generated takes retain their frozen prompts and artifacts.

The `video` and `audio` namespaces are reserved independently from `picture`, and ambiguity/wrong-kind validation is implemented. Actual video/audio uploads, conditioning and paired-video soundtrack labels are still unavailable and rejected before generation. Only image conditioning is active. Scoped LoRA controls and project/scene prompt inheritance remain later work; LoRAs already applied to external MODEL inputs stay active.

## Project resolution, duration and generation process

Use the project resolution button in the app header for presets or custom dimensions. All new scene/segment drafts use the project dimensions, and each take freezes the actual generated size. Existing projects derive a default from their saved media. Changing project dimensions does not resize saved latents; continuation from an incompatible source is rejected explicitly.

The **Duration** control beside **Extend scene** sets requested new-footage length and stays synchronized with generation settings. Zero disables generation/extension. Actual generated duration is shown on the take after native frame-grid rounding; context still counts toward the sampled-window limit.

**Generation process** distinguishes queueing, upstream model loading, preparation, encoding, sampling, decoding, saving and preview creation. Sampling uses real steps; other phases use an indeterminate indicator. Phase history, elapsed time and ComfyUI prompt/job identity remain visible after reconnecting. A take stays busy through preview preparation, and a saved take with a failed preview exposes rebuild recovery without resampling.

## Continuation and storage

The default motion context is 39 frames (1.625 seconds at 24 FPS), with 90 and 141 frames available when the source/window can supply them. New-footage duration is rounded to H3's `17k+5` sampled-frame grid; context is additional sampled duration. The first slice limits the total sampled window to 362 frames. The take inspector reports actual duration.

Both video and audio context use hard masks: **0 for copied source, 1 for new generation**. Source archives are verified by resource ID and SHA-256. There is no image fallback, source re-encoding, fractional drift mask, decoded seam correction, prompt timestamp compensation or HyperFlow skip. Authored prompt timestamps are sent unchanged; early-cut behavior still needs controlled model testing.

Projects are stored under ComfyUI's output directory at `LongCasterTimeline/<project-id>/`. Each take retains its complete original `.mmh3` latent archive, full decoded MP4, decoded WAV and a separate delivery preview with context trimmed. A preview failure keeps the sampled take and supports rebuilding the preview without resampling. Finalize is enabled once a preview is ready.

The workspace has four columns: a collapsible **Current segment** inspector containing its preview, frozen prompt and take information; a central **Scene preview**; a **Target segment** column containing the next/replacement preview and editable prompt; and a separate **Target segment settings** inspector for references, takes and generation controls. The timeline spans the full width underneath. The header's **Current segment** button collapses or restores the left inspector, and remembers that preference. The scene monitor stays available on smaller screens and plays only the selected scene.

**Include draft takes** is checked initially so you can review a new extension before finalizing it. Unfinalized segments use their latest playable take; the selected right-hand take can audition a tail replacement. Uncheck this option to review finalized outputs only. This never finalizes a take or changes the continuation source. Ungenerated drafts are skipped. A missing finalized preview must be rebuilt before scene playback.

The first review may show **Building scene preview** while FFmpeg assembles saved delivery previews. Subsequent playback reuses `project_previews/<content-key>/preview.mp4` and its manifest inside the project's artifact directory. Review media uses a common canvas with letterboxing where needed, 24 FPS and stereo 48 kHz audio. No model or VAE is loaded for assembly, and the existing overlap trim is not applied again. This is a derived review encode; original take archives and AV files remain intact.

**Validation:** Python state/compiler tests, production frontend build and Playwright browser checks passed. Browser tests use a simulated execution bridge and fixture media. Actual GPU generation, visual seam quality and repeated-extension audio drift have **not** been validated in this development environment. See [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) for evidence and the remaining acceptance gates.


## Duplicate a project without generations

Open the project selector in the app header. Enter a **Copy name** and click **Duplicate without generations**. The new project keeps scene/segment names and order, editable prompts, reference assets and scopes, project resolution, seeds, durations and the selected configuration ID. Reference files are copied and hash-verified, so the projects are independent. If an old segment has no working draft, its selected take's authored prompt/settings provide the fallback.

The copy starts with no takes, finalized outputs, jobs, latent archives, previews or old take-source links. Scene/segment/reference IDs and override owners are remapped. Copied segments appear as **PLANNED PROMPT** blocks: generate the first segment, review/finalize its take, and the next copied prompt opens automatically using that new take as its continuation source. Later prompts can be edited, but generation waits for their predecessor to be finalized. Each scene starts independently. Once the copied sequence is complete, ordinary Extend/Replace behavior resumes. The original project stays intact.

Prompt contract: only media assets receive aliases. Subject labels and every subject/source relationship are authored manually. The compiler does not generate definitions, renumber subjects, infer source bindings, or append retention/composition instructions. See the [official REF2VA prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md).

Playback synchronization: the timeline, segment monitors and scene preview share one review position. The player you use becomes the playback driver and pauses the others. Following monitors seek to the corresponding local frame; a monitor for another segment holds its first or last frame outside its range. Scene playback stays within the selected scene. Seeking waits for metadata and follower players cannot overwrite the active playhead. Position updates use an animation-frame clock rather than sparse media timeupdate events.

Project-preview scrubbing serializes decoder seeks and retains only the newest pending target. Routine seeks keep the image visible without an overlay. Review encoding v2 uses a maximum 12-frame keyframe interval (0.5 seconds at 24 FPS); its new cache key rebuilds old long-GOP review movies automatically. Original takes are not re-encoded.


## Home, Production and Timeline

The app opens on **Home**, a production library with New, Duplicate, Duplicate + Invalidate and Delete. Opening a production exposes the Production and Timeline routes. Duplicate copies saved generations and assets independently; Duplicate + Invalidate keeps editable prompts, reference assets and configuration but removes all takes, previews, latents, jobs and old take-source links in the new copy. Delete removes a production from the library and moves its directory into `.trash`; active generation prevents deletion or a complete copy.

**Production** edits the name, generation resolution and export resolution. Export stitches finalized outputs from all scenes. Raw export uses the review canvas; upscaled export uses explicitly labeled Lanczos resizing with aspect-preserving letterboxing, not an AI super-resolution model. Review/export artifacts are derived files; original takes remain unchanged.

**Timeline** retains the four-column arrangement. Its right inspector has Generate, References and LoRAs tabs; changing routes preserves the current draft. References have Project/Scene/Segment scopes and show inheritance explicitly. Editing an inherited source creates a narrower override. Alias renames remain reviewable and never create or link Subject definitions.

For images, Normal image preserves native REF2VA behavior. Latent strength mode scales only that image's diffusion reference latent, while the native text encoder still sees the original image. The retained percentage ranges from 0 to 100: 100 leaves encoded values unchanged; 35 multiplies them by 0.35; 0 sends a zero-scaled latent and does not disable the text-encoder image. Disable removes the reference completely. No random noise or blur is added. Controls are frozen into the take snapshot and recorded in its receipt; archived takes are never rewritten. Unsupported native reference payloads fail before sampling instead of guessing source order.

Model-only LoRAs can be selected per Project/Scene/Segment. A narrower definition overrides the same filename. They apply after the external generation configuration, with each actual file hash and strength recorded in the execution receipt. They do not modify the CLIP encoder or inject subject definitions. Audio/video reference conditioning is still unavailable; their sections say so.

Latent-reference investigation: [original Reddit discussion](https://www.reddit.com/r/StableDiffusion/comments/1whbdje/minimax_h3_latents_as_reference/), [reference node source](https://github.com/neph1/comfyui-minimaxh3-condition-latent/blob/main/nodes.py), and [native ComfyUI reference implementation](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py). Our implementation preserves the native text-encoder presentation and changes only the matching diffusion reference block. Strength is experimental and does not map linearly to visual similarity.
