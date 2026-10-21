"""Per-image diffusion reference strength; text-encoder image presentation stays native."""
import math


def reference_controls(reference):
    mode=reference.get("conditioning_mode","image")
    strength=reference.get("latent_strength",100)
    if mode not in ("image","latent"):raise ValueError("Reference conditioning mode must be image or latent.")
    if isinstance(strength,bool) or not isinstance(strength,(int,float)) or not math.isfinite(strength) or not 0<=strength<=100:
        raise ValueError("Latent strength must be a finite percentage from 0 to 100.")
    if mode=="latent" and reference.get("kind")!="image":raise ValueError("Latent strength is supported for image references only.")
    return {"conditioning_mode":mode,"latent_strength":strength}


def scale_reference_conditioning(positive,references):
    controls=[reference_controls(item) for item in references]
    if not any(item["conditioning_mode"]=="latent" for item in controls):return positive
    output=[]
    for embedding,metadata in positive:
        blocks=metadata.get("minimax_refs")
        if not isinstance(blocks,list) or len(blocks)<len(references) or any(block.get("kind")!="image" or block.get("latent") is None for block in blocks[:len(references)]) or any(block.get("kind") not in ("video","video_audio","audio") for block in blocks[len(references):]):
            raise ValueError("Native H3 image reference payload changed; cannot safely match latent controls to source images.")
        transformed=[]
        for index,(block,reference,control) in enumerate(zip(blocks,references,controls)):
            if reference.get("native_label")!=f"<Picture {index+1}>":raise ValueError("Frozen image reference order is inconsistent.")
            item=dict(block)
            if control["conditioning_mode"]=="latent" and control["latent_strength"]!=100:
                item["latent"]=block["latent"]*(control["latent_strength"]/100)
            transformed.append(item)
        output.append([embedding,{**metadata,"minimax_refs":[*transformed,*blocks[len(references):]]}])
    return output
