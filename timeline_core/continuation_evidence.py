"""Continuation invariants and explicit, video-only decoded ownership.

No fractional masks, latent rewriting, image guides or prompt clock changes.
"""
from copy import deepcopy


def edge_policy(value, source, plan):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 8:
        raise ValueError("Decode-edge frames must be an integer from 0 to 8.")
    if not source:
        value = 0  # An independent start has no join to correct.
    elif value > min(plan["context_frames"], source["plan"]["new_frames"]):
        raise ValueError("Decode-edge correction exceeds available source delivery/context.")
    return {"version": 1, "policy": "child_context_video_v1" if value else "off",
            "frames": value, "experimental": bool(value), "audio": "unchanged_delivery",
            "sampled_latents": "unchanged", "quality_validation": "requires_native_ab_test"}


def capture_context(latent, receipt):
    video, audio = latent["samples"].unbind()
    # Independent copies catch in-place sampler corruption as well as new tensors.
    return (video[:, :, :receipt["video_context_steps"]].detach().clone(),
            audio[..., :receipt["audio_context_steps"]].detach().clone())


def check_context(sampled, expected, receipt):
    import torch
    streams = sampled["samples"].unbind()
    if len(streams) != 2:
        raise RuntimeError("Sampled continuation does not contain both AV streams.")
    actual = (streams[0][:, :, :receipt["video_context_steps"]],
              streams[1][..., :receipt["audio_context_steps"]])
    result = {"version": 1, "policy": "hard_av_v1", "streams": {},
        "rtol": 8 * torch.finfo(torch.float32).eps, "atol": 8 * torch.finfo(torch.float32).eps,
        "comparison": "Exact equality recorded separately; fp32 tolerance allows native audio scale round-trip."}
    for name, before, after in zip(("video", "audio"), expected, actual):
        compatible = tuple(before.shape) == tuple(after.shape)
        finite = compatible and bool(torch.isfinite(after).all().item())
        reference = before.to(device=after.device, dtype=after.dtype)
        exact = finite and bool(torch.equal(reference, after))
        preserved = finite and bool(torch.allclose(reference, after, rtol=result["rtol"], atol=result["atol"]))
        result["streams"][name] = {"shape": list(after.shape), "finite": finite, "exact": exact,
            "preserved_within_fp32_tolerance": preserved,
            "max_abs_error": float((reference - after).abs().max().item()) if finite and after.numel() else None,
            "protected_values":after.numel()}
    result["passed"] = all(stream["preserved_within_fp32_tolerance"] for stream in result["streams"].values())
    return result


def apply_ownership(store, data, entries):
    """Keep logical clip bounds, replacing only a parent's decoded video tail."""
    entries = deepcopy(entries)
    for index, child in enumerate(entries):
        take = data["takes"][child["take_id"]]
        policy = take.get("snapshot", {}).get("decode_edge", {"policy": "off", "frames": 0})
        d = policy.get("frames", 0)
        if not d:
            continue
        frozen_source = take.get("snapshot", {}).get("source") or {}
        parent = entries[index - 1] if index else None
        child["join_correction"] = {**policy, "status": "not_applicable", "reason": "Frozen source is not the preceding reviewed take."}
        if not parent or parent["scene_id"] != child["scene_id"] or parent["take_id"] != frozen_source.get("id"):
            continue
        c = take["plan"]["context_frames"]
        if (isinstance(d, bool) or not isinstance(d, int) or not 1 <= d <= min(8, c, parent["frames"])
                or parent["latent_sha256"] != frozen_source.get("latent_sha256")
                or (parent["width"], parent["height"]) != (child["width"], child["height"])):
            raise ValueError("Decode-edge ownership is incompatible with the frozen source.")
        preview = store.preview(child["take_id"]) or {}
        path = preview.get("raw_path")
        if not path or not store.asset(path).is_file():
            raise ValueError("Rebuild the child's original decoded video for decode-edge correction.")
        stat = store.asset(path).stat()
        parent["borrowed_video_tail"] = {"frames": d, "source_path": path,
            "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
            "start_frame": c - d, "end_frame": c, "take_id": child["take_id"]}
        child["join_correction"] = {**policy, "status": "applied", "source_take_id": parent["take_id"],
            "original_parent_delivery": [0, parent["frames"]],
            "corrected_parent_delivery": [0, parent["frames"] - d], "borrowed_child_context": [c - d, c],
            "child_delivery": [c, take["plan"]["sampled_frames"]]}
    return entries
