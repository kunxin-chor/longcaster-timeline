"""Native H3 execution with explicit latent or last-frame continuation."""
from __future__ import annotations

import importlib
import inspect
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from .store import PIN, Store, atomic_json, digest, uid

LOG = logging.getLogger("longcaster_timeline")


def mh3_api():
    package = next((m for name, m in tuple(sys.modules.items()) if m is not None
                    and (name == "mmh3_media" or name.endswith(".mmh3_media"))
                    and hasattr(m, "build_h3_continuation_handover")), None)
    if package is None:
        try: package = importlib.import_module("mmh3_media")
        except ImportError as exc:
            raise RuntimeError("Install/enable the latest compatible MMH3 Media and restart ComfyUI. No sibling directory discovery is performed.") from exc
    api = importlib.import_module(package.__name__ + ".public_api")
    archive = importlib.import_module(package.__name__ + ".archive")
    contract = importlib.import_module(package.__name__ + ".h3_contract")
    api_version = getattr(api, "MMH3_ADAPTER_API_VERSION", None)
    latent_version = getattr(contract, "H3_LATENT_CONTRACT_VERSION", None)
    if api_version != 1 or latent_version != 2:
        raise RuntimeError(f"MMH3 adapter API v1 / H3 latent contract v2 is required; detected API {api_version!r}, latent contract {latent_version!r}. Update MMH3 Media and restart ComfyUI.")
    root = Path(package.__file__).resolve().parent.parent
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        revision = result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired): revision = ""
    # The reviewed public_api does not re-export archive I/O or h3_contract.
    # Keep a local facade; do not add attributes to another extension's modules.
    exports = {"MMH3Media": api, "pack_h3_result": api, "validate_generation_model_family": api,
        "build_h3_continuation_handover": api, "load_archive": archive, "save_archive": archive,
        "get_resource_payload": archive, "h3_latent_contract_from_resource": contract,
        "validate_h3_continuation_compatibility": contract}
    for name, module in exports.items():
        if not callable(getattr(module, name, None)):
            raise RuntimeError(f"MMH3 compatibility check failed: {module.__name__}.{name} is missing or not callable. Update MMH3 Media and restart ComfyUI.")
    facade = SimpleNamespace(**{name: getattr(module, name) for name, module in exports.items()})
    # Bind the calls that this adapter makes. A matching version number alone
    # does not prove that a fork still exposes the required keyword contracts.
    calls = {
        "load_archive": (("archive.mmh3",), {"verify": "full"}),
        "save_archive": ((None, "archive.mmh3"), {}),
        "get_resource_payload": ((None, {}), {}),
        "pack_h3_result": ((None,), {"latent": {}, "operation": "longcaster_timeline", "mode": "ref2va", "status": "complete", "latent_origin": "sampler_output", "process_info": {}}),
        "validate_generation_model_family": (("ref2va",), {"checkpoint_name": "ref2va.safetensors"}),
        "h3_latent_contract_from_resource": (({},), {}),
        "validate_h3_continuation_compatibility": (({},), {}),
        "build_h3_continuation_handover": (({},), {"source_origin": "sampler_output", "target_frames": 158, "video_handover_frames": 39,
            "audio_handover_frames": 39, "audio_feather_frames": 0, "target_width": 768, "target_height": 448}),
    }
    for name, (args, kwargs) in calls.items():
        compatible_signature(name, getattr(facade, name), args, kwargs)
    compatible_signature("MMH3Media.create", getattr(facade.MMH3Media, "create", None), (), {"name": "take", "generation": {}})
    for name in ("get_primary", "set_extension_value"):
        if not callable(getattr(facade.MMH3Media, name, None)):
            raise RuntimeError(f"MMH3 compatibility check failed: MMH3Media.{name} is missing.")
    facade.longcaster_dependency = {"git_revision": revision or None, "reviewed_revision": PIN,
        "adapter_api_version": api_version, "latent_contract_version": latent_version, "validation": "required_signatures_checked"}
    return facade


def compatible_signature(name, function, args, kwargs):
    try:
        if not callable(function): raise TypeError("required callable is missing")
        inspect.signature(function).bind(*args, **kwargs)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"MMH3 compatibility check failed for {name}: {exc}. Update MMH3 Media and restart ComfyUI.") from exc


