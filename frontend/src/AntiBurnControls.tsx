import {useCallback,useEffect,useState} from "react";
import {request} from "./api";
import {AntiBurnScene,AntiBurnSegment} from "./types";

type Status={available:boolean;filename?:string|null;warning?:string|null};
export function useAntiBurnStatus(){
 const [status,setStatus]=useState<Status|null>(null);
 const refresh=useCallback(async()=>{try{setStatus(await request("/anti-burn"));}catch(error){setStatus({available:false,warning:`Cannot check Anti-Burn LoRA: ${(error as Error).message}`});}},[]);
 useEffect(()=>{void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer);},[refresh]);
 return {status,refresh};
}
export function AntiBurnControls({scene,value,onChange,onSceneChange,disabled,hasSource,status,refresh}:{scene?:AntiBurnScene;value?:AntiBurnSegment;onChange?:(value:AntiBurnSegment)=>void;onSceneChange?:(value:AntiBurnScene)=>Promise<unknown>;disabled:boolean;hasSource?:boolean;status:Status|null;refresh:()=>Promise<void>}){
 const [localScene,setLocalScene]=useState(scene||{enabled:false,strength:.5}),[saving,setSaving]=useState(false);
 useEffect(()=>setLocalScene(scene||{enabled:false,strength:.5}),[scene?.enabled,scene?.strength]);
 const base=onSceneChange?localScene:(scene||{enabled:false,strength:.5});const mode=value?.mode||"inherit";
 const busy=disabled||saving;
 async function saveScene(next:AntiBurnScene){const previous=base;setLocalScene(next);setSaving(true);try{await onSceneChange?.(next);}catch{setLocalScene(previous);}finally{setSaving(false);}}
 const enabled=onSceneChange?base.enabled:mode==="inherit"?base.enabled:mode==="on";
 const amount=value?.strength??base.strength;
 return <section className="anti-burn-controls" aria-label={onSceneChange?"Scene Anti-Burn settings":"Segment Anti-Burn settings"}>
 {onSceneChange?<label className="anti-burn-toggle"><input aria-label="Scene Anti-Burn" type="checkbox" checked={base.enabled} disabled={busy} onChange={event=>void saveScene({...base,enabled:event.target.checked})}/><span>Anti-Burn for scene continuations</span></label>:<label className="field-label">Anti-Burn<select aria-label="Segment Anti-Burn" value={mode} disabled={busy} onChange={event=>onChange?.({...value,mode:event.target.value as AntiBurnSegment["mode"]})}><option value="inherit">Inherit scene - {base.enabled?"On":"Off"}</option><option value="on">On</option><option value="off">Off</option></select></label>}
 {enabled&&<>{!onSceneChange&&<label className="anti-burn-toggle"><input type="checkbox" aria-label="Override Anti-Burn strength" checked={value?.strength!==undefined} disabled={busy} onChange={event=>onChange?.({...value,mode,strength:event.target.checked?base.strength:undefined})}/><span>Override scene strength</span></label>}<label className="field-label">Anti-Burn strength<input aria-label={onSceneChange?"Scene Anti-Burn strength":"Segment Anti-Burn strength"} key={`${amount}:${!!onSceneChange}`} type="number" min={.01} max={2} step={.05} defaultValue={amount} disabled={busy||(!onSceneChange&&value?.strength===undefined)} onBlur={event=>{const next=Number(event.target.value);if(!Number.isFinite(next)||next<=0||next>2){event.target.value=String(amount);return;}if(next!==amount){if(onSceneChange)void saveScene({...base,strength:next});else onChange?.({...value,mode,strength:next});}}}/></label></>}
 <p className="muted">Reduces accumulated harshness during continuation. Experimental with standard REF2VA; identity preservation is not established.</p>
 {!onSceneChange&&!hasSource&&<p className="muted">Skipped for this independent start. Scene settings apply to later continuations.</p>}
 <div className="anti-burn-availability">{status?.available?<small className="muted">Installed: <span>{status.filename}</span></small>:<p className="warning" role="alert">{status?.warning||"Checking Anti-Burn LoRA availability..."}{enabled&&hasSource?" Generation is blocked until the file is available or Anti-Burn is off.":""}</p>}
 <button type="button" disabled={busy} onClick={()=>void refresh()}>Refresh Anti-Burn availability</button></div>
 </section>;
}
