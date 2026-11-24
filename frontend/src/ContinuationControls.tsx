import {useState} from 'react';
import {Info} from 'lucide-react';
import {Settings} from './types';
import {ContinuationMethod,HandoffSupport} from './continuation';

export function Hint({children}:{children:React.ReactNode}){
 return <span className="control-hint"><button type="button" aria-label="More information"><Info size={13}/></button><span role="tooltip">{children}</span></span>;
}
export function PddHandoff({settings,onChange,support,disabled}:{settings:Settings;onChange:(next:Settings)=>void;support:HandoffSupport;disabled:boolean}){
 const active=settings.pdd_warmup==='auto';
 if(support==='unsupported')return active?<div className="warning" role="alert">This checkpoint cannot recover a base model for PDD handoff. <button disabled={disabled} onClick={()=>onChange({...settings,pdd_warmup:'off'})}>Turn off PDD handoff</button></div>:null;
 return <label className="field-label"> <span>PDD base-model handoff <Hint>For compatible PDD-ACC models: eight base steps followed by two PDD steps. Compatibility is checked on the actual loaded model. Does not support fused Omni checkpoints.</Hint></span>
  <select aria-label="PDD base-model handoff" value={settings.pdd_warmup||'off'} disabled={disabled} onChange={event=>onChange({...settings,pdd_warmup:event.target.value as 'off'|'auto'})}>
   <option value="off">Off</option><option value="auto">On — runtime compatibility check</option>
  </select>
 </label>;
}

