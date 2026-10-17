"""Compile authored subjects separately from named source assets."""
import re
from copy import deepcopy
from .store import FIELDS, fingerprint
from .reference_conditioning import reference_controls

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
TOKEN = re.compile(r"<([^<>\r\n]+)>")
NATIVE = re.compile(r"(Subject|Picture|Video|Audio)\s+([1-9]\d*)\Z", re.I)
SUBJECT = re.compile(r"(?m)^\s*<Subject\s+([1-9]\d*)>[^\n]*", re.I)
TAGS = {"d", "/d", "scenetrans", "cutoff", *FIELDS, *("/"+x for x in FIELDS)}
KINDS = {"image":"picture", "video":"video", "audio":"audio"}
LABELS = {"image":"Picture", "video":"Video", "audio":"Audio"}


def validate_name(name):
    if not isinstance(name,str) or not NAME.fullmatch(name) or name.casefold() in TAGS:
        raise ValueError("Reference base name must be non-reserved and start with a letter or underscore and contain at most 64 letters, digits or underscores.")


def qualified_name(reference):
    return KINDS[reference["kind"]]+"."+reference["token_name"]


def effective_references(references, scene_id, segment_id):
    resolved={}
    for scope,owner in (("project",None),("scene",scene_id),("segment",segment_id)):
        for reference in references:
            if reference.get("scope","project")!=scope or reference.get("owner_id")!=owner: continue
            parent=reference.get("overrides")
            if parent:
                if parent not in resolved: raise ValueError("Reference override has no inherited source in this context.")
                if reference["kind"]!=resolved[parent]["kind"]: raise ValueError("Reference overrides must preserve the inherited media kind.")
                resolved[parent]={**deepcopy(reference),"logical_id":parent}
            else: resolved[reference["id"]]={**deepcopy(reference),"logical_id":reference["id"]}
    return list(resolved.values())


def compile_prompt(fields,references):
    if not isinstance(fields,dict) or set(fields)-set(FIELDS): raise ValueError("Unknown prompt field.")
    authored={name:fields.get(name,"") for name in FIELDS}
    if any(not isinstance(v,str) or len(v)>50000 for v in authored.values()): raise ValueError("Prompt fields must be text, at most 50,000 characters each.")
    names={}; legacy={}; mappings={}; images=[]; assets=[]; counts={kind:0 for kind in KINDS}
    declared=[int(m.group(1)) for m in SUBJECT.finditer(authored["subject_definitions"])]
    if len(declared)!=len(set(declared)):raise ValueError("Duplicate subject definition; define each Subject label once.")
    explicit=set(declared)
    for reference in sorted(references,key=lambda r:{"image":0,"video":1,"audio":2}.get(r.get("kind"),99)):
        validate_name(reference["token_name"])
        controls=reference_controls(reference)
        if reference["kind"] not in KINDS: raise ValueError("Unknown reference media kind.")
        key=qualified_name(reference).casefold()
        if key in names: raise ValueError(f"Ambiguous reference name: {qualified_name(reference)}")
        names[key]=reference;legacy.setdefault(reference["token_name"].casefold(),[]).append(reference)
        if not reference.get("enabled",True): continue
        kind=reference["kind"];counts[kind]+=1
        native=f"<{LABELS[kind]} {counts[kind]}>"
        # A reference is always a media asset, regardless of obsolete role metadata.
        record={**deepcopy(reference),**controls,"native_label":native,"qualified_token":key,"available":kind=="image"}
        assets.append(record)
        if kind=="image": images.append(record)
        mapping={"reference_id":reference["id"],"authored_name":qualified_name(reference),"label":native,"source_label":native,"asset_sha256":reference["asset_sha256"],"kind":kind}
        mappings[key]=mapping
    if len(images)>9: raise ValueError("H3 supports at most 9 image references.")
    def substitute(match):
        value=match.group(1);key=value.casefold()
        if key in TAGS:return match.group(0)
        native=NATIVE.fullmatch(value)
        if native:
            category=native.group(1).lower();number=int(native.group(2))
            if category=="subject":
                if number not in explicit:raise ValueError(f"Subject <Subject {number}> has no authored definition.")
                return f"<Subject {number}>"
            kind={"picture":"image","video":"video","audio":"audio"}[category]
            if number>counts[kind]: raise ValueError(f"Native label {match.group(0)} has no supplied reference.")
            if kind!="image":raise ValueError("Video/audio reference conditioning is not implemented yet; disable these sources before generation.")
            return f"<{LABELS[kind]} {number}>"
        if key in legacy and len(legacy[key])>1:
            choices=", ".join("<"+qualified_name(r)+">" for r in legacy[key])
            raise ValueError(f"Ambiguous legacy reference <{value}>; use {choices}.")
        reference=names.get(key)
        if reference and not reference.get("enabled",True):raise ValueError(f"Reference <{value}> is disabled.")
        if key in legacy:
            choices=", ".join("<"+qualified_name(r)+">" for r in legacy[key])
            raise ValueError(f"Bare reference <{value}> is not supported; use {choices} for assets. Write <Subject N> definitions and reference relationships manually.")
        if key not in mappings:raise ValueError(f"Unknown named reference <{value}>.")
        mapping=mappings[key]
        if mapping["kind"]!="image":raise ValueError("Video/audio reference conditioning is not implemented yet; disable these sources before generation.")
        return mapping["label"]
    for text in authored.values():
        if re.search(r"<(?:picture|video|audio)\.[^>\r\n]*(?:$|\n)",text,re.I):raise ValueError("Malformed qualified reference token; close it with >.")
    resolved={name:TOKEN.sub(substitute,value) for name,value in authored.items()}
    if any(authored.values()) and any(not a["available"] for a in assets):
        raise ValueError("Video/audio reference conditioning is not implemented yet; disable these sources before generation.")
    subjects=[]
    for match in SUBJECT.finditer(resolved["subject_definitions"]):
        line=match.group(0).strip()
        subjects.append({"label":f"<Subject {int(match.group(1))}>","definition":line})
    prompt="\n\n".join(f"{name}:\n{resolved[name]}" for name in FIELDS)
    return {"version":4,"authored_fields":authored,"resolved_fields":resolved,"prompt":prompt,"mappings":mappings,"images":images,
            "assets":assets,"subjects":subjects,"sha256":fingerprint({"prompt":prompt,"assets":assets})}
