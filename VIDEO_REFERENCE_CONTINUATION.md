# Video-reference continuation (VPipe-style)

Implemented and tested 2026-10-19. Experimental: two unique-seed native REF2VA/PDD
continuations failed visual continuity. Neither was finalized. The short
22-frame motion method remains preferable in this test; broader acceptance is open.

## Use

Restart ComfyUI and reload the Timeline UI to load the new backend and bundle.
Extend a finalized segment, then choose **Generation settings → Continuation
method → Video reference - VPipe-style continuation (experimental)**.

The first version requires native REF2VA video/audio reference inputs, at least
90 delivered source frames (3.75s), and at least 90 target frames. Use a new-
footage request of 3.75 seconds or longer. Existing image references, their
numbering, match/max sizing, and per-image latent strength remain available.
There is no workflow change or VPipe installation requirement.

The compiler preserves authored fields and adds visible, read-only instructions:

- Define `<Video 1>` as the preceding segment's final 3.75 seconds and the
  continuation starting point; define `<Audio 1>` as its synchronized soundtrack.
- Merge `video continuation + audio reference` into the summary task prefix,
  retaining existing task types and summary text.
- Add a video `fully_preserved` continuation relationship and an audio
  `reference` relationship in retention_analysis.
- Add instructions within Shot 1 to continue action/camera motion from the
  video's end, without replaying the reference, and follow the soundtrack's
  texture without copying its signal.

No Subject definitions or subject-to-asset links are inferred. Existing image
references still support manually authored Subject definitions. Authored
timestamps remain local to the new segment and are not shifted. Inspect H3 to
see the complete compiled model prompt; editor and queue share the compiler.

## Conditioning and provenance

The queued snapshot freezes the finalized source take, archive SHA256/resource,
delivery bounds and exact reference range `[delivery.end - 90, delivery.end)`.
Execution verifies the source and decodes its selected original/refined archive,
never the preview MP4. It extracts 90 float32 RGB frames and the same interval
from the decoded audio using frame-to-sample rounding. No lossy intermediate,
manual color adjustment or external video reader is involved.

Native `MiniMaxH3ReferenceToVideo.execute` receives ordinary image references,
`ref_videos={'ref_video_1': frames}` and index-paired
`ref_video_audios={'ref_video_audio_1': sound}`. Native H3 prepares the reference
presentation and VAE blocks. Its normal video-reference resizing/sampling still
applies; this is not claimed to be a bit-identical port of VPipe's Metal runtime.
Image latent softening modifies only the image blocks and preserves AV blocks.

The target latent is fresh. Reference video/audio are separate conditioning,
not a masked prefix in the generated target. Target context is zero; delivery
starts at frame zero with no overlap trim, replayed source or hidden timing skip.
The soundtrack is newly generated from an audio reference, not copied or frozen.
PDD warmup/handoff remains an independent setting, and the received sampler and
sigmas/configuration path still supply sampling. No switch-name detection was
introduced. Standard/accelerated execution is intended, not yet GPU validated.

Diagnostic `diagnostics/JOB/video-continuation.json` records source hashes,
resource/contract, video bounds, audio sample bounds/rate, decoded video/audio
float32 hashes, conditioning strategy and automatic prompt additions. The take
receipt records the same source and reference bindings. Missing/corrupt source,
wrong resource, invalid decoded dimensions/counts/audio, changed binding,
cancellation or unsupported native API fails explicitly.

## Limits and acceptance

Refinement, Drift Control/Color Stable, seam-frame correction and the 22-frame
image motion option are excluded from this initial separate experiment. Ordinary
uploaded video/audio reference management is still gated; only this generated
source-tail AV reference path is enabled. Regeneration retains the original
parent and continuation method, avoiding accidental self-continuation.

VPipe's demonstration deliberately puts seams in stationary holds. Its results
do not establish uninterrupted pull-up velocity or compatibility with PDD.
No seamlessness, identity-drift prevention, audio continuity or runtime claim is
made before native testing.

Original bounded test plan (subsequently run after explicit authorization): reuse the same finalized root and planned
prompts as the last-frame/motion comparison; keep PDD handoff enabled; generate
two continuations with 20s idle rest and review each before extending. Compare
framing, pose/velocity, body appearance, audio and sampling time. Existing
controls should be reused without regeneration.

Validation: 138 backend tests (135 passed, 3 skipped), TypeScript/Vite build,
and three mocked browser checks passed. These do not load models or sample.

## Sources

- VPipe approach: https://github.com/tgo-app-dev/vpipe/blob/main/docs/MINIMAX-H3.md#how-a-part-takes-its-guide
- VPipe held-seam example: https://github.com/tgo-app-dev/vpipe/blob/main/docs/MINIMAX-H3.md#writing-the-prompts
- Native REF2VA implementation: https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py
- Official prompt format: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md


## Native test outcome

Two independent continuations from the same original source were reviewed.
The first widened framing strongly; the different seed was closer in framing but jumped in action phase. No rejected take was used as a chain source.
PDD handoff remained 8 base + 2 PDD calls. No additional tests are queued.
Evidence: automated production 54cba551-3684-433d-800b-ac99a73b202a;
local `.test-tmp/vpipe-native-test/REPORT.md` in the authorized legacy workspace.
