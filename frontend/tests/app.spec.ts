import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {FIELDS,Project,Take,Reference} from '../src/types';
import {scopedReferences} from '../src/ReferencesPanel';

const fields=()=>Object.fromEntries(FIELDS.map(f=>[f,'']));
const draft=(scene_id:string,segment_id:string)=>({scene_id,segment_id,mode:'new',profile:'ref2va',seconds:5,width:768,height:448,seed:1,context:39,fields:fields()}) as any;
const fixtureVideo=readFileSync('tests/fixtures/scrub.webm');
const projectVideo=readFileSync('tests/fixtures/project-review.webm');
async function openConfiguration(page:Page){
 const group=page.locator('.target-inspector details.group[aria-label="Generation configuration"]');
 if(await group.count()&&await group.isVisible()&&!await group.evaluate(node=>(node as HTMLDetailsElement).open))await group.locator(':scope > summary').click();
}
async function openAdvanced(page:Page){
 const details=page.locator('.continuation-advanced');
 await expect(details).toHaveCount(1);
 if(await details.count()&&!await details.evaluate(node=>(node as HTMLDetailsElement).open))await details.locator(':scope > summary').click();
}
async function chooseContinuation(page:Page,method:string){
 if(method==='video_reference'){
  await page.getByRole('button',{name:'More continuation methods',exact:true}).click();
  await page.getByLabel('Experimental continuation method',{exact:true}).selectOption(method);
 }else await page.getByRole('button',{name:method==='latent'?'Motion latent':'Last frame',exact:true}).click();
}

