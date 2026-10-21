# Handoff plus refinement experiment

This round keeps runtime PDD warmup/handoff (eight base steps, two PDD finish
steps) in every treatment. Native pure PDD and handoff-only controls are reused.
Five isolated arms run four matched continuations each, with at least 20 seconds
of continuous queue-idle rest before every generation, including arm changes.
Anti-Burn, Drift Control, Color Stable and seam correction stay off.

| Arm | Refine model | Recipe |
| --- | --- | --- |
| H3 Refine PDD | Received PDD model | Two Euler steps from the original PDD tail |
| H3 Refine base | Recovered unaccelerated base | Same two-step tail |
| noEmbryo statistics | No extra sampling | First-take per-channel and high-band statistics, strength 1 |
| noEmbryo detail | Recovered base | Three Euler steps, normal schedule, denoise 0.4; statistics plus high-band donor |
| Character masked | Recovered base | Three Euler steps at 0.4, per-token semantic person mask |

The recovered refinement base is a separate clone with the warmup tracing hook
removed; its extra calls cannot inflate eight-base/two-PDD handoff evidence.
Refine sampling has independent sigma/call tracing. Original output is saved as
original.mmh3; refined.mmh3 is previewed and inherited by the next continuation.
Audio and the entire source prefix are verified before blending. The adapter
blends raw to corrected video from frame 39 to 61; the archived predecessor is
never edited. No extra prompt/reference image is injected.

noEmbryo implementation: MIT-licensed arithmetic from
https://github.com/noembryo/ComfyUI-noEmbryo at
4289beac758c836138d3eab560cefaa5dc0f6057. Extracted statistics/band helpers and
refine function; upstream's internal unmasked sampler/fallback is replaced by
an explicitly sampled, audio/head-masked donor. Current upstream changes both
head and tail; Timeline restores the protected head and ramps into the corrected
body/tail for its own continuation contract. This is an adapted implementation,
not a claim to reproduce upstream's whole Motion Context workflow.

H3 Refine: pinned dntpi helpers already vendored. The character mask follows
xyzDist/H3-LongTakeNoCuts' masked-refine/blend approach, with frame mapping from
dntpi's corrected helpers. Semantic person segmentation uses official Torchvision
LRASPP MobileNet V3 weights (SHA256
d234d4eae9d55d5f76de18b77cf0dc62c66fe5c5482758209d00f950c92bb280).
Inference runs on CPU at one decoded frame per H3 token. Mask support is dilated
one latent cell and feathered inside support. Audio/head are zero-masked;
background outside support must remain unchanged. Masks and cyan overlays are
saved with each take's diagnostics. No silent rectangle/whole-frame fallback.
The small weights are installed explicitly under models/refine_person and are
ignored by git; generation never automatically downloads them.

Controls remain off by default. UI: Generation settings -> Refinement -> method
and model. Non-PDD generation uses its received base normally; runtime PDD base
recovery requires Auto warmup. Refine and continuation protection remain mutually
exclusive for this round. Execution success does not establish quality benefit.

Validation before GPU trials: 114 backend tests passed; TypeScript/Vite build
passed; inspected three root-shot segmentation overlays covering the person.

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
