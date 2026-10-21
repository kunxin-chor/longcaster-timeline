"""Isolated continuation experiments. No generation or acceptance at import time."""
from copy import deepcopy
import shutil

from .store import Store, Conflict, active_job, atomic_json, digest, fingerprint, now, uid
from .configuration import configuration_difference

TREATMENTS = ("control", "h3_refine")
PROTECTION_TREATMENTS = ("drift_control", "color_stable", "drift_color")


def treatment_selection(value=None):
    if value is None: return ["h3_refine"]  # Older comparison clients.
    if not isinstance(value,list) or not value or len(value)>4 or any(not isinstance(v,str) or v not in ("h3_refine",*PROTECTION_TREATMENTS) for v in value) or len(set(value))!=len(value):
        raise ValueError("Select one or more distinct supported comparison treatments.")
    return list(value)


def experiment_plan(source, scene_id, count=4, generation_configuration=None, reuse_control=False, treatments=None):
    treatments = treatment_selection(treatments)
    if not isinstance(reuse_control, bool):
        raise ValueError("Reuse existing control must be a boolean.")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 12:
        raise ValueError("Choose 1-12 continuations per treatment.")
    state = source.load()
    if any(active_job(j) for j in state["jobs"].values()):
        raise Conflict("Finish the baseline generation before preparing experiments.")
    scene = next((s for s in state["scenes"] if s["id"] == scene_id), None)
    if not scene or not scene["segments"]: raise ValueError("Select a baseline scene.")
    root = state["takes"].get((scene["segments"][0].get("active_output") or {}).get("take_id"))
    if not root or root["snapshot"].get("source"):
        raise ValueError("Finalize an independently generated first segment as the common starting take.")
    _check_take(source, root)
    examples = []
    for segment in scene["segments"][1:]:
        take = state["takes"].get((segment.get("active_output") or {}).get("take_id"))
        if not take: break
        if not take["snapshot"].get("source"): raise ValueError("Baseline continuation is missing its source.")
        examples.append((segment, take))
    if not examples: raise ValueError("The baseline needs at least one finalized continuation to supply its exact prompt and seed.")
    from .compiler import compile_prompt, effective_references
    from .loras import effective_loras
    configuration = examples[0][1]["snapshot"].get("configuration")
    if configuration is None:
        raise ValueError("Experiments require a named configuration so upstream choices can be verified before every generation.")
    steps = []
    previous = root
    for segment, take in examples:
        _check_take(source, take)
        snap = take["snapshot"]
        if snap["source"]["id"] != previous["id"] or snap["source"]["latent_sha256"] != previous["latent_sha256"]:
            raise ValueError("Baseline selected takes do not form one continuous finalized chain.")
        if configuration_difference(configuration, snap.get("configuration")):
            raise ValueError("Baseline continuations use different configurations; choose a controlled baseline.")
        if (snap.get("anti_burn") or {}).get("applied") or (snap.get("refine") or {}).get("applied") or (snap.get("continuation_protection") or {}).get("applied") or (snap.get("decode_edge") or {}).get("frames"):
            raise ValueError("Use an untreated baseline without Anti-Burn, refinement, continuation protection or seam correction.")
        if effective_loras(state, scene_id, segment["id"]) != snap.get("loras", []):
            raise ValueError("Baseline LoRA settings have changed since generation. Restore them before comparison.")
        fields = snap["compiled"]["authored_fields"]
        current = compile_prompt(fields, effective_references(state["references"], scene_id, segment["id"]))
        if current["prompt"] != snap["compiled"]["prompt"] or fingerprint(current["images"]) != fingerprint(snap["compiled"]["images"]):
            raise ValueError("Baseline reference definitions have changed since generation. Restore them before comparison.")
        steps.append({"template_segment_id": segment["id"], "template_take_id": take["id"],
            "settings": {"profile": snap["profile"], "seconds": snap["plan"]["requested_seconds"],
                "context": snap["plan"]["context_frames"], "seed": snap["seed"], "fields": deepcopy(fields),
                "width": snap["width"], "height": snap["height"], "ref_image_size": snap.get("ref_image_size", "match"),
                "decode_edge_frames": 0, "anti_burn": {"mode": "off"}}})
        previous = take
    selected = [deepcopy(steps[min(i, len(steps)-1)]) for i in range(count)]
    if any(t in PROTECTION_TREATMENTS for t in treatments) and any(s["settings"]["context"]!=39 for s in selected):
        raise ValueError("Drift Control and Color Stable comparisons currently require a 39-frame context.")
    from .configuration import freeze_configuration
    selected_configuration = freeze_configuration(generation_configuration) if generation_configuration is not None else configuration
    if selected_configuration["profile"] != root["snapshot"]["profile"]:
        raise ValueError("Comparison configuration must keep the starting take's model profile.")
    changed = bool(configuration_difference(configuration, selected_configuration))
    existing_control = None
    if reuse_control:
        if changed:
            raise ValueError("Existing controls use a different generation configuration. Select their saved configuration, or turn off Reuse existing control to generate a matching control.")
        if count > len(examples):
            raise ValueError(f"Only {len(examples)} finalized control continuations exist. Reduce the count, or turn off Reuse existing control to generate a longer control.")
        existing_control = {"project_id": state["id"], "scene_id": scene_id, "revision": state["revision"],
            "continuations": count, "takes": [{"id": take["id"], "segment_id": take["segment_id"],
                "latent_sha256": take["latent_sha256"]} for take in [root, *(take for _,take in examples[:count])]]}
    return {"version": 1, "baseline_id": state["id"], "baseline_revision": state["revision"],
        "scene_id": scene_id, "seed_take_id": root["id"], "seed_sha256": root["latent_sha256"],
        "configuration": selected_configuration, "baseline_configuration": configuration,
        "configuration_changed": changed, "reuse_control": reuse_control, "existing_control": existing_control,
        "continuations": selected, "rest_seconds": 20,
        "between_treatments_seconds": 60, "repeated_last_template": max(0, count-len(steps)),
        "selected_treatments": treatments, "treatments": treatments if reuse_control else ["control",*treatments]}


