import React,{useEffect,useRef,useState} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {FlaskConical,Square,X} from "lucide-react";
import {request} from "./api";
import {Bridge,Configuration,Project,Settings} from "./types";

type ExistingControl={project_id:string;scene_id:string;continuations:number;takes:{id:string;latent_sha256:string}[]};
type Plan={baseline_revision:number;seed_take_id:string;seed_sha256:string;configuration:Configuration;baseline_configuration:Configuration;configuration_changed:boolean;repeated_last_template:number;continuations:unknown[];reuse_control:boolean;existing_control:ExistingControl|null};
type Arm={id:string;treatment:string};
const treatmentChoices=[{id:"drift_control",label:"Drift Control"},{id:"color_stable",label:"Color Stable only"},{id:"drift_color",label:"Drift Control + Color Stable"},{id:"h3_refine",label:"H3 Refine (separate comparison)"}];
const sleep=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
const active=(job:{status:string;progress?:{stage:string}})=>["queued","running","persisting","cancel_requested"].includes(job.status)||job.status==="succeeded"&&["decoding","saving_media","building_preview"].includes(job.progress?.stage||"");
const selections=(c:Configuration)=>({...((c as Configuration&{switch_values?:Record<string,string>}).switch_values||{}),...(c.selector_id&&c.slot?{[c.selector_id]:c.slot}:{})});
function same(a:unknown,b:unknown):boolean {
  if(a===b)return true;
  if(!a||!b||typeof a!=="object"||typeof b!=="object")return false;
  const x=a as Record<string,unknown>,y=b as Record<string,unknown>;
  return Object.keys(x).length===Object.keys(y).length&&Object.keys(x).every(k=>k in y&&same(x[k],y[k]));
}

