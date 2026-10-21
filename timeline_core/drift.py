"""Opt-in upstream context treatments on disposable 39-frame AV handovers.

No archived source is edited. Color carry deliberately changes the disposable
video prefix: preservation must be measured against that prepared prefix.
"""
from copy import deepcopy
import time
import weakref

UPSTREAM = "https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop"
REVISION = "43afeffcc570beb5f7382593e79e4b211c7e02f6"
MODES = ("off", "drift_control", "color_stable", "drift_color")
_STATS = {}


def freeze(mode, source, plan, anchor=None, refine=False):
    mode = "off" if mode is None else mode
    if mode not in MODES: raise ValueError("Choose a supported continuation protection mode.")
    applied = mode != "off" and bool(source)
    if applied and plan["context_frames"] != 39:
        raise ValueError("Drift Control and Color Stable currently require a 39-frame motion context.")
    if applied and refine:
        raise ValueError("Test continuation protection separately from H3 Refine; their sampling hooks cannot be stacked yet.")
    color = applied and mode in ("color_stable", "drift_color")
    if color and not anchor: raise ValueError("Color Stable requires the scene's finalized first take as its anchor.")
    return {"version": 1, "mode": mode, "applied": applied,
        "drift_control": applied and mode in ("drift_control", "drift_color"), "color_stable": color,
        "reason": "enabled" if applied else "independent_start" if mode != "off" else "disabled",
        "anchor": {key:deepcopy(anchor[key]) for key in ("id","latent_path","latent_sha256","width","height")} if color else None,
        "context_frames": 39, "audio": "unchanged_hard_context", "upstream": UPSTREAM,
        "upstream_revision": REVISION, "quality_validation": "experimental_requires_pdd_ab_review"}


def _stats(prefix, vae, archive_hash, width, height):
    from .vendor.context_loop.latent_color_carry import tensor_scene_color_stats
    key = (archive_hash, width, height, id(vae), type(vae).__module__, type(vae).__name__, REVISION)
    cached = _STATS.get(key)
    if cached and cached[0]() is vae: return deepcopy(cached[1]), True, None
    frames = vae.decode(prefix)
    if frames.ndim == 5: frames = frames.reshape(-1,*frames.shape[-3:])
    if frames.ndim != 4 or frames.shape[0] != 39:
        raise ValueError("Color Stable requires a video VAE decoding 12 H3 tokens into 39 frames.")
    stats = tensor_scene_color_stats(frames)
    if len(_STATS) >= 16: _STATS.pop(next(iter(_STATS)))
    try: _STATS[key] = (weakref.ref(vae),deepcopy(stats))
    except TypeError: pass  # Custom VAEs without weakref support are not cached.
    return stats, False, frames


