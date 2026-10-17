"""Project-owned geometry and explicit migration of editable prompt fields."""


def validate_resolution(width, height):
    if any(isinstance(v,bool) or not isinstance(v,int) or v<256 or v>2048 or v%32 for v in (width,height)):
        raise ValueError("Project dimensions must be multiples of 32 between 256 and 2048.")
    return {"width":width,"height":height}


def project_resolution(state):
    if state.get("resolution"):return validate_resolution(**state["resolution"])
    # Existing media determines migration defaults; no latent is resized.
    for scene in state["scenes"]:
        for segment in scene["segments"]:
            take=state["takes"].get((segment.get("active_output") or {}).get("take_id"))
            if take:return validate_resolution(take["width"],take["height"])
    take=next(iter(state["takes"].values()),None)
    if take:return validate_resolution(take["width"],take["height"])
    return {"width":768,"height":448}


def migrate_legacy_fields(fields, references):
    """Convert explicit legacy asset citations only; never infer subject semantics."""
    from .compiler import TOKEN, compile_prompt, qualified_name
    names={}
    for reference in references:
        names.setdefault(reference["token_name"].casefold(),[]).append(reference)
    def convert(match):
        items=names.get(match.group(1).casefold(),[])
        if not items:return match.group(0)
        if len(items)!=1:raise ValueError("Ambiguous legacy reference; correct the prompt manually.")
        if items[0].get("role")=="subject":
            raise ValueError("Legacy subject aliases require manual correction. Use <Subject N> for subjects and typed aliases for assets; write their relationships yourself.")
        return "<"+qualified_name(items[0])+">"
    result={name:TOKEN.sub(convert,value) for name,value in fields.items()}
    compile_prompt(result,references)
    return result
