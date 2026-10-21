"""Opt-in runtime PDD warmup. No workflow names, switch IDs or file discovery.

Adapter for Jalen-Brunson/ComfyUI-MiniMax-H3-PDD-Acc. Uses that loaded pack's
warmup_schedule and verified patch ancestry; never guesses a base checkpoint.
"""
import inspect
import sys
import time
import uuid

KEY = 'minimax_h3_pdd_acc'
HEAD = 'diffusion_model.final_layer.forward'


def freeze(value=None):
    value = 'off' if value is None else value
    if value not in ('off', 'auto'):
        raise ValueError('PDD warmup must be Auto or Off.')
    return {'version': 2, 'mode': value, 'warmup_steps': 8, 'handoff_sigma': 0.8,
            'detection': 'runtime_model_hooks_and_patch_ancestry'}


def _wrappers(model):
    return [(kind, fn) for kind, groups in getattr(model, 'wrappers', {}).items()
            for fn in groups.get(KEY, [])]


def _head(model):
    return getattr(model, 'object_patches', {}).get(HEAD)


def _recognized(model):
    head = _head(model)
    fn = getattr(head, '__func__', head)
    wrappers = _wrappers(model)
    return (len(wrappers) == 1 and callable(fn) and
            getattr(fn, '__name__', '') == 'pdd_final_forward' and
            getattr(fn, '__module__', '').endswith('.pdd_acc_core') and
            getattr(wrappers[0][1], '__name__', '') == 'pdd_acc_wrapper' and
            wrappers[0][1].__module__.rsplit('.', 1)[0] == fn.__module__.rsplit('.', 1)[0])


def _structure(value):
    if isinstance(value, dict): return {k: _structure(v) for k, v in value.items()}
    if isinstance(value, list): return [_structure(v) for v in value]
    return value


def for_refinement(prepared, received, use_base=False):
    if use_base and prepared is None:
        raise ValueError('Recovered-base refinement requires an applied PDD warmup. Use the selected generation model for other configurations.')
    original=prepared[0] if prepared is not None and use_base else received
    model=original.clone()
    if model is original:raise ValueError('Refinement MODEL clone is not isolated.')
    model.wrappers=_structure(original.wrappers)
    for group in model.wrappers.values():group.pop('longcaster_pdd_warmup_trace',None)
    model.model_options=_structure(original.model_options)
    return model


