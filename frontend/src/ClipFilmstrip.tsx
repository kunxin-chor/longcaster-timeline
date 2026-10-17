import {useEffect,useRef} from 'react';

// One offscreen decoder per visible clip; the timeline displays static frames.
export function ClipFilmstrip({src,width}:{src:string;width:number}){
 const canvas=useRef<HTMLCanvasElement>(null);
 const count=Math.max(1,Math.min(6,Math.ceil(width/96)));
 useEffect(()=>{
  const target=canvas.current;if(!target)return;
  const context=target.getContext('2d');if(!context)return;
  context.clearRect(0,0,target.width,target.height);
  let video:HTMLVideoElement|undefined,stopped=false,started=false,index=0;
  let timeout:ReturnType<typeof setTimeout>|undefined;
  function release(){if(!video)return;video.pause();video.removeAttribute('src');video.load();video=undefined;clearTimeout(timeout);}
  function capture(){
   if(stopped||!video||!context||!video.videoWidth||!video.videoHeight)return;
   const ratio=112/62,sourceRatio=video.videoWidth/video.videoHeight;
   const sw=sourceRatio>ratio?video.videoHeight*ratio:video.videoWidth;
   const sh=sourceRatio>ratio?video.videoHeight:video.videoWidth/ratio;
   context.drawImage(video,(video.videoWidth-sw)/2,(video.videoHeight-sh)/2,sw,sh,index*112,0,112,62);
   index++;
   if(index>=count){release();return;}
   const end=Math.max(0,video.duration-1/24);
   const next=index*end/(count-1);
   if(Math.abs(video.currentTime-next)<.001){capture();return;}
   video.currentTime=next;
  }
  function start(){
   if(started||stopped)return;started=true;
   video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';
   video.addEventListener('loadeddata',capture,{once:true});video.addEventListener('seeked',capture);
   video.addEventListener('error',release,{once:true});video.src=src;
   timeout=setTimeout(release,12000);
  }
  const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();start();}},{rootMargin:'200px'});
  observer.observe(target);
  return()=>{stopped=true;observer.disconnect();release();};
 },[src,count]);
 return <canvas ref={canvas} width={count*112} height={62} className="clip-filmstrip" aria-hidden="true"/>;
}
