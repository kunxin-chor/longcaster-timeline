from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import uuid


FIELDS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")
PIN = "86b96deb52ed3c753789b5bf846f58e0b0c2feba"
_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def duration(seconds, context=0, *, video_only=False):
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not 1 <= seconds <= 15:
        raise ValueError("New footage duration must be between 1 and 15 seconds.")
    if context not in ((0,22) if video_only else (0, 39, 90, 141)):
        raise ValueError("Unsupported motion context.")
    target = seconds * 24 + context
    k = max(0, math.floor((target - 5) / 17))
    candidates = [5 + 17 * x for x in (k, k + 1) if 5 + 17 * x > context]
    count = min(candidates, key=lambda n: (abs(n - target), -n))
    # Native profile is intentionally bounded until longer runs are validated.
    if count > 362:
        raise ValueError("New footage plus context exceeds this profile's 15-second sampled window. Reduce new duration or context.")
    audio_steps = round(count * 40 / 24)
    return {"requested_seconds": seconds, "fps": 24, "sampled_frames": count, "context_frames": context,
            "new_frames": count - context, "new_seconds": (count - context) / 24,
            "delivery": {"start": context, "end": count}, "mask_profile": "hard_av_v1", "edge_correction": "off",
            "audio": {"latent_rate": 40, "target_steps": audio_steps, "context_steps": 0 if video_only else context * 40 // 24,
                "target_rounding_error_numerator": audio_steps * 24 - count * 40, "target_rounding_error_denominator": 960,
                "phase_correction": "none_unvalidated"}}


def blank_segment(scene_id, number=1, draft=None):
    segment_id = uid()
    settings = {"scene_id": scene_id, "segment_id": segment_id, "mode": "new", "profile": "ref2va",
        "seconds": 5, "width": 768, "height": 448, "seed": 1, "context": 39,
        "fields": {name: "" for name in FIELDS}}
    if draft: settings.update(deepcopy(draft))
    settings.update(scene_id=scene_id, segment_id=segment_id)
    return {"id": segment_id, "name": f"Segment {number:02d}", "takes": [], "active_output": None, "working_draft": settings}


def new_scene(name):
    scene_id = uid()
    return {"id": scene_id, "name": name, "segments": [blank_segment(scene_id)]}


def active_job(job):
    return job["status"] in ("queued","running","persisting","cancel_requested") or (job["status"]=="succeeded" and (job.get("progress") or {}).get("stage") in ("decoding","saving_media","building_preview"))


def require_tail(scene, segment):
    index=next((i for i,item in enumerate(scene["segments"]) if item["id"]==segment["id"]),-1)
    later=scene["segments"][index+1:]
    # Empty copied prompt placeholders are not generated footage downstream.
    if index<0 or any(not item.get("planned") or item.get("takes") or item.get("active_output") for item in later):
        raise ValueError("Only the tail segment of a scene can be replaced or generated. Earlier segments are read-only.")