def _check_take(store, take):
    archive = store.asset(take["latent_path"])
    preview = store.preview(take["id"]) or {}
    if not archive.is_file() or digest(archive) != take["latent_sha256"]:
        raise ValueError("Baseline latent archive is missing or changed.")
    if preview.get("status") != "ready" or preview.get("source_sha256") != take["latent_sha256"] or not store.asset(preview.get("path", "")).is_file():
        raise ValueError("Baseline preview must be ready and match its latent archive.")
    if (take.get("receipt", {}).get("continuation_check") or {}).get("passed") is False:
        raise ValueError("Baseline failed protected-context verification.")


def create_comparison(source, scene_id, count, revision, generation_configuration=None, reuse_control=False, treatments=None):
    # Lock the baseline through validation and copying; publish each copy last.
    with source.locked():
        original = source._read()
        if revision != original["revision"]: raise Conflict("Baseline changed; review the experiment again.")
        # Store locks are reentrant, but the OS file lock isn't: use a read-only
        # snapshot facade while the owning lock is already held.
        class Snapshot:
            load = lambda self: deepcopy(original)
            asset = source.asset
            preview = source.preview
        plan = experiment_plan(Snapshot(), scene_id, count, generation_configuration, reuse_control, treatments)
        group_id = uid()
        created = []
        try:
            for treatment in plan["treatments"]:
                created.append(_create_arm(source, original, plan, treatment, group_id))
        except BaseException:
            # Published earlier arms remain recoverable; never alter the baseline.
            for target in created:
                with target.locked():
                    data = target._read(); data["experiment"].update(status="setup_failed", updated_at=now());target._commit(data)
            raise
    return {"id": group_id, "plan": plan, "existing_control": plan["existing_control"],
        "projects": [{"id": s.path.name, "treatment": t} for s,t in zip(created,plan["treatments"])]}


def verify_reused_control(store, state=None):
    """Reject changed/missing control selections; never queue work in the source."""
    state = state if state is not None else store.load()
    control = (state.get("experiment", {}).get("plan") or {}).get("existing_control")
    if not control: return
    source = Store(store.root, control["project_id"])
    baseline = source.load()
    scene = next((s for s in baseline["scenes"] if s["id"] == control["scene_id"]), None)
    if not scene or len(scene["segments"]) < len(control["takes"]):
        raise ValueError("Reused control scene is missing or shortened. Stop and check the comparison again.")
    for segment, expected in zip(scene["segments"],control["takes"]):
        selected = (segment.get("active_output") or {}).get("take_id")
        take = baseline["takes"].get(selected)
        if segment["id"] != expected["segment_id"] or selected != expected["id"] or not take or take["latent_sha256"] != expected["latent_sha256"]:
            raise ValueError("Reused control selection changed. Stop and check the comparison again.")
        _check_take(source, take)


