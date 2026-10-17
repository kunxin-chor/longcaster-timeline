"""Production copies, reversible deletion and stitched review exports."""
from copy import deepcopy
from pathlib import Path
import json,os,shutil,subprocess
from .store import Store,Conflict,active_job,atomic_json,now,uid,fingerprint,digest


def duplicate_complete(source,name):
    if not isinstance(name,str) or not 1<=len(name.strip())<=120:raise ValueError("Copy name must contain 1-120 characters.")
    target=Store(source.root,uid());created=[]
    with source.locked():
        original=source._read()
        if any(active_job(job) for job in original['jobs'].values()):raise Conflict("Finish generation before duplicating a production with its generations.")
        result=deepcopy(original);result.update(id=target.path.name,name=name.strip(),revision=1,created_at=now(),updated_at=now())
        result['duplicated_from']={'project_id':original['id'],'revision':original['revision'],'without_generations':False}
        target.path.mkdir(parents=True,exist_ok=False)
        try:
            for folder in ('assets','takes'):
                root=source.path/folder
                if not root.exists():continue
                for path in root.rglob('*'):
                    if path.is_symlink() or not path.resolve().is_relative_to(source.path):raise ValueError("Production contains an external asset link.")
                    if not path.is_file():continue
                    destination=target.asset(str(path.relative_to(source.path)));destination.parent.mkdir(parents=True,exist_ok=True)
                    created.append(destination);shutil.copyfile(path,destination)
            atomic_json(target.manifest,result)
            return result
        except BaseException:
            for path in reversed(created):path.unlink(missing_ok=True)
            for path in sorted(target.path.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if path.is_dir():path.rmdir()
            target.path.rmdir();raise


def delete_production(store,revision):
    with store.locked():
        original=store._read()
        if revision!=original['revision']:raise Conflict("Production changed; refresh before deleting.")
        if any(active_job(job) for job in original['jobs'].values()):raise Conflict("Finish or cancel generation before deleting a production.")
        marked=deepcopy(original);marked['deleted']=True;store._commit(marked)
    trash=store.root/'.trash';trash.mkdir(exist_ok=True)
    destination=(trash/f'{store.path.name}-{uid()}').resolve()
    if store.path.parent!=store.root or not destination.is_relative_to(trash.resolve()):raise ValueError("Invalid production deletion path.")
    try:os.replace(store.path,destination)
    except BaseException:
        with store.locked():store._commit(original)
        raise
    return {'deleted':True,'project_id':original['id']}


def export_production(store,mode):
    if mode not in ('raw','upscaled'):raise ValueError("Export mode must be raw or upscaled.")
    from .project_preview import request_project_preview
    from .preview import ffmpeg
    review=request_project_preview(store,False)
    if review['status']!='ready':return {**review,'download_url':None}
    data=store.load();resolution=data.get('upscale_resolution')
    if mode=='upscaled' and not resolution:raise ValueError("Choose an upscale export resolution first.")
    key=fingerprint({'review':review['key'],'mode':mode,'resolution':resolution if mode=='upscaled' else None,'version':1})
    directory=store.asset(f'exports/{key}');manifest=directory/'manifest.json'
    if manifest.exists():
        cached=json.loads(manifest.read_text(encoding='utf-8'))
        if store.asset(cached['path']).is_file():return cached
    directory.mkdir(parents=True,exist_ok=True)
    source=store.asset(review['path'])
    if mode=='raw':path=review['path']
    else:
        width,height=resolution['width'],resolution['height']
        if any(isinstance(v,bool) or not isinstance(v,int) or v%2 or not 256<=v<=8192 for v in (width,height)):raise ValueError("Invalid upscale export dimensions.")
        temporary=directory/f'.{uid()}.mp4'
        try:
            filters=f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
            result=subprocess.run([ffmpeg(),'-y','-nostdin','-hide_banner','-loglevel','error','-i',str(source),'-vf',filters,'-c:v','libx264','-preset','fast','-crf','18','-threads','2','-c:a','copy','-movflags','+faststart',str(temporary)],capture_output=True,timeout=1200)
            if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
            os.replace(temporary,directory/'movie.mp4')
        finally:temporary.unlink(missing_ok=True)
        path=f'exports/{key}/movie.mp4'
    record={'status':'ready','key':key,'path':path,'mode':mode,'method':'lanczos' if mode=='upscaled' else 'stitched_review','frames':review['frames'],'sha256':digest(store.asset(path)),
        'download_url':f'/longcaster-timeline/projects/{store.path.name}/exports/{key}'}
    atomic_json(manifest,record);return record
