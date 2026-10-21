import {test,expect,Page} from '@playwright/test';

async function setup(page:Page,finish=true,count=1,reuse=false){
  const fields={subject_definitions:'',summary:'',retention_analysis:'',detailed_description:'[Shot 1] Continue the exercise.',overall_soundscape:'',non_diegetic_music:''};
  const config={id:'config',name:'PDD REF2VA - 8 steps',profile:'ref2va',selector_id:'switch',slot:'A',upstream:{model:{inputs:{strength:1}}}};
  const baseTake={id:'seed',number:1,segment_id:'root',scene_id:'scene',plan:{new_seconds:5,new_frames:120,context_frames:0,sampled_frames:120,delivery:{start:0,end:120}},width:768,height:448,latent_sha256:'a'.repeat(64),snapshot:{seed:1,source:null,profile:'ref2va',configuration:config,compiled:{prompt:'prompt',authored_fields:fields,resolved_fields:fields,mappings:{}}},receipt:{sigma_values:[1,.5,0],sampler:'euler'},preview:{status:'ready'}};
  const baseline:any={id:'baseline',name:'Untreated exercise',revision:1,resolution:{width:768,height:448},references:[],effective_references:{root:[],tail:[]},jobs:{},takes:{seed:baseTake},scenes:[{id:'scene',name:'Scene 01',segments:[{id:'root',name:'Segment 01',takes:['seed'],active_output:{take_id:'seed',kind:'single_take'},working_draft:{scene_id:'scene',segment_id:'root',mode:'new',profile:'ref2va',seconds:5,width:768,height:448,seed:1,context:39,fields}},{id:'tail',name:'Segment 02',takes:[],active_output:null,planned:true,working_draft:{scene_id:'scene',segment_id:'tail',source_segment_id:'root',mode:'extend',profile:'ref2va',seconds:5,width:768,height:448,seed:2,context:39,fields}}]}]};
  if(reuse){baseline.takes['saved-control']={...structuredClone(baseTake),id:'saved-control',segment_id:'tail'};baseline.scenes[0].segments[1].takes=['saved-control'];baseline.scenes[0].segments[1].active_output={kind:'single_take',take_id:'saved-control'};delete baseline.scenes[0].segments[1].planned;}
  const projects:Record<string,any>={baseline};const submissions:any[]=[],accepted:string[]=[],statuses:any[]=[];
  let blocked=false,protectionProof=true;
  await page.clock.install();
  await page.addInitScript(configuration=>{
    (window as any).testConfig=configuration;
    window.longcasterTimelineBridge={status:()=>({connected:true,message:'test'}),configurations:async()=>[{id:'config',name:'PDD REF2VA - 8 steps',profile:'ref2va'}],prepareConfiguration:async()=>structuredClone((window as any).testConfig),subscribe:()=>()=>{},submit:async data=>{await (window as any).dispatchTest(data);return {};},cancel:async()=>({queuedRemoved:true})};
  },config);
  await page.exposeFunction('dispatchTest',(data:any)=>{
    submissions.push(data);if(!finish)return;
    const p=projects[data.project_id],job=p.jobs[data.job_id],segment=p.scenes[0].segments.find((s:any)=>s.id===job.segment_id);
    const id=`take-${data.project_id}-${segment.id}`;
    p.takes[id]={...structuredClone(baseTake),id,number:1,segment_id:segment.id,snapshot:{...structuredClone(baseTake.snapshot),source:{id:segment.working_draft.source_take_id},refine:{applied:data.project_id==='refine'}},receipt:{...baseTake.receipt,continuation_check:{passed:true},refine:{applied:data.project_id==='refine',protected_head_exact:true,output_audio_exact:true},continuation_protection:protectionProof?{mode:p.testTreatment,applied:['drift_control','color_stable','drift_color'].includes(p.testTreatment),drift_control:p.testTreatment!=='color_stable',mask_calls:8}:undefined}};
    segment.takes.push(id);job.status='succeeded';job.take_id=id;job.progress={stage:'complete'};p.revision++;
  });
  await page.route('**/queue',route=>route.fulfill({json:{queue_running:[],queue_pending:blocked?[[1,'other-job']]:[]}}));
  await page.route('**/longcaster-timeline/anti-burn',route=>route.fulfill({json:{available:false}}));
  await page.route('**/longcaster-timeline/projects**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const id=path.match(/\/projects\/([^/]+)/)?.[1]||'baseline';const p=projects[id];const body=route.request().method()==='POST'?route.request().postDataJSON():{};
    let result:any=p;
    if(path.endsWith('/projects'))result={projects:[{id:'baseline',name:baseline.name}]};
    else if(path.endsWith('/experiments')){
      if(body.preview)result={baseline_revision:1,seed_take_id:'seed',seed_sha256:'a'.repeat(64),configuration:body.configuration||config,baseline_configuration:config,configuration_changed:false,repeated_last_template:0,continuations:[{}],reuse_control:body.reuse_control,existing_control:body.reuse_control?{project_id:"baseline",scene_id:"scene",continuations:body.count,takes:[{id:"seed",latent_sha256:"a".repeat(64)},{id:"saved-control",latent_sha256:"a".repeat(64)}]}:null};
      else {
        const treatments=[...(body.reuse_control?[]:['control']),...(body.treatments||['h3_refine'])];
        const entries=treatments.map((treatment:string)=>({id:treatment==='h3_refine'?'refine':treatment,treatment}));
        for(const entry of entries){
          const key=entry.id;projects[key]=structuredClone(baseline);projects[key].id=key;projects[key].testTreatment=entry.treatment;projects[key].jobs={};projects[key].takes={seed:structuredClone(baseTake)};projects[key].scenes[0].segments[1].takes=[];projects[key].scenes[0].segments[1].active_output=null;
          for(let i=1;i<body.count;i++){const segment=structuredClone(baseline.scenes[0].segments[1]);segment.id=`tail-${i}`;segment.name=`Segment ${i+2}`;projects[key].scenes[0].segments.push(segment);}
          for(const segment of projects[key].scenes[0].segments.slice(1)){segment.working_draft.refine={enabled:key==='refine',steps:2};segment.working_draft.continuation_protection=['drift_control','color_stable','drift_color'].includes(entry.treatment)?entry.treatment:'off';}
        }
        result={projects:entries,existing_control:body.reuse_control?{project_id:'baseline',scene_id:'scene',continuations:body.count,takes:[]}:null};
      }
    }
    else if(path.endsWith('/experiment-status')){statuses.push({id,...body});result={ok:true};}
    else if(path.endsWith('/compile'))result={prompt:'prompt',subjects:[],mappings:{}};
    else if(path.endsWith('/preview'))result={status:'empty',entries:[],frames:0,seconds:0};
    else if(path.includes('/media/')){await route.fulfill({status:404});return;}
    else if(path.endsWith('/jobs')){
      const job={id:`job-${id}-${body.settings.segment_id}`,segment_id:body.settings.segment_id,status:'queued',progress:{stage:'queued'}};p.jobs[job.id]=job;p.scenes[0].segments.find((s:any)=>s.id===body.settings.segment_id).working_draft=body.settings;p.revision++;result={job,state:p};
    }
    else if(path.endsWith('/command')){
      if(body.action==='finalize'){accepted.push(id);p.scenes[0].segments.find((s:any)=>s.id===p.takes[body.take_id].segment_id).active_output={kind:'single_take',take_id:body.take_id};}
      if(body.action==='cancel')p.jobs[body.job_id].status='cancel_requested';
      if(body.action==='resolve_cancel')p.jobs[body.job_id].status='cancelled';
      if(body.action==='fail_dispatch')p.jobs[body.job_id].status='failed';
      p.revision++;
    }
    await route.fulfill({json:result});
  });
  await page.goto('./#/timeline/generate');
  await page.getByRole('button',{name:'Drift comparison',exact:true}).click();
  for(const label of ['Drift Control','Color Stable only','Drift Control + Color Stable'])await page.getByLabel(`Compare ${label}`,{exact:true}).uncheck();
  await page.getByLabel('Compare H3 Refine (separate comparison)',{exact:true}).check();
  await expect(page.getByLabel('Reuse existing control')).not.toBeChecked();
  if(reuse)await page.getByLabel('Reuse existing control').check();
  await page.getByLabel('Experiment continuation count').fill(String(count));
  await page.getByRole('button',{name:'Check baseline and configuration'}).click();
  await expect(page.getByRole('button',{name:reuse?'Run H3 Refine only':'Run control + H3 Refine'})).toBeEnabled();
  return {projects,submissions,accepted,statuses,block:(value:boolean)=>{blocked=value;},omitProtection:()=>{protectionProof=false;}};
}

