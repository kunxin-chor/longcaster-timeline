// Switch adapters are explicit: arbitrary third-party switches cannot be safely
// frozen or pruned without an adapter describing their selection semantics.
export const MODEL_SWITCH='LongCasterTimelineModelSwitch';
export const CONFIG_SWITCH='LongCasterTimelineConfigurationSwitch';
const SLOTS=['A','B','C','D','E'];
const link=value=>Array.isArray(value)&&value.length===2&&Number.isInteger(value[1]);

export function discoverSwitches(graph,executionId,configurationId,selections={}){
 const root=graph[String(executionId)]?.inputs?.configuration;
 if(!link(root))throw new Error('Connect a LongCaster Configuration Switch to Execution.');
 const found=[],visited=new Set(),visiting=new Set();
 function visit(id){
  id=String(id);if(visiting.has(id))throw new Error('Configuration contains a dependency cycle.');if(visited.has(id))return;
  const node=graph[id];if(!node)throw new Error(`Missing upstream node ${id}.`);
  visiting.add(id);const inputs=node.inputs||{};
  if([MODEL_SWITCH,CONFIG_SWITCH].includes(node.class_type)){
   const kind=node.class_type===MODEL_SWITCH?'model':'configuration';
   const options=SLOTS.filter(slot=>link(inputs[`source_${slot.toLowerCase()}`])).map(slot=>{
    const source=graph[String(inputs[`source_${slot.toLowerCase()}`][0])];
    return {value:slot,label:kind==='model'?(inputs[`label_${slot.toLowerCase()}`]||`Source ${slot}`):(source?.inputs?.name||`Source ${slot}`),configuration_id:kind==='configuration'?String(inputs[`source_${slot.toLowerCase()}`][0]):undefined};
   });
   if(!options.length)throw new Error(`Switch ${inputs.name||id} has no connected sources.`);
   if(kind==='configuration'&&options.some(option=>graph[option.configuration_id]?.class_type!=='LongCasterTimelineConfiguration'))throw new Error(`Configuration switch ${id} requires Configuration nodes; nested configuration switches are unsupported.`);
   const matched=kind==='configuration'?options.find(option=>option.configuration_id===configurationId)?.value:undefined;
   const select=selections[id]||matched||inputs.select;
   if(!options.some(option=>option.value===select))throw new Error(`Switch ${inputs.name||id}: selected source ${select} is missing.`);
   found.push({id,name:inputs.name||node._meta?.title||(kind==='model'?'Model source':'Generation configuration'),kind,select,options});
  }else if(/switch|selector/i.test(node.class_type||''))throw new Error(`Unsupported switch ${node.class_type}. Use a LongCaster switch so its selection can be frozen safely.`);
  for(const value of Object.values(inputs))if(link(value))visit(value[0]);
  visiting.delete(id);visited.add(id);
 }
 visit(root[0]);
 for(const id of Object.keys(selections))if(!found.some(item=>item.id===id))throw new Error(`Saved switch ${id} is missing from this workflow.`);
 if(!found.length)throw new Error('No supported generation switches are connected.');
 return found.sort((a,b)=>a.kind===b.kind?a.id.localeCompare(b.id):a.kind==='model'?-1:1);
}

export function applyModelSwitches(graph,selections={},rootId=null){
 const reachable=new Set();
 function visit(id){id=String(id);if(reachable.has(id)||!graph[id])return;reachable.add(id);for(const value of Object.values(graph[id].inputs||{}))if(link(value))visit(value[0]);}
 if(rootId!==null&&rootId!==undefined)visit(rootId);
 graph=structuredClone(graph);
 for(const [id,node] of Object.entries(graph))if(node.class_type===MODEL_SWITCH&&(rootId===null||reachable.has(id))){
  const inputs=node.inputs;const select=selections[id]||inputs.select;
  if(!SLOTS.includes(select)||!link(inputs[`source_${select.toLowerCase()}`]))throw new Error(`Model switch ${inputs.name||id}: selected source is missing.`);
  inputs.select=select;
  for(const slot of SLOTS)if(slot!==select)delete inputs[`source_${slot.toLowerCase()}`];
 }
 return graph;
}

export function validateDefinitions(graph,definitions){
 for(const [id,node] of Object.entries(graph)){
  const definition=definitions[node.class_type];
  if(!definition)throw new Error(`Missing node pack: ${node.class_type} (node ${id}).`);
  const inputs=node.inputs||{},schema={...definition.input?.required,...definition.input?.optional};
  for(const [name,spec] of Object.entries(definition.input?.required||{}))if(!(name in inputs)&&!spec[1]?.default&&spec[1]?.default!==0&&spec[1]?.default!==false)throw new Error(`${node.class_type}: connect or configure ${name}.`);
  for(const [name,value] of Object.entries(inputs)){
   const spec=schema[name];if(!spec)continue;
   if(link(value)){
    const source=graph[String(value[0])],type=definitions[source?.class_type]?.output?.[value[1]];
    if(!source||!type)throw new Error(`${node.class_type}: missing source for ${name}.`);
    if(typeof spec[0]==='string'&&spec[0]!=='*'&&type!=='*'&&!spec[0].split(',').includes(type))throw new Error(`${node.class_type}: incompatible ${name} connection (${type} instead of ${spec[0]}).`);
   }else if(Array.isArray(spec[0])&&!spec[0].includes(value))throw new Error(`${node.class_type}: ${name} is unavailable (${value}). Select an installed file or supported option.`);
  }
 }
}