def primary(api, packet):
    descriptor = packet.get_primary("latent")
    if descriptor is None: raise ValueError("Archive has no primary H3 latent.")
    contract = api.h3_latent_contract_from_resource(descriptor)
    return api.get_resource_payload(packet, descriptor), descriptor, contract


def prepare(api, store, snapshot):
    source = snapshot["source"]
    path = store.asset(source["latent_path"])
    if not path.is_file() or digest(path) != source["latent_sha256"]:
        raise ValueError("The frozen source archive is missing or changed.")
    packet = api.load_archive(str(path), verify="full")
    latent, descriptor, contract = primary(api, packet)
    if descriptor["id"] != source["latent_resource_id"]:
        raise ValueError("Loaded latent resource differs from the frozen source.")
    api.validate_h3_continuation_compatibility(contract)
    result = api.build_h3_continuation_handover(latent, source_origin=contract["origin"],
        target_frames=snapshot["plan"]["sampled_frames"], video_handover_frames=snapshot["plan"]["context_frames"],
        audio_handover_frames=snapshot["plan"]["context_frames"], audio_feather_frames=0,
        target_width=snapshot["width"], target_height=snapshot["height"])
    if "noise_mask" not in result.latent: raise RuntimeError("MH3 did not prepare per-stream masks.")
    import torch
    masks = result.latent["noise_mask"].unbind()
    streams = result.latent["samples"].unbind()
    source_streams = latent["samples"].unbind()
    c = snapshot["plan"]["context_frames"]
    video_t = 2 + 5 * ((c - 5) // 17); audio_t = c * 40 // 24
    if len(masks) != 2 or not torch.all(masks[0][:, :, :video_t] == 0) or not torch.all(masks[1][..., :audio_t] == 0):
        raise RuntimeError("Protected source mask does not equal zero.")
    if not torch.all(masks[0][:, :, video_t:] == 1) or not torch.all(masks[1][..., audio_t:] == 1):
        raise RuntimeError("New generation mask does not equal one.")
    if not torch.equal(streams[0][:, :, :video_t], source_streams[0][:, :, -video_t:]) or not torch.equal(streams[1][..., :audio_t], source_streams[1][..., -audio_t:]):
        raise RuntimeError("Prepared context does not exactly match original source tensors.")
    return result.latent, {"source_take_id": source["id"], "source_sha256": digest(path), "source_resource_id": descriptor["id"],
        "source_contract": contract, "handover": result.plan.to_dict(), "mask": "hard_av_v1", "video_context_steps": video_t,
        "audio_context_steps": audio_t, "source_tail_exact_before_sampling": True}


def mask_capability(model):
    base = getattr(model, "model", None)
    candidates = [getattr(base, name, None) for name in ("extra_conds", "_denoise_mask_conds", "_denoise_mask_values")]
    if not any("audio_denoise_mask" in (*fn.__code__.co_names, *fn.__code__.co_consts)
               for fn in candidates if hasattr(fn, "__code__")) or not callable(getattr(base, "scale_latent_inpaint", None)):
        raise RuntimeError("This MODEL does not expose native H3 joint video/audio mask conditioning. Check third-party masking replacements.")


def sanitized(value, key="", depth=0):
    if key.casefold() in ("token", "api_key", "password", "secret", "authorization", "cookie"):
        return "[redacted]"
    if depth > 20: return "[depth limit]"
    if isinstance(value, dict): return {str(k): sanitized(v, str(k), depth + 1) for k, v in value.items()}
    if isinstance(value, list): return [sanitized(v, depth=depth + 1) for v in value]
    if value is None or isinstance(value, (str, float, int, bool)): return value
    return f"[{type(value).__name__}]"


def model_checkpoint_sources(graph):
    """Follow selected MODEL ancestry and record explicit experimental ref patches."""
    graph = graph or {}
    outputs = [record for record in graph.values() if record.get("class_type") == "LongCasterTimelineExecute"]
    if len(outputs) != 1: return []
    found = []; visited = set()
    def visit(link, ref_patch=None):
        if not isinstance(link, list) or len(link) != 2: return
        node_id = str(link[0])
        if (node_id, ref_patch) in visited: return
        visited.add((node_id, ref_patch))
        record = graph.get(node_id, {}); inputs = record.get("inputs", {})
        if record.get("class_type") == "MiniMaxH3RefPatchLoader":
            if not isinstance(inputs.get("ref_strength"), (int, float)) or inputs["ref_strength"] <= 0:
                raise ValueError("REF2VA patch strength must be positive for this experimental source.")
            ref_patch = node_id
        checkpoint_keys = ("unet_name", "ckpt_name", "model_name")
        if record.get("class_type") == "MMH3FastH3V2Model":
            checkpoint_keys += ("checkpoint",)
        for key in checkpoint_keys:
            if isinstance(inputs.get(key), str): found.append({"checkpoint":inputs[key], "ref_patch_node":ref_patch})
        if record.get("class_type") == "LongCasterTimelineModelSwitch":
            visit(inputs.get("source_"+str(inputs.get("select", "")).lower()), ref_patch)
        else:
            for value in inputs.values():
                if isinstance(value, list): visit(value, ref_patch)
    inputs = outputs[0].get("inputs", {})
    root = inputs.get("model")
    config = inputs.get("configuration")
    if isinstance(config, list) and len(config) == 2:
        record = graph.get(str(config[0]), {})
        if record.get("class_type") == "LongCasterTimelineConfigurationSwitch":
            switch = record.get("inputs", {})
            config = switch.get("source_"+str(switch.get("select", "")).lower())
            record = graph.get(str(config[0]), {}) if isinstance(config, list) else {}
        root = record.get("inputs", {}).get("model")
    visit(root)
    return found


def model_checkpoint_names(graph):
    return list(dict.fromkeys(source["checkpoint"] for source in model_checkpoint_sources(graph)))


def execute(root, project_id, job_id, model, sampler, sigmas, clip, video_vae, audio_vae, model_mode, graph=None, execution_id=None, configuration=None):
    store = Store(root, project_id)
    job = store.claim(job_id); snapshot = job["snapshot"]
    try:
        from .configuration import verify_configuration
        verify_configuration(snapshot.get("configuration"), configuration, graph or {}, execution_id)
        api = mh3_api()
        import torch
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo
        from comfy_extras.nodes_custom_sampler import BasicGuider, RandomNoise, SamplerCustomAdvanced
        from .image_continuation import method as continuation_method, validate as validate_image_continuation
        continuation = continuation_method(snapshot.get("continuation_method"))
        if continuation == "last_frame":
            validate_image_continuation(snapshot["profile"], snapshot["source"], snapshot)
            if snapshot["plan"]["context_frames"] != snapshot.get("image_motion_frames",0):
                raise ValueError("Last-frame continuation context differs from the selected image-motion setting.")
        if continuation == 'video_reference':
            from .video_continuation import validate as validate_video
            validate_video(snapshot['profile'],snapshot['source'],snapshot,snapshot['plan'])
        if model_mode != snapshot["profile"]:
            raise ValueError(f"Execution node model mode {model_mode} differs from job mode {snapshot['profile']}. Connect the matching H3 checkpoint family.")
        sources = model_checkpoint_sources(graph)
        from .fasth3_omni import is_checkpoint as is_omni_checkpoint, ATTACHMENT as OMNI_ATTACHMENT
        contracts = [api.validate_generation_model_family("t2va" if source["ref_patch_node"] else ("ref2va" if model_mode == "ref2va" else "t2va"), checkpoint_name=source["checkpoint"], **({"model_family":"ref2va"} if is_omni_checkpoint(source["checkpoint"]) else {})).to_dict()
                     for source in sources]
        if any(source["ref_patch_node"] for source in sources):
            LOG.warning("Experimental FL2VA + REF patch source selected; this is not a native REF2VA checkpoint. Receipt records the explicit patch path.")
        for contract in contracts:
            if not contract["ready"]:
                raise ValueError(" ".join(item["message"] for item in contract["diagnostics"] if item["severity"] == "error"))
        if not contracts: LOG.warning("MODEL checkpoint family cannot be inferred; execution node declares %s", model_mode)
        schedule = sigmas.detach().cpu().double().flatten().tolist()
        if len(schedule) < 2 or any(not __import__('math').isfinite(s) for s in schedule) or schedule[0] <= 0 or abs(schedule[-1]) > 1e-8 or any(a < b for a, b in zip(schedule, schedule[1:])):
            raise ValueError("External SIGMAS must be finite, descending and terminate at zero.")
        from .loras import apply_loras
        model,lora_receipt=apply_loras(model,snapshot.get("loras",[]))
        from .anti_burn import apply as apply_anti_burn
        model,anti_burn_receipt=apply_anti_burn(model,snapshot.get("anti_burn"))
        from .pdd_warmup import prepare as prepare_pdd_warmup, sample as sample_pdd_warmup
        warmup, warmup_receipt = prepare_pdd_warmup(model,sigmas,snapshot.get("pdd_warmup"),sampler=sampler,
            incompatible=bool((snapshot.get("anti_burn") or {}).get("applied")))
        if warmup is not None: schedule = warmup[2].detach().cpu().double().tolist()
        requested_refine = snapshot.get("refine") or {}
        if requested_refine.get("applied") and requested_refine.get("model")=="base" and requested_refine.get("mode")!="noembryo_stats" and warmup is None:
            raise ValueError("Recovered-base refinement requires applied PDD warmup. Choose the selected generation model for non-PDD configurations.")
        if requested_refine.get("applied") and requested_refine.get("mode")=="character_masked":
            from .person_refine import verify_weights
            verify_weights()
        images = {}; consumed = []
        for reference in snapshot["compiled"]["images"]:
            if reference.get("generated_role")=="continuation_frame":
                if continuation!="last_frame" or snapshot["profile"]!="ref2va" or reference["source_archive_sha256"]!=snapshot["source"]["latent_sha256"] or reference["source_take_id"]!=snapshot["source"]["id"]:
                    raise ValueError("Generated continuation picture does not match the frozen source.")
                continue
            from PIL import Image
            import numpy as np
            path = store.asset(reference["asset_path"])
            if not path.is_file() or digest(path) != reference["asset_sha256"]:
                raise ValueError(f"Reference <{reference['token_name']}> is missing or changed.")
            with Image.open(path) as image:
                images[reference["id"]] = torch.from_numpy(np.array(image.convert("RGB"), dtype=np.float32) / 255).unsqueeze(0)
            from .reference_conditioning import reference_controls
            controls=reference_controls(reference)
            consumed.append({"id": reference["id"], "native_label": reference["native_label"], "sha256": digest(path),
                **controls,"effective_latent_multiplier":controls["latent_strength"]/100 if controls["conditioning_mode"]=="latent" else 1.0,
                "text_encoder_reference":"original_image"})
        if store.cancelled(job_id): raise RuntimeError("Generation cancelled before encoding.")
        store.stage(job_id,"encoding")
        prompt = snapshot["compiled"]["prompt"]
        args = dict(clip=clip, vae=video_vae, prompt=prompt, width=snapshot["width"], height=snapshot["height"], length=snapshot["plan"]["sampled_frames"])
        image_receipt = None
        if continuation == "last_frame":
            store.stage(job_id, "preparing_continuation")
            from .image_continuation import load_frame
            first_frame, image_receipt = load_frame(api, store, snapshot, video_vae, job_id, lambda:store.cancelled(job_id))
            if snapshot["profile"]=="ref2va":
                picture=snapshot["compiled"].get("continuation_picture")
                if not picture or picture["source_frame_index"]!=image_receipt["source_frame_index"]:
                    raise ValueError("Continuation picture frame differs from the frozen prompt binding.")
                images[picture["id"]]=first_frame
                image_receipt.update(native_label=picture["native_label"],conditioning_strategy="reference_picture_prompt",
                    automatic_additions=snapshot["compiled"]["automatic_additions"],hard_latent_pin=False)
                consumed.append({"id":picture["id"],"native_label":picture["native_label"],"sha256":image_receipt["image_sha256"],
                    "input_float32_sha256":image_receipt["conditioning_rgb_float32_sha256"],"generated_role":"continuation_frame",
                    "source_take_id":snapshot["source"]["id"],"source_archive_sha256":snapshot["source"]["latent_sha256"],
                    "conditioning_mode":"image","latent_strength":100,"text_encoder_reference":"decoded_source_frame"})
            else:
                compatible_signature("MiniMaxH3ImageToVideo.execute", MiniMaxH3ImageToVideo.execute, (), {**args,"first_frame":first_frame})
                args["first_frame"]=first_frame
                image_receipt.update(conditioning_strategy="native_fl2va_first_frame",hard_latent_pin=False)
            atomic_json(store.asset(f"diagnostics/{job_id}/image-continuation.json"),image_receipt)
        if snapshot["profile"] == "ref2va":
            if continuation=='video_reference':
                store.stage(job_id,'preparing_continuation')
                from .video_continuation import load_reference, condition
                from inspect import signature
                if not {'ref_videos','ref_video_audios'} <= set(signature(MiniMaxH3ReferenceToVideo.execute).parameters):
                    raise RuntimeError('Installed ComfyUI lacks native REF2VA video/audio reference inputs. Update ComfyUI before using this mode.')
                frames,sound,image_receipt=load_reference(api,store,snapshot,video_vae,audio_vae,job_id,lambda:store.cancelled(job_id))
                output=condition(MiniMaxH3ReferenceToVideo.execute,args,images,audio_vae,frames,sound,snapshot.get('ref_image_size','match'))
                consumed.extend([{'generated_role':'continuation_video','native_label':'<Video 1>','sha256':image_receipt['video_float32_sha256'],'source_take_id':snapshot['source']['id']},
                    {'generated_role':'continuation_audio','native_label':'<Audio 1>','sha256':image_receipt['audio_float32_sha256'],'source_take_id':snapshot['source']['id']}])
                del frames,sound
            else:
                if not images: raise ValueError("REF2VA requires enabled references.")
                output = MiniMaxH3ReferenceToVideo.execute(**args, audio_vae=audio_vae, ref_image_size=snapshot.get("ref_image_size", "match"), ref_images=images)
        else:
            if images: raise ValueError("FL2VA text mode does not silently consume REF2VA assets.")
            output = MiniMaxH3ImageToVideo.execute(**args)
        positive, latent = output[0], output[1]
        if snapshot["profile"]=="ref2va":
            from .reference_conditioning import scale_reference_conditioning
            positive=scale_reference_conditioning(positive,snapshot["compiled"]["images"])
        source_receipt = None
        if continuation=="last_frame" and snapshot.get("image_motion_frames"):
            mask_capability(model)
            from .image_continuation import prepare_motion
            latent,source_receipt=prepare_motion(api,store,snapshot,latent)
            image_receipt.update(motion_history=True,motion_context=source_receipt)
            atomic_json(store.asset(f"diagnostics/{job_id}/image-continuation.json"),image_receipt)
        if snapshot["source"] and continuation == "latent":
            store.stage(job_id,"preparing_continuation")
            mask_capability(model)
            latent, source_receipt = prepare(api, store, snapshot)
        from .drift import prepare as prepare_protection, install_sampling as install_protection, validate_sampling as validate_protection
        if (snapshot.get("continuation_protection") or {}).get("applied"):
            store.stage(job_id,"preparing_protection")
        # Color carry prepares the disposable prefix once. Both warmup phases
        # then use that same clean reference and the full 10-step schedule.
        latent, sampling_model, protection_receipt = prepare_protection(api,store,snapshot,latent,
            warmup[0] if warmup else model, warmup[2] if warmup else sigmas, video_vae,
            phase="base" if warmup else "single")
        if warmup is not None:
            pdd_model = install_protection(warmup[1],latent,warmup[2],protection_receipt,phase="pdd")
            warmup = (sampling_model,pdd_model,warmup[2],warmup[3])
        if source_receipt:
            source_receipt["sampling_mask_policy"] = snapshot["plan"]["mask_profile"]
            source_receipt["preservation_reference"] = protection_receipt.get("preservation_reference","original_source_prefix")
        from .continuation_evidence import capture_context, check_context
        expected_context = capture_context(latent, source_receipt) if source_receipt else None
        if store.cancelled(job_id): raise RuntimeError("Generation cancelled before sampling.")
        LOG.info("LongCaster Timeline job=%s source=%s context=%s references=%s continuation=%s drift=%s", job_id,
                 (snapshot["source"] or {}).get("id"), snapshot["plan"]["context_frames"], consumed, continuation, snapshot.get("drift", "off"))
        store.stage(job_id,"sampling")
        if torch.cuda.is_available(): torch.cuda.synchronize()
        sampling_started = time.perf_counter()
        if warmup is not None:
            sampled = sample_pdd_warmup(warmup,warmup_receipt,positive,sampler,latent,snapshot["seed"],
                lambda:store.cancelled(job_id),lambda phase:store.stage(job_id,phase))
        else:
            sampled = SamplerCustomAdvanced.execute(RandomNoise.execute(snapshot["seed"])[0], BasicGuider.execute(sampling_model, positive)[0], sampler, sigmas, latent)[0]
        if torch.cuda.is_available(): torch.cuda.synchronize()
        sampling_seconds = time.perf_counter() - sampling_started
        validate_protection(protection_receipt)
        if warmup is not None and protection_receipt.get("drift_control"):
            if protection_receipt.get("phase_mask_calls") != {"base":8,"pdd":2} or protection_receipt.get("split_handoff_calls") != 1:
                raise RuntimeError("Warmup Drift Control did not verify all ten masks and the clean-reference handoff.")
        runtime_memory = {"scope":"process_lifetime_peak_not_job_peak", "allocated_bytes":torch.cuda.memory_allocated(), "reserved_bytes":torch.cuda.memory_reserved(), "peak_allocated_bytes":torch.cuda.max_memory_allocated()} if torch.cuda.is_available() else None
        from .refine import apply as apply_refine, clone_latent
        raw_sampled = clone_latent(sampled, cpu=True) if snapshot.get("refine", {}).get("applied") else None
        if raw_sampled is not None:
            store.stage(job_id, "refining")
        refine_model = model
        refine_setting = snapshot.get("refine") or {}
        if refine_setting.get("applied") and refine_setting.get("mode")!="noembryo_stats":
            from .pdd_warmup import for_refinement
            refine_model = for_refinement(warmup,model,refine_setting.get("model")=="base")
        anchor_latent=None; person_mask=None; mask_receipt=None
        if refine_setting.get("applied") and refine_setting.get("anchor"):
            anchor_info=refine_setting['anchor'];anchor_path=store.asset(anchor_info['latent_path'])
            if digest(anchor_path)!=anchor_info['latent_sha256']:raise ValueError('Refinement anchor archive changed.')
            anchor_latent,_,_=primary(api,api.load_archive(str(anchor_path),verify='full'))
        if refine_setting.get("applied") and refine_setting.get("mode")=="character_masked":
            from .person_refine import mask_for_latent
            person_mask,mask_receipt=mask_for_latent(sampled,video_vae,store,job_id,lambda:store.cancelled(job_id),context_frames=snapshot['plan']['context_frames'])
        sampled, refine_receipt = apply_refine(sampled, refine_model, positive, sigmas, snapshot["seed"],
            snapshot["plan"]["context_frames"], refine_setting, lambda: store.cancelled(job_id),anchor=anchor_latent,person_mask=person_mask)
        if mask_receipt is not None:refine_receipt['person_mask']=mask_receipt
        continuation_check = check_context(sampled, expected_context, source_receipt) if source_receipt else None
        if continuation_check:
            continuation_check["policy"] = snapshot["plan"]["mask_profile"]
            continuation_check["reference"] = protection_receipt.get("preservation_reference","original_source_prefix")
            atomic_json(store.asset(f"diagnostics/{job_id}/continuation.json"), continuation_check)
            if not continuation_check["passed"]:
                LOG.error("Sampler changed protected continuation context. Saving the take for diagnosis; finalization is blocked.")
        del expected_context
        if snapshot["source"] and digest(store.asset(snapshot["source"]["latent_path"])) != snapshot["source"]["latent_sha256"]:
            raise RuntimeError("Source archive changed while sampling.")
        store.stage(job_id,"saving_latent")
        take_id = uid(); archive = store.asset(f"takes/{take_id}/original.mmh3")
        archive.parent.mkdir(parents=True, exist_ok=True)
        clean = {key: value for key, value in sampled.items() if key != "noise_mask"}
        packet = api.MMH3Media.create(name=f"LongCaster Timeline {take_id}", generation={"task": snapshot["profile"], "prompt": prompt,
            "seed": snapshot["seed"], "frames": snapshot["plan"]["sampled_frames"]})
        receipt = {"version": 1, "model_class": type(model.model).__name__, "sampler": type(sampler).__name__, "sigma_values": schedule,
            "continuation_check": continuation_check, "decode_edge": snapshot.get("decode_edge", {"policy":"off","frames":0}), "sampling_seconds": sampling_seconds, "refinement_seconds": refine_receipt["seconds"], "total_sampling_seconds": sampling_seconds + refine_receipt["seconds"], "cuda_memory": runtime_memory,
            "pdd_warmup": warmup_receipt, "continuation_protection": protection_receipt, "refine": refine_receipt, "source": image_receipt or source_receipt, "continuation_method": continuation, "ref_image_size": snapshot.get("ref_image_size", "match"), "loras":lora_receipt, "anti_burn":anti_burn_receipt, "configuration": snapshot.get("configuration"), "references": consumed, "upstream": sanitized(graph), "torch": torch.__version__,
            "native_recipe":getattr(model,"get_attachment",lambda key:None)(OMNI_ATTACHMENT), "mh3_revision": api.longcaster_dependency["git_revision"], "mh3_compatibility": api.longcaster_dependency,
            "model_family_contracts": contracts, "model_sources": sources, "auto_frame": False, "prompt_timing": "authored"}
        packet = packet.set_extension_value("longcaster_timeline", "take", {"take_id": take_id, "snapshot": snapshot, "receipt": receipt})
        packed = api.pack_h3_result(packet, latent=clean, operation="longcaster_timeline", mode=snapshot["profile"], status="complete", latent_origin="sampler_output", process_info=receipt)
        if raw_sampled is not None:
            raw_clean = {key: value for key, value in raw_sampled.items() if key != "noise_mask"}
            raw_receipt = {**receipt, "archive_role":"before_refine", "refine":{**refine_receipt,"applied":False,"reason":"raw_archive_before_refinement"}}
            raw_media = packet.set_extension_value("longcaster_timeline", "take", {"take_id": take_id, "snapshot": snapshot, "receipt": raw_receipt})
            raw_packet = api.pack_h3_result(raw_media, latent=raw_clean, operation="longcaster_timeline_raw",
                mode=snapshot["profile"], status="complete", latent_origin="sampler_output", process_info=raw_receipt)
            api.save_archive(raw_packet.packet, str(archive))
            receipt["raw_latent"] = {"path": str(archive.relative_to(store.path)).replace("\\", "/"), "sha256": digest(archive)}
            archive = archive.with_name("refined.mmh3")
            packet = packet.set_extension_value("longcaster_timeline", "take", {"take_id": take_id, "snapshot": snapshot, "receipt": receipt})
            packed = api.pack_h3_result(packet, latent=clean, operation="longcaster_timeline", mode=snapshot["profile"],
                status="complete", latent_origin="sampler_output", process_info=receipt)
        _, final_path = api.save_archive(packed.packet, str(archive))
        verified = api.load_archive(final_path, verify="full")
        _, descriptor, _ = primary(api, verified)
        take = store.complete(job_id, {"take_id": take_id, "latent_path": str(Path(final_path).relative_to(store.path)).replace("\\", "/"),
            "latent_sha256": digest(final_path), "latent_resource_id": descriptor["id"]}, receipt)
    except BaseException as exc:
        from comfy.model_management import InterruptProcessingException
        store.fail(job_id, "Generation cancelled in ComfyUI." if isinstance(exc, InterruptProcessingException) else str(exc),
                   cancelled=isinstance(exc, InterruptProcessingException))
        raise
    # A preview failure does not erase a successful sampled take.
    try:
        from .preview import build_preview
        build_preview(store, take, video_vae, audio_vae, api, on_stage=lambda stage:store.stage(job_id,stage))
        store.stage(job_id,"complete")
    except Exception as exc:
        store.stage(job_id,"preview_failed",message=str(exc))
        LOG.exception("Timeline take %s saved; preview failed", take_id)
        atomic_json(store.asset(f"takes/{take_id}/preview.json"), {"status": "failed", "error": str(exc), "source_sha256": take["latent_sha256"]})
    return {"project_id": project_id, "job_id": job_id, "take_id": take_id, "status": "succeeded"}