test('comparison rests, waits for queue idle, accepts verified takes and uses each accepted parent',async({page})=>{
  const f=await setup(page,true,2);f.block(true);
  await page.getByRole('button',{name:'Run control + H3 Refine'}).click();
  await expect(page.getByRole('status')).toContainText('queue to become idle');
  await page.clock.fastForward(25000);expect(f.submissions).toHaveLength(0);
  f.block(false);await page.clock.fastForward(1000);
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.accepted.length).toBe(1);
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.accepted.length).toBe(2);
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(59000);expect(f.submissions).toHaveLength(2);
  await page.clock.fastForward(1100);
  await expect.poll(()=>f.accepted.length).toBe(3);
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.accepted.length).toBe(4);
  await expect(page.getByRole('status')).toContainText('Comparison complete');
  expect(f.submissions.map(s=>s.project_id)).toEqual(['control','control','refine','refine']);
  expect(f.projects.control.scenes[0].segments[1].working_draft.source_take_id).toBe('seed');
  expect(f.projects.refine.scenes[0].segments[1].working_draft.refine.enabled).toBe(true);
  expect(f.projects.control.scenes[0].segments[2].working_draft.source_take_id).toBe('take-control-tail');
  expect(f.projects.refine.scenes[0].segments[2].working_draft.source_take_id).toBe('take-refine-tail');
  expect(f.projects.baseline.jobs).toEqual({});
});