export function ContinuationControls({settings,onChange,onMethod,hasSource,hasTarget,sourceLabel,sourceFrames,disabled,replacement,handoff,antiBurn,antiBurnEnabled,referenceSizing}:{settings:Settings;onChange:(next:Settings)=>void;onMethod:(method:ContinuationMethod)=>void;hasSource:boolean;hasTarget:boolean;sourceLabel:string;sourceFrames:number;disabled:boolean;replacement:boolean;handoff:HandoffSupport;antiBurn:React.ReactNode;antiBurnEnabled:boolean;referenceSizing:React.ReactNode}){
 const [more,setMore]=useState(false);
 const method=settings.continuation_method||'latent';
 const latent=method==='latent';
 const refine=settings.refine||{enabled:false,steps:2,mode:'h3_refine',model:'received'};
 const protection=settings.continuation_protection||'off';
 const refining=!!refine.enabled;
 const advancedSummary=[refining?'Refinement on':null,antiBurnEnabled?'Anti-Burn on':null,settings.decode_edge_frames?`Seam: ${settings.decode_edge_frames}f`:null].filter(Boolean).join(' · ');
 if(!hasSource)return <section className="continuation-controls"><h3>{!hasTarget?'Prepare a segment':settings.mode==='extend'?'Waiting for source':'Generate first segment'}</h3><p className="muted">{!hasTarget?'Extend the scene, replace its tail, or start a new scene to prepare generation.':settings.mode==='extend'?'Finalize the preceding segment before configuring its continuation.':'Independent start. Continuation controls appear when you extend a finalized segment.'}</p></section>;
 return <section className="continuation-controls" aria-label="Continuation settings">
  <div className="continuation-heading"><h3>Continuation</h3><small>From {sourceLabel}</small></div>
  <div className="continuation-methods" role="group" aria-label="Continuation method">
   <button type="button" aria-pressed={latent} disabled={disabled||replacement} onClick={()=>{setMore(false);onMethod('latent');}}>Motion latent</button>
   <button type="button" aria-pressed={method==='last_frame'} disabled={disabled||replacement} onClick={()=>{setMore(false);onMethod('last_frame');}}>Last frame</button>
   <button type="button" aria-expanded={more} aria-label="More continuation methods" className={method==='video_reference'?'active':''} disabled={disabled||replacement} onClick={()=>setMore(!more)}>More ▾</button>
  </div>
  {(more||method==='video_reference')&&<label className="field-label experimental-method">Experimental method<select aria-label="Experimental continuation method" value={method==='video_reference'?'video_reference':''} disabled={disabled||replacement} onChange={()=>{onMethod('video_reference');setMore(false);}}><option value="" disabled>Select a method</option><option value="video_reference">Video reference — VPipe-style</option></select></label>}
  {latent?<>
   <label className="field-label"><span>Motion and audio context <Hint>Reuses a protected tail of the selected take. Longer context uses more of the sampled window.</Hint></span><select aria-label="Motion and audio context" value={settings.context||39} disabled={disabled||replacement} onChange={event=>onChange({...settings,context:Number(event.target.value)})}>{[39,90,141].map(frames=><option key={frames} value={frames} disabled={sourceFrames<frames||protection!=='off'&&frames!==39}>{frames} frames · {(frames/24).toFixed(3)}s</option>)}</select></label>
   <label className="field-label"><span>Drift treatment <Hint>Uses 39-frame context. Color Stable anchors to the scene's first finalized take. Use separately from refinement.</Hint></span><select aria-label="Drift treatment" value={protection} disabled={disabled||refining} onChange={event=>onChange({...settings,continuation_protection:event.target.value as Settings['continuation_protection'],...(event.target.value!=='off'?{context:39}:{})})}><option value="off">Off</option><option value="drift_control">Drift Control</option><option value="color_stable">Color Stable</option><option value="drift_color">Drift Control + Color Stable</option></select></label>
   {refining&&<small className="muted">Refinement is on in Advanced. Turn it off to use a drift treatment.</small>}
  </>:method==='last_frame'?<>
   <label className="field-label"><span>Carry motion <Hint>22 frames copies seven video latent steps. Audio is generated fresh in either option.</Hint></span><select aria-label="Carry motion" value={settings.image_motion_frames||0} disabled={disabled||replacement||settings.profile==='fl2va'} onChange={event=>onChange({...settings,image_motion_frames:Number(event.target.value) as 0|22})}><option value={0}>Off — image only</option>{settings.profile==='ref2va'&&<option value={22} disabled={sourceFrames<22}>22 frames — short motion context</option>}</select></label>
   <p className="method-note">Last frame supplied automatically. Audio starts fresh.</p>
  </>:<p className="method-note">Uses the preceding 3.75 seconds as video and audio references. Experimental.</p>}
  {handoff==='pdd'||settings.pdd_warmup==='auto'?<PddHandoff settings={settings} onChange={onChange} support={handoff} disabled={disabled}/>:null}
  <details key={method} className="continuation-advanced"><summary>Advanced <small>{advancedSummary}</small></summary><div>
   {latent&&<>
    <label className="refinement-toggle"><input type="checkbox" aria-label="Enable refinement" checked={refining} disabled={disabled||protection!=='off'} onChange={event=>onChange({...settings,refine:{...refine,enabled:event.target.checked}})}/>Refinement <Hint>Video only; audio stays frozen. Cannot be combined with a drift treatment.</Hint></label>
    {protection!=='off'&&<small className="muted">Turn off the drift treatment to enable refinement.</small>}
    {refining&&<>
     <label className="field-label">Refinement method<select aria-label="Refinement method" disabled={disabled} value={refine.mode||'h3_refine'} onChange={event=>onChange({...settings,refine:{...refine,mode:event.target.value as NonNullable<Settings['refine']>['mode'],steps:event.target.value==='h3_refine'?2:3}})}><option value="h3_refine">H3 Refine — original sigma tail</option><option value="noembryo_stats">noEmbryo — statistics only</option><option value="noembryo_detail">noEmbryo — statistics + detail</option><option value="character_masked">Character-masked refine</option></select></label>
     {refine.mode!=='noembryo_stats'&&<label className="field-label">Refinement model<select aria-label="Refinement model" value={refine.model||'received'} disabled={disabled} onChange={event=>onChange({...settings,refine:{...refine,model:event.target.value as 'received'|'base'}})}><option value="received">Selected generation model</option><option value="base">Recovered base — requires PDD handoff</option></select></label>}
    </>}
    <label className="field-label"><span>Seam frame correction <Hint>Replaces the previous ending frames with matching decoded overlap frames. Experimental; sampled latents stay unchanged.</Hint></span><select aria-label="Seam frame correction" value={settings.decode_edge_frames||0} disabled={disabled} onChange={event=>onChange({...settings,decode_edge_frames:Number(event.target.value)})}><option value={0}>Off</option>{[1,2,3,4,5,6,7,8].map(frames=><option key={frames} value={frames}>Borrow {frames} context frame{frames===1?'':'s'}</option>)}</select></label>
   </>}
   {referenceSizing}
   {handoff==='unknown'&&settings.pdd_warmup!=='auto'&&<PddHandoff settings={settings} onChange={onChange} support={handoff} disabled={disabled}/>}
   <details className="anti-burn-disclosure"><summary>Anti-Burn</summary>{antiBurn}</details>
  </div></details>
 </section>;
}

