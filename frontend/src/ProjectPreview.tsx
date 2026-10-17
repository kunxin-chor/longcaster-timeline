import React,{useEffect,useRef,useState} from "react";
import {Film,LoaderCircle,Maximize,Pause,Play,RefreshCw,SkipBack,Volume2,VolumeX} from "lucide-react";
import {BASE,request} from "./api";
import {Project} from "./types";
import {usePlaybackClock} from "./playback";
import {createSeekQueue} from "./seek";

type Entry={scene_id:string;scene_name:string;segment_id:string;segment_name:string;take_id:string;take_number:number;draft:boolean;start_frame:number;end_frame:number;scene_start_frame:number};
type Movie={key:string;status:"empty"|"building"|"ready"|"failed";seconds:number;frames:number;draft_count:number;entries:Entry[];error?:string;message?:string};
export type ProjectSeek={sceneId:string;takeId:string;segmentId?:string;time:number;serial:number};
type Props={sceneId:string;project:Project|null;draftTakeId?:string;videoRef:React.RefObject<HTMLVideoElement|null>;seek:ProjectSeek|null;
  onPosition:(sceneId:string,seconds:number)=>void;onActivate:()=>void};

const clock=(seconds:number)=>{const frame=Math.max(0,Math.round(seconds*24));return `${String(Math.floor(frame/1440)).padStart(2,"0")}:${String(Math.floor(frame/24)%60).padStart(2,"0")}:${String(frame%24).padStart(2,"0")}`;};

