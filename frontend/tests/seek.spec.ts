import {test,expect} from '@playwright/test';
import {createSeekQueue} from '../src/seek';
class SlowVideo extends EventTarget{
  readyState=2;seeking=false;time=0;writes:number[]=[];
  get currentTime(){return this.time;}
  set currentTime(value:number){this.writes.push(value);this.time=value;this.seeking=true;}
  complete(){this.seeking=false;this.dispatchEvent(new Event('seeked'));}
}
test('rapid seeks finish in flight work then decode only the newest requested frame',()=>{
 const video=new SlowVideo(),pending:boolean[]=[],settled:number[]=[];
 const queue=createSeekQueue(video as unknown as HTMLVideoElement,value=>pending.push(value),value=>settled.push(value));
 queue.seek(1);for(let frame=2;frame<=200;frame++)queue.seek(frame/24);
 expect(video.writes).toEqual([1]);expect(queue.pending()).toBe(true);expect(settled).toEqual([]);
 video.complete();expect(video.writes).toEqual([1,200/24]);expect(settled).toEqual([]);
 video.complete();expect(queue.pending()).toBe(false);expect(settled).toEqual([200/24]);expect(pending.at(-1)).toBe(false);
 queue.dispose();
});
test('a seek requested before metadata is retained and disposed players cannot deliver stale positions',()=>{
 const video=new SlowVideo();video.readyState=0;const settled:number[]=[];
 const queue=createSeekQueue(video as unknown as HTMLVideoElement,()=>{},value=>settled.push(value));
 queue.seek(2);queue.seek(5);expect(video.writes).toEqual([]);
 video.readyState=1;video.dispatchEvent(new Event('loadedmetadata'));expect(video.writes).toEqual([5]);
 queue.dispose();video.complete();expect(settled).toEqual([]);
});
