import {test,expect,Page} from '@playwright/test';

async function fixture(page:Page,independent=false){
 page.on("pageerror",error=>console.log("PAGE ERROR:",error.stack));
 const fields={subject_definitions:'',summary:'',retention_analysis:'',detailed_description:'[Shot 1] Continue controlled pull-ups.',overall_soundscape:'Gym ambience.',non_diegetic_music:'N/A'};
 const draft={scene_id:'scene',segment_id:'tail',source_segment_id:'root',mode:'extend',profile:'ref2va',seconds:5,width:1024,height:576,seed:42,context:39,fields};
 const rootTake={latent_sha256:'a'.repeat(64),created_at:'2026-10-21T00:00:00Z',id:'root-take',number:1,scene_id:'scene',segment_id:'root',plan:{sampled_frames:158,context_frames:0,new_frames:158,new_seconds:158/24,delivery:{start:0,end:158}},width:1024,height:576,snapshot:{seed:1,profile:'ref2va',source:null,compiled:{prompt:'Root prompt',authored_fields:fields,resolved_fields:fields,mappings:{}}},receipt:{sigma_values:[1,0],sampler:'euler'},preview:{status:'ready'}};
 const p:any={id:'ui-fixture',name:'Continuation UI fixture',revision:1,resolution:{width:1024,height:576},references:[],effective_references:{root:[],tail:[]},jobs:{},takes:{'root-take':rootTake},scenes:[{id:'scene',name:'Scene 01',segments:[{id:'root',name:'Segment 01',takes:['root-take'],active_output:{kind:'single_take',take_id:'root-take'},working_draft:{...draft,mode:'new',segment_id:'root',source_segment_id:undefined}},{id:'tail',name:'Segment 02',takes:[],active_output:null,planned:true,working_draft:draft}]}]};
 if(independent){p.takes={};p.scenes[0].segments=[{id:'tail',name:'Segment 01',takes:[],active_output:null,working_draft:{...draft,mode:'new',source_segment_id:undefined}}];}
 const queued:any[]=[];
 await page.addInitScript(()=>{
  const choices=[{id:'pdd',name:'Setup A',profile:'ref2va' as const},{id:'omni',name:'Setup B',profile:'ref2va' as const}];
  window.longcasterTimelineBridge={status:()=>({connected:true,message:'Fixture'}),configurations:async()=>choices,prepareConfiguration:async(id)=>({...choices.find(c=>c.id===id)!,selector_id:null,slot:null,upstream:{model:{class_type:id==='omni'?'LongCasterTimelineFastH3Omni':'MiniMaxH3PDDAccApply',inputs:{enabled:true}}}}),subscribe:()=>()=>{},submit:async()=>({}),cancel:async()=>({queuedRemoved:true})};
 });
 await page.route('**/longcaster-timeline/anti-burn',route=>route.fulfill({json:{available:true,filename:'test-antiburn.safetensors'}}));
 await page.route('**/longcaster-timeline/capabilities',route=>route.fulfill({json:{pdd_warmup:2,pdd_warmup_refine:1,pdd_warmup_protection:1,image_continuation:4,image_motion:1,video_continuation:1}}));
 await page.route('**/longcaster-timeline/projects**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const body=route.request().method()==='POST'?route.request().postDataJSON():{};
  let result:any=p;
  if(path.endsWith('/projects'))result={projects:[{id:p.id,name:p.name}]};
  else if(path.endsWith('/compile'))result={prompt:'Compiled prompt',mappings:{},subjects:[],continuation_picture:body.continuation_method==='last_frame'?{native_label:'<Picture 3>'}:undefined};
  else if(path.endsWith('/preview'))result={status:'empty',entries:[],frames:0,seconds:0};
  else if(path.includes('/media/')){await route.fulfill({status:404});return;}
  else if(path.endsWith('/command')){if(body.action==='save_draft')p.scenes[0].segments.at(-1).working_draft=body.draft;p.revision++;}
  else if(path.endsWith('/jobs')){queued.push(body.settings);const job={id:'fixture-job',segment_id:'tail',status:'queued',progress:{stage:'queued'}};p.jobs[job.id]=job;p.revision++;result={state:p,job};}
  await route.fulfill({json:result});
 });
 await page.goto('./#/timeline/generate');
 await expect(page.getByRole('heading',{name:independent?'Generate first segment':'Continuation',exact:true})).toBeVisible();
 if(!independent)await expect(page.getByLabel('PDD base-model handoff',{exact:true})).toBeVisible();
 return {p,queued};
}

