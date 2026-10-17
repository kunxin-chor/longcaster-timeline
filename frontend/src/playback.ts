import {RefObject,useEffect,useRef} from 'react';

// Read the active element every animation frame, with fresh callbacks and cleanup.
// This also covers paused seeks, frame stepping and videos replaced after metadata loads.
export function usePlaybackClock(videoRef:RefObject<HTMLVideoElement|null>,onPosition:(seconds:number)=>void){
  const callback=useRef(onPosition);callback.current=onPosition;
  useEffect(()=>{
    let frame=0,lastVideo:HTMLVideoElement|null=null,lastTime=-1;
    const tick=()=>{
      const video=videoRef.current;
      if(video&&video.readyState>=2&&!video.seeking&&(video!==lastVideo||video.currentTime!==lastTime)){
        lastVideo=video;lastTime=video.currentTime;callback.current(lastTime);
      }
      frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);
  },[videoRef]);
}
export function seekVideo(video:HTMLVideoElement,seconds:number){
  const target=Math.max(0,seconds);
  // Avoid repeatedly asking a decoding video to seek to its current frame.
  if(Math.abs(video.currentTime-target)>1/48)video.currentTime=target;
}
