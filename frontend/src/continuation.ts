import {Settings,Configuration} from './types';

export type ContinuationMethod=NonNullable<Settings['continuation_method']>;
export type ContinuationOptions=Pick<Settings,'context'|'image_motion_frames'|'decode_edge_frames'|'continuation_protection'|'refine'>;
export type HandoffSupport='pdd'|'unsupported'|'unknown';

export function handoffSupport(configuration:Configuration|null):HandoffSupport {
 const nodes=Object.values(configuration?.upstream||{}) as {class_type?:string;inputs?:Record<string,unknown>}[];
 if(nodes.some(node=>node.class_type==='LongCasterTimelineFastH3Omni'||node.class_type==='MMH3FastH3V2Model'))return 'unsupported';
 if(nodes.some(node=>node.class_type==='MiniMaxH3PDDAccApply'&&node.inputs?.enabled!==false))return 'pdd';
 return 'unknown';
}

function options(settings:Settings):ContinuationOptions {
 return {context:settings.context,image_motion_frames:settings.image_motion_frames,decode_edge_frames:settings.decode_edge_frames,
  continuation_protection:settings.continuation_protection,refine:settings.refine?{...settings.refine}:undefined};
}

export function applicableContinuation(settings:Settings):Settings {
 const next={...settings};
 const independent=!next.source_take_id&&next.mode!=='extend';
 if(independent)next.continuation_method='latent';
 if((next.continuation_method&&next.continuation_method!=='latent')||independent){
  next.context=0;next.decode_edge_frames=0;next.continuation_protection='off';
  next.refine={...next.refine,enabled:false,steps:next.refine?.steps||2};
 }else{
  next.context=next.context||39;next.image_motion_frames=0;
  if(next.refine?.mode==='noembryo_stats')next.refine={...next.refine,model:'received'};
 }
 if(next.continuation_method!=='last_frame'||next.profile!=='ref2va'||independent)next.image_motion_frames=0;
 return next;
}

export function changeContinuation(settings:Settings,method:ContinuationMethod,sourceProfile:Settings['profile']):Settings {
 const previous=settings.continuation_method||'latent';
 const saved={...settings.continuation_options,[previous]:options(settings)};
 const defaults:ContinuationOptions={context:method==='latent'?39:0,image_motion_frames:0,decode_edge_frames:0,
  continuation_protection:'off',refine:{enabled:false,steps:2,mode:'h3_refine',model:'received'}};
 return applicableContinuation({...settings,...defaults,...saved[method],continuation_options:saved,continuation_method:method,
  profile:method==='video_reference'?'ref2va':method==='latent'?sourceProfile:settings.profile});
}
