"""Explicit reference-picture restart, without motion/audio latent history."""
from .store import atomic_json, digest


def method(value=None):
    value = "latent" if value is None else value
    if value not in ("latent", "last_frame", "video_reference"):
        raise ValueError("Choose latent, last-frame or video-reference continuation.")
    return value


def validate(profile, source, settings):
    if profile not in ("ref2va", "fl2va"):
        raise ValueError("Last-frame continuation requires a supported H3 generation profile.")
    if not source:
        raise ValueError("Last-frame continuation requires a finalized source take.")
    motion=settings.get("image_motion_frames",0)
    if isinstance(motion,bool) or motion not in (0,22):
        raise ValueError("Image motion context must be off or 22 video frames.")
    if motion and profile!="ref2va":
        raise ValueError("Motion-assisted image continuation currently requires REF2VA.")
    protection = settings.get("continuation_protection", "off")
    if isinstance(protection, dict): protection = protection.get("mode", "off")
    edge = settings.get("decode_edge_frames", (settings.get("decode_edge") or {}).get("frames", 0))
    if edge or (settings.get("refine") or {}).get("enabled") or protection not in (None, "off"):
        raise ValueError("Last-frame continuation has no motion overlap. Disable seam correction, refinement and continuation protection for this first implementation.")


def compile_with_frame(fields, references, source):
    """One shared compiler for editor preview and the immutable queued prompt."""
    import re
    from .compiler import compile_prompt, qualified_name
    from .store import FIELDS, fingerprint
    if not source:
        raise ValueError("Select a finalized source take for last-frame continuation.")
    names={qualified_name(item).casefold() for item in references}
    name="_continuation_frame"
    while "picture."+name in names: name="_"+name
    virtual={"id":"continuation-frame-"+source["id"], "token_name":name,
        "display_name":"Previous segment's final frame", "kind":"image", "role":"picture",
        "scope":"segment", "owner_id":None, "enabled":True,
        "asset_path":None, "asset_sha256":None, "generated_role":"continuation_frame",
        "source_take_id":source["id"], "source_archive_sha256":source["latent_sha256"],
        "source_frame_index":source["plan"]["delivery"]["end"]-1,
        "conditioning_mode":"image", "latent_strength":100}
    compiled=compile_prompt(fields,[*references,virtual])
    picture=compiled["images"][-1]
    label=picture["native_label"]
    additions={
        "subject_definitions":f"{label} is the final frame of the preceding segment and the first frame of [Shot 1].",
        "retention_analysis":f"{label} ([Shot 1] first frame): fully_preserved - Preserve the depicted composition, subject appearance, pose, environment and lighting at the opening frame.",
        "detailed_description":f"The video continues from {label} as its first frame. Start from the depicted pose and composition, then continue the following action naturally."}
    resolved=compiled["resolved_fields"]
    summary=resolved["summary"].strip()
    prefix=re.match(r"^\[([^\]]+)\]\s*",summary)
    tasks=[item.strip().lower() for item in prefix.group(1).split("+")] if prefix else (["reference generation"] if len(compiled["images"])>1 else [])
    tasks=list(dict.fromkeys(["keyframe completion",*tasks]))
    body=summary[prefix.end():] if prefix else summary
    additions["summary"]="["+" + ".join(tasks)+f"] The target video starts from {label} as the first frame of [Shot 1]."
    resolved["summary"]=(additions["summary"]+" "+body).strip()
    for field in ("subject_definitions","retention_analysis"):
        resolved[field]=(resolved[field].rstrip()+"\n"+additions[field]).strip()
    text=resolved["detailed_description"]
    shot=re.compile(r"\[Shot\s+1\]",re.I)
    if len(shot.findall(text))>1:
        raise ValueError("Last-frame continuation requires a single [Shot 1] opening.")
    if shot.search(text):
        text=shot.sub(lambda match:match.group(0)+" "+additions["detailed_description"],text,count=1)
    elif re.search(r"\[Shot\s+\d+\]",text,re.I):
        raise ValueError("Start the continuation prompt with [Shot 1].")
    else:
        text="[Shot 1] "+additions["detailed_description"]+" "+text
    resolved["detailed_description"]=text.strip()
    compiled["automatic_additions"]=additions
    compiled["continuation_picture"]={key:picture[key] for key in ("id","native_label","source_take_id","source_archive_sha256","source_frame_index")}
    compiled["prompt"]="\n\n".join(f"{field}:\n{resolved[field]}" for field in FIELDS)
    compiled["sha256"]=fingerprint({"prompt":compiled["prompt"],"assets":compiled["assets"]})
    return compiled


def preview_source(data, settings):
    """Resolve the same parent used by generation, including tail regeneration."""
    if settings.get("mode")=="regenerate":
        segment=next((segment for scene in data["scenes"] for segment in scene["segments"] if segment["id"]==settings.get("segment_id")),None)
        take=data["takes"].get((segment.get("active_output") or {}).get("take_id")) if segment else None
        return (take or {}).get("snapshot",{}).get("source")
    take=data["takes"].get(settings.get("source_take_id"))
    if not take:return None
    parent=next((segment for scene in data["scenes"] for segment in scene["segments"] if segment["id"]==take["segment_id"]),None)
    if take["scene_id"]!=settings.get("scene_id") or ((parent or {}).get("active_output") or {}).get("take_id")!=take["id"]:
        raise ValueError("The continuation source must be the explicitly finalized take in this scene.")
    return take


