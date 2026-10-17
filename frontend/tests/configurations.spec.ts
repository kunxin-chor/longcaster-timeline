import {test,expect} from '@playwright/test';
import {configurationChoices,prepareConfiguration,executionGraph} from '../../web/extension/configurations.js';
import {discoverSwitches,validateDefinitions} from '../../web/extension/switches.js';
import {defaultsCompatibility} from '../src/GenerationSwitches';

function dualFixture(){
 const graph=fixture();
 graph['source']={class_type:'LongCasterTimelineModelSwitch',inputs:{select:'A',name:'Model source',profile:'ref2va',label_a:'Full REF2VA',label_b:'Patched model',source_a:['model-a',0],source_b:['model-b',0]}};
 graph.a.inputs.model=['source',0];graph.b.inputs.model=['source',0];
 graph.switch._meta={title:'Acceleration'};
 return graph;
}

test('dual selectors freeze all four combinations and prune both unused paths',()=>{
 const graph=dualFixture(),before=structuredClone(graph);
 for(const pack of ['a','b'])for(const source of ['A','B']){
  const selected=prepareConfiguration(graph,'run',pack,{source});
  const queued=executionGraph(graph,'run',selected);
  expect(selected.switch_values).toEqual({source});
  expect(queued.source.inputs.select).toBe(source);
  expect(queued.source.inputs[`source_${source==='A'?'b':'a'}`]).toBeUndefined();
  expect(queued[source==='A'?'model-b':'model-a']).toBeUndefined();
  expect(queued[pack==='a'?'b':'a']).toBeUndefined();
  expect(queued[pack==='a'?'sigmas-b':'sigmas-a']).toBeUndefined();
 }
 expect(graph).toEqual(before);
 const switches=discoverSwitches(graph,'run','b',{source:'B'});
 expect(switches.map(item=>item.name)).toEqual(['Model source','Acceleration']);
 expect(switches.map(item=>item.select)).toEqual(['B','B']);
 graph.source.inputs.label_c='Another model';graph.source.inputs.source_c=['model-a',0];
 expect(discoverSwitches(graph,'run','a',{}).find(item=>item.id==='source')?.options).toHaveLength(3);
});

test('missing or unsupported switches, cycles and changed defaults warn explicitly',()=>{
 const graph=dualFixture();
 const schema=discoverSwitches(graph,'run','a',{});
 const saved:any={configuration_id:'a',selections:{source:'A',switch:'A'},schema};
 expect(defaultsCompatibility(saved,schema)).toBe('');
 expect(defaultsCompatibility(saved,schema.slice(1))).toContain('missing');
 expect(defaultsCompatibility(saved,schema.map(item=>item.id==='source'?{...item,name:'Replaced model selector'}:item))).toContain('incompatible');
 graph.source.inputs.label_a='Different model';
 expect(defaultsCompatibility(saved,discoverSwitches(graph,'run','a',{}))).toContain('changed sources');
 expect(()=>discoverSwitches(graph,'run','a',{missing:'A'})).toThrow('Saved switch missing');
 expect(()=>discoverSwitches(graph,'run','a',{source:'E'})).toThrow('selected source E is missing');
 graph.source.class_type='ThirdPartySwitch';
 expect(()=>discoverSwitches(graph,'run','a',{})).toThrow('Unsupported switch');
});

test('installed definitions reject absent node packs, unavailable weights and incompatible sockets',()=>{
 const graph:any={loader:{class_type:'Loader',inputs:{filename:'installed.safetensors'}},consumer:{class_type:'Consumer',inputs:{model:['loader',0]}}};
 const definitions:any={Loader:{input:{required:{filename:[['installed.safetensors']]}},output:['MODEL']},Consumer:{input:{required:{model:['MODEL']}},output:['MODEL']}};
 expect(()=>validateDefinitions(graph,definitions)).not.toThrow();
 graph.loader.inputs.filename='missing.safetensors';expect(()=>validateDefinitions(graph,definitions)).toThrow('unavailable');
 graph.loader.inputs.filename='installed.safetensors';definitions.Loader.output=['SIGMAS'];expect(()=>validateDefinitions(graph,definitions)).toThrow('incompatible model');
 delete definitions.Loader;expect(()=>validateDefinitions(graph,definitions)).toThrow('Missing node pack');
});

