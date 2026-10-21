"""Create an independent prompt blueprint without generation artifacts."""
from copy import deepcopy
from pathlib import Path
import shutil

from .project_settings import project_resolution
from .store import FIELDS,Store,atomic_json,digest,new_scene,now,uid


def duplicate_without_generations(source, name):
    if not isinstance(name,str) or not 1<=len(name.strip())<=120:
        raise ValueError("Copy name must contain 1-120 characters.")
    original=source.load()
    project_id=uid();target=Store(source.root,project_id)
    scene_ids={scene['id']:uid() for scene in original['scenes']}
    segment_ids={segment['id']:uid() for scene in original['scenes'] for segment in scene['segments']}
    ref_ids={reference['id']:uid() for reference in original['references']}
    resolution=project_resolution(original)
    result={'schema_version':original.get('schema_version',1),'id':project_id,'name':name.strip(),
        'revision':1,'created_at':now(),'updated_at':now(),'resolution':resolution,
        'scenes':[],'references':[],'takes':{},'jobs':{},'layout':deepcopy(original.get('layout',{})),
        'duplicated_from':{'project_id':original['id'],'revision':original['revision'],'without_generations':True}}
    for field in ('fields','prompt_fields','ref_image_size'):
        if field in original:result[field]=deepcopy(original[field])
    for scene in original['scenes']:
        copied={**{k:deepcopy(scene[k]) for k in ('name','fields','prompt_fields','anti_burn') if k in scene},
            'id':scene_ids[scene['id']],'segments':[]}
        for index,segment in enumerate(scene['segments']):
            selected=original['takes'].get((segment.get('active_output') or {}).get('take_id'))
            if not selected and segment.get('takes'):selected=original['takes'].get(segment['takes'][-1])
            snapshot=(selected or {}).get('snapshot') or {}
            draft=deepcopy(segment.get('working_draft') or {})
            fields=draft.get('fields')
            if fields is None:fields=deepcopy((snapshot.get('compiled') or {}).get('authored_fields') or {key:'' for key in FIELDS})
            fields={**{key:"" for key in FIELDS},**fields}
            # Retain authored content; clear workflow choices so this blueprint
            # can be retried with the currently connected generation setup.
            for key in ('source_take_id','source_segment_id','configuration','configuration_id','switch_selections','configuration_override','take_id','job_id'):
                draft.pop(key,None)
            draft.update(scene_id=copied['id'],segment_id=segment_ids[segment['id']],mode='new' if index==0 else 'extend',
                profile=draft.get('profile',snapshot.get('profile','ref2va')),fields=fields,
                seconds=draft.get('seconds',(snapshot.get('plan') or {}).get('requested_seconds',5)),
                seed=draft.get('seed',snapshot.get('seed',1)),context=draft.get('context',39),**resolution)
            if index:draft['source_segment_id']=segment_ids[scene['segments'][index-1]['id']]
            copied['segments'].append({'id':draft['segment_id'],'name':segment['name'],'takes':[],
                'active_output':None,'working_draft':draft,'planned':True})
        if not copied['segments']:
            copied['segments']=new_scene(copied['name'])['segments']
            copied['segments'][0]['working_draft'].update(scene_id=copied['id'],**resolution)
        result['scenes'].append(copied)
    if not result['scenes']:result['scenes']=[new_scene('Scene 01')]
    result["loras"]=[]
    for item in original.get("loras",[]):
        record=deepcopy(item)
        if record["scope"]=="scene":record["owner_id"]=scene_ids[record["owner_id"]]
        elif record["scope"]=="segment":record["owner_id"]=segment_ids[record["owner_id"]]
        result["loras"].append(record)
    if original.get("upscale_resolution"):result["upscale_resolution"]=deepcopy(original["upscale_resolution"])
    # Publish project.json last: the project list never exposes a partial copy.
    target.path.mkdir(parents=True,exist_ok=False)
    created=[];copied_paths={}
    try:
        for reference in original['references']:
            record=deepcopy(reference);record['id']=ref_ids[reference['id']]
            if record['scope']=='scene':record['owner_id']=scene_ids[reference['owner_id']]
            elif record['scope']=='segment':record['owner_id']=segment_ids[reference['owner_id']]
            if record.get('overrides'):record['overrides']=ref_ids[record['overrides']]
            record.pop('logical_id',None)
            relative=reference['asset_path']
            asset=source.asset(relative)
            if not asset.is_file() or digest(asset)!=reference['asset_sha256']:
                raise ValueError(f"Reference {reference['token_name']} is missing or corrupt; copy was not created.")
            if relative not in copied_paths:
                destination=target.asset(f"assets/{record['id']}{asset.suffix}")
                destination.parent.mkdir(exist_ok=True);created.append(destination)
                shutil.copyfile(asset,destination)
                if digest(destination)!=reference['asset_sha256']:raise ValueError("Reference copy verification failed.")
                copied_paths[relative]=str(destination.relative_to(target.path)).replace('\\','/')
            record['asset_path']=copied_paths[relative]
            result['references'].append(record)
        atomic_json(target.manifest,result)
        return result
    except BaseException:
        # Remove only files created by this operation, never source project data.
        for path in created:
            if path.resolve().is_relative_to(target.path.resolve()):path.unlink(missing_ok=True)
        assets=target.path/'assets'
        if assets.exists() and not any(assets.iterdir()):assets.rmdir()
        if not any(target.path.iterdir()):target.path.rmdir()
        raise
