import {applyModelSwitches} from "./switches.js";
// Pure serialized-prompt helpers, shared by the execution bridge and its tests.
const PACK = "LongCasterTimelineConfiguration";
const SWITCH = "LongCasterTimelineConfigurationSwitch";
const slots = ["A", "B", "C", "D", "E"];
const sensitive = new Set(["token", "api_key", "password", "secret", "authorization", "cookie"]);
const isLink = value => Array.isArray(value) && value.length === 2 && Number.isInteger(value[1]);
const scrub = (value, key="") => sensitive.has(key.toLowerCase()) ? "[redacted]" : Array.isArray(value) ? value.map(v=>scrub(v)) : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).map(([k,v])=>[k,scrub(v,k)])) : value;
const canonical = value => JSON.stringify(value, (_, item)=>item && !Array.isArray(item) && typeof item === "object" ? Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))) : item);

function ancestry(graph, root) {
  const result={},visiting=new Set();
  const visit=id=>{
    id=String(id);if(visiting.has(id))throw new Error("Configuration contains a dependency cycle.");if(result[id])return;
    const node=graph[id];if(!node)throw new Error(`Missing configuration node ${id}.`);
    visiting.add(id);result[id]={class_type:node.class_type,inputs:structuredClone(node.inputs||{})};
    for(const value of Object.values(node.inputs||{}))if(isLink(value)&&graph[String(value[0])])visit(value[0]);
    visiting.delete(id);
  };
  visit(root);return scrub(result);
}

function describe(graph, id, selector_id=null, slot=null) {
  id=String(id);const node=graph[id],inputs=node?.inputs||{};
  if(node?.class_type!==PACK)throw new Error("Connect a LongCaster Configuration node to each switch input.");
  const name=typeof inputs.name==="string"?inputs.name.trim():"";
  if(!name||name.length>120)throw new Error("Give each configuration a name of 1-120 characters.");
  if(!["ref2va","fl2va"].includes(inputs.profile))throw new Error(`Choose the mode for ${name}.`);
  for(const input of ["model","sampler","sigmas"])if(!isLink(inputs[input])||!graph[String(inputs[input][0])])throw new Error(`Connect ${input.toUpperCase()} for ${name}.`);
  return {id,name,profile:inputs.profile,selector_id,slot,upstream:ancestry(graph,id)};
}

export function configurationChoices(graph, executionId) {
  const input=graph[String(executionId)]?.inputs?.configuration;
  if(!input)return [{id:"direct",name:"Direct canvas inputs",profile:graph[String(executionId)]?.inputs?.model_mode}];
  if(!isLink(input)||input[1]!==0)throw new Error("Invalid execution configuration connection.");
  const root=graph[String(input[0])];
  const branches=root?.class_type===PACK?[[input[0],null,null]]:root?.class_type===SWITCH?
    slots.filter(slot=>root.inputs?.[`source_${slot.toLowerCase()}`]).map(slot=>[root.inputs[`source_${slot.toLowerCase()}`][0],String(input[0]),slot]):[];
  if(!branches.length)throw new Error("Connect named Configuration nodes through a Configuration Switch to Execution.");
  const seen=new Set();
  return branches.map(([id,selector,slot])=>{
    id=String(id);if(seen.has(id))throw new Error("Connect each Configuration node to only one switch slot.");seen.add(id);
    try{return describe(graph,id,selector,slot);}catch(error){return {id,name:graph[id]?.inputs?.name||`Slot ${slot||"?"}`,profile:graph[id]?.inputs?.profile,error:error.message};}
  });
}

export function prepareConfiguration(graph, executionId, id, selections={}) {
  graph=applyModelSwitches(graph,selections,graph[String(executionId)]?.inputs?.configuration?.[0]);
  const choice=configurationChoices(graph,executionId).find(item=>item.id===id);
  if(!choice)throw new Error("Selected configuration is no longer connected. Select another configuration.");
  if(choice.error)throw new Error(choice.error);
  if(choice.id==="direct")return null;
  for(const node of Object.values(choice.upstream))if(node.class_type==='LongCasterTimelineModelSwitch'&&node.inputs.profile!==choice.profile)throw new Error('Model switch profile is incompatible with the generation configuration.');
  const switch_values=Object.fromEntries(Object.entries(choice.upstream).filter(([,node])=>node.class_type==='LongCasterTimelineModelSwitch').map(([key,node])=>[key,node.inputs.select]));
  return Object.keys(switch_values).length?{...choice,switch_values}:choice;
}

export function executionGraph(graph, executionId, frozen=null, operation="generate") {
  graph=structuredClone(graph);executionId=String(executionId);
  const execution=graph[executionId];if(!execution)throw new Error("Execution node is missing.");
  if(operation==="preview"){
    for(const key of ["configuration","model","sampler","sigmas"])delete execution.inputs[key];
  }else if(frozen){
    const current=prepareConfiguration(graph,executionId,frozen.id,frozen.switch_values||{});
    if(!current||["name","profile","selector_id","slot"].some(key=>current[key]!==frozen[key])||canonical(current.upstream)!==canonical(frozen.upstream))
      throw new Error("Upstream configuration changed after queueing. Generate a fresh take.");
    graph=applyModelSwitches(graph,frozen.switch_values||{},graph[executionId].inputs.configuration?.[0]);
    if(current.selector_id!==null){
      const inputs=graph[current.selector_id].inputs;inputs.select=current.slot;
      for(const slot of slots)if(slot!==current.slot)delete inputs[`source_${slot.toLowerCase()}`];
    }
    for(const key of ["model","sampler","sigmas"])delete graph[executionId].inputs[key];
  }else if(execution.inputs.configuration){
    throw new Error("Choose a named generation configuration before generating.");
  }
  const output={},visiting=new Set();
  const visit=id=>{
    id=String(id);if(visiting.has(id))throw new Error("Execution contains a dependency cycle.");if(output[id])return;
    const record=graph[id];if(!record)throw new Error(`Missing execution node ${id}.`);
    visiting.add(id);output[id]=record;
    for(const value of Object.values(record.inputs||{}))if(isLink(value)&&graph[String(value[0])])visit(value[0]);
    visiting.delete(id);
  };
  visit(executionId);return output;
}
