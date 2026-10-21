# Last-frame continuation

Implemented as an explicit experimental alternative to latent continuation.
REF2VA follows the official Picture-reference prompting approach. Native GPU
testing has now exercised native REF2VA/PDD: image-only failed three joins; adding
a 22-frame video prefix improved two joins substantially, with residual discontinuity.
Audio and long-chain identity acceptance remain open.

## Use

1. Generate and finalize a source take, then extend the scene.
2. In Generation settings choose Continuation method -> Last frame - image restart.
3. Keep the REF2VA configuration and your existing named references enabled.
4. Write the next action normally. No manual first-frame/continuation wording is
   required. The prompt editor shows a notice identifying the actual Picture N
   and a read-only block containing the automatic additions for the selected
   field. H3 displays the complete final model prompt.
5. Generate, then review the draft together with the previous segment before
   finalizing. This is learned reference conditioning, not a pixel-exact boundary.

For a source shorter than 39 frames, select Last frame before Extend scene.
Restart ComfyUI and reload Timeline to load backend capability image_continuation=4.
No workflows are modified. A selected generation configuration must match the
segment profile. FL2VA remains supported through its native first_frame input;
it does not consume REF2VA named references or Picture prompting.

## Automatic REF2VA prompt additions

The summary task prefix automatically includes keyframe completion alongside any
existing authored task types, and identifies the first-frame Picture. Authored
summary text remains intact.

The compiler reserves the next unused Picture number after the enabled authored
image references and appends the decoded source frame to the same native input
order. Existing aliases/numbered labels stay unchanged. The added frame counts
against H3's nine-image limit, leaving room for eight authored image references.

Using Picture 3 as an example:

subject_definitions:
<Picture 3> is the final frame of the preceding segment and the first frame of [Shot 1].

retention_analysis:
<Picture 3> ([Shot 1] first frame): fully_preserved - Preserve the depicted composition, subject appearance, pose, environment and lighting at the opening frame.

detailed_description (inserted inside the existing Shot 1):
[Shot 1] The video continues from <Picture 3> as its first frame. Start from the depicted pose and composition, then continue the following action naturally. ...authored action...

If there are no shot markers, a Shot 1 marker is added. Ambiguous/missing Shot 1
in a numbered multi-shot prompt is rejected. Existing timestamps, later shots,
subject definitions and authored text are retained. No subject-to-reference
relationships are inferred or added automatically.

Editor preview and queued generation use the same compiler. The automatic lines
are separate from authored_fields and never written back into the working draft;
retries/extensions therefore cannot accumulate them. The final resolved fields,
full model prompt, additions and generated-picture binding are frozen in the
snapshot. Regeneration uses the original parent, not the segment's own last frame.

## Image and archive provenance

The source must be the explicitly finalized preceding take. The job freezes its
ID, archive SHA256/resource ID, dimensions and delivery bounds. The executor
verifies and decodes that archive, selects delivery.end - 1, and supplies that
float32 image directly to the native REF2VA ref_images input. A lossy preview,
thumbnail, other draft or newly selected take cannot silently replace it.

The generated picture's pending asset SHA is null in the queued snapshot because
its pixels do not exist until VAE decoding. It is bound instead to the immutable
source archive SHA and exact frame index. The actual PNG and float32 input hashes
are recorded after extraction; neither is falsely claimed to equal the archive
hash. The saved PNG is a rounded inspection copy, not reloaded for conditioning.

Per-job diagnostics:
- diagnostics/JOB/source-last-frame.png
- diagnostics/JOB/image-continuation.json

REF2VA uses its ordinary text-encoder image presentation and VAE reference block.
With motion context off there is no hard target-latent pin, inherited video prefix or copied audio history.
The target is a fresh joint AV latent, delivered from frame zero, with no overlap,
hidden prompt timing offset or HyperFlow skip. The generated opening frame may
reinterpret the image. Audio starts fresh and may have an audible seam.

Existing reference strengths/sizing remain effective. The generated continuation
picture uses normal image conditioning at full strength. A virtual per-job
reference does not become a cumulative project/scene reference asset.

## Controls, tests and pending validation

Latent continuation remains the default. Last-frame selection resets refinement,
continuation protection and seam correction to off; the backend rejects attempts
to stack those overlap-dependent features in this first implementation. PDD warmup
remains a separate opt-in. FL2VA/PDD, native REF2VA/PDD and other acceleration
paths need native visual/audio acceptance. An optional 22-frame (0.917 s) video-only motion prefix is now available for
REF2VA last-frame continuation. It copies seven phase-aligned native video tokens
from the frozen source, protects them through sampling and trims the prefix from
delivery. Audio is generated fresh; no old audio tokens are copied. This avoids
pretending that 22 frames is an exact joint AV handover boundary. PDD handoff
restores the masked source prefix between phases and the final output is checked
against the frozen prefix. VPipe-style video-reference continuation is now a separate experimental option; see VIDEO_REFERENCE_CONTINUATION.md. Native testing is pending. Existing drift in the final source
image is inherited, not repaired automatically.

Backend regression tests cover prompt numbering, the three automatic entries,
original timestamps/text, retries/regeneration, reference retention, native image
limits, source frame selection, corruption and cancellation. Targeted browser
checks cover latent extension, FL2VA image extension and REF2VA with enabled named
references, automatic editor instructions and complete compiled-prompt visibility.
TypeScript/Vite build passed. Backend regression: 129 tests, 126 passed and
3 skipped; three targeted browser checks passed. Native REF2VA/PDD testing
verified source/reference binding, protected video prefix and 8-base/2-PDD handoff.
Image-only join MAE was 19.64% in the corrected-prompt trial; motion-assisted
joins were 1.55% and 1.32%. These are descriptive RGB differences, not a
seamlessness or identity score. Residual pose/texture changes and a brief opening
slowdown remain; other configurations and audio continuity need acceptance.

Official prompting reference:
https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
