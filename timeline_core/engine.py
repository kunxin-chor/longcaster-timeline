"""Native H3 execution. No inherited legacy controller or image guide injection."""
from __future__ import annotations

import importlib
import inspect
import json
import logging
from pathlib import Path
import subprocess
import sys
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
        for key in ("unet_name", "ckpt_name", "model_name"):
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
        if model_mode != snapshot["profile"]:
            raise ValueError(f"Execution node model mode {model_mode} differs from job mode {snapshot['profile']}. Connect the matching H3 checkpoint family.")
        sources = model_checkpoint_sources(graph)
        contracts = [api.validate_generation_model_family("t2va" if source["ref_patch_node"] else ("ref2va" if model_mode == "ref2va" else "t2va"), checkpoint_name=source["checkpoint"]).to_dict()
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
        images = {}; consumed = []
        for reference in snapshot["compiled"]["images"]:
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
        if snapshot["profile"] == "ref2va":
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
        if snapshot["source"]:
            store.stage(job_id,"preparing_continuation")
            mask_capability(model)
            latent, source_receipt = prepare(api, store, snapshot)
        if store.cancelled(job_id): raise RuntimeError("Generation cancelled before sampling.")
        LOG.info("LongCaster Timeline job=%s source=%s context=%s references=%s auto_frame=False drift=off", job_id,
                 (snapshot["source"] or {}).get("id"), snapshot["plan"]["context_frames"], consumed)
        store.stage(job_id,"sampling")
        sampled = SamplerCustomAdvanced.execute(RandomNoise.execute(snapshot["seed"])[0], BasicGuider.execute(model, positive)[0], sampler, sigmas, latent)[0]
        if snapshot["source"] and digest(store.asset(snapshot["source"]["latent_path"])) != snapshot["source"]["latent_sha256"]:
            raise RuntimeError("Source archive changed while sampling.")
        store.stage(job_id,"saving_latent")
        take_id = uid(); archive = store.asset(f"takes/{take_id}/original.mmh3")
        archive.parent.mkdir(parents=True, exist_ok=True)
        clean = {key: value for key, value in sampled.items() if key != "noise_mask"}
        packet = api.MMH3Media.create(name=f"LongCaster Timeline {take_id}", generation={"task": snapshot["profile"], "prompt": prompt,
            "seed": snapshot["seed"], "frames": snapshot["plan"]["sampled_frames"]})
        receipt = {"version": 1, "model_class": type(model.model).__name__, "sampler": type(sampler).__name__, "sigma_values": schedule,
            "source": source_receipt, "ref_image_size": snapshot.get("ref_image_size", "match"), "loras":lora_receipt, "configuration": snapshot.get("configuration"), "references": consumed, "upstream": sanitized(graph), "torch": torch.__version__,
            "mh3_revision": api.longcaster_dependency["git_revision"], "mh3_compatibility": api.longcaster_dependency,
            "model_family_contracts": contracts, "model_sources": sources, "auto_frame": False, "prompt_timing": "authored"}
        packet = packet.set_extension_value("longcaster_timeline", "take", {"take_id": take_id, "snapshot": snapshot, "receipt": receipt})
        packed = api.pack_h3_result(packet, latent=clean, operation="longcaster_timeline", mode=snapshot["profile"], status="complete", latent_origin="sampler_output", process_info=receipt)
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
