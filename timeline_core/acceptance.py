"""Read-only continuation evidence report: python -m timeline_core.acceptance PROJECT_DIR."""
import json
from pathlib import Path
from .store import Store


def report(store):
    data = store.load()
    takes = []
    for take in sorted(data["takes"].values(), key=lambda t: t.get("created_at", "")):
        evidence = store.asset(f"takes/{take['id']}/continuation_evidence.json")
        saved = json.loads(evidence.read_text(encoding="utf-8")) if evidence.is_file() else {}
        snap = take["snapshot"]; receipt = take.get("receipt", {})
        source = snap.get("source") or {}
        takes.append({"take_id": take["id"], "scene_id": take["scene_id"], "segment_id": take["segment_id"],
            "source_take_id": source.get("id"), "source_sha256": source.get("latent_sha256"),
            "continuation_method": snap.get("continuation_method", "latent"), "source_conditioning": receipt.get("source"),
            "latent_sha256": take["latent_sha256"], "plan": take["plan"],
            "configuration": (snap.get("configuration") or {}).get("name", "Direct canvas inputs"),
            "context_check": receipt.get("continuation_check"), "sampling_seconds": receipt.get("sampling_seconds"), "refinement_seconds": receipt.get("refinement_seconds"), "total_sampling_seconds": receipt.get("total_sampling_seconds"), "refine": receipt.get("refine"), "cuda_memory": receipt.get("cuda_memory"),
            "decode_edge": snap.get("decode_edge", {"policy": "off", "frames": 0}), "seam": saved.get("seam")})
    selected = []
    for scene in data["scenes"]:
        frame = 0
        for segment in scene["segments"]:
            take_id = (segment.get("active_output") or {}).get("take_id")
            if not take_id: continue
            take = data["takes"][take_id]
            end = frame + take["plan"]["new_frames"]
            selected.append({"scene_id": scene["id"], "take_id": take_id,
                "video_frame_range": [frame, end], "planned_review_pcm_range_48000": [frame * 2000, end * 2000]})
            frame = end
    joins = [t for t in takes if t["source_take_id"]]
    return {"version": 1, "project_id": data["id"], "takes": takes, "finalized_timeline": selected,
        "summary": {"takes": len(takes), "continuations": len(joins),
            "verified_contexts": sum(bool((t["context_check"] or {}).get("passed")) for t in joins),
            "measured_seams": sum((t["seam"] or {}).get("status") == "measured" for t in joins)},
        "acceptance": "Human seam/appearance/audio review and 5-10 segment native A/B runs still required; metrics alone do not establish quality."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_directory", type=Path)
    args = parser.parse_args()
    project = args.project_directory.resolve()
    print(json.dumps(report(Store(project.parent, project.name)), indent=2, allow_nan=False))