export function ProjectPreview({sceneId,project,draftTakeId,videoRef,seek,onPosition,onActivate}:Props){
  const [includeDrafts,setIncludeDrafts]=useState(()=>localStorage.getItem("longcaster-preview-drafts")!=="false");
  const [movie,setMovie]=useState<Movie|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState("");
  const [position,setPosition]=useState(0),[playing,setPlaying]=useState(false),[muted,setMuted]=useState(false),[retry,setRetry]=useState(0);
  const appliedSeek=useRef("");
  const queue=useRef<ReturnType<typeof createSeekQueue>|null>(null);
  useEffect(()=>{
    const video=videoRef.current;if(!video)return;appliedSeek.current="";
    const current=createSeekQueue(video,()=>{},seconds=>setPosition(seconds));queue.current=current;
    // Requests can arrive before the assembled movie or its metadata is ready.
    applyExternalSeek();
    return()=>{current.dispose();if(queue.current===current)queue.current=null;};
  },[movie?.key,movie?.status,error]);
  function requestSeek(seconds:number){queue.current?.seek(seconds);}

  // Poll responses recreate objects; encode only changes that can affect review inputs.
  const inputs=JSON.stringify([project?.id,sceneId,includeDrafts,includeDrafts?draftTakeId:null,project?.scenes.map(scene=>[scene.id,scene.name,scene.segments.map(segment=>[
    segment.id,segment.name,segment.active_output?.take_id,segment.takes.map(id=>[id,project.takes[id]?.preview])])])]);
  useEffect(()=>{
    if(!project)return;let current=true;let timer:ReturnType<typeof setTimeout>|undefined;
    videoRef.current?.pause();setLoading(true);setError("");
    const poll=async(first=false)=>{
      try{
        const next:Movie=await request(`/projects/${project.id}/preview`,{scene_id:sceneId,include_drafts:includeDrafts,draft_take_id:includeDrafts?draftTakeId:undefined,retry:first&&retry>0});
        if(!current)return;setMovie(next);setLoading(next.status==="building");
        if(next.status==="failed")setError(next.error||"Scene preview could not be built.");
        if(next.status==="building")timer=setTimeout(()=>void poll(),900);
      }catch(error){if(current){setLoading(false);setError((error as Error).message);}}
    };
    void poll(true);return()=>{current=false;clearTimeout(timer);};
  },[inputs,retry]);
  useEffect(()=>{setPosition(0);setPlaying(false);appliedSeek.current="";},[movie?.key]);
  const ready=movie?.status==="ready"&&!loading&&!error;
  const maxTime=Math.max(0,(movie?.frames||1)-1)/24;
  const entry=movie?.entries.find(entry=>position*24>=entry.start_frame-.01&&position*24<entry.end_frame-.01)||movie?.entries.at(-1);
  function report(seconds:number){
    const frame=Math.min(Math.max(0,Math.round(seconds*24)),(movie?.frames||1)-1);
    const current=movie?.entries.find(entry=>frame>=entry.start_frame&&frame<entry.end_frame);
    if(current)onPosition(current.scene_id,(current.scene_start_frame+frame-current.start_frame)/24);
  }
  usePlaybackClock(videoRef,seconds=>{if(queue.current?.pending())return;setPosition(Math.min(maxTime,seconds));report(seconds);});
  function seekTo(seconds:number){
    const video=videoRef.current;if(!video||!ready)return;
    const target=Math.min(maxTime,Math.max(0,Math.round(seconds*24)/24));
    onActivate();video.pause();requestSeek(target);setPosition(target);report(target);
  }
  function applyExternalSeek(){
    if(!seek||!movie||movie.status!=="ready"||!videoRef.current||!queue.current)return;
    const token=`${movie.key}:${seek.serial}`;if(appliedSeek.current===token)return;
    const range=movie.entries.find(entry=>entry.scene_id===seek.sceneId&&(entry.take_id===seek.takeId||entry.segment_id===seek.segmentId));
    if(!range)return;
    appliedSeek.current=token;
    const target=(range.start_frame+Math.min(range.end_frame-range.start_frame-1,Math.max(0,Math.round(seek.time*24))))/24;
    videoRef.current.pause();requestSeek(target);setPosition(target);
  }
  useEffect(applyExternalSeek,[seek,movie?.key,movie?.status]);
  async function togglePlay(){
    const video=videoRef.current;if(!video||!ready)return;onActivate();
    if(!video.paused){video.pause();return;}
    if(video.ended||video.currentTime>=maxTime)video.currentTime=0;
    try{await video.play();}catch(error){setError(`Scene preview playback failed: ${(error as Error).message}`);}
  }
  return <section className="project-preview" aria-label="Scene preview" onPointerDown={onActivate} onKeyDown={event=>{
    if((event.target as HTMLElement).closest("input,select,textarea"))return;
    if(event.code==="Space"){event.preventDefault();void togglePlay();}
    if(event.key==="ArrowLeft"||event.key==="ArrowRight"){event.preventDefault();seekTo(position+(event.key==="ArrowLeft"?-1:1)/24);}
  }}>
    <div className="project-preview-heading"><Film size={15}/><strong>Scene preview</strong><span className="badge">{movie?.draft_count?`${movie.draft_count} draft${movie.draft_count===1?"":"s"}`:"Finalized"}</span></div>
    <div className="preview-options"><label><input aria-label="Include draft takes" type="checkbox" checked={includeDrafts} onChange={event=>{setIncludeDrafts(event.target.checked);localStorage.setItem("longcaster-preview-drafts",String(event.target.checked));}}/>Include draft takes</label><span>{project?.scenes.find(scene=>scene.id===sceneId)?.name||"Current scene"}</span></div>
    <div className="project-preview-screen">{movie?.status==="ready"&&!error?<video key={movie.key} ref={videoRef} src={`${BASE}/projects/${project!.id}/preview/${movie.key}`} preload="auto" playsInline muted={muted}
      onLoadedMetadata={applyExternalSeek} onPlay={()=>{onActivate();setPlaying(true);}} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)}
      onError={()=>{setError("The scene preview could not be played. Retry its build or check the saved preview files.");setPlaying(false);}}/>:
      <div className="project-preview-empty">{loading?<LoaderCircle size={24} className="spin"/>:<Film size={26}/>}<span>{error||movie?.message||"Preparing project playback"}</span>{!!error&&<button onClick={()=>{setError("");setRetry(value=>value+1);}}><RefreshCw size={13}/>Retry preview</button>}</div>}
      {loading&&<div className="project-preview-building"><LoaderCircle size={15} className="spin"/>Building scene preview</div>}
    </div>
    <div className="project-preview-transport"><button aria-label={playing?"Pause scene preview":"Play scene preview"} disabled={!ready} onClick={()=>void togglePlay()}>{playing?<Pause size={16}/>:<Play size={16}/>}</button><button aria-label="Previous project frame" disabled={!ready} onClick={()=>seekTo(position-1/24)}><SkipBack size={13}/></button><span className="timecode">{clock(position)} <i>/ {clock(movie?.seconds||0)}</i></span><button aria-label="Mute scene preview" disabled={!ready} onClick={()=>setMuted(value=>!value)}>{muted?<VolumeX size={15}/>:<Volume2 size={15}/>}</button><button aria-label="Fullscreen scene preview" disabled={!ready} onClick={()=>void videoRef.current?.requestFullscreen()}><Maximize size={15}/></button></div>
    <input className="project-preview-progress" aria-label="Scene preview seek" type="range" min={0} max={maxTime||1} step={1/24} value={position} disabled={!ready} onChange={event=>seekTo(Number(event.target.value))}/>
    <div className="project-preview-caption" aria-live="polite">{entry?`${entry.scene_name} / ${entry.segment_name} - Take ${entry.take_number}${entry.draft?" (unfinalized)":""}`:"Finalized segments play in scene order. Drafts are included only while checked."}</div>
  </section>;
}