def load_frame(api, store, snapshot, vae, job_id, cancelled=lambda: False):
    """Decode the exact frozen archive, not its lossy preview or a newer take."""
    import hashlib
    import torch
    from PIL import Image
    from .engine import primary

    source = snapshot["source"]
    path = store.asset(source["latent_path"])
    if not path.is_file() or digest(path) != source["latent_sha256"]:
        raise ValueError("The frozen last-frame source archive is missing or changed.")
    if cancelled(): raise RuntimeError("Generation cancelled before source-frame decoding.")
    packet = api.load_archive(str(path), verify="full")
    latent, descriptor, contract = primary(api, packet)
    if descriptor["id"] != source["latent_resource_id"]:
        raise ValueError("Loaded source resource differs from the frozen last-frame source.")
    video = latent["samples"].unbind()[0]
    frames = vae.decode(video.detach().to("cpu", copy=True).contiguous())
    if frames.ndim == 5: frames = frames.reshape(-1, *frames.shape[-3:])
    if frames.ndim != 4 or len(frames) != source["plan"]["sampled_frames"]:
        raise ValueError("Decoded last-frame source does not match its frozen frame count.")
    delivery = source["plan"]["delivery"]
    if not 0 <= delivery["start"] < delivery["end"] <= len(frames):
        raise ValueError("Source delivery bounds are invalid.")
    index = delivery["end"] - 1
    frame = frames[index:index+1, ..., :3].detach().float().cpu().contiguous()
    if tuple(frame.shape) != (1, snapshot["height"], snapshot["width"], 3) or not torch.isfinite(frame).all():
        raise ValueError("Decoded source frame has invalid geometry or pixel values.")
    frame = frame.clamp(0, 1)
    if cancelled(): raise RuntimeError("Generation cancelled during source-frame decoding.")
    if digest(path) != source["latent_sha256"]:
        raise ValueError("Last-frame source archive changed during decoding.")
    relative = f"diagnostics/{job_id}/source-last-frame.png"
    target = store.asset(relative); target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((frame[0].numpy()*255).round().astype("uint8")).save(target)
    report = {"version": 1, "method": "last_frame", "source_take_id": source["id"],
        "source_sha256": source["latent_sha256"], "source_resource_id": descriptor["id"],
        "source_contract": contract, "source_frame_index": index,
        "source_delivered_frame_index": index-delivery["start"],
        "image_path": relative, "image_sha256": digest(target),
        "conditioning_rgb_float32_sha256": hashlib.sha256(frame.numpy().tobytes()).hexdigest(),
        "conditioning_input": "decoded_archive_float32_not_preview_or_png",
        "target_frame_index": 0, "motion_history": False, "audio_history": False,
        "boundary_frame_delivery": "included", "quality_validation": "requires_native_test"}
    atomic_json(store.asset(f"diagnostics/{job_id}/image-continuation.json"), report)
    return frame, report


def prepare_motion(api, store, snapshot, latent):
    """Video-only 22-frame prefix; audio is fresh, so no AV-boundary rounding."""
    import torch
    from .engine import primary
    source=snapshot["source"];path=store.asset(source["latent_path"])
    if source["plan"]["delivery"]["end"]!=source["plan"]["sampled_frames"]:
        raise ValueError("Short motion requires source delivery to end at the archive's final frame.")
    if snapshot.get("image_motion_frames")!=22 or snapshot["plan"]["context_frames"]!=22:
        raise ValueError("Short image-motion context must be exactly 22 frames.")
    if digest(path)!=source["latent_sha256"]:raise ValueError("Motion source archive changed.")
    original,descriptor,contract=primary(api,api.load_archive(str(path),verify="full"))
    if descriptor["id"]!=source["latent_resource_id"]:raise ValueError("Motion source resource changed.")
    api.validate_h3_continuation_compatibility(contract)
    sv=original["samples"].unbind()[0]
    video,audio=latent["samples"].unbind()
    head=7  # H3 1,4,4,4,4,1,4 frame spans = 22 video frames.
    if sv.shape[:2]!=video.shape[:2] or sv.shape[3:]!=video.shape[3:] or sv.shape[2]<head or (sv.shape[2]-head)%5 or video.shape[2]<=head:
        raise ValueError("Source/target geometry or H3 temporal phase is incompatible with short motion context.")
    if latent.get("noise_mask") is not None:raise ValueError("Short motion requires a fresh target.")
    v=video.detach().clone();v[:,:,:head]=sv[:,:,-head:].to(v)
    vm=torch.ones((v.shape[0],1,*v.shape[2:]),device=v.device);vm[:,:,:head]=0
    am=torch.ones((audio.shape[0],1,*audio.shape[2:]),device=audio.device)
    joint=type(latent["samples"])
    prepared={**latent,"samples":joint((v,audio.detach().clone())),"noise_mask":joint((vm,am))}
    return prepared,{"source_take_id":source["id"],"source_sha256":source["latent_sha256"],
        "source_resource_id":descriptor["id"],"video_context_steps":head,"audio_context_steps":0,
        "video_context_frames":22,"audio_history":False,"source_tail_exact_before_sampling":True,
        "mask":"short_video_only_v1","source_contract":contract}
