"""Cached project review movie assembled from delivered take previews, without VAEs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
import re
import subprocess
import threading

from .preview import ffmpeg
from .store import Store, atomic_json, digest, fingerprint, now, uid

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="longcaster-project-preview")
_jobs = {}
_lock = threading.Lock()
KEY = re.compile(r"[0-9a-f]{64}\Z")


def plan_project_preview(store, include_drafts=False, draft_take_id=None, scene_id=None, apply_decode_edge=True):
    if not isinstance(include_drafts, bool): raise ValueError("Include drafts must be boolean.")
    if not isinstance(apply_decode_edge, bool): raise ValueError("Apply decode edge must be boolean.")
    data = store.load()
    if scene_id is not None and not any(scene["id"]==scene_id for scene in data["scenes"]): raise ValueError("Preview scene not found.")
    candidate = data["takes"].get(draft_take_id) if draft_take_id and include_drafts else None
    if draft_take_id and include_drafts and not candidate: raise ValueError("Draft preview take not found.")
    if candidate and scene_id is not None and candidate["scene_id"]!=scene_id: raise ValueError("Draft take belongs to another scene.")
    # Auditioning is read-only: any segment's generated take can be reviewed,
    # including one followed by empty planned segments. Tail restrictions apply
    # to generation/finalization, not to assembling a review movie.
    entries = []; project_frame = 0
    for scene in data["scenes"]:
        if scene_id is not None and scene["id"]!=scene_id: continue
        scene_frame = 0
        for segment in scene["segments"]:
            active_id = (segment.get("active_output") or {}).get("take_id")
            take_id = active_id
            if candidate and candidate["segment_id"] == segment["id"]:
                take_id = candidate["id"]
            elif include_drafts and not active_id:
                # A working take must have a saved, playable preview to enter review.
                take_id = next((tid for tid in reversed(segment["takes"])
                    if (store.preview(tid) or {}).get("status") == "ready"), None)
            if not take_id: continue
            take = data["takes"].get(take_id)
            if not take: raise ValueError(f"Missing take for {scene['name']} / {segment['name']}.")
            preview = store.preview(take_id) or {}
            if preview.get("status") != "ready" or preview.get("source_sha256") != take["latent_sha256"]:
                raise ValueError(f"Rebuild the saved preview for {scene['name']} / {segment['name']} before project playback.")
            source = store.asset(preview["path"])
            if not source.is_file(): raise ValueError(f"Preview file missing for {scene['name']} / {segment['name']}.")
            stat = source.stat(); frames = take["plan"]["new_frames"]
            if not isinstance(frames, int) or frames <= 0: raise ValueError("Invalid delivered take duration.")
            entries.append({"scene_id": scene["id"], "scene_name": scene["name"], "segment_id": segment["id"], "segment_name": segment["name"],
                "take_id": take_id, "take_number": take["number"], "draft": take_id != active_id,
                "start_frame": project_frame, "end_frame": project_frame + frames, "scene_start_frame": scene_frame,
                "frames": frames, "source_path": preview["path"], "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
                "latent_sha256": take["latent_sha256"], "width": take["width"], "height": take["height"]})
            project_frame += frames; scene_frame += frames
    from .continuation_evidence import apply_ownership
    entries = apply_ownership(store, data, entries) if apply_decode_edge else entries
    plan = {"version": 3, "encoding": "scrub_gop12_v1", "project_id": data["id"], "fps": 24, "audio_sample_rate": 48000, "frames": project_frame,
        "seconds": project_frame / 24, "width": entries[0]["width"] if entries else 0, "height": entries[0]["height"] if entries else 0,
        "draft_count": sum(entry["draft"] for entry in entries), "entries": entries}
    # Display-only names do not require encoding a new movie.
    identity = {**plan, "entries": [{k:v for k,v in entry.items() if k not in ("scene_name", "segment_name")} for entry in entries]}
    plan["key"] = fingerprint(identity)
    return plan


def cached_preview(store, key):
    if not KEY.fullmatch(key): raise ValueError("Invalid project preview key.")
    manifest = store.asset(f"project_previews/{key}/manifest.json")
    if not manifest.is_file(): return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    movie = store.asset(data["path"])
    if data.get("key") == key and data.get("status") == "ready" and movie.is_file() and movie.stat().st_size:
        return data
    return None


def render_project_preview(store, plan):
    directory = store.asset(f"project_previews/{plan['key']}")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{uid()}.mp4"
    inputs = []; filters = []; pads = []
    input_index = 0
    def normalize(input_id, start, end, label):
        filters.append(f"[{input_id}:v:0]fps=24,scale={plan['width']}:{plan['height']}:force_original_aspect_ratio=decrease,"
            f"pad={plan['width']}:{plan['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,trim=start_frame={start}:end_frame={end},setpts=N/(24*TB)[{label}]")
    for index, entry in enumerate(plan["entries"]):
        source = store.asset(entry["source_path"])
        own_input = input_index; input_index += 1
        inputs.extend(["-i", str(source)])
        borrowed = entry.get("borrowed_video_tail")
        # Audio keeps its original ownership and exact sample count. Video alone
        # may borrow preserved context from the next take's FULL decode.
        if borrowed:
            count = borrowed["frames"]
            inputs.extend(["-i", str(store.asset(borrowed["source_path"]))])
            borrow_input = input_index; input_index += 1
            normalize(borrow_input, borrowed["start_frame"], borrowed["end_frame"], f"borrow{index}")
            if entry["frames"] > count:
                normalize(own_input, 0, entry["frames"] - count, f"own{index}")
                filters.append(f"[own{index}][borrow{index}]concat=n=2:v=1:a=0[v{index}]")
            else:
                filters.append(f"[borrow{index}]null[v{index}]")
        else:
            normalize(own_input, 0, entry["frames"], f"v{index}")
        samples = entry["frames"] * 2000
        filters.append(f"[{own_input}:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=end_sample={samples},asetpts=N/SR/TB[a{index}]")
        pads.append(f"[v{index}][a{index}]")
    filters.append("".join(pads) + f"concat=n={len(pads)}:v=1:a=1[v][a]")
    command = [ffmpeg(), "-y", "-nostdin", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex_threads", "1", "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
        "-frames:v", str(plan["frames"]), "-t", str(plan["seconds"]), "-r", "24", "-c:v", "libx264", "-threads", "2",
        "-preset", "fast", "-crf", "20", "-g", "12", "-keyint_min", "12", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(temporary)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=600)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace")[-3000:] or "FFmpeg could not build project preview.")
        frames = re.findall(rb"(?:^|\n)frame=(\d+)", result.stdout)
        if not frames or int(frames[-1]) != plan["frames"]:
            raise RuntimeError("A source preview was shorter than its saved frame plan. Rebuild that take's preview.")
        for entry in plan["entries"]:
            for resource in (entry, entry.get("borrowed_video_tail")):
                if resource is None: continue
                stat = store.asset(resource["source_path"]).stat()
                if (stat.st_size, stat.st_mtime_ns) != (resource["source_size"], resource["source_mtime_ns"]):
                    raise RuntimeError("A source preview changed during assembly. Rebuild the project preview.")
        destination = directory / "preview.mp4"
        os.replace(temporary, destination)
        record = {**deepcopy(plan), "status": "ready", "path": f"project_previews/{plan['key']}/preview.mp4",
            "sha256": digest(destination), "created_at": now(), "purpose": "review", "context_already_trimmed": True}
        atomic_json(directory / "manifest.json", record)
        return record
    finally:
        temporary.unlink(missing_ok=True)


def request_project_preview(store, include_drafts=False, draft_take_id=None, retry=False, scene_id=None, apply_decode_edge=True):
    if not isinstance(retry, bool): raise ValueError("Retry must be boolean.")
    plan = plan_project_preview(store, include_drafts, draft_take_id, scene_id, apply_decode_edge)
    if not plan["entries"]: return {**plan, "status": "empty", "message": "Generate a take preview to review the project."}
    cached = cached_preview(store, plan["key"])
    if cached:
        # Refresh display labels without rewriting the cached artifact or saved takes.
        return {**cached, "entries": plan["entries"]}
    identity = (str(store.path), plan["key"])
    with _lock:
        future = _jobs.get(identity)
        if future and future.done():
            error = future.exception()
            if not error: return {**future.result(), "entries": plan["entries"]}
            if not retry: return {**plan, "status": "failed", "error": str(error)}
            _jobs.pop(identity)
        if identity not in _jobs:
            # Fail early if FFmpeg is unavailable instead of queueing an unusable job.
            ffmpeg()
            _jobs[identity] = _executor.submit(render_project_preview, store, deepcopy(plan))
        # Keep completed in-memory job bookkeeping bounded. Disk caches survive restarts.
        for key, job in list(_jobs.items()):
            if len(_jobs) <= 32: break
            if key != identity and job.done(): _jobs.pop(key)
    return {**plan, "status": "building"}
