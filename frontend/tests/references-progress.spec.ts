import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {FIELDS,Field,Reference} from '../src/types';
import {renameAssetFields} from '../src/references';
import {routedProgress} from '../../web/extension/generation_progress.js';

test('bridge forwards ComfyUI interruptions and errors only for its own prompt',async()=>{
 const source=readFileSync(fileURLToPath(new URL('../../web/extension/launcher.js',import.meta.url)),'utf8').replace(/^import .*;\r?$/gm,'');
 const handlers=new Map<string,(event:any)=>void>();const sent:any[]=[];
 const node={id:1,type:'LongCasterTimelineExecute',inputs:['model','clip','video_vae','audio_vae','sampler','sigmas'].map(name=>({name,link:1})),widgets:[{name:'request_token',value:''}]};
 const app={graph:{_nodes:[node]},graphToPrompt:async()=>({output:{},workflow:{}}),registerExtension:()=>{}};
 const api={queuePrompt:async()=>({prompt_id:'ours'}),addEventListener:(name:string,handler:any)=>handlers.set(name,handler),fetchApi:async(_url:string,options:any)=>{sent.push(JSON.parse(options.body));return {ok:true};}};
 const target:any={};
 new Function('app','api','configurationChoices','prepareConfiguration','executionGraph','routedProgress','window',source)(app,api,()=>[],()=>{},(output:any)=>output,routedProgress,target);
 await target.longcasterTimelineBridge.submit({project_id:'project',job_id:'job',operation:'generate'});
 handlers.get('execution_interrupted')!({detail:{prompt_id:'unrelated'}});
 expect(sent.filter(item=>item.stage==='cancelled')).toHaveLength(0);
 handlers.get('execution_interrupted')!({detail:{prompt_id:'ours'}});
 expect(sent[sent.length-1]).toMatchObject({project_id:'project',job_id:'job',prompt_id:'ours',stage:'cancelled'});
 handlers.get('execution_error')!({detail:{prompt_id:'ours',exception_message:'Loader failed'}});
 expect(sent[sent.length-1]).toMatchObject({stage:'failed',message:'Loader failed'});
});

test('asset rename preserves subject labels and handles qualified and legacy names independently',()=>{
  const reference={id:'image',kind:'image',token_name:'main'} as Reference;
  const fields=Object.fromEntries(FIELDS.map(f=>[f,''])) as Record<Field,string>;
  fields.subject_definitions='<Subject 1> is the woman in <PiCtUrE.Main>.';
  fields.detailed_description='[Shot 1] <Subject 1> waves. <main> is a legacy citation.';
  const renamed=renameAssetFields(fields,reference,'hero',[reference]);
  expect(renamed.subject_definitions).toBe('<Subject 1> is the woman in <picture.hero>.');
  expect(renamed.detailed_description).toBe('[Shot 1] <Subject 1> waves. <hero> is a legacy citation.');
  const ambiguous=renameAssetFields(fields,reference,'hero',[reference,{...reference,id:'video',kind:'video'}]);
  expect(ambiguous.detailed_description).toContain('<main>');
});

test('progress is associated with the identified ComfyUI prompt and ignores unrelated executions',()=>{
  const jobs=new Map([['job',{promptId:'ours',request:{project_id:'project',job_id:'job'}}]]);
  expect(routedProgress({value:4,max:8,prompt_id:'ours'},null,jobs)).toEqual({value:4,max:8,prompt_id:'ours',project_id:'project',job_id:'job'});
  expect(routedProgress({value:4,max:8},'ours',jobs)?.job_id).toBe('job');
  expect(routedProgress({value:4,max:8},null,jobs)).toBeNull();
  expect(routedProgress({value:4,max:8},'unrelated',jobs)).toBeNull();
  expect(routedProgress({value:8,max:8,prompt_id:'other'},'ours',jobs)).toBeNull();
  expect(routedProgress({value:20,max:8,prompt_id:'ours'},null,jobs)).toBeNull();
});