function fixture():any {return {
  run:{class_type:'LongCasterTimelineExecute',inputs:{configuration:['switch',0],model:['unused',0],sampler:['unused',0],sigmas:['unused',0],clip:['clip',0],video_vae:['vae',0],audio_vae:['vae',0]}},
  switch:{class_type:'LongCasterTimelineConfigurationSwitch',inputs:{select:'A',source_a:['a',0],source_b:['b',0]}},
  a:{class_type:'LongCasterTimelineConfiguration',inputs:{name:'Baseline',profile:'ref2va',model:['model-a',0],sampler:['sampler',0],sigmas:['sigmas-a',0]}},
  b:{class_type:'LongCasterTimelineConfiguration',inputs:{name:'PDD 8 steps',profile:'ref2va',model:['model-b',0],sampler:['sampler',0],sigmas:['sigmas-b',0]}},
  'model-a':{class_type:'Loader',inputs:{unet_name:'base.safetensors'}},
  'model-b':{class_type:'Loader',inputs:{unet_name:'pdd.safetensors',token:'private'}},
  sampler:{class_type:'Sampler',inputs:{sampler_name:'euler'}},
  'sigmas-a':{class_type:'Schedule',inputs:{steps:30}},'sigmas-b':{class_type:'Schedule',inputs:{steps:8,shift:1e-7}},
  unused:{class_type:'Unused',inputs:{}},clip:{class_type:'CLIPLoader',inputs:{}},vae:{class_type:'VAELoader',inputs:{}},
  otherOutput:{class_type:'SaveImage',inputs:{image:['unused',0]}}
};}

test('named choice freezes the entire path and prunes unused nodes without changing the canvas',()=>{
  const graph=fixture();const before=structuredClone(graph);
  const choices=configurationChoices(graph,'run');
  expect(choices.map(c=>c.name)).toEqual(['Baseline','PDD 8 steps']);
  const selected=prepareConfiguration(graph,'run','b');
  expect(selected.upstream['model-b'].inputs.token).toBe('[redacted]');
  const queued=executionGraph(graph,'run',selected);
  expect(queued.switch.inputs.select).toBe('B');
  expect(queued.switch.inputs.source_a).toBeUndefined();
  expect(queued.run.inputs.model).toBeUndefined();
  expect(queued['sigmas-b'].inputs.steps).toBe(8);
  for(const id of ['a','model-a','sigmas-a','unused','otherOutput'])expect(queued[id]).toBeUndefined();
  expect(graph).toEqual(before);
});

test('configuration edits and disconnected choices fail instead of falling back',()=>{
  const graph=fixture();const selected=prepareConfiguration(graph,'run','b');
  graph['sigmas-b'].inputs.steps=12;
  expect(()=>executionGraph(graph,'run',selected)).toThrow('changed after queueing');
  delete graph.switch.inputs.source_b;
  expect(()=>executionGraph(graph,'run',selected)).toThrow('no longer connected');
});

test('an incomplete inactive path cannot stop a complete selected path',()=>{
  const graph=fixture();delete graph['model-a'];
  const choices=configurationChoices(graph,'run');expect(choices[0].error).toContain('Connect MODEL');
  const selected=prepareConfiguration(graph,'run','b');
  expect(executionGraph(graph,'run',selected)['model-b']).toBeDefined();
  expect(()=>prepareConfiguration(graph,'run','a')).toThrow('Connect MODEL');
});

test('direct configurations, legacy inputs and preview-only requests remain supported',()=>{
  const graph=fixture();graph.run.inputs.configuration=['b',0];
  const selected=prepareConfiguration(graph,'run','b');
  expect(selected.selector_id).toBeNull();
  expect(executionGraph(graph,'run',selected).switch).toBeUndefined();
  const preview=executionGraph(graph,'run',null,'preview');
  for(const id of ['a','b','sampler','sigmas-b','unused'])expect(preview[id]).toBeUndefined();
  expect(preview.vae).toBeDefined();
  delete graph.run.inputs.configuration;
  expect(configurationChoices(graph,'run')[0].id).toBe('direct');
  expect(prepareConfiguration(graph,'run','direct')).toBeNull();
  expect(executionGraph(graph,'run').unused).toBeDefined();
});
