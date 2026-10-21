# Continuation acceptance and seam frame correction

Implementation: 2026-10-18. Native H3 quality acceptance remains open.

## Implemented

Generation settings > **Seam frame correction** selects Off (default), or an
experimental 1-8 frame decoded ownership adjustment. Four frames is a candidate
for testing, not a validated universal offset. Independent starts have no join
and always resolve to Off. Settings freeze in each job/take snapshot.

Given source delivery length L, context C and adjustment d, assembled video is
source delivery `[0,L-d)` + child original decode `[C-d,C)` + child delivery
`[C,N)`. It still contains `L + N - C` frames. Audio uses the original source and
child deliveries, with unchanged boundaries. No interpolation, color repair,
reference injection, latent edits, fractional masks or prompt timing shifts.
Hard AV continuation masks remain the sampling baseline for every policy.

The planner requires the preceding reviewed take to match the frozen source
take and archive hash, matching geometry, sufficient source delivery/context,
and an available full child decode. A different auditioned parent makes the
correction inapplicable; its context is never substituted into an unrelated take.
Logical clip ranges stay fixed. Original and corrected ownership intervals are
saved in the assembled preview manifest. Raw and scaled export use this same
assembly plan; original artifacts are unchanged.

Scene preview's **Seam frame correction** checkbox auditions the saved correction
versus baseline without resampling. This is a review-only override: export uses
the correction stored in each take. Older takes remain Off. Rebuilding an old
preview can collect decoded measurements, but cannot create missing historical
sampling evidence.

## Recorded evidence

Before sampling, source archive hash/resource/contract, hard masks and exact
source-tail insertion are checked. Independent detached context copies then
allow verification after sampling, including detection of in-place corruption.
Video and audio report exact equality separately from a finite FP32 comparison
with `rtol = atol = 8 * float32 epsilon`. The tolerance accounts for native H3's
audio scale/unscale round trip, rather than mislabelling numerical round-off as
mask failure. Out-of-tolerance or non-finite protected context blocks finalization, while the
sampled take and preview remain available for diagnosis. Job diagnostics remain in `diagnostics/<job>/continuation.json`. No protected tensors
are silently repaired to make the check pass.

Successful receipts save this check, source provenance, sampling wall time and
CUDA allocation/reservation counters. CUDA peak is explicitly a **process lifetime
peak**, not an isolated per-take maximum. Synchronization brackets the sampler
timer. This timer excludes encoding, decoding and saving; persisted job stage
timestamps remain available for total elapsed time.

Each successful preview also writes
`takes/<take>/continuation_evidence.json`. Decoded seam measurements include:

- Preserved source/context pixel difference and mean RGB change.
- Original join, child internal boundary and corrected ownership join differences.
- Source motion near its end, audio boundary sample jump and PCM trim position.

Pixel measurements compare the encoded source original with the uncompressed
child decode, so codec error contributes. The corrected join is at an earlier
time; a smaller number alone does not establish an improvement. Audio sample
jump alone is not a click detector. Missing/incompatible source media marks
measurements unavailable without discarding a successful generation. These
metrics cannot certify identity retention, composition or perceived continuity.

Current segment > Frozen settings exposes seam measurements and the execution
receipt. A read-only aggregate report can be printed from the extension root:

```powershell
python -m timeline_core.acceptance "ABSOLUTE_PRODUCTION_DIRECTORY"
```

It lists all takes, source hashes, runtime checks, settings and metrics. Finalized
scene frame ranges and planned 48-kHz PCM ranges use integer arithmetic. Planned
ranges are not a measurement of actual native audio drift. Legacy missing
evidence remains unknown rather than being counted as passed.

## Required native acceptance session

1. Use a simple REF2VA subject/action test, fixed references, resolution, prompts,
   motion context and seeds. Begin with the Standard path; record model and VAE
   versions from receipts. Include both continuous motion and a deliberate cut.
2. Generate and finalize a start plus 5-10 extensions. Select an experimental
   boundary offset on extensions. Confirm source hashes and post-sampling checks
   in receipts after reopening the production.
3. Audition each seam with correction on/off from the same saved take. Review
   normal speed and frame stepping, including the earlier ownership boundary.
   Record pose/camera/character drift, brightness/color changes, audio clicks and
   lip sync separately. A decoder boundary adjustment may help edge artifacts;
   it does not prevent cumulative appearance drift inside new footage.
4. Repeat with 39/90/141 frame contexts within the native 15-second sampled limit,
   then HyperFlow and PDD paths. Do not transfer one path's quality finding to
   another. Compare generation time and memory with their recorded scope.
5. Export the chain and check delivered frame counts, duration and PCM boundaries
   at every join and at the end. Retain the aggregate report and human review
   notes. Only measured native results can justify changing the default.

Automated coverage exercises real FFmpeg assembly/export, frame ownership, exact
decoded audio comparison, source immutability, decoded diagnostic math, policy
freezing and browser interaction. CPU PyTorch invariant tests are included and
skip when PyTorch is unavailable. Neither fixture media nor CPU tensor tests
constitutes GPU H3 sampling/quality acceptance.

## Source review

The implementation follows architecture section 20's decoded ownership policy,
not the legacy LongCaster schedule-matched taper treatment. Current upstream
[ComfyUI H3 model](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/model_base.py)
scales/unscales packed audio around sampling. Its
[sampler](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/samplers.py)
merges protected latent regions through the inpaint mask. These source checks
explain the numerical comparison policy; installed runtime behavior must still
be verified with the actual connected MODEL and SAMPLER.


## Verification for this change

- Backend/media: 78 tests run, 77 passed, 1 skipped because PyTorch is absent.
  Includes real FFmpeg video ownership, exact decoded baseline/corrected audio
  comparison, export consistency and seam measurement fixtures using NumPy.
- Browser: full 46-test suite passed; after adding preservation/finalization
  behavior, 3 targeted generation/boundary/failure-preview checks passed.
- TypeScript and production Vite build passed.
- No native H3 GPU generation or repeated-chain quality acceptance was run in
  this development environment. The correction remains experimental and Off.
