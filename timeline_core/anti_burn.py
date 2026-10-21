"""Optional continuation-only Anti-Burn, separate from authored LoRAs."""
import math
from pathlib import Path, PurePosixPath

FILENAME = "h3_antiburn_universal_v1.safetensors"
PLACEMENT = "after_upstream_configuration"


def scene_controls(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or not isinstance(value.get("enabled", False), bool):
        raise ValueError("Anti-Burn scene settings require an enabled boolean.")
    return {"enabled": value.get("enabled", False), "strength": strength(value.get("strength", 0.5))}


def strength(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 2:
        raise ValueError("Anti-Burn strength must be greater than 0 and at most 2.")
    return value


def segment_controls(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or value.get("mode", "inherit") not in ("inherit", "on", "off"):
        raise ValueError("Anti-Burn segment mode must be inherit, on or off.")
    result = {"mode": value.get("mode", "inherit")}
    if value.get("strength") is not None:
        result["strength"] = strength(value["strength"])
    return result


def availability():
    import folder_paths
    names = sorted(name for name in folder_paths.get_filename_list("loras")
                   if PurePosixPath(name.replace("\\", "/")).name.lower() == FILENAME.lower())
    if len(names) != 1:
        message = (f"Anti-Burn LoRA not found. Install {FILENAME} in ComfyUI's models/loras folder and refresh."
                   if not names else "Multiple Anti-Burn LoRA copies found. Keep one copy in models/loras and refresh.")
        return {"available": False, "filename": None, "expected_filename": FILENAME, "warning": message}
    path = folder_paths.get_full_path("loras", names[0])
    if not path or not Path(path).is_file():
        return {"available": False, "filename": None, "expected_filename": FILENAME,
                "warning": "Anti-Burn LoRA is listed but its file is missing. Refresh after installing it."}
    return {"available": True, "filename": names[0], "expected_filename": FILENAME, "warning": None}


def freeze(scene, settings, source, loras):
    base = scene_controls(scene.get("anti_burn"))
    override = segment_controls(settings.get("anti_burn"))
    enabled = base["enabled"] if override["mode"] == "inherit" else override["mode"] == "on"
    result = {"enabled": enabled, "mode": override["mode"], "strength": override.get("strength", base["strength"]),
              "applied": False, "reason": "disabled", "filename": None, "sha256": None, "placement": PLACEMENT}
    if not enabled:
        return result
    if not source:
        result["reason"] = "independent_start"
        return result
    found = availability()
    if not found["available"]:
        raise ValueError(found["warning"] + " Disable Anti-Burn to generate without it.")
    if any(PurePosixPath(item["filename"].replace("\\", "/")).name.lower() == FILENAME.lower() for item in loras):
        raise ValueError("Anti-Burn is already enabled in the normal LoRA list. Remove that entry before using the dedicated toggle.")
    import folder_paths
    from .store import digest
    path = folder_paths.get_full_path_or_raise("loras", found["filename"])
    result.update(applied=True, reason="continuation", filename=found["filename"], sha256=digest(path))
    return result


def apply(model, frozen):
    if not frozen or not frozen.get("applied"):
        return model, dict(frozen or {"enabled": False, "applied": False, "reason": "legacy_take"})
    import folder_paths
    from .store import digest
    from .loras import apply_loras
    path = folder_paths.get_full_path_or_raise("loras", frozen["filename"])
    if digest(path) != frozen["sha256"]:
        raise ValueError("Anti-Burn LoRA changed after queueing. Generate a fresh take.")
    model, receipt = apply_loras(model, [{"filename": frozen["filename"], "strength": frozen["strength"],
                                        "enabled": True, "scope": "segment", "owner_id": None}])
    return model, {**frozen, "sha256": receipt[0]["sha256"]}
