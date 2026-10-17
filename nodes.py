import json
from .timeline_core.store import Store
from .timeline_core.routes import projects_root


class LongCasterTimelineExecute:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",), "video_vae": ("VAE",), "audio_vae": ("VAE",),
            "model_mode": (["ref2va", "fl2va"], {"default": "ref2va"}),
            "request_token": ("STRING", {"default": "", "multiline": False, "tooltip": "Filled by the LongCaster app; connect external execution inputs once."})},
            "optional": {"model": ("MODEL", {"lazy": True}), "sampler": ("SAMPLER", {"lazy": True}), "sigmas": ("SIGMAS", {"lazy": True}), "configuration": ("LONGCASTER_CONFIGURATION", {"lazy": True})},
            "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result",)
    FUNCTION = "execute"
    CATEGORY = "LongCaster Timeline"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return kwargs.get("request_token", "")

    def check_lazy_status(self, request_token="", configuration=None, model=None, sampler=None, sigmas=None, prompt=None, unique_id=None, **kwargs):
        if not request_token or json.loads(request_token).get("operation") == "preview": return []
        inputs = (prompt or {}).get(str(unique_id), {}).get("inputs", {})
        if "configuration" in inputs:
            return ["configuration"] if configuration is None else []
        return [name for name, value in (("model", model), ("sampler", sampler), ("sigmas", sigmas)) if value is None and name in inputs]

    def execute(self, clip, video_vae, audio_vae, model_mode, request_token, model=None, sampler=None, sigmas=None, configuration=None, prompt=None, unique_id=None):
        if not request_token:
            return {"result": ("Open LongCaster from the app button to generate.",)}
        request = json.loads(request_token)
        if request.get("operation") == "preview":
            from .timeline_core.engine import mh3_api
            from .timeline_core.preview import build_preview
            store = Store(projects_root(), request["project_id"])
            take = store.load()["takes"][request["take_id"]]
            from .timeline_core.store import active_job, atomic_json
            if any(active_job(job) for job in store.load()["jobs"].values()):raise ValueError("Finish current generation before rebuilding a preview.")
            try:
                build_preview(store, take, video_vae, audio_vae, mh3_api(),on_stage=lambda phase:store.stage(take["job_id"],phase))
                store.stage(take["job_id"],"complete")
            except Exception as exc:
                atomic_json(store.asset(f"takes/{take['id']}/preview.json"),{"status":"failed","source_sha256":take["latent_sha256"],"error":str(exc)})
                store.stage(take["job_id"],"preview_failed",message=str(exc))
                raise
            result = {"project_id": request["project_id"], "take_id": take["id"], "status": "preview_ready"}
        else:
            from .timeline_core.engine import execute
            if configuration is not None:
                model, sampler, sigmas = (configuration[key] for key in ("model", "sampler", "sigmas"))
                model_mode = configuration["metadata"]["profile"]
            if any(value is None for value in (model, sampler, sigmas)):
                raise ValueError("Connect a configuration, or direct MODEL, SAMPLER and SIGMAS inputs.")
            result = execute(projects_root(), request["project_id"], request["job_id"], model, sampler, sigmas, clip,
                             video_vae, audio_vae, model_mode, graph=prompt, execution_id=unique_id,
                             configuration=configuration["metadata"] if configuration is not None else None)
        return {"ui": {"longcaster_timeline": [result]}, "result": (json.dumps(result),)}
