export type SeekRequest={takeId:string;time:number;autoplay:boolean;serial:number};

export function frameTime(seconds:number){return Math.max(0,Math.round(seconds*24))/24;}

export function locateFrame<T extends {start:number;length:number}>(blocks:T[],seconds:number){
  if(!blocks.length)return null;
  const end=blocks.at(-1)!.start+blocks.at(-1)!.length;
  const time=Math.min(frameTime(seconds),Math.max(0,frameTime(end)-1/24));
  const block=blocks.find(block=>time>=block.start-1e-7&&time<block.start+block.length-1e-7)||blocks.at(-1)!;
  return {block,time,local:frameTime(time-block.start)};
}