def _create_arm(source, original, plan, treatment, group_id):
    target = Store(source.root, uid())
    root = deepcopy(original["takes"][plan["seed_take_id"]])
    scene = deepcopy(next(s for s in original["scenes"] if s["id"] == plan["scene_id"]))
    seed_segment = deepcopy(scene["segments"][0]);seed_segment["takes"] = [root["id"]]
    seed_segment["working_draft"] = {};scene["segments"] = [seed_segment]
    scene["anti_burn"] = {"enabled": False, "strength": .5}
    result = {**deepcopy(original), "id": target.path.name,
        "name": f'{original["name"][:80]} — {treatment}', "revision": 1,
        "created_at": now(), "updated_at": now(), "scenes": [scene], "jobs": {}, "takes": {root["id"]: root}}
    result.pop("generation_defaults", None)
    result.pop("deleted", None)
    records = []
    for index, step in enumerate(plan["continuations"], 2):
        segment_id = uid()
        draft = {**deepcopy(step["settings"]), "scene_id": scene["id"], "segment_id": segment_id,
            "source_segment_id": scene["segments"][-1]["id"], "mode": "extend",
            "configuration_override": True, "refine": {"enabled": treatment == "h3_refine", "steps": 2},
            "continuation_protection": treatment if treatment in PROTECTION_TREATMENTS else "off"}
        scene["segments"].append({"id": segment_id, "name": f"Segment {index:02d}", "takes": [],
            "active_output": None, "working_draft": draft, "planned": True})
        records.append((step["template_segment_id"], segment_id))
    # Preserve root IDs and relative assets for the immutable common starting
    # take. Clone segment-scoped resources for each new continuation target.
    for key in ("references", "loras"):
        source_records = original.get(key, [])
        result[key] = [deepcopy(r) for r in source_records if r["scope"] == "project" or
            (r["scope"] == "scene" and r["owner_id"] == scene["id"]) or
            (r["scope"] == "segment" and r["owner_id"] == seed_segment["id"])]
        for old_id, new_id in records:
            for record in source_records:
                if record["scope"] == "segment" and record["owner_id"] == old_id:
                    copied = deepcopy(record);copied["owner_id"] = new_id
                    if key == "references": copied["id"] = uid()
                    result[key].append(copied)
    result["experiment"] = {"id": group_id, "treatment": treatment, "status": "prepared", "plan": deepcopy(plan),
        "technical_acceptance_only": True, "accepted_take_ids": [], "updated_at": now()}
    target.path.mkdir(parents=True, exist_ok=False)
    # No recursive delete: clean up only files created by this operation.
    copied_files = []
    try:
        relative_files = {r["asset_path"] for r in result["references"]}
        root_dir = source.asset(f'takes/{root["id"]}')
        for p in root_dir.rglob("*"):
            if p.is_symlink() or not p.resolve().is_relative_to(root_dir): raise ValueError("External take asset link refused.")
            if p.is_file(): relative_files.add(p.relative_to(source.path).as_posix())
        for relative in sorted(relative_files):
            src = source.asset(relative);dest = target.asset(relative)
            dest.parent.mkdir(parents=True, exist_ok=True);copied_files.append(dest);shutil.copyfile(src,dest)
            if digest(src) != digest(dest): raise ValueError("Experiment asset copy failed verification.")
        atomic_json(target.manifest, result)
    except BaseException:
        for p in reversed(copied_files): p.unlink(missing_ok=True)
        for p in sorted(target.path.rglob("*"), key=lambda p:len(p.parts), reverse=True):
            if p.is_dir(): p.rmdir()
        target.path.rmdir()
        raise
    return target


def update_status(store, status, message=""):
    if status not in ("running", "resting", "stopped", "failed", "complete"):
        raise ValueError("Invalid experiment status.")
    if status == "complete": verify_reused_control(store)
    with store.locked():
        state = store._read(); record = state.get("experiment")
        if not record: raise ValueError("This production is not an experiment.")
        accepted = [s["active_output"]["take_id"] for s in state["scenes"][0]["segments"][1:] if s.get("active_output")]
        if status == "complete" and len(accepted) != len(record["plan"]["continuations"]):
            raise ValueError("Experiment still has unfinished continuations.")
        record.update(status=status, message=str(message)[:2000], accepted_take_ids=accepted, updated_at=now())
        store._commit(state)
    return {"ok": True}
