/** Serialize decoder work: finish the current seek, then apply only the newest request. */
export function createSeekQueue(video:HTMLVideoElement,onPending:(pending:boolean)=>void,onSettled:(seconds:number)=>void){
  let desired:number|null=null,busy=false,disposed=false;
  function pump(){
    if(disposed||busy||desired===null||video.readyState<1)return;
    if(video.seeking){busy=true;onPending(true);return;}
    if(Math.abs(video.currentTime-desired)<=1/48){desired=null;onPending(false);onSettled(video.currentTime);return;}
    busy=true;onPending(true);
    try{video.currentTime=desired;}catch{busy=false;onPending(false);}
  }
  function settled(){
    if(disposed)return;
    busy=false;
    if(desired!==null&&Math.abs(video.currentTime-desired)>1/48){pump();return;}
    desired=null;onPending(false);onSettled(video.currentTime);
  }
  video.addEventListener('seeked',settled);
  video.addEventListener('loadedmetadata',pump);
  return {
    seek(seconds:number){desired=Math.max(0,seconds);pump();},
    pending(){return busy||desired!==null;},
    dispose(){disposed=true;video.removeEventListener('seeked',settled);video.removeEventListener('loadedmetadata',pump);}
  };
}