def prepare(model, sigmas, setting=None, *, sampler=None, incompatible=False):
    setting = freeze() if setting is None else setting
    report = {**setting, 'applied': False, 'reason': 'disabled', 'detected': False,
              'base_calls': 0, 'pdd_calls': 0, 'base_sigma_trace': [], 'pdd_sigma_trace': []}
    if setting['mode'] == 'off': return None, report
    marked = bool(_wrappers(model)) or 'pdd' in getattr(_head(model), '__name__', '').lower()
    if not marked:
        # Native fused-head checkpoints lack this pack's reversible patch ancestry.
        try:
            layer = model.get_model_object('diffusion_model.final_layer')
            fused = layer.video_out.weight.shape[0] > 96
        except (AttributeError, KeyError): fused = False
        if fused: raise ValueError('PDD warmup cannot recover a base from fused PDD checkpoint weights.')
        report['reason'] = 'non_pdd_model'
        return None, report
    if not _recognized(model):
        raise ValueError('PDD warmup found unsupported or incomplete runtime PDD hooks.')
    report['detected'] = True
    if incompatible:
        raise ValueError('Test PDD warmup separately from Anti-Burn.')
    if sampler is not None and getattr(getattr(sampler, 'sampler_function', None), '__name__', '') != 'sample_euler':
        raise ValueError('PDD warmup requires the plain Euler sampler.')
    import torch
    fn = getattr(_head(model), '__func__', _head(model))
    module = sys.modules.get(fn.__module__)
    scheduler = getattr(module, 'warmup_schedule', None)
    if not callable(scheduler): raise ValueError('Installed PDD pack does not expose the supported warmup schedule.')
    bounds = inspect.getclosurevars(fn).nonlocals.get('bounds')
    actual = sigmas.detach().cpu().double().flatten().tolist()
    expected = [12*t/(1+11*t) for t in [1-i/8 for i in range(9)]]
    if bounds is None or len(bounds) != 9 or len(actual) != 9 or any(abs(a-b)>1e-6 for a,b in zip(actual,expected)) or any(abs(a-b)>1e-6 for a,b in zip(bounds,expected)):
        raise ValueError('PDD warmup currently requires the complete trained 8-step PDD schedule.')
    schedule, split = scheduler(8, 0.8)
    if split != 8 or len(schedule) != 11 or any(abs(a-b)>1e-6 for a,b in zip(schedule[-3:],actual[-3:])):
        raise ValueError('Installed PDD warmup schedule has an incompatible handoff.')
    current = model
    seen = set()
    for _ in range(64):
        if id(current) in seen: raise ValueError('PDD model ancestry contains a cycle.')
        seen.add(id(current))
        parent = getattr(current, 'parent', None)
        if parent is None: raise ValueError('PDD warmup needs intact pre-PDD model ancestry; base recovery unavailable.')
        if not _wrappers(parent): break
        if not _recognized(parent): raise ValueError('PDD ancestor hooks are incompatible.')
        current = parent
    else: raise ValueError('PDD model ancestry is too deep.')
    # Remove precisely the LoRA entries introduced at the PDD boundary. Keep
    # upstream subject LoRAs and any patches added after PDD, by object identity.
    base = model.clone()
    if base is model: raise ValueError('MODEL clone is not isolated.')
    base.patches = {key: list(values) for key, values in model.patches.items()}
    removed = 0
    for key, boundary in current.patches.items():
        before = parent.patches.get(key, [])
        after = model.patches.get(key, [])
        if len(boundary)<len(before) or len(after)<len(boundary) or any(a is not b for a,b in zip(before,boundary)) or any(a is not b for a,b in zip(boundary,after)):
            raise ValueError('PDD patch history was rewritten; cannot safely recover base weights.')
        count = len(boundary)-len(before)
        if count:
            removed += count
            retained = list(before) + list(after[len(boundary):])
            if retained: base.patches[key] = retained
            else: base.patches.pop(key, None)
    if not removed:
        raise ValueError('PDD warmup cannot verify removal of the PDD trunk LoRA; baked/zero-strength PDD is unsupported.')
    base.patches_uuid = uuid.uuid4()
    base.object_patches = dict(model.object_patches)
    layer = model.get_model_object('diffusion_model.final_layer')
    base.object_patches[HEAD] = parent.object_patches.get(HEAD, type(layer).forward.__get__(layer, type(layer)))
    base.wrappers = _structure(model.wrappers)
    for groups in base.wrappers.values(): groups.pop(KEY, None)
    base.model_options = _structure(model.model_options)
    pdd = model.clone()
    pdd.wrappers = _structure(model.wrappers)
    pdd.model_options = _structure(model.model_options)
    kind, original = _wrappers(model)[0]
    def tracking(stage, callback=None):
        def tracked(executor, *args, **kwargs):
            timestep = args[1] if len(args)>1 else kwargs['timestep']
            report[stage+'_calls'] += 1
            report[stage+'_sigma_trace'].append(float(timestep.flatten()[0])/1000)
            return callback(executor,*args,**kwargs) if callback else executor(*args,**kwargs)
        return tracked
    base.add_wrapper_with_key(kind, 'longcaster_pdd_warmup_trace', tracking('base'))
    pdd.wrappers[kind][KEY] = [tracking('pdd', original)]
    report.update(applied=True, reason='runtime_pdd_detected', removed_trunk_patch_entries=removed,
                  runtime_module=fn.__module__, original_sigma_values=actual,
                  base_sigmas=schedule[:split+1], pdd_sigmas=schedule[split:],
                  audio='joint_av_original_masks', second_phase_noise='disabled',
                  quality_validation='experimental_requires_identity_review')
    return (base,pdd,torch.tensor(schedule,device=sigmas.device,dtype=sigmas.dtype),split), report


