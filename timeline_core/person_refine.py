"""Explicit CPU person segmentation for the experimental character refine arm."""
from pathlib import Path
import hashlib
import time

WEIGHT = 'lraspp_mobilenet_v3_large-d234d4ea.pth'
SHA256 = 'd234d4eae9d55d5f76de18b77cf0dc62c66fe5c5482758209d00f950c92bb280'


def verify_weights():
    path=Path(__file__).resolve().parents[1]/'models'/'refine_person'/WEIGHT
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('Character refine needs the verified Torchvision LRASPP person model in models/refine_person. No automatic download.')
    return path


def mask_for_latent(latent, vae, store, job_id, cancelled=lambda:False, *, context_frames=39):
    import torch
    import torch.nn.functional as F
    import numpy as np
    from PIL import Image,ImageDraw
    from torchvision.models.segmentation import lraspp_mobilenet_v3_large,LRASPP_MobileNet_V3_Large_Weights
    from .store import atomic_json
    from .vendor.h3_refine.refine_blend import whole_steps_for_frames
    head=whole_steps_for_frames(context_frames)
    if not head:raise ValueError('Character refinement requires an exact H3 token boundary.')
    path=verify_weights()
    started=time.perf_counter()
    video=latent['samples'].unbind()[0]
    frames=vae.decode(video.detach().to('cpu',copy=True).contiguous())
    if frames.ndim==5:frames=frames.reshape(-1,*frames.shape[-3:])
    if frames.ndim!=4:raise ValueError('Person masking requires decoded IMAGE frames.')
    weights=LRASPP_MobileNet_V3_Large_Weights.DEFAULT
    model=lraspp_mobilenet_v3_large(weights=None,weights_backbone=None).eval()
    model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
    person=weights.meta['categories'].index('person');transform=weights.transforms()
    masks=[];previews=[];covered=0
    with torch.inference_mode():
        for token in range(video.shape[2]):
            if cancelled():raise RuntimeError('Generation cancelled during person masking.')
            count=(1,4,4,4,4)[token%5]
            index=min(len(frames)-1,covered+count//2);covered+=count
            rgb=frames[index,:,:,:3].detach().cpu().permute(2,0,1).float().clamp(0,1)
            prediction=model(transform(rgb).unsqueeze(0))['out'].argmax(1)
            binary=(prediction==person).float().unsqueeze(1)
            resized=F.interpolate(binary,size=rgb.shape[-2:],mode='nearest')
            latent_mask=F.adaptive_max_pool2d(resized,video.shape[-2:])
            # One latent-cell expansion includes contour detail; feather only
            # inside the expanded support, so remote background stays exact.
            expanded=F.max_pool2d(latent_mask,3,stride=1,padding=1)
            feather=F.avg_pool2d(expanded,3,stride=1,padding=1)*expanded
            fraction=float((expanded>0).float().mean())
            if not .005<fraction<.65:raise RuntimeError('Person segmentation is empty or covers most of the frame; refusing a misleading masked trial.')
            masks.append(feather[0,0]);
            if token in (12,video.shape[2]//2,video.shape[2]-1):
                image=(rgb.permute(1,2,0).numpy()*255).astype(np.uint8)
                alpha=F.interpolate(feather,size=rgb.shape[-2:],mode='nearest')[0,0].numpy()[...,None]*.45
                overlay=(image*(1-alpha)+np.array([0,220,255])*alpha).clip(0,255).astype(np.uint8)
                previews.append(Image.fromarray(overlay).resize((512,288)))
    mask=torch.stack(masks).unsqueeze(0).unsqueeze(0)
    mask[:,:,:head]=0
    folder=store.asset('diagnostics/'+job_id);folder.mkdir(parents=True,exist_ok=True)
    np.save(folder/'person-mask.npy',mask.numpy())
    sheet=Image.new('RGB',(512*len(previews),310),'#101b26');draw=ImageDraw.Draw(sheet)
    for i,im in enumerate(previews):sheet.paste(im,(i*512,22))
    draw.text((5,5),'Person refine support - cyan overlay (head remains protected)',fill='white')
    sheet.save(folder/'person-mask-preview.png')
    report={'model':'torchvision/LRASPP_MobileNet_V3_Large','weights_sha256':SHA256,'device':'cpu',
        'semantic_class':'person','tokens':video.shape[2],'protected_head':head,'mean_support':float((mask>0).float().mean()),
        'seconds':time.perf_counter()-started,'mask':'diagnostics/'+job_id+'/person-mask.npy',
        'preview':'diagnostics/'+job_id+'/person-mask-preview.png','algorithm':'per_token_person_argmax_max_pool_dilate1_feather1'}
    atomic_json(folder/'person-mask.json',report)
    return mask.to(video),report