test('continuation methods remember their own settings and hide unrelated controls',async({page})=>{
 await fixture(page);
 await page.getByLabel('Drift treatment',{exact:true}).selectOption('drift_color');
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await expect(page.getByLabel('Motion and audio context',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Drift treatment',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Enable refinement',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Seam frame correction',{exact:true})).toHaveCount(0);
 await page.getByLabel('Carry motion',{exact:true}).selectOption('22');
 await page.getByRole('button',{name:'Motion latent',exact:true}).click();
 await expect(page.getByLabel('Drift treatment',{exact:true})).toHaveValue('drift_color');
 await expect(page.getByLabel('Carry motion',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await expect(page.getByLabel('Carry motion',{exact:true})).toHaveValue('22');
 await page.getByRole('button',{name:'Motion latent',exact:true}).click();
 await page.getByLabel('Drift treatment',{exact:true}).selectOption('off');
 await page.locator('.continuation-advanced>summary').click();
 await expect(page.getByLabel('Refinement method',{exact:true})).toHaveCount(0);
 await page.getByLabel('Enable refinement',{exact:true}).check();
 await expect(page.getByLabel('Drift treatment',{exact:true})).toBeDisabled();
 await page.getByLabel('Refinement method',{exact:true}).selectOption('noembryo_stats');
 await expect(page.getByLabel('Refinement model',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await page.getByRole('button',{name:'Motion latent',exact:true}).click();
 await page.locator('.continuation-advanced>summary').click();
 await expect(page.getByLabel('Enable refinement',{exact:true})).toBeChecked();
 await expect(page.getByLabel('Refinement method',{exact:true})).toHaveValue('noembryo_stats');
});

test('last-frame queue excludes inactive latent treatments while retaining remembered choices',async({page})=>{
 const {queued}=await fixture(page);
 await page.locator('.continuation-advanced>summary').click();
 await page.getByLabel('Enable refinement',{exact:true}).check();
 await page.getByLabel('Refinement method',{exact:true}).selectOption('noembryo_stats');
 await page.getByLabel('Seam frame correction',{exact:true}).selectOption('2');
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await page.getByLabel('Carry motion',{exact:true}).selectOption('22');
 await page.getByRole('button',{name:'Generate segment',exact:true}).click();
 await expect.poll(()=>queued.length).toBe(1);
 expect(queued[0]).toMatchObject({continuation_method:'last_frame',context:0,image_motion_frames:22,decode_edge_frames:0,continuation_protection:'off',refine:{enabled:false}});
 expect(queued[0].continuation_options.latent.refine.enabled).toBe(true);
 expect(queued[0].continuation_options.latent.decode_edge_frames).toBe(2);
});

test('actual Omni ancestry blocks saved PDD handoff without relying on configuration labels',async({page})=>{
 await fixture(page);
 await page.getByLabel('PDD base-model handoff',{exact:true}).selectOption('auto');
 await page.getByText('Generation configuration',{exact:true}).first().click();
 await page.getByRole('combobox',{name:'Generation configuration',exact:true}).selectOption('omni');
 await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeDisabled();
 await expect(page.getByLabel('PDD base-model handoff',{exact:true})).toHaveCount(0);
 await page.locator('.generate-footer').getByRole('button',{name:'Turn off handoff',exact:true}).click();
 await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeEnabled();
});

test('duration, seed and generate remain in view while advanced settings scroll on a smaller screen',async({page})=>{
 await page.setViewportSize({width:1366,height:768});
 await fixture(page);
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await page.getByLabel('Carry motion',{exact:true}).selectOption('22');
 await page.screenshot({path:'../.test-tmp/continuation-last-frame-1366.png'});
 await page.getByRole('button',{name:'Motion latent',exact:true}).click();
 await page.locator('.continuation-advanced>summary').click();
 await page.getByLabel('Enable refinement',{exact:true}).check();
 await page.locator('.anti-burn-disclosure>summary').click();
 await page.locator('.target-inspector .inspector-scroll').evaluate(node=>{node.scrollTop=node.scrollHeight;});
 for(const locator of [page.getByLabel('New footage duration',{exact:true}),page.getByLabel('Seed',{exact:true}),page.getByRole('button',{name:'Generate segment',exact:true})]){
  await expect(locator).toBeInViewport();
 }
 await page.locator('.target-inspector .inspector-scroll').evaluate(node=>{node.scrollTop=0;});
 await page.screenshot({path:'../.test-tmp/continuation-ui-1366.png'});
});

test('independent first segment hides continuation-only settings',async({page})=>{
 await fixture(page,true);
 await expect(page.getByRole('group',{name:'Continuation method',exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Motion and audio context',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Carry motion',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeVisible();
});


test('method preferences survive a saved draft reload',async({page})=>{
 const {p}=await fixture(page);
 await page.getByLabel('Drift treatment',{exact:true}).selectOption('drift_color');
 await page.getByRole('button',{name:'Last frame',exact:true}).click();
 await page.getByLabel('Carry motion',{exact:true}).selectOption('22');
 await expect.poll(()=>p.scenes[0].segments[1].working_draft.image_motion_frames).toBe(22);
 await page.reload();
 await expect(page.getByRole('button',{name:'Last frame',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByLabel('Carry motion',{exact:true})).toHaveValue('22');
 await page.getByRole('button',{name:'Motion latent',exact:true}).click();
 await expect(page.getByLabel('Drift treatment',{exact:true})).toHaveValue('drift_color');
});

test('statistics-only refinement does not inherit the hidden recovered-model setting',async({page})=>{
 const {queued}=await fixture(page);
 await page.locator('.continuation-advanced>summary').click();
 await page.getByLabel('Enable refinement',{exact:true}).check();
 await page.getByLabel('Refinement model',{exact:true}).selectOption('base');
 await page.getByLabel('Refinement method',{exact:true}).selectOption('noembryo_stats');
 await expect(page.getByLabel('Refinement model',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Generate segment',exact:true}).click();
 await expect.poll(()=>queued.length).toBe(1);
 expect(queued[0].refine).toMatchObject({enabled:true,mode:'noembryo_stats',model:'received'});
});

test('VPipe is under experimental methods and excludes latent-only treatments',async({page})=>{
 await fixture(page);
 await page.getByRole('button',{name:'More continuation methods',exact:true}).click();
 await page.getByLabel('Experimental continuation method',{exact:true}).selectOption('video_reference');
 await expect(page.getByLabel('Motion and audio context',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Carry motion',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Drift treatment',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Enable refinement',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('PDD base-model handoff',{exact:true})).toBeVisible();
});
