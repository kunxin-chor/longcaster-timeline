"""Explicit, video-only H3 refinement using pinned dntpi schedule/blend helpers.

The Timeline adapter deliberately uses plain Euler and a hard protected head,
not upstream's default res_multistep and fractional head ramp. No fallback.
"""
import time

UPSTREAM = "https://github.com/dntpi/ComfyUI-H3-Refine"
REVISION = "903e66219569eef22d46f81ec478f7556b0b9ab3"


def controls(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or not isinstance(value.get("enabled", False), bool):
        raise ValueError("H3 Refine requires an enabled boolean.")
    steps = value.get("steps", 2)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 4:
        raise ValueError("H3 Refine steps must be an integer from 1 to 4.")
    mode = value.get("mode", "h3_refine")
    model = value.get("model", "received")
    if mode not in ("h3_refine","noembryo_stats","noembryo_detail","character_masked"):
        raise ValueError("Choose a supported refinement method.")
    if model not in ("received","base"): raise ValueError("Refinement model must be received or base.")
    return {"enabled": value.get("enabled", False), "steps": steps, "mode":mode, "model":model}


def freeze(value, source, anchor=None):
    setting = controls(value)
    if setting["enabled"] and source and setting["mode"].startswith("noembryo") and not anchor:
        raise ValueError("noEmbryo refinement requires the scene's finalized first take as anchor.")
    return {**setting, "version": 2, "applied": setting["enabled"] and bool(source),
        "reason": "enabled" if setting["enabled"] and source else "independent_start" if setting["enabled"] else "disabled",
        "align": "hop_tail" if setting["mode"]=="h3_refine" else "statistics" if setting["mode"]=="noembryo_stats" else "normal_denoise",
        "denoise":0.4 if setting["mode"] in ("noembryo_detail","character_masked") else None,
        "sampler": "none" if setting["mode"]=="noembryo_stats" else "euler", "audio": "freeze", "head": "hard_freeze",
        "blend": "auto", "upstream": UPSTREAM if not setting["mode"].startswith("noembryo") else "https://github.com/noembryo/ComfyUI-noEmbryo",
        "upstream_revision": REVISION if not setting["mode"].startswith("noembryo") else "4289beac758c836138d3eab560cefaa5dc0f6057",
        "anchor":{key:anchor[key] for key in ("id","latent_path","latent_sha256","width","height")} if anchor and setting["mode"].startswith("noembryo") else None}


def clone_latent(latent, cpu=False):
    parts = [p.detach().to("cpu", copy=True) if cpu else p.detach().clone()
             for p in latent["samples"].unbind()]
    return {**latent, "samples": type(latent["samples"])(parts)}


def apply(raw, model, conditioning, sigmas, seed, context_frames, frozen, cancelled=lambda: False, *, anchor=None, person_mask=None):
    if not frozen or not frozen.get("applied"):
        return raw, {**(frozen or {"applied": False}), "seconds": 0}
    import torch
    from comfy.nested_tensor import NestedTensor
    from comfy_extras.nodes_custom_sampler import BasicGuider, RandomNoise, KSamplerSelect, SamplerCustomAdvanced
    from .vendor.h3_refine import schedule, refine_blend

    if cancelled(): raise RuntimeError("Generation cancelled before refinement.")
    head = refine_blend.whole_steps_for_frames(context_frames)
    if not head: raise ValueError("Refinement requires an exact H3 context token boundary.")
    mode = frozen.get("mode","h3_refine")
    tail, steps, base_steps = schedule.tail(sigmas, frozen["steps"])
    if mode in ("noembryo_detail","character_masked"):
        from comfy_extras.nodes_custom_sampler import BasicScheduler
        tail = BasicScheduler.execute(model,"normal",frozen["steps"],0.4)[0]
        steps = len(tail)-1
    values = tail.detach().cpu().double().tolist()
    if not 0 < values[0] < 1 or values[-1] != 0 or any(a <= b for a,b in zip(values, values[1:])):
        raise ValueError("Refine sigma tail must strictly descend from below 1 to zero.")
    video, audio = raw["samples"].unbind()
    if video.ndim != 5 or audio.ndim != 4 or video.shape[2] <= head:
        raise ValueError("Refinement requires a joint AV latent with footage beyond the head.")
    work = clone_latent(raw)
    vmask = torch.ones((video.shape[0], 1, *video.shape[2:]), device=video.device)
    vmask[:, :, :head] = 0
    if mode == "character_masked":
        if person_mask is None or person_mask.shape != vmask.shape or not torch.isfinite(person_mask).all():
            raise ValueError("Character refinement requires a matching, finite person mask.")
        vmask = vmask * (person_mask.to(vmask)>0).to(vmask)
    amask = torch.zeros((audio.shape[0], 1, *audio.shape[2:]), device=audio.device)
    if raw.get("noise_mask") is not None:
        vm, am = raw["noise_mask"].unbind()
        vmask = vmask * vm.to(vmask)
        amask = amask * am.to(amask)
    work["noise_mask"] = NestedTensor((vmask, amask))
    refine_seed = (int(seed) ^ 0x5EF1) & 0x7FFFFFFF
    noise = RandomNoise.execute(refine_seed)[0]
    guider = BasicGuider.execute(model, conditioning)[0]
    sampler = KSamplerSelect.execute("euler")[0]
    if torch.cuda.is_available(): torch.cuda.synchronize()
    started = time.perf_counter()
    if mode == "noembryo_stats":
        donor = work
        actual_calls = 0
    else:
        # Trace the refine pass on an isolated clone, separate from warmup.
        model = model.clone()
        model.wrappers={kind:{key:list(fns) for key,fns in groups.items()} for kind,groups in model.wrappers.items()}
        from comfy.patcher_extension import WrappersMP
        trace=[]
        def tracked(executor,*args,**kwargs):
            timestep=args[1] if len(args)>1 else kwargs['timestep']
            trace.append(float(timestep.flatten()[0])/1000)
            return executor(*args,**kwargs)
        model.add_wrapper_with_key(WrappersMP.DIFFUSION_MODEL,'longcaster_refine_trace',tracked)
        guider = BasicGuider.execute(model, conditioning)[0]
        donor = SamplerCustomAdvanced.execute(noise, guider, sampler, tail, work)[0]
        actual_calls=len(trace)
        if actual_calls != steps:raise RuntimeError("Refinement sampling call count did not match its schedule.")
    if torch.cuda.is_available(): torch.cuda.synchronize()
    if cancelled(): raise RuntimeError("Generation cancelled during refinement.")
    dv, da = donor["samples"].unbind()
    if dv.shape != video.shape or da.shape != audio.shape or not torch.isfinite(dv).all() or not torch.isfinite(da).all():
        raise RuntimeError("Refinement returned invalid or non-finite AV streams.")
    # Verify the sampler honored the masks before explicitly retaining raw data.
    tol = 8 * torch.finfo(torch.float32).eps
    if not torch.allclose(dv[:, :, :head], video[:, :, :head].to(dv), rtol=tol, atol=tol):
        raise RuntimeError("Refine sampler changed the protected continuation head.")
    if not torch.allclose(da, audio.to(da), rtol=tol, atol=tol):
        raise RuntimeError("Refine sampler changed frozen audio.")
    upstream_report = None
    if mode.startswith("noembryo"):
        if anchor is None: raise ValueError("noEmbryo anchor latent is missing.")
        from .vendor.noembryo.core import refine as noembryo_refine
        corrected,upstream_report = noembryo_refine(raw,1.0,context_frames,reference_latent=anchor,
            detail_donor=dv if mode=="noembryo_detail" else None)
        dv=corrected["samples"].unbind()[0].to(video)
    ramp = refine_blend.auto_ramp(context_frames)
    weights = refine_blend.step_weights(video.shape[2], refine_blend.parse(ramp), "linear")
    mixed = refine_blend.blend_video(video, dv, weights)
    mixed[:, :, :head] = video[:, :, :head].to(mixed)
    if mode == "character_masked":
        outside=person_mask.to(video)==0
        if not torch.allclose(donor['samples'].unbind()[0][outside.expand_as(video)],video[outside.expand_as(video)],rtol=tol,atol=tol):
            raise RuntimeError("Character refine sampler changed background outside its mask.")
        mixed=video+(mixed-video)*person_mask.to(video)
    output = {**raw, "samples": type(raw["samples"])((mixed, audio.detach().clone()))}
    if not torch.isfinite(mixed).all():raise RuntimeError("Refinement produced non-finite video.")
    elapsed = time.perf_counter()-started
    return output, {**frozen, "seconds": elapsed, "base_steps": base_steps,
        "sigma_values": values if mode!="noembryo_stats" else [], "seed": refine_seed, "blend_frames": ramp,
        "actual_steps":actual_calls,"sigma_trace":trace if mode!="noembryo_stats" else [],
        "schedule_source":"original_tail" if mode=="h3_refine" else "base_normal_denoise_0.4" if mode!="noembryo_stats" else "no_sampling",
        "upstream_report":upstream_report,
        "runtime_pdd_active":None if mode=="noembryo_stats" else any(bool(group.get('minimax_h3_pdd_acc')) for group in model.wrappers.values()),
        "background_outside_mask_verified":mode=="character_masked",
        "protected_video_steps": head, "output_audio_exact": True,
        "protected_head_exact": True, "continuation_uses": "refined.mmh3",
        "quality_validation": "experimental_requires_ab_review"}