class Store:
    def __init__(self, root, project_id):
        uuid.UUID(project_id)
        self.root = Path(root).resolve()
        self.path = self.root / project_id
        self.manifest = self.path / "project.json"

    def asset(self, relative):
        path = (self.path / relative).resolve()
        if not path.is_relative_to(self.path) or path == self.path:
            raise ValueError("Invalid project asset path.")
        return path

    @contextmanager
    def locked(self):
        self.path.mkdir(parents=True, exist_ok=True)
        with _guard:
            lock = _locks.setdefault(str(self.path), threading.RLock())
        with lock, (self.path / ".lock").open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"0"); handle.flush()
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _read(self):
        with self.manifest.open(encoding="utf-8") as handle:
            data=json.load(handle)
            if data.get("deleted"):raise ValueError("Production was deleted.")
            return data

    def _commit(self, state):
        state["revision"] += 1
        state["updated_at"] = now()
        atomic_json(self.manifest, state)

    def load(self):
        with self.locked():
            return self._read()

    @classmethod
    def create(cls, root, name):
        name = str(name).strip()
        if not 1 <= len(name) <= 120:
            raise ValueError("Project name must contain 1–120 characters.")
        store = cls(root, uid())
        with store.locked():
            state = {"schema_version": 1, "id": store.path.name, "name": name, "revision": 0,
                     "created_at": now(), "updated_at": now(), "scenes": [new_scene("Scene 01")],
                     "takes": {}, "jobs": {}, "references": [], "layout": {}, "resolution": {"width":768,"height":448}}
            store._commit(state)
        return state

    @staticmethod
    def segment(state, segment_id):
        for scene in state["scenes"]:
            for segment in scene["segments"]:
                if segment["id"] == segment_id:
                    return scene, segment
        raise ValueError("Segment not found.")

    def command(self, revision, action, payload):
        from .project_settings import project_resolution
        with self.locked():
            state = self._read()
            if state["revision"] != revision:
                raise Conflict("Project changed. Refresh and retry the action.")
            if action == "set_reference_image_size":
                size = payload.get("ref_image_size")
                if size not in ("match", "max"):
                    raise ValueError("Reference image size must be match or max.")
                state["ref_image_size"] = size
            elif action == "set_generation_defaults":
                defaults = payload.get("defaults")
                if not isinstance(defaults, dict) or not isinstance(defaults.get("configuration_id"), str):
                    raise ValueError("Invalid default configuration.")
                selections, schema = defaults.get("selections"), defaults.get("schema")
                if not isinstance(selections, dict) or not isinstance(schema, list) or not 1 <= len(schema) <= 40 or len(selections) > 40:
                    raise ValueError("Invalid default switch schema.")
                ids = set()
                for item in schema:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in ids or item.get("kind") not in ("model", "configuration"):
                        raise ValueError("Invalid or duplicate default switch.")
                    if not 1 <= len(item["id"]) <= 128 or not isinstance(item.get("name"), str) or not 1 <= len(item["name"]) <= 120:
                        raise ValueError("Default switches require a valid name and node ID.")
                    ids.add(item["id"])
                    options = item.get("options", [])
                    if not isinstance(options, list) or not 1 <= len(options) <= 5 or any(not isinstance(option, dict) or option.get("value") not in ("A","B","C","D","E") or not isinstance(option.get("label"), str) for option in options):
                        raise ValueError("Invalid default switch options.")
                    if len({option["value"] for option in options}) != len(options):
                        raise ValueError("Default switch options must be unique.")
                    if selections.get(item["id"]) not in [option["value"] for option in options]:
                        raise ValueError("Select a connected source for each default switch.")
                    if item["kind"] == "configuration":
                        selected = next(option for option in options if option["value"] == selections[item["id"]])
                        if selected.get("configuration_id") != defaults["configuration_id"]:
                            raise ValueError("Default configuration does not match the selected switch source.")
                if set(selections) != ids or len(json.dumps(defaults)) > 40000:
                    raise ValueError("Default switches do not match the saved schema.")
                state["generation_defaults"] = deepcopy(defaults)
            elif action == "finalize":
                take = state["takes"].get(payload.get("take_id"))
                if not take:
                    raise ValueError("Take not found.")
                if (take.get("receipt", {}).get("continuation_check") or {}).get("passed") is False:
                    raise ValueError("Protected continuation context changed during sampling. This take is saved for review but cannot be finalized; inspect its execution receipt.")
                path = self.asset(take["latent_path"])
                if not path.is_file() or digest(path) != take["latent_sha256"]:
                    raise ValueError("Take latent is missing or corrupt.")
                preview = self.preview(take["id"]) or {}
                if preview.get("status") != "ready" or preview.get("source_sha256") != take["latent_sha256"] or not self.asset(preview.get("path", "")).is_file():
                    raise ValueError("Build and review the saved preview before finalizing this take.")
                scene, segment = self.segment(state, take["segment_id"])
                if (segment.get("active_output") or {}).get("take_id") != take["id"]:
                    require_tail(scene, segment)
                if any(j["scene_id"] == scene["id"] and active_job(j) for j in state["jobs"].values()):
                    raise Conflict("Finish or cancel scene generation before changing its finalized output.")
                segment["active_output"] = {"kind": "single_take", "take_id": take["id"]}
            elif action == "create_scene":
                name = str(payload.get("name", "")).strip()
                if not name or len(name) > 120:
                    raise ValueError("Scene name must contain 1–120 characters.")
                state["scenes"].append(new_scene(name))
                state["scenes"][-1]["segments"][0]["working_draft"].update(project_resolution(state))
            elif action == "ensure_scene":
                scene = next((s for s in state["scenes"] if s["id"] == payload.get("scene_id")), None)
                if not scene: raise ValueError("Scene not found.")
                if scene["segments"]: return deepcopy(state)
                scene["segments"].append(blank_segment(scene["id"]))
                scene["segments"][-1]["working_draft"].update(project_resolution(state))
            elif action == "set_scene_anti_burn":
                from .anti_burn import scene_controls
                scene = next((s for s in state["scenes"] if s["id"] == payload.get("scene_id")), None)
                if not scene: raise ValueError("Scene not found.")
                scene["anti_burn"] = scene_controls(payload.get("anti_burn"))
            elif action == "rename_scene":
                scene = next((s for s in state["scenes"] if s["id"] == payload.get("scene_id")), None)
                name = str(payload.get("name", "")).strip()
                if not scene or not name or len(name) > 120:
                    raise ValueError("Valid scene and name required.")
                scene["name"] = name
            elif action == "rename_project":
                name=payload.get("name","")
                if not isinstance(name,str) or not 1<=len(name.strip())<=120:raise ValueError("Production name must contain 1-120 characters.")
                state["name"]=name.strip()
            elif action == "set_upscale":
                width,height=payload.get("width"),payload.get("height")
                if any(isinstance(v,bool) or not isinstance(v,int) or not 256<=v<=8192 or v%2 for v in (width,height)):raise ValueError("Export dimensions must be even numbers from 256 to 8192.")
                state["upscale_resolution"]={"width":width,"height":height}
            elif action == "set_loras":
                from .loras import validate_lora
                scope=payload.get("scope");owner=payload.get("owner_id")
                if scope not in ("project","scene","segment"):raise ValueError("Invalid LoRA scope.")
                if scope=="project" and owner is not None:raise ValueError("Project LoRAs have no owner.")
                if scope=="scene" and not any(sc["id"]==owner for sc in state["scenes"]):raise ValueError("Scene not found.")
                if scope=="segment":self.segment(state,owner)
                entries=payload.get("entries")
                if not isinstance(entries,list) or len(entries)>16:raise ValueError("At most 16 LoRAs per scope.")
                clean=[validate_lora(item) for item in entries]
                if len({item["filename"] for item in clean})!=len(clean):raise ValueError("A LoRA may be defined once in each scope.")
                state["loras"]=[item for item in state.get("loras",[]) if (item["scope"],item.get("owner_id"))!=(scope,owner)]+[{**item,"scope":scope,"owner_id":owner} for item in clean]
            elif action == "set_resolution":
                from .project_settings import validate_resolution
                if any(active_job(j) for j in state["jobs"].values()):raise Conflict("Finish generation before changing project resolution.")
                if state["takes"]:raise Conflict("Generation resolution is locked after the first generated take. Duplicate without generations to choose a different resolution.")
                state["resolution"]=validate_resolution(payload.get("width"),payload.get("height"))
                for scene in state["scenes"]:
                    for segment in scene["segments"]:
                        segment.setdefault("working_draft",{}).update(state["resolution"])
            elif action == "migrate_prompt":
                from .compiler import effective_references
                from .project_settings import migrate_legacy_fields
                scene,segment=self.segment(state,payload["segment_id"])
                draft=segment.setdefault("working_draft",{})
                # Recompute on the server so the reviewed result cannot retarget sources.
                migrated=migrate_legacy_fields(draft.get("fields",{}),effective_references(state["references"],scene["id"],segment["id"]))
                if payload.get("reviewed_fields")!=migrated:raise Conflict("Prompt changed; review the migration again.")
                draft["fields"]=migrated
            elif action == "save_draft":
                _, segment = self.segment(state, payload["segment_id"])
                from .anti_burn import segment_controls
                draft = deepcopy(payload.get("draft", {}))
                if "anti_burn" in draft: draft["anti_burn"] = segment_controls(draft["anti_burn"])
                segment["working_draft"] = draft
                from .project_settings import project_resolution
                segment["working_draft"].update(project_resolution(state))
            elif action == "create_segment":
                scene = next((s for s in state["scenes"] if s["id"] == payload.get("scene_id")), None)
                if not scene: raise ValueError("Scene not found.")
                source_id = payload.get("after_segment_id")
                if any(j["scene_id"] == scene["id"] and active_job(j) for j in state["jobs"].values()):
                    raise Conflict("Finish or cancel scene generation before adding a segment.")
                if scene["segments"]:
                    tail = scene["segments"][-1]
                    if not tail.get("active_output"): raise ValueError("Generate and finalize the current tail segment before adding another.")
                    draft = payload.get("draft", {})
                    if source_id != tail["id"] or draft.get("mode") != "extend" or draft.get("source_take_id") != tail["active_output"]["take_id"]:
                        raise ValueError("Add segments by extending the finalized scene tail.")
                duration(payload.get("draft",{}).get("seconds",5),payload.get("draft",{}).get("context",39))
                segment = blank_segment(scene["id"], len(scene["segments"]) + 1, payload.get("draft"))
                segment["working_draft"].update(project_resolution(state))
                scene["segments"].append(segment)
                state["last_created_segment_id"] = segment["id"]
            elif action == "reference":
                reference = next((r for r in state["references"] if r["id"] == payload.get("reference_id")), None)
                if not reference: raise ValueError("Reference not found.")
                scope = payload.get("scope", reference["scope"])
                owner = payload.get("owner_id", reference["owner_id"])
                if scope not in ("project", "scene", "segment"): raise ValueError("Invalid reference scope.")
                if scope == "project" and owner is not None: raise ValueError("Project references have no owner.")
                if scope == "scene" and not any(s["id"] == owner for s in state["scenes"]): raise ValueError("Scene not found.")
                if scope == "segment": self.segment(state, owner)
                ranks = {"project": 0, "scene": 1, "segment": 2}
                if ranks[scope] < ranks[reference["scope"]]: raise ValueError("An override must be in a narrower scope.")
                if scope == reference["scope"] and owner != reference["owner_id"]: raise ValueError("Cannot move a reference definition to another owner.")
                if payload.get("scope") and payload["scope"] != reference["scope"]:
                    override = deepcopy(reference)
                    override.update(id=uid(), scope=payload["scope"], owner_id=payload.get("owner_id"), overrides=reference.get("overrides") or reference["id"])
                    reference = override; state["references"].append(reference)
                from .compiler import validate_name
                if "token_name" in payload:
                    validate_name(payload["token_name"]); reference["token_name"] = payload["token_name"]
                if "enabled" in payload:
                    if not isinstance(payload["enabled"], bool): raise ValueError("Enabled must be boolean.")
                    reference["enabled"] = payload["enabled"]
                if "role" in payload:
                    if payload["role"] not in ("subject", "picture"): raise ValueError("Invalid image role.")
                    reference["role"] = payload["role"]
                from .reference_conditioning import reference_controls
                reference.update(reference_controls({**reference,**{key:payload[key] for key in ("conditioning_mode","latent_strength") if key in payload}}))
                if "replacement_draft" in payload:
                    _, segment = self.segment(state, payload["segment_id"])
                    segment["working_draft"] = deepcopy(payload["replacement_draft"])
                from .compiler import compile_prompt, effective_references
                # A definition edit must not create ambiguous names in another scene.
                for scene in state["scenes"]:
                    compile_prompt({}, effective_references(state["references"], scene["id"], None))
                    for segment in scene["segments"]:
                        compile_prompt({}, effective_references(state["references"], scene["id"], segment["id"]))
            elif action == "cancel":
                job = state["jobs"].get(payload.get("job_id"))
                if not job or job["status"] not in ("queued", "running", "persisting"):
                    raise ValueError("No active job to cancel.")
                job["status"] = "cancel_requested"
                job["claimed_before_cancel"] = bool(job.get("claimed_at"))
                job["updated_at"] = now()
            elif action == "resolve_cancel":
                job = state["jobs"].get(payload.get("job_id"))
                if not job or job["status"] != "cancel_requested": raise ValueError("Job is not awaiting cancellation.")
                if job.get("claimed_before_cancel"): raise ValueError("A running job must acknowledge its own cancellation.")
                job.update(status="cancelled", updated_at=now())
                job.setdefault("progress",{})["stage"]="cancelled"
            elif action == "fail_dispatch":
                job = state["jobs"].get(payload.get("job_id"))
                if not job or job["status"] != "queued":
                    raise ValueError("Only an undispatched queued job can fail dispatch.")
                job.update(status="failed", error=str(payload.get("error", "Execution dispatch failed"))[:2000], updated_at=now())
                job.setdefault("progress",{})["stage"]="failed"
            else:
                raise ValueError("Unknown project command.")
            self._commit(state)
            return deepcopy(state)

    def queue(self, revision, settings):
        from .compiler import compile_prompt, effective_references
        with self.locked():
            state = self._read()
            if revision != state["revision"]:
                raise Conflict("Project changed. Refresh before generating.")
            if any(active_job(j) for j in state["jobs"].values()):
                raise Conflict("Finish or cancel the current project job first.")
            if state.get("experiment"):
                from .experiments import verify_reused_control
                verify_reused_control(self, state)
            mode = settings.get("mode", "new")
            if mode not in ("new", "extend", "regenerate"):
                raise ValueError("Unsupported operation.")
            ref_image_size = settings.get("ref_image_size")
            if ref_image_size is None: ref_image_size = state.get("ref_image_size", "match")
            if ref_image_size not in ("match", "max"):
                raise ValueError("Reference image size must be match or max.")
            profile = settings.get("profile", "ref2va")
            if profile not in ("ref2va", "fl2va"): raise ValueError("Unsupported model profile.")
            from .image_continuation import method as continuation_method, validate as validate_image_continuation
            continuation = continuation_method(settings.get("continuation_method"))
            scene = next((s for s in state["scenes"] if s["id"] == settings.get("scene_id")), None)
            if not scene:
                raise ValueError("Select a scene.")
            requested=next((s for s in scene["segments"] if s["id"]==settings.get("segment_id")),None)
            if requested and requested.get("planned"):
                first_unfinished=next((s for s in scene["segments"] if not s.get("active_output")),None)
                if first_unfinished is not requested:
                    raise ValueError("Generate copied segments in order; finalize the preceding segment first.")
            source = None
            if mode == "extend":
                take = state["takes"].get(settings.get("source_take_id"))
                if not take:
                    raise ValueError("Select a finalized source take.")
                _, parent = self.segment(state, take["segment_id"])
                if (parent.get("active_output") or {}).get("take_id") != take["id"]:
                    raise ValueError("The continuation source must be the explicitly finalized take.")
                if take["scene_id"] != scene["id"]:
                    raise ValueError("Cross-scene continuation is not in the first slice.")
                if continuation == "latent" and take["snapshot"]["profile"]!=profile:raise ValueError("Latent continuation must keep the source generation profile.")
                source = {k: deepcopy(take[k]) for k in ("id", "segment_id", "scene_id", "latent_path", "latent_sha256", "latent_resource_id", "plan", "width", "height")}
                if not self.asset(source["latent_path"]).is_file() or digest(self.asset(source["latent_path"])) != source["latent_sha256"]:
                    raise ValueError("Source latent is missing or corrupt.")
            from .project_settings import project_resolution
            state["resolution"]=project_resolution(state)
            width,height=state["resolution"]["width"],state["resolution"]["height"]
            if (settings.get("width",width),settings.get("height",height))!=(width,height):
                raise ValueError("Generation uses the project resolution. Refresh this draft before generating.")
            if any(isinstance(v, bool) or not isinstance(v, int) or v < 256 or v > 2048 or v % 32 for v in (width, height)):
                raise ValueError("Dimensions must be multiples of 32 between 256 and 2048.")
            if source and (width, height) != (source["width"], source["height"]):
                raise ValueError("Latent continuation must use the source resolution.")
            if continuation == "last_frame" and mode != "regenerate":
                validate_image_continuation(profile, source, settings)
            if continuation == 'video_reference' and mode != 'regenerate':
                from .video_continuation import validate as validate_video
                validate_video(profile, source, settings)
            image_motion=settings.get("image_motion_frames",0) if continuation=="last_frame" else 0
            context = settings.get("context", 39) if source and continuation == "latent" else image_motion
            plan = duration(settings.get("seconds", 5), context, video_only=bool(image_motion))
            if source and source["plan"]["sampled_frames"] < context:
                raise ValueError("The source is shorter than the requested motion context.")
            seed = settings.get("seed", 1)
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFFFFFFFFFF:
                raise ValueError("Seed must be an unsigned 64-bit integer.")
            target_id = settings.get("segment_id")
            if not target_id and scene["segments"] and not scene["segments"][-1].get("active_output"):
                target_id = scene["segments"][-1]["id"]
            refs=effective_references(state["references"], scene["id"], target_id)
            if continuation=="last_frame" and profile=="ref2va":
                from .image_continuation import compile_with_frame, preview_source
                compiled=compile_with_frame(settings.get("fields", {}), refs, source if mode!="regenerate" else preview_source(state,settings))
            elif continuation=='video_reference':
                compiled=None
            else:
                compiled=compile_prompt(settings.get("fields", {}), refs)
            if continuation=='video_reference':
                from .video_continuation import compile_with_video
                from .image_continuation import preview_source
                compiled=compile_with_video(settings.get('fields',{}), refs, source if mode!='regenerate' else preview_source(state,settings))
            if settings.get("profile", "ref2va") == "ref2va" and not compiled["images"] and continuation!='video_reference':
                raise ValueError("REF2VA requires at least one enabled project, scene or segment image reference.")
            if profile == "fl2va" and compiled["images"]:
                raise ValueError("Exclude reference assets for this segment before using FL2VA text mode.")
            if not compiled["authored_fields"]["detailed_description"].strip():
                raise ValueError("Write a shot description before generating.")
            if mode == "regenerate":
                target_scene, segment = self.segment(state, settings.get("segment_id"))
                if target_scene["id"] != scene["id"]: raise ValueError("Regeneration target must belong to the selected scene.")
                require_tail(scene, segment)
                # Regenerate restores the original source, not the segment's own final frame.
                previous = state["takes"].get((segment.get("active_output") or {}).get("take_id"))
                if not previous:
                    raise ValueError("Finalize a take before regenerating it.")
                if previous["snapshot"]["profile"]!=profile:raise ValueError("Replacement must keep the original generation profile.")
                if continuation != previous["snapshot"].get("continuation_method", "latent"):
                    raise ValueError("Replacement must keep the original continuation method.")
                if image_motion!=previous["snapshot"].get("image_motion_frames",0):
                    raise ValueError("Replacement must keep its original image motion context.")
                source = deepcopy(previous["snapshot"].get("source"))
                plan = duration(settings.get("seconds", 5), previous["plan"]["context_frames"], video_only=bool(image_motion))
                if source and (width, height) != (source["width"], source["height"]):
                    raise ValueError("Regeneration must keep source geometry.")
                if source and (not self.asset(source["latent_path"]).is_file() or digest(self.asset(source["latent_path"])) != source["latent_sha256"]):
                    raise ValueError("Original regeneration source is missing or corrupt.")
            elif target_id:
                target_scene, segment = self.segment(state, target_id)
                if target_scene["id"] != scene["id"] or segment.get("active_output"):
                    raise ValueError("Generation target must be an unfinished segment in this scene.")
                require_tail(scene, segment)
            else:
                if scene["segments"] and (not source or source["segment_id"] != scene["segments"][-1]["id"]):
                    raise ValueError("Add segments by extending the finalized scene tail.")
                segment = blank_segment(scene["id"], len(scene["segments"]) + 1, settings)
                scene["segments"].append(segment)
            index = scene["segments"].index(segment)
            if mode == "new" and index != 0:
                raise ValueError("Only the first segment starts independently; extend the scene tail to add footage.")
            if mode == "extend" and (index == 0 or source["segment_id"] != scene["segments"][index - 1]["id"]):
                raise ValueError("An extension must continue the preceding finalized scene segment.")
            if continuation == "last_frame":
                validate_image_continuation(profile, source, settings)
                plan["mask_profile"] = "ref2va_picture_first_frame_v1" if profile=="ref2va" else "first_frame_keyframe_v1"
                if image_motion:plan["mask_profile"]="picture_short_video_context_v1"
                plan["boundary_frame_delivery"] = "included"
            if continuation=='video_reference':
                from .video_continuation import validate as validate_video
                validate_video(profile,source,settings,plan)
                plan['mask_profile']='ref2va_video_reference_v1'
            from .configuration import freeze_configuration
            configuration = freeze_configuration(settings.get("configuration"))
            if configuration is not None and configuration["profile"] != profile:
                raise ValueError("Selected configuration mode differs from the segment generation mode.")
            defaults = state.get("generation_defaults")
            if defaults and settings.get("configuration_override") is not True:
                if configuration is None or configuration["id"] != defaults["configuration_id"]:
                    raise ValueError("Generation must follow production defaults unless a segment override is enabled. Refresh generation settings.")
                selected = dict(configuration.get("switch_values", {}))
                if configuration.get("selector_id") is not None:
                    selected[configuration["selector_id"]] = configuration["slot"]
                if any(defaults["selections"].get(key) != value for key,value in selected.items()):
                    raise ValueError("Generation switches differ from production defaults. Refresh generation settings or enable a segment override.")
            from .continuation_evidence import edge_policy
            decode_edge = edge_policy(settings.get("decode_edge_frames", 0), source, plan)
            plan["edge_correction"] = decode_edge["policy"]
            snapshot = {"version": 1, "continuation_method": continuation, "image_motion_frames":image_motion,"configuration": configuration, "operation": mode, "source": source, "plan": plan, "width": width, "height": height,
                        "seed": seed, "ref_image_size": ref_image_size, "compiled": compiled, "profile": settings.get("profile", "ref2va"), "mh3_reviewed_revision": PIN, "drift": decode_edge["policy"], "decode_edge": decode_edge, "auto_frame": False, "prompt_timing": "authored"}
            from .loras import effective_loras
            snapshot["loras"]=effective_loras(state,scene["id"],segment["id"])
            from .anti_burn import freeze as freeze_anti_burn
            snapshot["anti_burn"] = freeze_anti_burn(scene, settings, source, snapshot["loras"])
            from .pdd_warmup import freeze as freeze_pdd_warmup
            snapshot["pdd_warmup"] = freeze_pdd_warmup(settings.get("pdd_warmup"))
            from .refine import freeze as freeze_refine
            anchor_take = state["takes"].get((scene["segments"][0].get("active_output") or {}).get("take_id"))
            snapshot["refine"] = freeze_refine(settings.get("refine"), source, anchor_take)
            from .drift import freeze as freeze_protection
            anchor_take = state["takes"].get((scene["segments"][0].get("active_output") or {}).get("take_id"))
            snapshot["continuation_protection"] = freeze_protection(settings.get("continuation_protection"), source, plan, anchor_take, snapshot["refine"]["applied"])
            if snapshot["continuation_protection"]["applied"]:
                plan["mask_profile"] = "drift_control_av_v1" if snapshot["continuation_protection"]["drift_control"] else "hard_av_color_prefix_v1"
            job = {"id": uid(), "scene_id": scene["id"], "segment_id": segment["id"], "status": "queued", "snapshot": snapshot,
                   "snapshot_sha256": fingerprint(snapshot), "created_at": now(), "updated_at": now(), "error": None,
                   "progress": {"stage":"queued","updated_at":now(),"history":[{"stage":"queued","at":now()}]}}
            state["jobs"][job["id"]] = job
            segment["working_draft"] = deepcopy(settings)
            if state.get("generation_defaults") and settings.get("configuration_override") is not True:
                # Effective settings belong in the immutable take snapshot. An
                # inherited draft must continue tracking later production defaults.
                segment["working_draft"]["configuration_override"] = False
                for key in ("configuration_id", "switch_selections", "configuration"):
                    segment["working_draft"].pop(key, None)
            segment.pop("planned",None)
            self._commit(state)
            return deepcopy(state), deepcopy(job)

    def claim(self, job_id):
        with self.locked():
            state = self._read(); job = state["jobs"].get(job_id)
            if not job or job["status"] != "queued":
                raise Conflict("Job is no longer queued; it cannot execute twice.")
            if fingerprint(job["snapshot"]) != job["snapshot_sha256"]:
                raise ValueError("Job snapshot changed after queueing.")
            scene, segment = self.segment(state, job["segment_id"])
            require_tail(scene, segment)
            job.update(status="running", claimed_at=now(), updated_at=now())
            job["progress"]={"stage":"preparing_references","updated_at":now(),"history":[*(job.get("progress") or {}).get("history",[]),{"stage":"preparing_references","at":now()}]}
            self._commit(state)
            return deepcopy(job)

    def stage(self, job_id, stage, *, prompt_id=None, value=None, maximum=None, dispatch=False, message=None):
        phases=("queued","loading_models","preparing_references","encoding","preparing_continuation","preparing_protection","warming_up","sampling","refining","saving_latent","decoding","saving_media","building_preview","complete","preview_failed","failed","cancelled")
        if stage not in phases:raise ValueError("Unknown generation stage.")
        with self.locked():
            state=self._read();job=state["jobs"].get(job_id)
            if not job:raise ValueError("Generation job not found.")
            if dispatch:
                if not isinstance(prompt_id,str) or not prompt_id or len(prompt_id)>128:raise ValueError("A ComfyUI prompt ID is required.")
                if job.get("prompt_id") and job["prompt_id"]!=prompt_id:raise Conflict("Progress belongs to another ComfyUI prompt.")
                if job["status"] not in ("queued","running","persisting","succeeded"):return
                job["prompt_id"]=prompt_id
                if (stage=="loading_models" and job["status"]!="queued") or (stage=="queued" and (job.get("progress") or {}).get("stage")!="queued"):
                    self._commit(state);return
                if stage=="sampling" and (job.get("progress") or {}).get("stage")!="sampling":return
            if job["status"] in ("failed","cancelled"):return
            progress=job.setdefault("progress",{})
            if progress.get("stage")!=stage:
                progress.setdefault("history",[]).append({"stage":stage,"at":now()})
                progress.pop("value",None);progress.pop("max",None)
            progress.update(stage=stage,updated_at=now())
            if message is not None:progress["message"]=str(message)[:2000]
            if value is not None:
                if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (value,maximum)) or not 0<=value<=maximum or maximum<=0:raise ValueError("Invalid sampling progress.")
                progress.update(value=value,max=maximum)
            job["updated_at"]=now();self._commit(state)

    def execution_ended(self, job_id, prompt_id, status, message):
        """Apply a terminal ComfyUI result only to the matching prompt."""
        if status not in ("cancelled", "failed"):
            raise ValueError("Invalid execution result.")
        with self.locked():
            state = self._read(); job = state["jobs"].get(job_id)
            if not job or job.get("prompt_id") != prompt_id:
                raise Conflict("Execution result belongs to another ComfyUI prompt.")
            if job["status"] == "succeeded":
                if (job.get("progress") or {}).get("stage") not in ("decoding", "saving_media", "building_preview"):
                    return
                # The latent take was already published. Preserve it and unlock
                # the UI, marking only its unfinished preview as failed.
                stage = "preview_failed"
            elif job["status"] in ("queued", "running", "persisting", "cancel_requested") or (job["status"] == "failed" and status == "cancelled"):
                job["status"] = status
                job["error"] = str(message)[:4000]
                stage = status
            else:
                return
            progress = job.setdefault("progress", {})
            progress.update(stage=stage, message=str(message)[:2000], updated_at=now())
            progress.setdefault("history", []).append({"stage": stage, "at": now()})
            job["updated_at"] = now()
            self._commit(state)

    def cancelled(self, job_id):
        return self.load()["jobs"][job_id]["status"] == "cancel_requested"

    def fail(self, job_id, error, *, cancelled=False):
        with self.locked():
            state = self._read(); job = state["jobs"][job_id]
            if job["status"] == "succeeded":
                return
            job.update(status="cancelled" if cancelled or job["status"] in ("cancel_requested", "cancelled") else "failed", error=str(error)[:4000], updated_at=now())
            job.setdefault("progress", {}).update(stage=job["status"], updated_at=now())
            self._commit(state)

    def complete(self, job_id, artifact, receipt):
        with self.locked():
            state = self._read(); job = state["jobs"][job_id]
            if job["status"] == "cancel_requested":
                raise Conflict("Cancelled result retained on disk but not attached as a completed take.")
            if job["status"] != "running":
                raise Conflict("Only this running job can publish its result.")
            path = self.asset(artifact["latent_path"])
            if not path.is_file() or digest(path) != artifact["latent_sha256"]:
                raise ValueError("Latent publication failed verification.")
            _, segment = self.segment(state, job["segment_id"])
            snap = deepcopy(job["snapshot"])
            take = {"id": artifact["take_id"], "scene_id": job["scene_id"], "segment_id": segment["id"],
                    "job_id": job_id, "number": len(segment["takes"]) + 1, "snapshot": snap, "receipt": receipt,
                    "plan": snap["plan"], "width": snap["width"], "height": snap["height"],
                    "latent_path": artifact["latent_path"], "latent_sha256": artifact["latent_sha256"],
                    "latent_resource_id": artifact["latent_resource_id"], "created_at": now()}
            journal = self.path / "transactions" / f"{job_id}.json"
            atomic_json(journal, {"job_id": job_id, "take": take})
            state["takes"][take["id"]] = take; segment["takes"].append(take["id"])
            job.update(status="succeeded", take_id=take["id"], updated_at=now())
            job["progress"]={"stage":"decoding","updated_at":now(),"history":[*(job.get("progress") or {}).get("history",[]),{"stage":"decoding","at":now()}]}
            self._commit(state)
            journal.unlink(missing_ok=True)
            return deepcopy(take)

    def recover(self):
        """Called once at backend startup, never when a browser merely refreshes."""
        with self.locked():
            state = self._read(); changed = False
            for journal in (self.path / "transactions").glob("*.json"):
                record = json.loads(journal.read_text(encoding="utf-8")); take = record["take"]
                job = state["jobs"].get(record["job_id"])
                if job and self.asset(take["latent_path"]).is_file() and digest(self.asset(take["latent_path"])) == take["latent_sha256"]:
                    _, segment = self.segment(state, take["segment_id"])
                    state["takes"].setdefault(take["id"], take)
                    if take["id"] not in segment["takes"]: segment["takes"].append(take["id"])
                    job.update(status="succeeded", take_id=take["id"], updated_at=now()); changed = True
                    journal.unlink()
            for job in state["jobs"].values():
                if job["status"]=="succeeded" and (job.get("progress") or {}).get("stage") in ("decoding","saving_media","building_preview"):
                    preview=self.preview(job.get("take_id","")) or {}
                    job["progress"]["stage"]="complete" if preview.get("status")=="ready" else "preview_failed"; changed=True
                if job["status"] in ("queued", "running", "persisting", "cancel_requested"):
                    job.update(status="failed", error="Execution interrupted by backend restart. Saved takes remain available; generate a new attempt.", updated_at=now())
                    changed = True
            if changed: self._commit(state)

    def preview(self, take_id):
        path = self.asset(f"takes/{take_id}/preview.json")
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def view(self):
        state = self.load()
        from .project_settings import project_resolution
        state["resolution"]=project_resolution(state)
        from .compiler import effective_references
        state["effective_references"] = {segment["id"]: effective_references(state["references"], scene["id"], segment["id"])
            for scene in state["scenes"] for segment in scene["segments"]}
        for take in state["takes"].values():
            take["preview"] = self.preview(take["id"])
        return state