test('stop cancels the active job and never accepts or dispatches the next arm',async({page})=>{
  const f=await setup(page,false);
  await page.getByRole('button',{name:'Run control + H3 Refine'}).click();
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.submissions.length).toBe(1);
  await page.getByRole('button',{name:'Stop comparison'}).click();
  await page.clock.fastForward(1500);
  await expect(page.getByRole('alert')).toContainText('Experiment stopped');
  await expect.poll(()=>f.projects.control.jobs['job-control-tail'].status).toBe('cancelled');
  expect(f.accepted).toHaveLength(0);expect(f.submissions).toHaveLength(1);
});

test('changed upstream settings stop the comparison before creating productions',async({page})=>{
  const f=await setup(page);
  await page.evaluate(()=>{(window as any).testConfig.upstream.model.inputs.strength=.5;});
  await page.getByRole('button',{name:'Run control + H3 Refine'}).click();
  await expect(page.getByRole('alert')).toContainText('differs from the checked experiment setup');
  expect(Object.keys(f.projects)).toEqual(['baseline']);expect(f.submissions).toHaveLength(0);
});

test('current generation switches allow a standard configuration instead of the saved accelerated path',async({page})=>{
  const f=await setup(page);
  await page.evaluate(()=>{(window as any).testConfig.name='Standard REF2VA - 20 steps';(window as any).testConfig.upstream.model.inputs.strength=.25;});
  await page.getByLabel('Experiment generation setup').selectOption('current');
  await expect(page.getByRole('button',{name:'Run control + H3 Refine'})).toBeDisabled();
  await page.getByRole('button',{name:'Check baseline and configuration'}).click();
  await expect(page.getByRole('button',{name:'Run control + H3 Refine'})).toBeEnabled();
  await expect(page.getByRole('dialog')).toContainText('Standard REF2VA - 20 steps');
  await page.getByRole('button',{name:'Run control + H3 Refine'}).click();
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.accepted.length).toBe(1);
  expect(f.submissions[0].configuration.name).toBe('Standard REF2VA - 20 steps');
  await page.getByRole('button',{name:'Stop comparison'}).click();
  await page.clock.fastForward(1100);
  await expect(page.getByRole('alert')).toContainText('Experiment stopped');
});

test('reuse option dispatches only refinement generations and preserves existing controls',async({page})=>{
  const f=await setup(page,true,1,true);
  await expect(page.getByRole('dialog')).toContainText('No control generation will be queued');
  const baseline=structuredClone(f.projects.baseline);
  await page.getByRole('button',{name:'Run H3 Refine only'}).click();
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect.poll(()=>f.accepted.length).toBe(1);
  await expect(page.getByRole('status')).toContainText('Existing control reused');
  expect(f.submissions.map(s=>s.project_id)).toEqual(['refine']);
  expect(Object.keys(f.projects)).toEqual(['baseline','refine']);
  expect(f.projects.baseline).toEqual(baseline);
  await expect(page.getByRole('button',{name:'Open existing control production'})).toBeEnabled();
});

test('drift, color and combined treatments run as distinct chains without H3 refinement',async({page})=>{
  const f=await setup(page,true,1,true);
  await page.getByLabel('Compare H3 Refine (separate comparison)',{exact:true}).uncheck();
  for(const label of ['Drift Control','Color Stable only','Drift Control + Color Stable'])await page.getByLabel(`Compare ${label}`,{exact:true}).check();
  await page.getByRole('button',{name:'Check baseline and configuration'}).click();
  await page.getByRole('button',{name:'Run selected treatments'}).click();
  await expect(page.getByRole('status')).toContainText('GPU rest');
  for(let i=0;i<3;i++){
    await page.clock.fastForward(i===0?20001:60001);
    await expect.poll(()=>f.accepted.length).toBe(i+1);
    if(i<2)await expect(page.getByRole('status')).toContainText('GPU rest');
  }
  await expect(page.getByRole('status')).toContainText('Comparison complete');
  expect(f.submissions.map(s=>s.project_id)).toEqual(['drift_control','color_stable','drift_color']);
  for(const id of ['drift_control','color_stable','drift_color']){
    expect(f.projects[id].scenes[0].segments[1].working_draft.continuation_protection).toBe(id);
    expect(f.projects[id].scenes[0].segments[1].working_draft.refine.enabled).toBe(false);
  }
  expect(f.projects.baseline.jobs).toEqual({});
});

test('missing protection evidence stops automatic acceptance',async({page})=>{
  const f=await setup(page,true,1,true);f.omitProtection();
  await page.getByLabel('Compare H3 Refine (separate comparison)',{exact:true}).uncheck();
  await page.getByLabel('Compare Drift Control + Color Stable',{exact:true}).check();
  await page.getByRole('button',{name:'Check baseline and configuration'}).click();
  await page.getByRole('button',{name:'Run selected treatments'}).click();
  await expect(page.getByRole('status')).toContainText('GPU rest');
  await page.clock.fastForward(20001);
  await expect(page.getByRole('alert')).toContainText('protection evidence is missing');
  expect(f.accepted).toHaveLength(0);expect(f.submissions).toHaveLength(1);
});
