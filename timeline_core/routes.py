from copy import deepcopy
import io
import json
from pathlib import Path
import uuid

import folder_paths
from aiohttp import web
from server import PromptServer
from .store import Store, Conflict, atomic_json, digest, uid
from .compiler import compile_prompt, effective_references, validate_name

APP = Path(__file__).resolve().parents[1] / "web" / "app"
_registered = False


def projects_root():
    root = Path(folder_paths.get_output_directory()) / "LongCasterTimeline"
    root.mkdir(parents=True, exist_ok=True)
    return root


def error(exc):
    return web.json_response({"error": str(exc)}, status=409 if isinstance(exc, Conflict) else 400)


async def list_projects(request):
    rows = []
    for path in projects_root().glob("*/project.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("deleted"):continue
            rows.append({"id": data["id"], "name": data["name"], "updated_at": data["updated_at"]})
        except (ValueError, OSError, KeyError): continue
    return web.json_response({"projects": sorted(rows, key=lambda p: p["updated_at"], reverse=True)})


async def create_project(request):
    try:
        body = await request.json(); return web.json_response(Store.create(projects_root(), body.get("name", "Untitled production")))
    except (ValueError, OSError, KeyError) as exc: return error(exc)


async def duplicate_project(request):
    try:
        import asyncio
        from .duplicate import duplicate_without_generations
        from .production import duplicate_complete
        body=await request.json();source=Store(projects_root(),request.match_info["project"])
        # Reference copies and hash verification must not block ComfyUI's event loop.
        result=await asyncio.to_thread(duplicate_without_generations if body.get("without_generations",True) else duplicate_complete,source,body.get("name",""))
        return web.json_response(Store(projects_root(),result["id"]).view())
    except (ValueError,OSError,KeyError) as exc:return error(exc)


async def state(request):
    try:
        store = Store(projects_root(), request.match_info["project"])
        from .execution_status import reconcile
        reconcile(store, PromptServer.instance.prompt_queue)
        return web.json_response(store.view())
    except (ValueError, OSError, KeyError) as exc: return error(exc)


async def command(request):
    try:
        body = await request.json(); store = Store(projects_root(), request.match_info["project"])
        store.command(body.get("revision"), body.get("action"), body)
        return web.json_response(store.view())
    except (ValueError, OSError, KeyError) as exc: return error(exc)


async def queue(request):
    try:
        body = await request.json(); store = Store(projects_root(), request.match_info["project"])
        # Reject a missing/incompatible adapter before ComfyUI loads large models.
        from .engine import mh3_api
        mh3_api()
        result, job = store.queue(body.get("revision"), body.get("settings", {}))
        return web.json_response({"state": store.view(), "job": job})
    except (ValueError, RuntimeError, ImportError, OSError, KeyError) as exc: return error(exc)


async def compile_route(request):
    try:
        body = await request.json(); store = Store(projects_root(), request.match_info["project"]); data = store.load()
        refs = effective_references(data["references"], body.get("scene_id"), body.get("segment_id"))
        return web.json_response(compile_prompt(body.get("fields", {}), refs))
    except (ValueError, OSError, KeyError) as exc: return error(exc)


async def migration_preview(request):
    try:
        from .project_settings import migrate_legacy_fields
        body=await request.json();store=Store(projects_root(),request.match_info["project"]);data=store.load()
        scene,segment=store.segment(data,body["segment_id"])
        return web.json_response({"fields":migrate_legacy_fields(segment.get("working_draft",{}).get("fields",{}),effective_references(data["references"],scene["id"],segment["id"]))})
    except (ValueError,OSError,KeyError) as exc:return error(exc)


async def generation_progress(request):
    try:
        body=await request.json();stage=body.get("stage")
        if stage not in ("queued","loading_models","sampling","cancelled","failed"):raise ValueError("Unsupported bridge progress stage.")
        store=Store(projects_root(),request.match_info["project"])
        if stage in ("cancelled", "failed"):
            store.execution_ended(request.match_info["job"],body.get("prompt_id"),stage,body.get("message") or ("Generation cancelled in ComfyUI." if stage == "cancelled" else "ComfyUI execution failed."))
        else:
            store.stage(request.match_info["job"],stage,prompt_id=body.get("prompt_id"),value=body.get("value"),maximum=body.get("max"),dispatch=True)
        return web.json_response({"ok":True})
    except (ValueError,OSError,KeyError) as exc:return error(exc)


async def reference_upload(request):
    destination = None
    try:
        reader = await request.multipart(); fields = {}; blob = None
        async for part in reader:
            value = bytearray()
            while chunk := await part.read_chunk():
                value.extend(chunk)
                if len(value) > (32 * 1024 * 1024 if part.name == "file" else 10000): raise ValueError("Reference upload too large (32 MiB maximum).")
            if part.name == "file": blob = bytes(value)
            else: fields[part.name] = bytes(value).decode("utf-8")
        store = Store(projects_root(), request.match_info["project"])
        name = fields.get("token_name", ""); validate_name(name)
        scope = fields.get("scope", "project"); owner = fields.get("owner_id") or None
        if scope not in ("project", "scene", "segment"): raise ValueError("Invalid reference scope.")
        role = fields.get("role", "picture")
        if role not in ("subject", "picture"): raise ValueError("Invalid H3 image role.")
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(blob or b"")) as image:
            if image.width * image.height > 32_000_000: raise ValueError("Reference exceeds 32 megapixels.")
            normalized = ImageOps.exif_transpose(image).convert("RGB")
        with store.locked():
            data = store._read()
            if int(fields.get("revision", -1)) != data["revision"]: raise Conflict("Project changed; retry the upload.")
            if scope == "scene" and not any(s["id"] == owner for s in data["scenes"]): raise ValueError("Scene not found.")
            if scope == "segment": store.segment(data, owner)
            if scope == "project" and owner is not None: raise ValueError("Project reference has no owner ID.")
            if len(data["references"]) >= 128: raise ValueError("Project reference limit reached.")
            parent_id = fields.get("overrides")
            parent = next((r for r in data["references"] if r["id"] == parent_id), None) if parent_id else None
            if parent_id and not parent: raise ValueError("Override source not found.")
            if parent and parent["kind"]!="image":raise ValueError("Image overrides must replace an image source.")
            if parent and not any(r["id"] == parent_id for r in effective_references(data["references"], fields.get("scene_id"), fields.get("segment_id"))):
                raise ValueError("Override must replace a reference inherited by this target.")
            if parent and {"project":0,"scene":1,"segment":2}[scope] <= {"project":0,"scene":1,"segment":2}[parent["scope"]]:
                raise ValueError("Choose a narrower scope for the image override.")
            if any(r["kind"]=="image" and r["token_name"].casefold() == name.casefold() and r["scope"] == scope and r["owner_id"] == owner for r in data["references"]):
                raise ValueError("This scope already has that reference name. Use an explicit override.")
            reference_id = uid(); relative = f"assets/{reference_id}.png"; destination = store.asset(relative)
            destination.parent.mkdir(parents=True, exist_ok=True); normalized.save(destination, "PNG")
            record = {"id": reference_id, "token_name": name, "display_name": fields.get("display_name") or name, "kind": "image", "role": role,
                      "scope": scope, "owner_id": owner, "asset_path": relative, "asset_sha256": digest(destination), "enabled": True}
            from .reference_conditioning import reference_controls
            record.update(reference_controls({**record,"conditioning_mode":fields.get("conditioning_mode","image"),"latent_strength":float(fields.get("latent_strength",100))}))
            if parent: record["overrides"] = parent.get("overrides") or parent["id"]
            data["references"].append(record)
            # Validate affected effective context before publishing the upload.
            scene_id = owner if scope == "scene" else fields.get("scene_id")
            segment_id = owner if scope == "segment" else fields.get("segment_id")
            compile_prompt({}, effective_references(data["references"], scene_id, segment_id))
            for scene in data["scenes"]:
                compile_prompt({}, effective_references(data["references"], scene["id"], None))
                for segment in scene["segments"]:
                    compile_prompt({}, effective_references(data["references"], scene["id"], segment["id"]))
            store._commit(data)
        return web.json_response(store.view())
    except (ValueError, OSError, KeyError) as exc:
        if destination is not None: destination.unlink(missing_ok=True)
        return error(exc)


