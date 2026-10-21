"""The `hop_tail` slice, without importing ComfyUI.

One function, kept out of `nodes.py` for the same reason `latents.py` is: the
arithmetic is the part that can be wrong, and a module with no ComfyUI import
can be asserted against by `tools/check_blend.py` with no server, no model and
no GPU. Nothing else in this pack knows how a schedule is cut.
"""
from __future__ import annotations


def tail(base_sigmas, steps):
    """The base schedule's own last `steps` sigmas. -> (sigmas, k, n_base).

    `base_sigmas` is a BasicScheduler SIGMAS tensor of length n+1 for an n-step
    schedule, descending and ending at 0.

    `k` is the honoured step count, which is not always `steps`: at least one
    of the base's own steps always stays untouched. Without that clamp
    `steps >= n_base` would slice from sigma 1.0 and the "refine" would
    silently become a full re-render -- which costs a full render, ships
    something that continues nothing, and looks in the log exactly like a
    refine that worked.
    """
    n_base = int(base_sigmas.shape[-1]) - 1
    if n_base < 2:
        raise ValueError(
            f"base_sigmas holds {n_base} step(s); hop_tail always leaves one "
            "of the base's steps untouched, so it needs at least 2")
    k = max(1, min(int(steps), n_base - 1))
    return base_sigmas[n_base - k:], k, n_base
