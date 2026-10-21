Source: https://github.com/noembryo/ComfyUI-noEmbryo
Revision: 4289beac758c836138d3eab560cefaa5dc0f6057
License: MIT.
Extracted band helpers, frame mapping, AV pair and H3ClipRefiner.refine. The generative sampler block is replaced by an explicit externally sampled detail_donor argument; no silent fallback. All statistics, gain and high-band transfer arithmetic is retained. Timeline adapter protects original context/audio and applies its own 39-to-61-frame blend. No archive, stitch, purge or unrelated nodes are included.