def prepare(api, store, snapshot, latent, model, sigmas, vae, *, phase="single"):
    frozen = snapshot.get("continuation_protection") or {"mode":"off","applied":False}
    report = {**deepcopy(frozen), "preparation_seconds": 0, "mask_calls": 0, "sigma_trace": [],
        "color": {"applied":False,"reason":"disabled"}}
    if not frozen["applied"]: return latent, model, report
    import torch
    from .store import digest
    from .vendor.context_loop.contracts_v05 import DRIFT_CONTROL_AV_RECIPE, LATENT_COLOR_CARRY_RECIPE
    started = time.perf_counter()
    video, audio = latent["samples"].unbind()
    if video.ndim != 5 or audio.ndim != 4 or video.shape[2] <= 12:
        raise ValueError("Continuation protection requires a joint AV latent with a 12-token source prefix and new footage.")
    report["drift_recipe"] = deepcopy(DRIFT_CONTROL_AV_RECIPE) if frozen["drift_control"] else None
    report["color_recipe"] = deepcopy(LATENT_COLOR_CARRY_RECIPE) if frozen["color_stable"] else None
    output = latent
    if frozen["color_stable"]:
        anchor = frozen["anchor"]
        if anchor["latent_sha256"] == snapshot["source"]["latent_sha256"]:
            report["color"] = {"applied":False,"neutral":True,"reason":"first_continuation_from_anchor"}
        else:
            from .engine import primary
            from .vendor.context_loop.latent_color_carry import apply_delta_vae_color_carry
            path = store.asset(anchor["latent_path"])
            if not path.is_file() or digest(path) != anchor["latent_sha256"]:
                raise ValueError("Color Stable anchor archive is missing or changed.")
            if (anchor["width"],anchor["height"]) != (snapshot["width"],snapshot["height"]):
                raise ValueError("Color Stable anchor resolution differs from the continuation.")
            packet = api.load_archive(str(path),verify="full")
            reference, _, _ = primary(api,packet)
            anchor_video = reference["samples"].unbind()[0][:,:,-12:].detach().clone()
            prefix = video[:,:,:12].detach().clone()
            anchor_stats, anchor_hit, _ = _stats(anchor_video,vae,anchor["latent_sha256"],snapshot["width"],snapshot["height"])
            source_stats, source_hit, source_decoded = _stats(prefix,vae,snapshot["source"]["latent_sha256"],snapshot["width"],snapshot["height"])
            corrected, color = apply_delta_vae_color_carry(prefix,vae,anchor_stats,source_stats,decoded_current=source_decoded)
            if corrected.shape != prefix.shape or not torch.isfinite(corrected).all():
                raise RuntimeError("Color Stable returned an invalid video prefix.")
            treated = video.detach().clone();treated[:,:,:12] = corrected.to(treated)
            output = {**latent,"samples":type(latent["samples"])((treated,audio))}
            report.update(color={**color,"reason":"corrected" if color["applied"] else "neutral"},
                anchor_stats=anchor_stats,source_stats=source_stats,stats_cache={"anchor_hit":anchor_hit,"source_hit":source_hit})
        report["preservation_reference"] = "prepared_color_prefix_not_untreated_source"
    else:
        report["preservation_reference"] = "original_source_prefix"
    patched = install_sampling(model,output,sigmas,report,phase=phase)
    report["preparation_seconds"] = time.perf_counter()-started
    return output, patched, report


def install_sampling(model, latent, sigmas, report, *, phase="single"):
    """Attach phase-local hooks sharing one receipt and one prepared prefix."""
    patched = model
    if report.get("drift_control"):
        from .vendor.context_loop.drift_control import install_drift_control_av_model
        patched = install_drift_control_av_model(model,latent,12,schedule_override=sigmas)
        callback = patched.model_options["denoise_mask_function"]
        state = patched.model_options["h3_context_loop_drift_control_av"]
        def tracked(sigma,denoise_mask,extra_options=None):
            mask = callback(sigma,denoise_mask,extra_options)
            report["mask_calls"] += 1
            counts = report.setdefault("phase_mask_calls",{})
            counts[phase] = counts.get(phase,0)+1
            if len(report["sigma_trace"]) < 64:
                report["sigma_trace"].append({"sigma":state.last_sigma,"ratio":state.last_ratio,"phase":phase})
            return mask
        patched.set_model_denoise_mask_function(tracked)
        # Record a successful upstream split-reference correction, without
        # replacing its deterministic boundary-state reconstruction.
        from comfy.patcher_extension import WrappersMP
        key = "h3_context_loop_drift_control_split_handoff"
        original = patched.wrappers[WrappersMP.SAMPLER_SAMPLE][key][0]
        def tracked_handoff(executor,guider,schedule,*args,**kwargs):
            result = original(executor,guider,schedule,*args,**kwargs)
            if state._is_split_tail(schedule):
                report["split_handoff_calls"] = report.get("split_handoff_calls",0)+1
            return result
        patched.wrappers[WrappersMP.SAMPLER_SAMPLE][key] = [tracked_handoff]
    return patched


def validate_sampling(report):
    if report.get("drift_control") and report.get("mask_calls",0) == 0:
        raise RuntimeError("Drift Control was selected but its sampler mask hook never ran. Refusing an untreated result.")