async function fixture(page:Page,empty=false,configurations:any[]=[],initialRoute="timeline/generate",switches?:any[]){
  let created=!empty;
  const video=fixtureVideo;
  let p:Project={resolution:{width:768,height:448},id:'production',name:'Coastal Journey',revision:1,scenes:[{id:'scene',name:'A New Horizon',segments:[{id:'segment-1',name:'Segment 01',takes:[],active_output:null,working_draft:draft('scene','segment-1')}]}],takes:{},jobs:{},references:[],effective_references:{'segment-1':[]}};
  const catalog:Project[]=empty?[]:[p];
  let count=1;const submitted:Record<string,unknown>[]=[];
  const allSegments=()=>p.scenes.flatMap(scene=>scene.segments);
  const compile=(body:any)=>{
    const images=structuredClone(scopedReferences(p,'segment',body.scene_id,body.segment_id)).filter(item=>item.enabled);
    const result:any={prompt:Object.entries(body.fields).map(([key,value])=>`${key}:\n${value}`).join('\n'),mappings:{},images};
    if(body.continuation_method==='last_frame'&&body.profile==='ref2va'&&body.source_take_id){
      const native_label=`<Picture ${images.length+1}>`;
      result.continuation_picture={native_label};
      result.automatic_additions={subject_definitions:`${native_label} is the final frame of the preceding segment and the first frame of [Shot 1].`,retention_analysis:`${native_label} ([Shot 1] first frame): fully_preserved - Preserve the opening frame.`,detailed_description:`The video continues from ${native_label} as its first frame. Start from the depicted pose and composition, then continue the following action naturally.`};
      result.prompt+='\n'+Object.values(result.automatic_additions).join('\n');
      images.push({id:'continuation',native_label,generated_role:'continuation_frame'} as any);
    }
    if(body.continuation_method==='video_reference'&&body.source_take_id){
      result.continuation_video={native_label:'<Video 1>',audio_label:'<Audio 1>'};
      result.automatic_additions={summary:'[video continuation + audio reference] '+body.fields.summary,detailed_description:'Continue immediately from the end of <Video 1>. Use <Audio 1> as a sound reference.'};
      result.prompt+='\n'+Object.values(result.automatic_additions).join('\n');
    }
    return result;
  };
  const addScene=(name:string)=>{
    const id=`scene-${++count}`,segmentId=`segment-${++count}`;
    const scene={id,name,segments:[{id:segmentId,name:'Segment 01',takes:[],active_output:null,working_draft:draft(id,segmentId)}]};
    p.scenes.push(scene);p.effective_references[segmentId]=p.references;return scene;
  };
  await page.addInitScript(({choices,switches})=>{window.longcasterTimelineBridge={status:()=>({connected:true,message:'Fixture execution bridge'}),submit:async(data)=>{await (window as any).testSubmit(data);return {prompt_id:'fixture'};},cancel:async()=>({queuedRemoved:true}),subscribe:(callback)=>{(window as any).testProgress=callback;return()=>{};}};if(choices.length){window.longcasterTimelineBridge.configurations=async()=>choices;window.longcasterTimelineBridge.prepareConfiguration=async(id)=>{const choice=choices.find(c=>c.id===id);if(!choice)throw new Error('Configuration unavailable');return {...choice,selector_id:'switch',slot:id==='pdd'?'B':'A',upstream:{}};};}if(switches){(window as any).testSwitches=switches;window.longcasterTimelineBridge.configurationSwitches=async(id,selections)=>{
 const live=(window as any).testSwitches.map((item:any)=>({...item,select:selections[item.id]||item.options.find((option:any)=>option.configuration_id===id)?.value||item.select}));
 if(Object.keys(selections).some(key=>!live.some((item:any)=>item.id===key)))throw new Error('Saved switch is missing from this workflow.');
 return {switches:live,error:(window as any).testSwitchError||''};
 };}}, {choices:configurations,switches});
  await page.exposeFunction('testSubmit',async(data:Record<string,unknown>)=>{submitted.push(data);});
  await page.route('**/longcaster-timeline/anti-burn',route=>route.fulfill({json:{available:false,warning:'Anti-Burn LoRA not found. Install h3_antiburn_universal_v1.safetensors in models/loras.'}}));
  await page.route('**/longcaster-timeline/loras',route=>route.fulfill({json:{filenames:['style.safetensors','motion.safetensors']}}));
  await page.route('**/longcaster-timeline/projects**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname;const id=path.match(/\/projects\/([^/]+)/)?.[1];if(id){const selected=catalog.find(row=>row.id===id);if(selected)p=selected;}let result:unknown=p;
    if(path.endsWith('/projects')) {
      if(req.method()==='POST'){if(created)p={...structuredClone(p),id:`production-${++count}`,scenes:[],references:[],effective_references:{},takes:{},jobs:{}};created=true;p.name=req.postDataJSON().name;p.scenes=[];addScene('Scene 01');p.revision++;catalog.push(p);result=p;}
      else result={projects:catalog.map(row=>({id:row.id,name:row.name}))};
    }
    else if(path.endsWith('/duplicate')&&req.method()==='POST'){
      const copied=structuredClone(p);copied.id=`copy-production-${++count}`;copied.name=req.postDataJSON().name;copied.revision=1;
      if(req.postDataJSON().without_generations===false){catalog.push(copied);await route.fulfill({json:copied});return;}
      copied.takes={};copied.jobs={};copied.effective_references={};delete copied.generation_defaults;
      for(const scene of copied.scenes){scene.id='copy-'+scene.id;for(let i=0;i<scene.segments.length;i++){
        const segment=scene.segments[i];segment.id='copy-'+segment.id;segment.takes=[];segment.active_output=null;segment.planned=true;
        const settings=segment.working_draft!;delete settings.source_take_id;delete settings.configuration;delete settings.configuration_id;delete settings.switch_selections;delete settings.configuration_override;
        Object.assign(settings,{scene_id:scene.id,segment_id:segment.id,mode:i?'extend':'new',source_segment_id:i?scene.segments[i-1].id:undefined});
        copied.effective_references[segment.id]=copied.references;
      }}
      catalog.push(copied);p=copied;result=copied;
    }
    else if(path.endsWith('/delete')){catalog.splice(catalog.findIndex(row=>row.id===p.id),1);created=catalog.length>0;result={deleted:true};}
    else if(path.endsWith('/export')){result={status:'ready',download_url:`/longcaster-timeline/projects/${p.id}/exports/fixture`};}
    else if(path.endsWith('/preview')&&req.method()==='POST'){
      const body=req.postDataJSON();let frame=0;const entries:any[]=[];
      for(const scene of p.scenes){if(body.scene_id&&scene.id!==body.scene_id)continue;let local=0;for(const segment of scene.segments){
        const active=segment.active_output?.take_id;
        const selected=body.include_drafts&&segment.takes.includes(body.draft_take_id)?body.draft_take_id:active||(body.include_drafts?segment.takes.at(-1):undefined);
        const take=p.takes[selected||''];if(!take)continue;
        entries.push({scene_id:scene.id,scene_name:scene.name,segment_id:segment.id,segment_name:segment.name,take_id:take.id,take_number:take.number,draft:take.id!==active,start_frame:frame,end_frame:frame+take.plan.new_frames,scene_start_frame:local});
        frame+=take.plan.new_frames;local+=take.plan.new_frames;
      }}
      result={key:entries.map(e=>e.take_id+e.draft).join('-'),status:entries.length?'ready':'empty',message:'Generate a take preview to review the project.',frames:frame,seconds:frame/24,draft_count:entries.filter(e=>e.draft).length,entries};
    }
    else if(path.includes('/media/take/')||/\/preview\/[^/]+$/.test(path)){
      const video=path.includes('/media/take/')?fixtureVideo:projectVideo;
      const range=req.headers()['range']?.match(/bytes=(\d+)-(\d*)/);
      if(range){const start=Number(range[1]),end=range[2]?Math.min(Number(range[2]),video.length-1):video.length-1;await route.fulfill({status:206,contentType:'video/webm',headers:{'Accept-Ranges':'bytes','Content-Range':`bytes ${start}-${end}/${video.length}`},body:video.subarray(start,end+1)});}
      else await route.fulfill({status:200,contentType:'video/webm',headers:{'Accept-Ranges':'bytes'},body:video});
      return;
    }
    else if(path.includes('/media/reference/')){await route.fulfill({status:200,contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#53748d"/><circle cx="50" cy="35" r="15" fill="#e0c7a0"/></svg>'});return;}
    else if(req.method()==='POST') {
      const body=req.postDataJSON();
      if(path.endsWith('/migration-preview')){const segment=allSegments().find(s=>s.id===body.segment_id)!;const authored=segment.working_draft!.fields;result={fields:{...authored,subject_definitions:authored.subject_definitions.replace(/<hero>/gi,'<Subject 1>')+' Referenced appearance comes from <picture.hero>.',detailed_description:authored.detailed_description.replace(/<hero>/gi,'<Subject 1>')}};}
      else if(path.endsWith('/compile'))result=compile(body);
      else if(path.endsWith('/command')){
        if(body.action==='set_reference_image_size')p.ref_image_size=body.ref_image_size;
        if(body.action==='set_generation_defaults')p.generation_defaults=body.defaults;
        if(body.action==='rename_project')p.name=body.name;
        if(body.action==='set_upscale')p.upscale_resolution={width:body.width,height:body.height};
        if(body.action==='set_loras')p.loras=(p.loras||[]).filter(item=>item.scope!==body.scope||item.owner_id!==body.owner_id).concat(body.entries.map((item:any)=>({...item,scope:body.scope,owner_id:body.owner_id})));
        if(body.action==='create_scene')addScene(body.name);
        if(body.action==='set_resolution'){p.resolution={width:body.width,height:body.height};for(const s of allSegments())Object.assign(s.working_draft!,p.resolution);}
        if(body.action==='migrate_prompt')allSegments().find(s=>s.id===body.segment_id)!.working_draft!.fields=body.reviewed_fields;
        if(body.action==='rename_scene')p.scenes.find(scene=>scene.id===body.scene_id)!.name=body.name;
        if(body.action==='create_segment'){
          const scene=p.scenes.find(scene=>scene.id===body.scene_id)!;
          const id=`segment-${++count}`;scene.segments.push({id,name:`Segment ${String(scene.segments.length+1).padStart(2,'0')}`,takes:[],active_output:null,working_draft:{...body.draft,segment_id:id}});p.last_created_segment_id=id;
          p.effective_references[id]=p.references;
        }
        if(body.action==='plan_segment'){
          const scene=p.scenes.find(scene=>scene.id===body.scene_id)!;
          const index=scene.segments.findIndex(segment=>segment.id===body.after_segment_id);
          const id=`segment-${++count}`;
          scene.segments.splice(index+1,0,{id,name:`Segment ${String(index+2).padStart(2,'0')}`,takes:[],active_output:null,planned:true,working_draft:draft(scene.id,id)});
          scene.segments.forEach((segment,i)=>{if(i>index)segment.name=`Segment ${String(i+1).padStart(2,'0')}`;});
          p.last_created_segment_id=id;p.effective_references[id]=p.references;
        }
        if(body.action==='set_scene_anti_burn')p.scenes.find(scene=>scene.id===body.scene_id)!.anti_burn=body.anti_burn;
        if(body.action==='save_draft')allSegments().find(segment=>segment.id===body.segment_id)!.working_draft=body.draft;
        if(body.action==='finalize'){const t=p.takes[body.take_id];allSegments().find(segment=>segment.id===t.segment_id)!.active_output={kind:'single_take',take_id:t.id};}
        if(body.action==='reference'){let r=p.references.find(r=>r.id===body.reference_id)!;if(body.scope&&body.scope!==r.scope){r={...r,id:`ref-override-${++count}`,scope:body.scope,owner_id:body.owner_id,overrides:r.overrides||r.id};p.references.push(r);}Object.assign(r,...['enabled','token_name','conditioning_mode','latent_strength'].filter(key=>body[key]!==undefined).map(key=>({[key]:body[key]})));if(body.replacement_draft)allSegments().find(segment=>segment.id===body.segment_id)!.working_draft=body.replacement_draft;}
        if(body.action==='cancel')p.jobs[body.job_id].status='cancel_requested';
        if(body.action==='resolve_cancel')p.jobs[body.job_id].status='cancelled';
        p.revision++;
      } else if(path.endsWith('/jobs')){
        const workingDraft=structuredClone(body.settings);
        if(p.generation_defaults&&workingDraft.configuration_override!==true){workingDraft.configuration_override=false;delete workingDraft.configuration_id;delete workingDraft.switch_selections;delete workingDraft.configuration;}
        allSegments().find(segment=>segment.id===body.settings.segment_id)!.working_draft=workingDraft;
        const id=`job-${++count}`;const job={id,segment_id:body.settings.segment_id,status:'queued',created_at:new Date().toISOString(),progress:{stage:'queued'},snapshot:{...structuredClone(body.settings),ref_image_size:body.settings.ref_image_size||p.ref_image_size||'match',compiled:compile(body.settings),loras:structuredClone(p.loras||[])}};p.jobs[id]=job;p.revision++;result={state:p,job};
      }
    }
    await route.fulfill({json:result});
  });
  await page.goto(`./#/${initialRoute}`);if(initialRoute==='home'){await expect(page.getByRole('heading',{name:'Productions',exact:true})).toBeVisible();}else if(empty)await expect(page.getByRole('dialog')).toBeVisible();else {await expect(page.getByText('Coastal Journey',{exact:true})).toBeVisible();await expect(page.getByLabel('Generation prompt',{exact:true})).toBeEnabled();}
  if(initialRoute==='timeline/generate'&&!empty)await openConfiguration(page);
  return {p,current:()=>p,submitted,finish(segmentId:string){
    const segment=allSegments().find(segment=>segment.id===segmentId)!;const scene=p.scenes.find(scene=>scene.segments.includes(segment))!;
    const id=`take-${++count}`;const f={...fields(),detailed_description:'[Shot 1] <hero> watches the waves.'};
    const settings=segment.working_draft!;const original=p.takes[segment.active_output?.take_id||''];
    const source=original?.snapshot.source||p.takes[settings.source_take_id||''];
    const context=source?39:0;const sampled=context?158:124;
    const take={id,number:segment.takes.length+1,segment_id:segment.id,scene_id:scene.id,width:768,height:448,created_at:new Date().toISOString(),latent_sha256:'a'.repeat(64),plan:{sampled_frames:sampled,context_frames:context,new_frames:sampled-context,new_seconds:(sampled-context)/24,delivery:{start:context,end:sampled}},snapshot:{configuration:settings.configuration,seed:1,source:source?{id:source.id}:null,profile:'ref2va',compiled:{prompt:JSON.stringify(f),authored_fields:f,resolved_fields:f,mappings:{hero:{label:'<Subject 1>',source_label:'<Picture 1>'}}}},receipt:{sigma_values:[1,.5,0],sampler:'fixture',model_class:'fixture',source:null,references:[]},preview:{status:'ready'}} as Take;
    p.takes[id]=take;segment.takes.push(id);for(const job of Object.values(p.jobs))if(job.segment_id===segmentId){job.status='succeeded';job.progress={stage:'complete'};}p.revision++;return take;
  }};
}

test('new segment, generate, finalize and frozen extension source',async({page})=>{
  const failures:string[]=[];page.on('pageerror',e=>failures.push(e.message));
  const {p,submitted,finish}=await fixture(page);
  await expect(page.getByLabel('Generation prompt',{exact:true})).toBeEnabled();
  const a=p.scenes[0].segments[0];
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] A traveller watches the waves.');
  await page.getByRole('button',{name:/^Generate (first segment|segment)$/}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  await expect(page.getByRole('button',{name:'Stop generation'})).toBeVisible();
  const take=finish(a.id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await expect(page.getByRole('button',{name:'Extend scene',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await expect.poll(()=>p.scenes[0].segments.length).toBe(2);
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The traveller turns toward the lighthouse.');
  await page.getByRole('button',{name:/^Generate (first segment|segment)$/}).click();
  await expect.poll(()=>submitted.length).toBe(2);
  const job=Object.values(p.jobs).at(-1) as any;
  expect(job.snapshot.source_take_id).toBe(take.id);
  expect(job.snapshot.context).toBe(39);
  await expect(page.getByLabel('Frozen source prompt')).toHaveValue('[Shot 1] <hero> watches the waves.');
  expect(failures).toEqual([]);
});

test('last-frame extension uses FL2VA, keeps the finalized source and sends zero motion context',async({page})=>{
  const failures:string[]=[];page.on('pageerror',e=>failures.push(e.message));
  const {p,submitted,finish}=await fixture(page,false,[{id:'ref',name:'Native REF2VA',profile:'ref2va'},{id:'image',name:'FL2VA image',profile:'fl2va'}]);
  await page.route('**/longcaster-timeline/capabilities',route=>route.fulfill({json:{image_continuation:4,image_motion:1,pdd_warmup:2}}));
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] A traveller watches the waves.');
  await page.getByRole('button',{name:/^Generate (first segment|segment)$/}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const take=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await page.getByRole('combobox',{name:'Generation configuration',exact:true}).selectOption('ref');
  await chooseContinuation(page,'last_frame');
  await page.getByRole('combobox',{name:'Generation mode',exact:true}).selectOption('fl2va');
  await expect(page.getByRole('combobox',{name:'Generation mode',exact:true})).toHaveValue('fl2va');
  await expect(page.getByLabel('Carry motion',{exact:true})).toBeDisabled();
  await expect(page.getByLabel('Carry motion',{exact:true})).toHaveValue('0');
  await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeDisabled();
  await page.getByRole('combobox',{name:'Generation configuration',exact:true}).selectOption('image');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The traveller turns toward the lighthouse.');
  await page.getByRole('button',{name:'Generate segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(2);
  const snapshot=(Object.values(p.jobs).at(-1) as any).snapshot;
  expect(snapshot.source_take_id).toBe(take.id);
  expect(snapshot.continuation_method).toBe('last_frame');
  expect(snapshot.profile).toBe('fl2va');expect(snapshot.context).toBe(0);
  expect(snapshot.refine.enabled).toBe(false);expect(snapshot.continuation_protection).toBe('off');
  expect(failures).toEqual([]);
});

test('REF2VA last-frame continuation retains enabled named references and generation profile',async({page})=>{
  const {p,submitted,finish}=await fixture(page,false,[{id:'ref',name:'Native REF2VA',profile:'ref2va'}]);
  await page.route('**/longcaster-timeline/capabilities',route=>route.fulfill({json:{image_continuation:4,image_motion:1,pdd_warmup:2}}));
  const reference={id:'main',token_name:'main',display_name:'Main',scope:'project',owner_id:null,role:'picture',kind:'image',enabled:true,asset_path:'assets/main.png',asset_sha256:'b'.repeat(64)} as Reference;
  p.references.push(reference);p.effective_references[p.scenes[0].segments[0].id]=p.references;p.revision++;
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] A person performs pull-ups.');
  await page.getByRole('button',{name:/^Generate (first segment|segment)$/}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const take=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await chooseContinuation(page,'last_frame');
  await expect(page.getByRole('combobox',{name:'Generation mode',exact:true})).toHaveValue('ref2va');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The person continues performing pull-ups.');
  await expect(page.getByRole('note')).toContainText('<Picture 2> is the last frame');
  await page.locator('.continuation-prompt-note details>summary').click();
  await expect(page.getByLabel('Automatic continuation instructions')).toContainText('The video continues from <Picture 2> as its first frame.');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] The person continues performing pull-ups.');
  await page.getByRole('button',{name:'Toggle compiled prompt',exact:true}).click();
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue(/<Picture 2> \(\[Shot 1\] first frame\): fully_preserved/);
  await page.getByRole('button',{name:'Toggle compiled prompt',exact:true}).click();
  await page.getByLabel('Carry motion',{exact:true}).selectOption('22');
  await page.getByRole('button',{name:'Generate segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(2);
  const snapshot=(Object.values(p.jobs).at(-1) as any).snapshot;
  expect(snapshot.profile).toBe('ref2va');expect(snapshot.continuation_method).toBe('last_frame');
  expect(snapshot.source_take_id).toBe(take.id);expect(snapshot.context).toBe(0);
  expect(snapshot.image_motion_frames).toBe(22);
  expect(snapshot.compiled.images).toHaveLength(2);
  expect(snapshot.compiled.images[0]).toMatchObject({token_name:'main',enabled:true,asset_sha256:reference.asset_sha256});
  expect(p.references[0].enabled).toBe(true);
  expect(snapshot.compiled.images[1]).toMatchObject({native_label:'<Picture 2>',generated_role:'continuation_frame'});
  expect(snapshot.compiled.prompt).toContain('The video continues from <Picture 2> as its first frame.');
});

test('VPipe-style continuation shows automatic wording, keeps PDD and blocks incompatible controls',async({page})=>{
  const {p,submitted,finish}=await fixture(page,false,[{id:'ref',name:'Native REF2VA',profile:'ref2va'}]);
  await page.route('**/longcaster-timeline/capabilities',route=>route.fulfill({json:{video_continuation:1,pdd_warmup:2}}));
  const take=finish(p.scenes[0].segments[0].id);
  await page.getByRole('button',{name:'Finalize selected take',exact:true}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await openAdvanced(page);
  await page.getByLabel('PDD base-model handoff',{exact:true}).selectOption('auto');
  await chooseContinuation(page,'video_reference');
  await expect(page.getByLabel('Generation mode',{exact:true})).toHaveValue('ref2va');
  await expect(page.getByLabel('Generation mode',{exact:true})).toBeDisabled();
  await expect(page.getByLabel('Carry motion',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Motion and audio context',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('PDD base-model handoff',{exact:true})).toHaveValue('auto');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Continue the pull-ups.');
  await page.locator('.continuation-prompt-note details>summary').click();
  await expect(page.getByLabel('Automatic video continuation instructions')).toContainText('<Video 1>');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] Continue the pull-ups.');
  await page.getByLabel('New footage duration',{exact:true}).fill('2');
  await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeDisabled();
  await page.getByLabel('New footage duration',{exact:true}).fill('5');
  await expect(page.getByLabel('Drift treatment',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Enable refinement',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Generate segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const snapshot=(Object.values(p.jobs).at(-1) as any).snapshot;
  expect(snapshot.continuation_method).toBe('video_reference');
  expect(snapshot.source_take_id).toBe(take.id);expect(snapshot.pdd_warmup).toBe('auto');
  expect(snapshot.image_motion_frames).toBe(0);
  expect(snapshot.compiled.prompt).toContain('video continuation + audio reference');
});

test('queued cancellation allows another attempt',async({page})=>{
  const {p,submitted}=await fixture(page);
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The sea rises.');
  await page.getByRole('button',{name:/^Generate (first segment|segment)$/}).click();await expect.poll(()=>submitted.length).toBe(1);
  await page.getByRole('button',{name:'Stop generation'}).click();
  await expect(page.getByRole('button',{name:/^Generate (first segment|segment)$/})).toBeEnabled();
  expect(Object.values(p.jobs)[0].status).toBe('cancelled');
});

test('reference rename previews and updates current draft tokens',async({page})=>{
  const {p}=await fixture(page);
  const reference={id:'hero',token_name:'hero',display_name:'Hero',scope:'project',owner_id:null,role:'subject',kind:'image',enabled:true,asset_path:'assets/hero.png',asset_sha256:'b'.repeat(64)} as Reference;
  p.references.push(reference);p.effective_references[p.scenes[0].segments[0].id]=[reference];p.revision++;
  await page.getByRole('tab',{name:'References',exact:true}).click();
  await expect(page.getByText('<picture.hero>',{exact:true})).toBeVisible();
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] <Hero> approaches the shore.');
  await page.getByTitle('Rename reference',{exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Other drafts using the old name must be updated');
  await page.getByLabel('New reference name').fill('traveller');
  await page.getByRole('button',{name:'Apply rename',exact:true}).click();
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] <traveller> approaches the shore.');
  expect(p.scenes[0].segments[0].working_draft?.fields.detailed_description).toContain('<traveller>');
});

test('layout, reference scopes and prompt editing at desktop sizes',async({page})=>{
  const {p,finish}=await fixture(page);
  const a=p.scenes[0].segments[0];const take=finish(a.id);a.active_output={kind:'single_take',take_id:take.id};p.revision++;
  await expect(page.getByRole('button',{name:'Select Segment 01'})).toContainText('FINALIZED');
  await page.getByRole('button',{name:'Select Segment 01'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  const r={id:'hero',token_name:'hero',display_name:'Hero',scope:'project',owner_id:null,role:'subject',kind:'image',enabled:true,asset_path:'assets/hero.png',asset_sha256:'b'.repeat(64)} as Reference;
  p.references.push(r);for(const seg of p.scenes[0].segments)p.effective_references[seg.id]=[r];p.revision++;
  await page.getByRole('tab',{name:'References',exact:true}).click();
  await expect(page.getByText('<picture.hero>',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Scene',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('group',{name:'Reference settings scope'}).getByRole('button')).toHaveCount(3);
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] <hero> turns toward a distant lighthouse. The breeze pulls at his jacket.');
  await page.getByRole('button',{name:'Expand prompt editor'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByLabel('Expanded generation prompt').fill('[Shot 1] <hero> walks toward the lighthouse.');
  await page.getByRole('button',{name:'Close expanded prompt'}).click();
  for(const [width,height] of [[1920,1080],[1366,768],[2560,1440]]){
    await page.setViewportSize({width,height});
    await expect(page.getByRole('region',{name:'Current segment preview',exact:true})).toBeVisible();
    await expect(page.getByRole('region',{name:'New generation',exact:true})).toBeVisible();
    await expect(page.getByText('Generation timeline',{exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`../docs/screenshots/first-slice-${width}.png`,fullPage:true});
  }
});

test('new project and new scene each open their own first segment ready to generate',async({page})=>{
  const {p}=await fixture(page,true);
  await page.getByLabel('New production name').fill('New Production');
  await page.getByRole('button',{name:'Create production',exact:true}).click();
  await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeEnabled();
  expect(p.scenes).toHaveLength(1);expect(p.scenes[0].segments).toHaveLength(1);
  const originalScene=p.scenes[0].id;
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The first scene.');
  await page.getByRole('button',{name:'New scene',exact:true}).click();
  await page.getByLabel('Scene name').fill('Second Scene');
  await page.getByRole('button',{name:'Create new scene',exact:true}).click();
  await expect.poll(()=>p.scenes.length).toBe(2);await expect(page.getByLabel('Current scene')).toHaveValue(p.scenes[1].id);
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('');
  await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeEnabled();
  expect(p.scenes[1].segments[0].name).toBe('Segment 01');
  await page.getByLabel('Current scene').selectOption(originalScene);
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] The first scene.');
});

test('paste prompt distributes the sections, including direct clipboard paste',async({page})=>{
  await fixture(page);
  await page.getByRole('button',{name:'Paste prompt',exact:true}).click();
  await page.getByLabel('Complete prompt to import').fill('subject_definitions:\n<hero> is a traveller.\nsummary:\nA journey.\nretention_analysis:\n<hero>: weak_reference - preserve appearance.\ndetailed_description:\n[Shot 1] At 00:01.000 <hero> walks.\noverall_soundscape:\nWaves.\nnon_diegetic_music:\nNone.');
  await expect(page.getByRole('dialog')).toContainText('Detected: Subject definitions, Summary');
  await page.getByRole('button',{name:'Apply prompt sections'}).click();
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] At 00:01.000 <hero> walks.');
  await page.getByLabel('Generation prompt field').selectOption('summary');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('A journey.');
  await page.getByLabel('Generation prompt',{exact:true}).evaluate((element)=>{
    const clipboard=new DataTransfer();clipboard.setData('text/plain','summary:\nUpdated journey.\ndetailed_description:\n[Shot 1] A new camera angle.');
    element.dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}));
  });
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('Updated journey.');
  await page.getByLabel('Generation prompt field').selectOption('detailed_description');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] A new camera angle.');
  await page.getByLabel('Generation prompt field').selectOption('overall_soundscape');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('Waves.');
});

test('replace stays in the tail segment and is unavailable on earlier segments',async({page})=>{
  const {p,finish,submitted}=await fixture(page);
  const a=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Replace tail segment'}).click();
  await expect(page.getByRole('button',{name:'Generate replacement'})).toBeVisible();
  await page.getByRole('button',{name:'Generate replacement'}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const replacementJob=Object.values(p.jobs).at(-1) as any;
  expect(replacementJob.segment_id).toBe(a.segment_id);
  expect(replacementJob.snapshot.mode).toBe('regenerate');
  expect(replacementJob.snapshot.source_take_id).toBeUndefined();
  const replacement=finish(a.segment_id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  expect(p.scenes[0].segments).toHaveLength(1);expect(p.takes[a.id]).toBeDefined();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  const b=finish(p.scenes[0].segments[1].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Select Segment 01'}).click();
  await expect(page.getByRole('button',{name:'Replace tail segment'})).toBeDisabled();
  await page.getByRole('button',{name:'Select Segment 02'}).click();
  await page.getByRole('button',{name:'Replace tail segment'}).click();
  await page.getByRole('button',{name:'Generate replacement'}).click();
  await expect.poll(()=>submitted.length).toBe(2);
  const next=Object.values(p.jobs).at(-1) as any;
  expect(next.segment_id).toBe(b.segment_id);expect(next.snapshot.source_take_id).toBe(replacement.id);
});

test('planned segments can be inserted after the current draft and do not block replacing its take',async({page})=>{
  const {p,finish,submitted}=await fixture(page);
  const first=p.scenes[0].segments[0];
  await page.getByRole('button',{name:'Add planned segment'}).click();
  await expect(page.getByRole('button',{name:'Select Segment 02'})).toBeVisible();
  await page.getByRole('button',{name:'Add planned segment'}).click();
  await expect(page.getByRole('button',{name:'Select Segment 03'})).toBeVisible();
  expect(p.scenes[0].segments.map(segment=>segment.name)).toEqual(['Segment 01','Segment 02','Segment 03']);
  await expect(page.getByLabel('Generation prompt',{exact:true})).toBeEnabled();
  const firstTake=finish(first.id);
  await expect(page.getByRole('button',{name:'Generate replacement'})).toBeVisible();
  await page.getByRole('button',{name:'Generate replacement'}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const retry=finish(first.id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  expect(first.active_output?.take_id).toBe(retry.id);
  await page.getByRole('button',{name:'Select Segment 01'}).click();
  await expect(page.getByRole('button',{name:'Replace tail segment'})).toBeEnabled();
  await page.getByRole('button',{name:'Replace tail segment'}).click();
  await expect(page.getByRole('button',{name:'Generate replacement'})).toBeVisible();
  expect(p.scenes[0].segments).toHaveLength(3);
  expect(p.takes[firstTake.id]).toBeDefined();
});

test('dragging the scene timeline scrubs real video across segment boundaries and keeps the generation draft',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const {p,finish}=await fixture(page);
  const a=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  finish(p.scenes[0].segments[1].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Preserve this pending third segment.');
  const ruler=page.getByRole('slider',{name:'Scene timeline',exact:true});const box=(await ruler.boundingBox())!;
  await page.mouse.move(box.x+2.5*30,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+(a.plan.new_seconds+1.5)*30,box.y+box.height/2,{steps:12});await page.mouse.up();
  const video=page.getByRole('region',{name:'Current segment preview',exact:true}).locator('video');
  await expect.poll(()=>video.evaluate(element=>(element as HTMLVideoElement).currentTime)).toBeCloseTo(1.5,1);
  await expect(page.locator('.source-inspector .inspector-title')).toContainText('Segment 02');
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] Preserve this pending third segment.');
  await ruler.focus();await page.keyboard.press('ArrowRight');
  await expect.poll(()=>video.evaluate(element=>(element as HTMLVideoElement).currentTime)).toBeCloseTo(1.5+1/24,2);
  const playhead=page.getByLabel('Drag scene playhead');const handle=(await playhead.boundingBox())!;
  await page.mouse.move(handle.x+1,Math.max(handle.y+12,box.y+box.height+5));await page.mouse.down();
  await page.mouse.move(box.x+1*30,box.y+box.height/2,{steps:10});await page.mouse.up();
  await expect(page.locator('.source-inspector .inspector-title')).toContainText('Segment 01');
  await expect.poll(()=>video.evaluate(element=>(element as HTMLVideoElement).currentTime)).toBeCloseTo(1,1);
  expect(errors).toEqual([]);
});

test('scene preview plays across the draft seam, seeks from timeline and collapses',async({page})=>{
  const {p,finish}=await fixture(page);
  const a=p.scenes[0].segments[0];const first=finish(a.id);a.active_output={kind:'single_take',take_id:first.id};p.revision++;
  await expect(page.getByRole('button',{name:'Select Segment 01'})).toContainText('FINALIZED');
  await page.getByRole('button',{name:'Select Segment 01'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await expect(page.getByRole('button',{name:'Select Segment 02'})).toBeVisible();
  const b=p.scenes[0].segments[1];const second=finish(b.id);
  // A prompt-only segment can follow the generated draft in an invalidated production.
  p.scenes[0].segments.push({id:'future-segment',name:'Segment 03',takes:[],active_output:null,planned:true,working_draft:draft('scene','future-segment')});p.revision++;
  const region=page.getByRole('region',{name:'Scene preview',exact:true});
  await expect(region.getByText('1 draft',{exact:true})).toBeVisible();
  const movie=region.locator('video');
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThanOrEqual(1);
  const filmstrip=page.getByRole('button',{name:'Select Segment 01',exact:true}).locator('canvas.clip-filmstrip');
  await expect.poll(()=>filmstrip.evaluate((canvas:HTMLCanvasElement)=>canvas.getContext('2d')!.getImageData(0,0,1,1).data[3])).toBe(255);
  await page.locator('.timeline').screenshot({path:'tests/screenshots/video-editor-clips.png'});
  const seek=page.getByRole('slider',{name:'Scene preview seek',exact:true});
  await seek.fill("5");
  await region.getByRole('button',{name:'Play scene preview',exact:true}).click();
  await expect(region.locator('.project-preview-caption')).toContainText('Segment 02');
  await expect(region.locator('.project-preview-caption')).toContainText('unfinalized');
  await region.getByRole('button',{name:'Pause scene preview',exact:true}).click();
  expect(b.active_output).toBeNull();
  expect(second.snapshot.source?.id).toBe(first.id);
  const ruler=page.getByRole('slider',{name:'Scene timeline',exact:true});
  await ruler.focus();await page.keyboard.press('Home');
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeLessThan(.1);
  await expect(region.locator('.project-preview-caption')).toContainText('Segment 01');
  await page.getByRole('checkbox',{name:'Include draft takes'}).uncheck();
  await expect(region.getByText('Finalized',{exact:true})).toBeVisible();
  await expect(seek).toHaveAttribute('max',String((first.plan.new_frames-1)/24));
  expect(b.active_output).toBeNull();
  await page.screenshot({path:'tests/screenshots/project-preview-1920.png',fullPage:true});
  await page.getByRole('button',{name:'Hide current segment inspector'}).click();
  await expect(region).toBeVisible();
  await expect(page.getByRole('button',{name:'Show current segment inspector'})).toHaveAttribute('aria-expanded','false');
  await page.getByRole('button',{name:'Show current segment inspector'}).click();
  await expect(page.getByRole('checkbox',{name:'Include draft takes'})).not.toBeChecked();
});

test('scene preview remains available on smaller screens',async({page})=>{
  await page.setViewportSize({width:1366,height:768});
  await fixture(page);
  await expect(page.getByRole('region',{name:'Scene preview',exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Scene preview',exact:true})).toBeVisible();
  await page.screenshot({path:'tests/screenshots/project-preview-1366.png',fullPage:true});
  await page.reload();await openConfiguration(page);
  await expect(page.getByRole('region',{name:'Scene preview',exact:true})).toBeVisible();
});



test('named configurations can be changed between takes and are recorded with each take',async({page})=>{
  const choices=[{id:'baseline',name:'REF2VA baseline',profile:'ref2va'},{id:'pdd',name:'PDD 8 steps',profile:'ref2va'}];
  const {p,finish,submitted}=await fixture(page,false,choices);
  const selector=page.getByRole('combobox',{name:'Generation configuration',exact:true});
  await expect(selector.locator('option')).toHaveCount(2);
  await selector.selectOption('pdd');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] A traveller walks.');
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  expect((submitted[0].configuration as any).name).toBe('PDD 8 steps');
  await expect(selector).toBeDisabled();
  const first=finish(p.scenes[0].segments[0].id);
  await expect(selector).toBeEnabled();
  await selector.selectOption('baseline');
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(2);
  expect((submitted[1].configuration as any).name).toBe('REF2VA baseline');
  expect(first.snapshot.configuration?.name).toBe('PDD 8 steps');
  const second=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  expect(second.snapshot.configuration?.name).toBe('REF2VA baseline');
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await expect(page.locator('.inspector').first().locator('dd').filter({hasText:/^REF2VA baseline$/})).toBeVisible();
  await selector.scrollIntoViewIfNeeded();
  await page.screenshot({path:'tests/screenshots/configurations-1920.png',fullPage:true});
});

test('extension duration is adjacent, zero disables Extend and the new draft uses it',async({page})=>{
  const {p,finish}=await fixture(page);
  const a=p.scenes[0].segments[0];const take=finish(a.id);a.active_output={kind:'single_take',take_id:take.id};p.revision++;
  await expect(page.getByRole('button',{name:'Select Segment 01'})).toContainText('FINALIZED');
  const duration=page.getByRole('spinbutton',{name:'Extension duration',exact:true});
  await duration.fill('0');
  await expect(page.getByRole('button',{name:'Extend scene',exact:true})).toBeDisabled();
  await duration.fill('7');
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await expect(page.getByRole('button',{name:'Select Segment 02'})).toBeVisible();
  expect(p.scenes[0].segments[1].working_draft?.seconds).toBe(7);
  await expect(page.getByRole('spinbutton',{name:'New footage duration',exact:true})).toHaveValue('7');
  await page.getByRole('spinbutton',{name:'New footage duration',exact:true}).fill('6');
  await expect(duration).toHaveValue('6');
});

test('generation resolution is only editable in Production and locks after an unfinalized take',async({page})=>{
  const {p,submitted,finish}=await fixture(page);
  await expect(page.getByRole('button',{name:'Project resolution',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Change project resolution',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Production',exact:true}).click();
  await page.getByLabel('Generation format',{exact:true}).selectOption('widescreen');
  await page.getByLabel('Generation megapixels',{exact:true}).fill('0.59');
  await page.getByRole('button',{name:'Update generation resolution',exact:true}).click();
  await expect.poll(()=>p.resolution).toEqual({width:1024,height:576});
  await page.getByRole('button',{name:'Timeline',exact:true}).click();
  await page.getByRole('button',{name:'New scene',exact:true}).click();
  await page.getByLabel('Scene name').fill('Second');
  await page.getByRole('button',{name:'Create new scene'}).click();
  await expect(page.getByRole('combobox',{name:'Current scene'})).toContainText('Second');
  await page.getByRole('combobox',{name:'Generation mode'}).selectOption('fl2va');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] A quiet street.');
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const job=Object.values(p.jobs).at(-1) as any;
  expect(job.snapshot.width).toBe(1024);expect(job.snapshot.height).toBe(576);
  const scene=p.scenes.find(scene=>scene.name==='Second')!;
  finish(scene.segments[0].id);
  expect(scene.segments[0].active_output).toBeNull();
  await page.getByRole('button',{name:'Production',exact:true}).click();
  await expect(page.getByText('Locked after the first generated take.',{exact:false})).toBeVisible();
  await expect(page.getByLabel('Generation megapixels',{exact:true})).toBeDisabled();
  await expect(page.getByLabel('Generation format',{exact:true})).toBeDisabled();
  await expect(page.getByLabel('Generation width',{exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Update generation resolution',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Generation width',{exact:true})).toHaveValue('1024');
  await expect(page.getByLabel('Upscale width',{exact:true})).toBeEnabled();
});

test('subjects remain manually authored and assets only have typed aliases',async({page})=>{
  const {p}=await fixture(page);
  const reference={id:'hero',token_name:'hero',display_name:'Hero',scope:'project',owner_id:null,role:'subject',kind:'image',enabled:true,asset_path:'assets/hero.png',asset_sha256:'b'.repeat(64)} as Reference;
  p.references.push(reference);p.effective_references[p.scenes[0].segments[0].id]=[reference];p.revision++;
  await page.getByRole('tab',{name:'References',exact:true}).click();
  await expect(page.getByText('<picture.hero>',{exact:true})).toBeVisible();
  await expect(page.getByLabel('H3 reference role')).toHaveCount(0);
  await expect(page.getByRole('textbox',{name:'Subject definitions',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Insert subject label',exact:true})).toHaveCount(0);
  await page.getByLabel('Generation prompt field').selectOption('subject_definitions');
  const definitions=page.getByLabel('Generation prompt',{exact:true});
  await expect(definitions).toHaveValue('');
  await definitions.fill('<Subject 1> is an imagined traveller.');
  await page.getByLabel('Generation prompt field').selectOption('detailed_description');
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] <Subject 1> waves.');
  await page.getByLabel('Generation prompt field').selectOption('subject_definitions');
  await expect(definitions).toHaveValue('<Subject 1> is an imagined traveller.');
  await expect(page.getByRole('button',{name:'Review legacy prompt conversion',exact:true})).toHaveCount(0);

});

test('generation process shows real stages and keeps decoding active after sampling',async({page})=>{
  const {p,finish,submitted}=await fixture(page);
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The sea rises.');
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(1);
  const job=Object.values(p.jobs).at(-1)!;
  job.status='running';job.progress={stage:'encoding'};p.revision++;
  const status=page.getByRole('status',{name:'Generation process',exact:true});
  await expect(status).toContainText('Encoding prompt and references');
  job.progress={stage:'sampling',value:4,max:8};p.revision++;
  await expect(status).toContainText('Step 4 / 8');
  await page.evaluate((data)=>(window as any).testProgress(data),{value:4,max:8,project_id:p.id,job_id:job.id,prompt_id:'ours'});
  await expect(page.locator('.status-bar')).toContainText('50%');
  await page.evaluate((data)=>(window as any).testProgress(data),{value:8,max:8,project_id:'other',job_id:job.id,prompt_id:'other'});
  await expect(page.locator('.status-bar')).toContainText('50%');
  finish(job.segment_id);job.progress={stage:'decoding'};p.revision++;
  await expect(status).toContainText('Decoding video and audio');
  await expect(page.getByRole('button',{name:'Finishing preview',exact:true})).toBeDisabled();
  job.progress={stage:'complete'};p.revision++;
  await expect(status).toContainText('Completed');
  await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeEnabled();
});


test('duplicate without generations preserves all prompts and prepares new continuation takes in order',async({page})=>{
  const {p:original,current,finish,submitted}=await fixture(page);
  const first=original.scenes[0].segments[0];
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] First copied action.');
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(1);const oldFirst=finish(first.id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await expect(page.getByRole('button',{name:'Select Segment 02'})).toBeVisible();
  const second=original.scenes[0].segments[1];
  await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Second copied action.');
  await page.getByRole('button',{name:'Generate segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(2);finish(second.id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.locator('.project-switch').click();
  await page.getByRole('textbox',{name:'Duplicate project name'}).fill('Retest copy');
  await page.getByRole('button',{name:'Duplicate without generations',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.project-switch')).toContainText('Retest copy');
  expect(original.scenes[0].segments[0].active_output?.take_id).toBe(oldFirst.id);
  expect(Object.keys(original.takes)).toHaveLength(2);
  const copy=current();expect(copy.takes).toEqual({});expect(copy.jobs).toEqual({});
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] First copied action.');
  await page.getByRole('button',{name:'Select Segment 02'}).click();
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] Second copied action.');
  await expect(page.getByRole('button',{name:'Finalize preceding segment first'})).toBeDisabled();
  await page.getByRole('button',{name:'Select Segment 01'}).click();
  await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(3);
  const newFirst=finish(copy.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] Second copied action.');
  await page.getByRole('button',{name:'Generate segment',exact:true}).click();
  await expect.poll(()=>submitted.length).toBe(4);
  const job=Object.values(copy.jobs).at(-1) as any;
  expect(job.snapshot.source_take_id).toBe(newFirst.id);
  expect(job.snapshot.source_take_id).not.toBe(oldFirst.id);
  expect((submitted[3] as any).project_id).toBe(copy.id);
});


test('one playback driver synchronizes timeline, segment previews and project in both directions',async({page})=>{
  const {p,finish}=await fixture(page);
  const first=finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  const second=finish(p.scenes[0].segments[1].id);
  const source=page.getByRole('region',{name:'Current segment preview',exact:true});
  const target=page.getByRole('region',{name:'New generation',exact:true});
  const project=page.getByRole('region',{name:'Scene preview',exact:true});
  const sourceVideo=source.locator('video'),targetVideo=target.locator('video'),movie=project.locator('video');
  const ruler=page.getByRole('slider',{name:'Scene timeline',exact:true});
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThanOrEqual(2);
  await target.getByRole('slider').fill('1.25');
  await expect.poll(()=>ruler.getAttribute('aria-valuenow')).toBe(String(first.plan.new_seconds+1.25));
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(first.plan.new_seconds+1.25,2);
  await expect.poll(()=>sourceVideo.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(first.plan.new_seconds-1/24,2);
  // Project scrubbing selects the matching local frame in the draft monitor.
  await project.getByRole('slider',{name:'Scene preview seek'}).fill('7');
  await expect.poll(()=>targetVideo.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(7-first.plan.new_seconds,2);
  // Both monitors must follow backward seeks too, rather than remaining on an old frame.
  await project.getByRole('slider',{name:'Scene preview seek'}).fill('0.75');
  await expect.poll(()=>sourceVideo.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(.75,2);
  await expect.poll(()=>targetVideo.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(0,2);
  // Start one monitor, then another: only the chosen driver may keep playing.
  await source.getByRole('button',{name:'Play',exact:true}).click();
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeGreaterThan(.85);
  await target.getByRole('button',{name:'Play',exact:true}).click();
  await expect.poll(()=>sourceVideo.evaluate((v:HTMLVideoElement)=>v.paused)).toBe(true);
  await expect.poll(()=>targetVideo.evaluate((v:HTMLVideoElement)=>v.paused)).toBe(false);
  await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.paused)).toBe(true);
  await target.getByRole('button',{name:'Pause',exact:true}).click();
  await expect.poll(async()=>Math.abs(await movie.evaluate((v:HTMLVideoElement)=>v.currentTime)-first.plan.new_seconds-await targetVideo.evaluate((v:HTMLVideoElement)=>v.currentTime))).toBeLessThan(.09);
  expect(second.segment_id).toBe(p.scenes[0].segments[1].id);
});


test('scene preview only plays the selected scene',async({page})=>{
  const {p,finish}=await fixture(page);
  finish(p.scenes[0].segments[0].id);
  await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
  await page.getByRole('button',{name:'Finalize selected take'}).click();
  const segment={id:'other-segment',name:'Segment 01',takes:[] as string[],active_output:null as any,working_draft:draft('other-scene','other-segment')};
  p.scenes.push({id:'other-scene',name:'Second scene',segments:[segment]});
  const second=finish(segment.id);segment.active_output={kind:'single_take',take_id:second.id};p.revision++;
  await expect(page.getByLabel('Current scene',{exact:true}).locator('option')).toHaveCount(2);
  await page.getByLabel('Current scene',{exact:true}).selectOption('other-scene');
  const region=page.getByRole('region',{name:'Scene preview',exact:true});
  await expect(region.locator('.preview-options')).toContainText('Second scene');
  await expect(region.getByRole('slider',{name:'Scene preview seek'})).toHaveAttribute('max',String((second.plan.new_frames-1)/24));
  await region.getByRole('slider',{name:'Scene preview seek'}).fill('2');
  const source=page.getByRole('region',{name:'Current segment preview',exact:true}).locator('video');
  await expect.poll(()=>source.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(2,2);
});


test('rapid timeline scrubbing converges to the actually decoded project frame',async({page})=>{
 const {p,finish}=await fixture(page);
 finish(p.scenes[0].segments[0].id);
 await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
 await page.getByRole('button',{name:'Finalize selected take'}).click();
 await page.getByRole('button',{name:'Extend scene',exact:true}).click();
 finish(p.scenes[0].segments[1].id);
 const region=page.getByRole('region',{name:'Scene preview',exact:true}),movie=region.locator('video');
 await expect(region.getByText('1 draft',{exact:true})).toBeVisible();
 await expect.poll(()=>movie.evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThanOrEqual(2);
 // A separate decoder establishes the expected image, not merely currentTime.
 const expected=await movie.evaluate(async(video:HTMLVideoElement)=>{
  const reference=document.createElement('video');reference.muted=true;reference.src=video.currentSrc;
  await new Promise<void>((resolve,reject)=>{reference.onloadeddata=()=>resolve();reference.onerror=()=>reject(new Error('Reference decode failed'));});
  const canvas=document.createElement('canvas');canvas.width=128;canvas.height=72;const ctx=canvas.getContext('2d')!;
  const hash=()=>{ctx.drawImage(reference,0,0,128,72);return Array.from(ctx.getImageData(0,0,128,72).data).reduce((value,byte)=>(value*31+byte)>>>0,0);};
  const first=hash();await new Promise<void>(resolve=>{reference.onseeked=()=>resolve();reference.currentTime=6.5;});
  await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
  const last=hash();reference.removeAttribute('src');reference.load();return {first,last};
 });
 expect(expected.last).not.toBe(expected.first);
 const ruler=page.getByRole('slider',{name:'Scene timeline',exact:true}),box=(await ruler.boundingBox())!;
 await page.mouse.move(box.x+30,box.y+box.height/2);await page.mouse.down();
 await page.mouse.move(box.x+9*30,box.y+box.height/2,{steps:35});
 await page.mouse.move(box.x+6.5*30,box.y+box.height/2,{steps:18});await page.mouse.up();
 await expect.poll(()=>movie.evaluate((video:HTMLVideoElement)=>{
  if(video.seeking||video.readyState<2)return -1;
  const canvas=document.createElement('canvas');canvas.width=128;canvas.height=72;const ctx=canvas.getContext('2d')!;
  ctx.drawImage(video,0,0,128,72);return Array.from(ctx.getImageData(0,0,128,72).data).reduce((value,byte)=>(value*31+byte)>>>0,0);
 })).toBe(expected.last);
 await expect(region.getByRole('status',{name:'Scene preview seeking'})).toHaveCount(0);
 await expect.poll(()=>ruler.getAttribute('aria-valuenow')).toBe('6.5');
});


test('four columns separate target settings and keep the timeline below all monitors',async({page})=>{
 await fixture(page);
 const scene=page.getByRole('region',{name:'Scene preview',exact:true});
 const current=page.locator('.source-inspector').getByRole('region',{name:'Current segment preview',exact:true});
 const target=page.getByRole('region',{name:'New generation',exact:true});
 await expect(current).toBeVisible();await expect(scene).toBeVisible();
 await expect(target).toContainText('First segment - Segment 01');
 const before=(await scene.boundingBox())!,targetBox=(await target.boundingBox())!,currentBox=(await current.boundingBox())!;
 expect(currentBox.x).toBeLessThan(before.x);expect(before.x).toBeLessThan(targetBox.x);
 const settingsBox=(await page.locator('.target-inspector').boundingBox())!;
 expect(settingsBox.x).toBeGreaterThanOrEqual(targetBox.x+targetBox.width);
 expect(Math.abs(settingsBox.y-currentBox.y)).toBeLessThan(100);
 const timeline=(await page.locator('.timeline').boundingBox())!;
 expect(timeline.y).toBeGreaterThan(before.y+before.height-1);
 expect(timeline.width).toBeGreaterThan(before.width+targetBox.width);
 await page.getByRole('button',{name:'Hide current segment inspector'}).click();
 await expect.poll(async()=>(await scene.boundingBox())!.width).toBeGreaterThan(before.width+50);
 await page.reload();await openConfiguration(page);
 await expect(page.getByRole('button',{name:'Show current segment inspector'})).toHaveAttribute('aria-expanded','false');
 await expect(scene).toBeVisible();
 await page.getByRole('button',{name:'Show current segment inspector'}).click();
 await expect(current).toBeVisible();
 await page.screenshot({path:'tests/screenshots/four-column-layout-1920.png',fullPage:true});
});


test('Home opens production settings and navigation preserves the timeline draft',async({page})=>{
 const {p}=await fixture(page,false,[],'home');
 await expect(page.getByRole('button',{name:'Timeline',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Coastal Journey',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Coastal Journey',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Keep this manually authored action.');
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await page.getByLabel('Production name',{exact:true}).fill('Renamed production');
 await page.getByRole('button',{name:'Save name',exact:true}).click();
 await expect.poll(()=>p.name).toBe('Renamed production');
 await page.getByLabel('Upscale resolution preset').selectOption('1920x1080');
 await page.getByRole('button',{name:'Update upscale resolution',exact:true}).click();
 await expect.poll(()=>p.upscale_resolution).toEqual({width:1920,height:1080});
 await page.getByRole('button',{name:'Export stitched movie',exact:true}).click();
 await expect(page.getByRole('link',{name:'Download movie',exact:true})).toBeVisible();
 await page.screenshot({path:'tests/screenshots/production-route-1920.png',fullPage:true});
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByLabel('Generation prompt',{exact:true})).toHaveValue('[Shot 1] Keep this manually authored action.');
 await page.getByRole('button',{name:'Home',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Productions',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Renamed production',exact:true})).toBeVisible();
 await page.screenshot({path:'tests/screenshots/home-route-1920.png',fullPage:true});
});

test('Home duplicate preserves generations while duplicate and invalidate clears them',async({page})=>{
 const {p,finish,current}=await fixture(page);
 p.generation_defaults={configuration_id:'old-path',selections:{'old-switch':'B'},schema:[]};
 Object.assign(p.scenes[0].segments[0].working_draft!,{configuration_id:'old-path',switch_selections:{'old-switch':'B'}});
 finish(p.scenes[0].segments[0].id);
 await expect(page.getByRole('button',{name:'Finalize selected take'})).toBeEnabled();
 await page.getByRole('button',{name:'Finalize selected take'}).click();
 await page.getByRole('button',{name:'Home',exact:true}).click();
 await page.getByRole('button',{name:'Duplicate Coastal Journey',exact:true}).click();
 await page.getByRole('button',{name:'Create copy',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'Coastal Journey (copy)',exact:true}).click();
 expect(Object.keys(current().takes)).toHaveLength(1);
 expect(current().generation_defaults?.selections).toEqual({'old-switch':'B'});
 await page.getByRole('button',{name:'Home',exact:true}).click();
 await page.getByRole('button',{name:'Duplicate and invalidate Coastal Journey',exact:true}).click();
 await page.getByRole('button',{name:'Create copy',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'Coastal Journey (prompts only)',exact:true}).click();
 expect(Object.keys(current().takes)).toHaveLength(0);expect(Object.keys(p.takes)).toHaveLength(1);
 expect(current().generation_defaults).toBeUndefined();
 for(const scene of current().scenes)for(const segment of scene.segments){expect(segment.working_draft?.configuration_id).toBeUndefined();expect(segment.working_draft?.switch_selections).toBeUndefined();}
 await page.getByRole('button',{name:'Home',exact:true}).click();
 await page.getByRole('button',{name:'Delete Coastal Journey (copy)',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByRole('button',{name:'Delete production',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Coastal Journey (copy)',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Coastal Journey',exact:true})).toBeVisible();
});

test('reference latent controls inherit by scope and freeze the requested percentage',async({page})=>{
 const {p,submitted}=await fixture(page);
 const reference={id:'main',token_name:'main',display_name:'Main subject',scope:'project',owner_id:null,role:'picture',kind:'image',enabled:true,asset_path:'assets/main.png',asset_sha256:'b'.repeat(64)} as Reference;
 p.references.push(reference);p.effective_references[p.scenes[0].segments[0].id]=[reference];p.revision++;
 await page.getByRole('tab',{name:'References',exact:true}).click();
 await expect(page.getByText('Inherited from project',{exact:true})).toBeVisible();
 await page.getByLabel('Reference mode picture.main').selectOption('latent');
 await expect.poll(()=>p.references.find(r=>r.scope==='scene')?.conditioning_mode).toBe('latent');
 await page.getByLabel('Latent strength picture.main').fill('35');
 await page.getByLabel('Latent strength picture.main').press('Enter');
 await expect.poll(()=>p.references.find(r=>r.scope==='scene')?.latent_strength).toBe(35);
 await page.getByLabel('Reference mode picture.main').selectOption('image');
 await expect(page.getByLabel('Latent strength picture.main')).toBeDisabled();
 await expect(page.getByLabel('Latent strength picture.main')).toHaveValue('100');
 await page.getByLabel('Reference mode picture.main').selectOption('latent');
 await expect(page.getByLabel('Latent strength picture.main')).toHaveValue('35');
 expect(p.references[0].conditioning_mode).toBeUndefined();
 await page.getByLabel('Generation prompt field').selectOption('subject_definitions');
 await page.getByLabel('Generation prompt',{exact:true}).fill('<Subject 1> is the person in <picture.main>.');
 await page.getByLabel('Generation prompt field').selectOption('detailed_description');
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] <Subject 1> exercises.');
 await page.screenshot({path:'tests/screenshots/latent-reference-tab-1920.png',fullPage:true});
 await page.getByRole('tab',{name:'Generate',exact:true}).click();
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>submitted.length).toBe(1);
 const job=Object.values(p.jobs).at(-1) as any;
 expect(job.snapshot.compiled.images).toHaveLength(1);expect(job.snapshot.compiled.images[0].latent_strength).toBe(35);
 expect(job.snapshot.fields.subject_definitions).toBe('<Subject 1> is the person in <picture.main>.');
});

test('LoRAs tab saves scoped model strength and survives route changes',async({page})=>{
 const {p}=await fixture(page);
 await page.getByRole('tab',{name:'LoRAs',exact:true}).click();
 await page.getByLabel('Installed LoRA').selectOption('style.safetensors');
 await page.getByRole('button',{name:'Add LoRA',exact:true}).click();
 await expect(page.getByLabel('LoRA strength style.safetensors')).toBeVisible();
 await page.getByLabel('LoRA strength style.safetensors').fill('0.6');
 await page.getByLabel('LoRA strength style.safetensors').press('Tab');
 await expect.poll(()=>p.loras?.[0].strength).toBe(.6);
 expect(p.loras?.[0].scope).toBe('scene');
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByLabel('LoRA strength style.safetensors')).toHaveValue('0.6');
});


test('Generation formats use megapixel targets, preserve existing sizes, and save only on update',async({page})=>{
 const {p}=await fixture(page,false,[],'home');
 await page.getByRole('button',{name:'Coastal Journey',exact:true}).click();
 const original=p.resolution ? {...p.resolution} : undefined;
 await expect(page.getByLabel('Generation width',{exact:true})).toHaveValue('768');
 await expect(page.getByLabel('Generation height',{exact:true})).toHaveValue('448');
 await expect(page.getByLabel('Generation format',{exact:true})).toHaveValue('widescreen');
 await expect(page.getByLabel('Generation megapixels',{exact:true})).toHaveValue('0.344');
 await page.getByLabel('Generation format',{exact:true}).selectOption('portrait-widescreen');
 await page.getByLabel('Generation megapixels',{exact:true}).fill('1');
 await expect(page.getByLabel('Generation width',{exact:true})).toHaveValue('736');
 await expect(page.getByLabel('Generation height',{exact:true})).toHaveValue('1344');
 await expect(page.getByText('0.989 MP actual',{exact:false})).toBeVisible();
 expect(p.resolution).toEqual(original);
 await page.getByRole('button',{name:'Update generation resolution',exact:true}).click();
 await expect.poll(()=>p.resolution).toEqual({width:736,height:1344});
 await page.getByLabel('Generation format',{exact:true}).selectOption('photo');
 await page.getByLabel('Generation megapixels',{exact:true}).fill('0.5');
 await expect(page.getByLabel('Generation width',{exact:true})).toHaveValue('864');
 await expect(page.getByLabel('Generation height',{exact:true})).toHaveValue('576');
 await page.getByLabel('Generation format',{exact:true}).selectOption('cinema');
 await page.getByLabel('Generation megapixels',{exact:true}).fill('4');
 await expect(page.getByRole('button',{name:'Update generation resolution',exact:true})).toBeDisabled();
 await page.getByLabel('Generation width',{exact:true}).fill('1024');
 await expect(page.getByLabel('Generation format',{exact:true})).toHaveValue('custom');
 await expect(page.getByLabel('Generation megapixels',{exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'Update generation resolution',exact:true})).toBeEnabled();
});


test('production defaults and one dropdown per switch, with missing switches blocking generation',async({page})=>{
 const choices=[{id:'hyper',name:'HyperFlow 8 steps',profile:'ref2va'},{id:'pdd',name:'PDD 8 steps',profile:'ref2va'}];
 const switches=[{id:'model',name:'Model source',kind:'model',select:'A',options:[{value:'A',label:'Full REF2VA'},{value:'B',label:'Patched model'}]},
 {id:'acceleration',name:'Acceleration',kind:'configuration',select:'A',options:[{value:'A',label:'HyperFlow 8 steps',configuration_id:'hyper'},{value:'B',label:'PDD 8 steps',configuration_id:'pdd'}]}];
 const {p}=await fixture(page,false,choices,'timeline/generate',switches);
 await expect(page.getByRole('combobox',{name:'Model source',exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await page.locator('.production-page').getByRole('combobox',{name:'Model source',exact:true}).selectOption('B');
 await expect(page.locator('.production-page').getByRole('combobox',{name:'Model source',exact:true})).toHaveValue('B');
 await page.locator('.production-page').getByRole('combobox',{name:'Acceleration',exact:true}).selectOption('B');
 await page.getByRole('button',{name:'Save default switches',exact:true}).click();
 await expect.poll(()=>p.generation_defaults?.selections).toEqual({model:'B',acceleration:'B'});
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Model source',exact:true})).toHaveValue('B');
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('B');
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeEnabled();
 await page.evaluate(()=>{(window as any).testSwitches=(window as any).testSwitches.filter((item:any)=>item.id!=='model');});
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeDisabled();
 await expect(page.getByText('Saved switch is missing from this workflow.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await expect(page.locator('.production-page').getByText('Saved switch is missing from this workflow.',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Save default switches',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Use current workflow switches',exact:true}).click();
 await expect(page.getByRole('button',{name:'Save default switches',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Save default switches',exact:true}).click();
 await expect.poll(()=>Object.keys(p.generation_defaults?.selections||{})).toEqual(['acceleration']);
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeEnabled();
 await page.evaluate(()=>{(window as any).testSwitchError='Incompatible MODEL socket on acceleration switch.';});
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeDisabled();
 await expect(page.getByText('Incompatible MODEL socket on acceleration switch.',{exact:true})).toBeVisible();
});


test('segments inherit changed production defaults after generation until explicitly overridden',async({page})=>{
 const choices=[{id:'hyper',name:'HyperFlow 8 steps',profile:'ref2va'},{id:'pdd',name:'PDD 8 steps',profile:'ref2va'},{id:'standard',name:'Standard 20 steps',profile:'ref2va'}];
 const switches=[{id:'model',name:'Model source',kind:'model',select:'A',options:[{value:'A',label:'Full REF2VA'},{value:'B',label:'Patched model'}]},
 {id:'acceleration',name:'Acceleration',kind:'configuration',select:'A',options:[{value:'A',label:'HyperFlow 8 steps',configuration_id:'hyper'},{value:'B',label:'PDD 8 steps',configuration_id:'pdd'},{value:'C',label:'Standard 20 steps',configuration_id:'standard'}]}];
 const {p}=await fixture(page,false,choices,'timeline/generate',switches);
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Continue exercising.');
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 expect(p.scenes[0].segments[0].working_draft?.configuration_id).toBe('hyper');
 await page.reload();await openConfiguration(page);
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('A');
 async function setDefaults(slot:string){
  await page.getByRole('button',{name:'Production',exact:true}).click();
  const production=page.locator('.production-page');
  await production.getByRole('combobox',{name:'Acceleration',exact:true}).selectOption(slot);
  await expect(production.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue(slot);
  await production.getByRole('button',{name:'Save default switches',exact:true}).click();
  await expect.poll(()=>p.generation_defaults?.selections.acceleration).toBe(slot);
  await page.getByRole('button',{name:'Timeline',exact:true}).click();
 }
 await setDefaults('C');
 await expect(page.getByRole('checkbox',{name:'Override production defaults',exact:true})).not.toBeChecked();
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('C');
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(2);
 expect((Object.values(p.jobs)[1] as any).snapshot.configuration.id).toBe('standard');
 expect((Object.values(p.jobs)[0] as any).snapshot.configuration.id).toBe('hyper');
 const draft=p.scenes[0].segments[0].working_draft!;
 expect(draft.configuration_id).toBeUndefined();expect(draft.switch_selections).toBeUndefined();expect(draft.configuration).toBeUndefined();
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 await setDefaults('B');
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('B');
 await page.getByRole('checkbox',{name:'Override production defaults',exact:true}).check();
 await page.getByRole('combobox',{name:'Acceleration',exact:true}).selectOption('A');
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('A');
 await setDefaults('C');
 await expect(page.getByRole('checkbox',{name:'Override production defaults',exact:true})).toBeChecked();
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('A');
 await page.getByRole('button',{name:'Use production defaults',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Acceleration',exact:true})).toHaveValue('C');
});


test('reference image sizing inherits production policy or freezes an explicit segment override',async({page})=>{
 const {p}=await fixture(page);
 await expect(page.getByRole('combobox',{name:'Reference image sizing',exact:true})).toHaveValue('inherit');
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The subject exercises.');
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await page.getByLabel('Default reference image sizing',{exact:true}).selectOption('max');
 await page.getByRole('button',{name:'Save reference image sizing',exact:true}).click();
 await expect.poll(()=>p.ref_image_size).toBe('max');
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Reference image sizing',exact:true})).toHaveValue('inherit');
 await expect(page.getByRole('combobox',{name:'Reference image sizing',exact:true})).toContainText('Production default - Max');
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(1);
 const first:any=Object.values(p.jobs)[0];expect(first.snapshot.ref_image_size).toBe('max');
 expect(p.scenes[0].segments[0].working_draft?.ref_image_size).toBeUndefined();
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 await page.getByRole('button',{name:'Production',exact:true}).click();
 await page.getByLabel('Default reference image sizing',{exact:true}).selectOption('match');
 await page.getByRole('button',{name:'Save reference image sizing',exact:true}).click();
 await expect.poll(()=>p.ref_image_size).toBe('match');
 await page.getByRole('button',{name:'Timeline',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Reference image sizing',exact:true})).toContainText('Production default - Match');
 expect(first.snapshot.ref_image_size).toBe('max');
 await page.getByRole('combobox',{name:'Reference image sizing',exact:true}).selectOption('max');
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(2);
 expect((Object.values(p.jobs)[1] as any).snapshot.ref_image_size).toBe('max');
 expect(p.scenes[0].segments[0].working_draft?.ref_image_size).toBe('max');
});


test('normal generation keeps its seed and random generation freezes a fresh visible seed',async({page})=>{
 const {p}=await fixture(page);
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The subject exercises.');
 await page.getByRole('spinbutton',{name:'Seed',exact:true}).fill('416');
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(1);
 expect((Object.values(p.jobs)[0] as any).snapshot.seed).toBe(416);
 await expect(page.getByRole('button',{name:'Generate segment with random seed',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 await page.getByRole('button',{name:'Generate segment with random seed',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(2);
 const random=(Object.values(p.jobs)[1] as any).snapshot;
 expect(random.seed).not.toBe(416);expect(Number.isSafeInteger(random.seed)).toBe(true);expect(random.seed).toBeGreaterThanOrEqual(0);
 await expect(page.getByRole('spinbutton',{name:'Seed',exact:true})).toHaveValue(String(random.seed));
 expect(random.fields.detailed_description).toBe('[Shot 1] The subject exercises.');
 expect(p.scenes[0].segments[0].working_draft?.seed).toBe(random.seed);
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(3);
 expect((Object.values(p.jobs)[2] as any).snapshot.seed).toBe(random.seed);
 await page.getByRole('button',{name:'Stop generation',exact:true}).click();
 await page.getByRole('spinbutton',{name:'New footage duration',exact:true}).fill('0');
 await expect(page.getByRole('button',{name:'Generate first segment',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'Generate segment with random seed',exact:true})).toBeDisabled();
});


test('seam frame correction freezes the requested offset and offers a review-only baseline',async({page})=>{
 const {p,finish}=await fixture(page);
 const control=page.getByRole('combobox',{name:'Seam frame correction',exact:true});
 await expect(control).toHaveCount(0);
 const segment=p.scenes[0].segments[0],first=finish(segment.id);
 segment.active_output={kind:'single_take',take_id:first.id};p.revision++;
 await expect(page.getByRole('button',{name:'Extend scene',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Extend scene',exact:true}).click();
 await openAdvanced(page);
 await expect(control).toBeEnabled();await expect(control).toHaveValue('0');
 await control.selectOption('4');
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] The action continues.');
 await page.getByRole('button',{name:'Generate segment',exact:true}).click();
 await expect.poll(()=>Object.values(p.jobs).length).toBe(1);
 expect((Object.values(p.jobs)[0] as any).snapshot.decode_edge_frames).toBe(4);
 await expect(control).toBeDisabled();
 const child=finish(p.scenes[0].segments[1].id);
 child.snapshot.decode_edge={policy:'child_context_video_v1',frames:4};p.revision++;
 const toggle=page.getByRole('checkbox',{name:'Use saved seam frame correction',exact:true});
 await expect(toggle).toBeVisible();await expect(toggle).toBeChecked();
 const request=page.waitForRequest(req=>req.url().endsWith('/preview')&&req.method()==='POST'&&req.postDataJSON().apply_decode_edge===false);
 await toggle.uncheck();await request;
 expect(child.snapshot.decode_edge.frames).toBe(4);
 await expect(page.getByRole('region',{name:'Scene preview',exact:true}).locator('video')).toBeVisible();
});


test('a failed continuation check keeps preview available and explains why finalize is disabled',async({page})=>{
 const {p,finish}=await fixture(page);
 const take=finish(p.scenes[0].segments[0].id);
 take.receipt.continuation_check={passed:false};p.revision++;
 await expect(page.getByRole('button',{name:'Finalize selected take',exact:true})).toBeDisabled();
 await expect(page.getByText('Protected context verification failed.',{exact:false})).toBeVisible();
 await expect(page.getByRole('region',{name:'New generation',exact:true}).locator('video')).toBeVisible();
});


test('Anti-Burn scene inheritance, independent skip, missing file guard and segment override',async({page})=>{
 const {p,submitted,finish}=await fixture(page);
 await page.getByRole('button',{name:'Scene settings',exact:true}).click();
 await page.getByLabel('Scene Anti-Burn',{exact:true}).check();
 await expect.poll(()=>p.scenes[0].anti_burn?.enabled).toBe(true);
 await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Anti-Burn LoRA not found');
 await page.getByRole('button',{name:'Close scene settings'}).click();
 await page.getByLabel('Generation prompt',{exact:true}).fill('[Shot 1] Waves roll.');
 await expect(page.getByLabel('Segment Anti-Burn',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Generate first segment',exact:true}).click();
 await expect.poll(()=>submitted.length).toBe(1);
 finish(p.scenes[0].segments[0].id);
 await page.getByRole('button',{name:'Finalize selected take'}).click();
 await page.getByRole('button',{name:'Extend scene',exact:true}).click();
 const generate=page.getByRole('button',{name:'Generate segment',exact:true});
 await expect(generate).toBeDisabled();
 await expect(page.getByRole('alert').filter({hasText:'Anti-Burn LoRA not found'})).toContainText('Generation is blocked');
 await openAdvanced(page);
 await page.locator('.anti-burn-disclosure>summary').click();
 await page.getByLabel('Segment Anti-Burn',{exact:true}).selectOption('off');
 await expect(generate).toBeEnabled();
 await page.getByLabel('Segment Anti-Burn',{exact:true}).selectOption('on');
 await page.route('**/longcaster-timeline/anti-burn',route=>route.fulfill({json:{available:true,filename:'h3_antiburn_universal_v1.safetensors'}}));
 await page.getByRole('button',{name:'Refresh Anti-Burn availability'}).click();
 await expect(generate).toBeEnabled();
 await page.getByLabel('Override Anti-Burn strength',{exact:true}).check();
 await page.getByLabel('Segment Anti-Burn strength',{exact:true}).fill('0.35');
 await page.getByLabel('Segment Anti-Burn strength',{exact:true}).blur();
 await generate.click();
 await expect.poll(()=>submitted.length).toBe(2);
 const job=Object.values(p.jobs).at(-1) as any;
 expect(job.snapshot.anti_burn).toEqual({mode:'on',strength:.35});
});


test('continuation protection is explicit and cannot stack with H3 Refine',async({page})=>{
  const {p,finish}=await fixture(page);
  finish(p.scenes[0].segments[0].id);
  await page.getByRole('button',{name:'Finalize selected take',exact:true}).click();
  await page.getByRole('button',{name:'Extend scene',exact:true}).click();
  await openAdvanced(page);
  const protection=page.getByLabel('Drift treatment',{exact:true});
  const refine=page.getByLabel('Enable refinement',{exact:true});
  await expect(protection).toHaveValue('off');
  await protection.selectOption('drift_color');
  await expect(refine).toBeDisabled();
  await protection.selectOption('off');
  await refine.check();
  await expect(protection).toBeDisabled();
  await refine.uncheck();
  await expect(protection).toBeEnabled();
});

test('short sources can choose image continuation without latent context',async({page})=>{
 const {p,finish}=await fixture(page);
 const take=finish(p.scenes[0].segments[0].id);take.plan.sampled_frames=22;take.plan.new_frames=22;take.plan.new_seconds=22/24;take.plan.delivery.end=22;
 await page.getByRole('button',{name:'Finalize selected take',exact:true}).click();
 await page.getByRole('button',{name:'Extend scene',exact:true}).click();
 await expect(page.getByText('The source is shorter than the selected context.',{exact:false})).toBeVisible();
 await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeDisabled();
 await chooseContinuation(page,'last_frame');
 await expect(page.getByLabel('Motion and audio context',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Carry motion',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Generate segment',exact:true})).toBeEnabled();
});