def sample(prepared, report, conditioning, sampler, latent, seed, cancelled=lambda: False, stage=lambda _: None):
    import torch
    from comfy_extras.nodes_custom_sampler import BasicGuider, RandomNoise, DisableNoise, SamplerCustomAdvanced
    base,pdd,sigmas,split = prepared
    dynamic_context = 'h3_context_loop_drift_control_av' in pdd.model_options
    report['handoff_policy'] = ('drift_control_preserve_boundary_state_and_restore_reference'
                                if dynamic_context else 'restore_zero_mask_reference')
    def phase(model, noise, schedule, label):
        if cancelled(): raise RuntimeError('Generation cancelled before PDD '+label+'.')
        stage('warming_up' if label=='base' else 'sampling')
        if torch.cuda.is_available(): torch.cuda.synchronize()
        started=time.perf_counter()
        result=SamplerCustomAdvanced.execute(noise,BasicGuider.execute(model,conditioning)[0],sampler,schedule,work)[0]
        if torch.cuda.is_available(): torch.cuda.synchronize()
        report[label+'_seconds']=time.perf_counter()-started
        return result
    # At a nonzero ending sigma, the public sampler output has undergone
    # inverse_noise_scaling. It is a valid resume value for generated regions,
    # but NOT a new clean inpainting reference. Preserve the original clean AV
    # reference before sampling and restore only zero-mask regions at handoff.
    # Final output is still checked independently; nothing is repaired afterward.
    mask = latent.get('noise_mask')
    reference = None
    tensor = isinstance(latent['samples'], torch.Tensor) and not latent['samples'].is_nested
    if mask is not None:
        masks = [mask] if tensor else list(mask.unbind())
        parts = [latent['samples']] if tensor else list(latent['samples'].unbind())
        if len(parts) != len(masks): raise ValueError('PDD warmup AV mask stream count differs.')
        if any(not bool(torch.all((m==0)|(m==1))) for m in masks):
            raise ValueError('PDD warmup requires binary AV masks at the sampler handoff.')
        reference = ([part.detach().clone() for part in parts], [m.detach().clone() for m in masks])
    work = latent
    handoff=phase(base,RandomNoise.execute(seed)[0],sigmas[:split+1],'base')
    work={**handoff}
    if reference is not None and not dynamic_context:
        clean,masks = reference
        parts = [handoff['samples']] if tensor else list(handoff['samples'].unbind())
        if len(parts)!=len(clean): raise RuntimeError('Warmup changed the AV stream count.')
        restored=[];counts=[]
        for partial,original,m in zip(parts,clean,masks):
            if partial.shape!=original.shape: raise RuntimeError('Warmup changed AV geometry.')
            keep=m.to(device=partial.device)==0
            restored.append(torch.where(keep,original.to(partial),partial))
            counts.append(int(keep.expand_as(partial).sum().item()))
        work['samples']=restored[0] if tensor else type(handoff['samples'])(restored)
        work['noise_mask']=masks[0] if tensor else type(mask)(masks)
        report['handoff_clean_context_restored']=True
        report['handoff_protected_values']=counts
    output=phase(pdd,DisableNoise.execute()[0],sigmas[split:],'pdd')
    if dynamic_context:
        # The upstream SAMPLER_SAMPLE wrapper restores the original clean
        # reference while reconstructing the exact partial boundary state.
        # Replacing zero-mask values here would erase its soft prefix state.
        report['handoff_clean_context_restored'] = True
    if report['base_calls'] != split or report['pdd_calls'] != len(sigmas)-1-split:
        raise RuntimeError('PDD warmup runtime call counts did not match the two-stage schedule.')
    if cancelled(): raise RuntimeError('Generation cancelled during PDD finish.')
    return output