async def asset(request):
    try:
        store = Store(projects_root(), request.match_info["project"]); data = store.view(); item = request.match_info["item"]
        if request.match_info["kind"] == "reference":
            record = next(r for r in data["references"] if r["id"] == item); path = store.asset(record["asset_path"])
        else:
            uuid.UUID(item); take = data["takes"][item]; preview = take.get("preview") or {}
            if preview.get("status") != "ready": raise ValueError("Preview is not ready. Rebuild it from the saved latent.")
            path = store.asset(preview["path"])
        if not path.is_file(): raise ValueError("Media file missing.")
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})
    except (ValueError, OSError, KeyError, StopIteration) as exc: return error(exc)


async def page(request):
    return web.FileResponse(APP / "index.html", headers={"Cache-Control": "no-cache"})


async def project_preview(request):
    try:
        from .project_preview import request_project_preview
        body = await request.json()
        store = Store(projects_root(), request.match_info["project"])
        return web.json_response(request_project_preview(store, body.get("include_drafts", False), body.get("draft_take_id"), body.get("retry", False), scene_id=body.get("scene_id")))
    except (ValueError, RuntimeError, OSError, KeyError) as exc: return error(exc)


async def project_preview_video(request):
    try:
        from .project_preview import cached_preview
        store = Store(projects_root(), request.match_info["project"])
        record = cached_preview(store, request.match_info["key"])
        if not record: raise ValueError("Project preview is not ready.")
        return web.FileResponse(store.asset(record["path"]), headers={"Cache-Control": "private, max-age=31536000, immutable"})
    except (ValueError, OSError, KeyError) as exc: return error(exc)