export function DriftExperiment({project,sceneId,bridge,flush,onOpen,configurationId,switchSelections}:{project:Project;sceneId:string;bridge?:Bridge;flush:()=>Promise<void>;onOpen:(id:string)=>Promise<void>;configurationId:string;switchSelections:Record<string,string>}){
  let availableControls=0;
  for(const segment of project.scenes.find(s=>s.id===sceneId)?.segments.slice(1)||[]){if(!segment.active_output)break;availableControls++;}
  const defaultCount=Math.max(1,Math.min(4,availableControls));
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[count,setCount]=useState(4),[reuseControl,setReuseControl]=useState(false);
  const [configurationSource,setConfigurationSource]=useState("baseline");
  const [treatments,setTreatments]=useState<string[]>(["drift_control","color_stable","drift_color"]);
  const [existingControl,setExistingControl]=useState<ExistingControl|null>(null);
  const [message,setMessage]=useState(""),[error,setError]=useState(""),[plan,setPlan]=useState<Plan|null>(null),[arms,setArms]=useState<Arm[]>([]);
  const stop=useRef(false),current=useRef<{project:string;job:string}|null>(null);
  useEffect(()=>{setPlan(null);setExistingControl(null);setArms([]);setError("");setMessage("");setCount(4);setReuseControl(false);},[project.id,sceneId]);
  const check=()=>{if(stop.current)throw new Error("Experiment stopped. Completed takes are retained.");if(!bridge?.status().connected)throw new Error("ComfyUI execution disconnected. Experiment stopped.");};
  async function configuration(expected:Configuration){
    check();if(!bridge?.prepareConfiguration)throw new Error("Reconnect through an updated LongCaster ComfyUI launcher.");
    const next=await bridge.prepareConfiguration(expected.id,selections(expected));
    if(!next||!same(expected.upstream,next.upstream)||next.profile!==expected.profile)throw new Error("The connected generation configuration differs from the checked experiment setup. Check the comparison again after changing switches.");
    return next;
  }
  async function idleRest(seconds:number){
    let idleSince:number|null=null;
    while(true){
      check();const queue=await fetch("/queue");if(!queue.ok)throw new Error("Cannot verify the ComfyUI queue is idle.");
      const body=await queue.json();if(!Array.isArray(body.queue_running)||!Array.isArray(body.queue_pending))throw new Error("Unsupported ComfyUI queue response.");
      if(body.queue_running.length||body.queue_pending.length){idleSince=null;setMessage("Waiting for the ComfyUI queue to become idle…");}
      else {idleSince??=Date.now();const remaining=Math.ceil(seconds-(Date.now()-idleSince)/1000);setMessage(`GPU rest · ${Math.max(0,remaining)} seconds remaining`);if(remaining<=0)return;}
      await sleep(1000);
    }
  }
  async function previewPlan(){
    setError("");setBusy(true);stop.current=false;
    try{
      await flush();
      const chosen=configurationSource==="current"?await bridge?.prepareConfiguration?.(configurationId,switchSelections):undefined;
      if(configurationSource==="current"&&!chosen)throw new Error("Choose a named generation configuration before comparing.");
      const value:Plan=await request(`/projects/${project.id}/experiments`,{scene_id:sceneId,count,preview:true,configuration:chosen,reuse_control:reuseControl,treatments});
      await configuration(value.configuration);setPlan(value);setMessage(value.reuse_control?"Existing control verified. Only the selected treatments will be generated.":"Generation configuration verified. The control and selected treatments will share this setup.");
    }
    catch(e){setError((e as Error).message);setPlan(null);}finally{setBusy(false);}
  }
  async function status(id:string,value:string,text=""){await request(`/projects/${id}/experiment-status`,{status:value,message:text});}
  async function start(){
    if(!plan)return;setBusy(true);setError("");stop.current=false;let copies:Arm[]=[];let armId="";
    const beforeUnload=(event:BeforeUnloadEvent)=>{event.preventDefault();};
    window.addEventListener("beforeunload",beforeUnload);
    try{
      await configuration(plan.configuration);
      const result=await request(`/projects/${project.id}/experiments`,{scene_id:sceneId,count,revision:plan.baseline_revision,configuration:plan.configuration,reuse_control:plan.reuse_control,treatments});
      copies=result.projects;setArms(copies);setExistingControl(result.existing_control||null);setPlan(null);
      for(let armIndex=0;armIndex<copies.length;armIndex++){
        const arm=copies[armIndex];armId=arm.id;check();await status(arm.id,"resting");
        let parentTakeId=plan.seed_take_id;
        await idleRest(armIndex===0?20:60);
        for(let index=0;index<count;index++){
          check();if(index>0){await status(arm.id,"resting");await idleRest(20);}
          const config=await configuration(plan.configuration);
          let state:Project=await request(`/projects/${arm.id}`);
          const scene=state.scenes[0],segment=scene.segments[index+1],parent=scene.segments[index];
          if(!segment||segment.active_output||!parent.active_output||parent.active_output.take_id!==parentTakeId)throw new Error("Experiment segment order or selected source changed. Stopping rather than selecting another source.");
          if(Object.values(state.jobs).some(active))throw new Error("Another generation is active in this experiment.");
          const settings:Settings={...segment.working_draft!,scene_id:scene.id,segment_id:segment.id,source_take_id:parent.active_output.take_id,
            mode:"extend",configuration:config,configuration_override:true};
          await status(arm.id,"running",`Continuation ${index+1}/${count}`);
          state=await request(`/projects/${arm.id}`);
          const queued=await request(`/projects/${arm.id}/jobs`,{revision:state.revision,settings});
          current.current={project:arm.id,job:queued.job.id};
          try{check();await bridge!.submit({project_id:arm.id,job_id:queued.job.id,operation:"generate",configuration:config});}
          catch(e){await request(`/projects/${arm.id}/command`,{revision:queued.state.revision,action:"fail_dispatch",job_id:queued.job.id,error:(e as Error).message});throw e;}
          while(true){
            check();state=await request(`/projects/${arm.id}`);const job=state.jobs[queued.job.id];
            setMessage(`${arm.treatment} · continuation ${index+1}/${count} · ${job.progress?.stage||job.status}`);
            if(job.status==="failed"||job.status==="cancelled"||job.status==="cancel_requested")throw new Error(job.error||"Generation cancelled. Experiment stopped.");
            if(!active(job)){
              if(job.status!=="succeeded"||job.progress?.stage!=="complete"||!job.take_id)throw new Error("Generation or preview did not complete successfully.");
              const take=state.takes[job.take_id];
              if(take.preview?.status!=="ready"||take.snapshot.source?.id!==parent.active_output.take_id||take.receipt.continuation_check?.passed!==true)throw new Error("Take failed preview, source or protected-context checks. It will not be accepted automatically.");
              const refined=take.receipt as typeof take.receipt&{refine?:{applied:boolean;protected_head_exact?:boolean;output_audio_exact?:boolean}};
              if(arm.treatment==="h3_refine"&&(!refined.refine?.applied||!refined.refine.protected_head_exact||!refined.refine.output_audio_exact))throw new Error("Refinement evidence is missing. Stopping the experiment.");
              if(["drift_control","color_stable","drift_color"].includes(arm.treatment)){
                const protection=(take.receipt as typeof take.receipt&{continuation_protection?:{mode:string;applied:boolean;drift_control:boolean;mask_calls:number}}).continuation_protection;
                if(!protection?.applied||protection.mode!==arm.treatment||protection.drift_control&&protection.mask_calls<1)throw new Error("Continuation protection evidence is missing or differs from this treatment. Stopping the experiment.");
              }
              check();await request(`/projects/${arm.id}/command`,{revision:state.revision,action:"finalize",take_id:take.id});parentTakeId=take.id;current.current=null;break;
            }
            await sleep(1200);
          }
        }
        await status(arm.id,"complete");
      }
      setMessage(plan.reuse_control?"Comparison complete. Existing control reused; treatment productions are ready for visual review. Automatic acceptance checked technical integrity only.":"Comparison complete. Control and treatment productions are ready for visual review; automatic acceptance checked technical integrity only.");
    }catch(e){
      const text=(e as Error).message;setError(text);
      const pending=current.current;
      if(pending){
        try{
          const state:Project=await request(`/projects/${pending.project}`);
          if(active(state.jobs[pending.job])){
            await request(`/projects/${pending.project}/command`,{revision:state.revision,action:"cancel",job_id:pending.job});
            const cancelled=await bridge?.cancel({job_id:pending.job});
            if(cancelled?.queuedRemoved){const fresh:Project=await request(`/projects/${pending.project}`);await request(`/projects/${pending.project}/command`,{revision:fresh.revision,action:"resolve_cancel",job_id:pending.job});}
          }
        }catch(cancelError){setError(`${text} Cancellation needs attention: ${(cancelError as Error).message}`);}
      }
      for(const arm of copies){if(arm.id===armId||copies.indexOf(arm)>copies.findIndex(a=>a.id===armId))await status(arm.id,stop.current?"stopped":"failed",text).catch(()=>{});}
    }finally{current.current=null;window.removeEventListener("beforeunload",beforeUnload);setBusy(false);}
  }
  const runLabel=treatments.length===1&&treatments[0]==="h3_refine"?(reuseControl?"Run H3 Refine only":"Run control + H3 Refine"):"Run selected treatments";
  return <><button onClick={()=>setOpen(true)}><FlaskConical size={15}/>Drift comparison</button><Dialog.Root open={open} onOpenChange={value=>{if(!busy)setOpen(value);}}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className="modal drift-experiment"><Dialog.Title>Automatic drift comparison</Dialog.Title><Dialog.Description>Generate separate control and treatment chains from the same finalized first take, or choose to reuse an existing control. The baseline stays intact. Keep this app and its ComfyUI tab open; reloading stops automation and never resumes it automatically.</Dialog.Description>
    <fieldset disabled={busy}><legend>Treatments</legend>{treatmentChoices.map(item=><label className="rename-option" key={item.id}><input type="checkbox" aria-label={`Compare ${item.label}`} checked={treatments.includes(item.id)} onChange={event=>{setTreatments(previous=>event.target.checked?[...previous,item.id]:previous.filter(id=>id!==item.id));setPlan(null);}}/>{item.label}</label>)}</fieldset>
    <p><strong>Baseline:</strong> {project.name}</p><label className="field-label">Generation setup<select aria-label="Experiment generation setup" value={configurationSource} disabled={busy} onChange={e=>{setConfigurationSource(e.target.value);setPlan(null);}}><option value="baseline">Saved baseline configuration</option><option value="current">Current generation switches</option></select></label><p className="muted">Supports standard REF2VA and accelerated configurations. To compare another path, choose its switches in Generation settings, then select Current generation switches here. Both arms share that path and the same saved first take.</p><label className="field-label">Continuations per treatment<input aria-label="Experiment continuation count" type="number" min={1} max={12} value={count} disabled={busy} onChange={e=>{setCount(Number(e.target.value));setPlan(null);}}/></label>
    <label className="rename-option"><input aria-label="Reuse existing control" type="checkbox" checked={reuseControl} disabled={busy} onChange={e=>{setReuseControl(e.target.checked);setPlan(null);setCount(e.target.checked?defaultCount:4);}}/>Reuse existing control</label><p className="muted">{reuseControl?`${availableControls} finalized control continuation(s) available. Generates only selected treatments; controls must match the selected generation configuration and requested length.`:"Generates a new untreated control and the selected treatment chains. Use this when changing generation configurations or testing a longer chain."}</p>
    <p className="muted">Prompt source: saved prompts and seeds from finalized continuation takes. Planned-only segments are not used. Longer new chains repeat the last saved continuation template; the checked plan reports how many repeats.</p>
    <p className="muted">20 seconds of idle GPU rest before each generation; 60 seconds between newly generated treatments. Takes are accepted only after successful preview and context checks. Visual quality still needs your review.</p>
    {plan&&<p>Starting take: {plan.seed_take_id.slice(0,8)} · {plan.seed_sha256.slice(0,12)}. {plan.repeated_last_template>0?`The last saved continuation prompt and seed repeat ${plan.repeated_last_template} time(s).`:"Uses the baseline's saved prompts and seeds in order."}</p>}
    {plan&&<p><strong>Comparison configuration:</strong> {plan.configuration.name}. {plan.reuse_control?`Reuses ${plan.existing_control?.continuations} saved control continuations. No control generation will be queued.`:plan.configuration_changed?"This differs from the historical baseline; judge refinement against the newly generated control. The common starting take retains its original configuration.":"Matches the historical baseline configuration."}</p>}
    {message&&<p role="status">{message}</p>}{error&&<p className="warning" role="alert">{error}</p>}
    <div className="modal-actions">{busy?<button onClick={()=>{stop.current=true;setMessage("Stopping automation and cancelling its active generation…");}}><Square size={14}/>Stop comparison</button>:<><button disabled={!treatments.length} onClick={()=>void previewPlan()}>Check baseline and configuration</button><button className="generate" disabled={!plan} onClick={()=>void start()}>{runLabel}</button></>}</div>
    {existingControl&&<p><button disabled={busy} onClick={()=>{setOpen(false);void onOpen(existingControl.project_id);}}>Open existing control production</button></p>}
    {arms.map(arm=><p key={arm.id}><button disabled={busy} onClick={()=>{setOpen(false);void onOpen(arm.id);}}>Open {arm.treatment} production</button></p>)}
    <Dialog.Close className="modal-close" disabled={busy} aria-label="Close drift comparison"><X size={17}/></Dialog.Close>
  </Dialog.Content></Dialog.Portal></Dialog.Root></>;
}
