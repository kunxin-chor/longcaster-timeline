"""Explicit, scoped model-only LoRAs, frozen per generation."""
import math
from copy import deepcopy
from pathlib import PurePosixPath


def validate_lora(item):
    if not isinstance(item,dict):raise ValueError("LoRA definitions must be objects.")
    name=item.get("filename","")
    if not isinstance(name,str) or not name or len(name)>500 or PurePosixPath(name.replace("\\","/")).is_absolute() or ".." in PurePosixPath(name.replace("\\","/")).parts or ":" in name:
        raise ValueError("Choose an installed LoRA filename.")
    strength=item.get("strength",1.0)
    if isinstance(strength,bool) or not isinstance(strength,(int,float)) or not math.isfinite(strength) or not -2<=strength<=2:raise ValueError("LoRA strength must be between -2 and 2.")
    if not isinstance(item.get("enabled",True),bool):raise ValueError("LoRA enabled must be boolean.")
    return {"filename":name,"strength":strength,"enabled":item.get("enabled",True)}


def effective_loras(state,scene_id,segment_id):
    result={}
    for scope,owner in (("project",None),("scene",scene_id),("segment",segment_id)):
        for item in state.get("loras",[]):
            if item["scope"]==scope and item.get("owner_id")==owner:
                normalized=validate_lora(item);result[normalized["filename"]]={**deepcopy(item),**normalized}
    return [item for item in result.values() if item["enabled"] and item["strength"]!=0]


def apply_loras(model,items):
    if not items:return model,[]
    import folder_paths,comfy.utils,comfy.sd
    from .store import digest
    receipt=[]
    for item in items:
        clean=validate_lora(item)
        path=folder_paths.get_full_path_or_raise("loras",clean["filename"])
        weights=comfy.utils.load_torch_file(path,safe_load=True)
        model,_=comfy.sd.load_lora_for_models(model,None,weights,clean["strength"],0)
        receipt.append({**clean,"sha256":digest(path),"scope":item["scope"],"owner_id":item.get("owner_id")})
    return model,receipt