async def static_asset(request):
    path = (APP / "assets" / request.match_info["name"]).resolve()
    if not path.is_relative_to(APP / "assets") or not path.is_file(): raise web.HTTPNotFound()
    return web.FileResponse(path)


async def lora_choices(request):
    return web.json_response({"filenames":folder_paths.get_filename_list("loras")})


async def delete_project(request):
    try:
        import asyncio
        from .production import delete_production
        body=await request.json();store=Store(projects_root(),request.match_info["project"])
        return web.json_response(await asyncio.to_thread(delete_production,store,body.get("revision")))
    except (ValueError,OSError,KeyError) as exc:return error(exc)


async def export_project(request):
    try:
        import asyncio
        from .production import export_production
        body=await request.json();store=Store(projects_root(),request.match_info["project"])
        return web.json_response(await asyncio.to_thread(export_production,store,body.get("mode","raw")))
    except (ValueError,RuntimeError,OSError,KeyError) as exc:return error(exc)


async def download_export(request):
    try:
        from .project_preview import KEY
        key=request.match_info["key"]
        if not KEY.fullmatch(key):raise ValueError("Invalid export key.")
        store=Store(projects_root(),request.match_info["project"]);store.load()
        record=json.loads(store.asset(f"exports/{key}/manifest.json").read_text(encoding="utf-8"))
        return web.FileResponse(store.asset(record["path"]),headers={"Content-Disposition":f'attachment; filename="longcaster-{record["mode"]}.mp4"'})
    except (ValueError,OSError,KeyError) as exc:return error(exc)


def register():
    global _registered
    server = PromptServer.instance
    if _registered or server is None: return
    routes = server.routes
    routes.get("/longcaster-timeline/app")(page)
    routes.get("/longcaster-timeline/assets/{name}")(static_asset)
    routes.get("/longcaster-timeline/loras")(lora_choices)
    routes.get("/longcaster-timeline/projects")(list_projects)
    routes.post("/longcaster-timeline/projects")(create_project)
    routes.post("/longcaster-timeline/projects/{project}/duplicate")(duplicate_project)
    routes.post("/longcaster-timeline/projects/{project}/delete")(delete_project)
    routes.post("/longcaster-timeline/projects/{project}/export")(export_project)
    routes.get("/longcaster-timeline/projects/{project}/exports/{key}")(download_export)
    routes.get("/longcaster-timeline/projects/{project}")(state)
    routes.post("/longcaster-timeline/projects/{project}/command")(command)
    routes.post("/longcaster-timeline/projects/{project}/jobs")(queue)
    routes.post("/longcaster-timeline/projects/{project}/compile")(compile_route)
    routes.post("/longcaster-timeline/projects/{project}/migration-preview")(migration_preview)
    routes.post("/longcaster-timeline/projects/{project}/jobs/{job}/progress")(generation_progress)
    routes.post("/longcaster-timeline/projects/{project}/references")(reference_upload)
    routes.post("/longcaster-timeline/projects/{project}/preview")(project_preview)
    routes.get("/longcaster-timeline/projects/{project}/preview/{key}")(project_preview_video)
    routes.get("/longcaster-timeline/projects/{project}/media/{kind}/{item}")(asset)
    for manifest in projects_root().glob("*/project.json"):
        try: Store(projects_root(), manifest.parent.name).recover()
        except Exception:
            import logging
            logging.getLogger("longcaster_timeline").exception("Could not recover project %s", manifest.parent.name)
    _registered = True
