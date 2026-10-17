import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";
import {configurationChoices,prepareConfiguration,executionGraph} from "./configurations.js";

import {discoverSwitches,validateDefinitions} from "./switches.js";
import {routedProgress} from "./generation_progress.js";

const listeners = new Set();
let executingPrompt=null;
let lastPrompt = null;
let definitionsCache=null,definitionsAt=0;
const jobPrompts = new Map();
const bridge = {
  status() {
    const nodes = app.graph?._nodes?.filter(n => n.comfyClass === "LongCasterTimelineExecute" || n.type === "LongCasterTimelineExecute") || [];
    return {connected: nodes.length === 1, count: nodes.length, message: nodes.length === 1 ? "Execution node connected" : nodes.length ? "Keep one Timeline Execution node in the canvas" : "Add LongCaster Timeline — Execution and connect a configuration (or MODEL/SAMPLER/SIGMAS), CLIP and VAEs"};
  },
  async configurations() {
    const nodes=app.graph?._nodes?.filter(n=>n.comfyClass==="LongCasterTimelineExecute"||n.type==="LongCasterTimelineExecute")||[];
    if(nodes.length!==1)throw new Error(bridge.status().message);
    return configurationChoices((await app.graphToPrompt()).output,String(nodes[0].id)).map(({upstream,...choice})=>choice);
  },
  async configurationSwitches(id,selections={}) {
    const nodes=app.graph?._nodes?.filter(n=>n.comfyClass==="LongCasterTimelineExecute"||n.type==="LongCasterTimelineExecute")||[];
    if(nodes.length!==1)throw new Error(bridge.status().message);
    const graph=(await app.graphToPrompt()).output,executionId=String(nodes[0].id);
    const switches=discoverSwitches(graph,executionId,id,selections);
    try {
      const configuration=prepareConfiguration(graph,executionId,id,selections);
      if(!definitionsCache||Date.now()-definitionsAt>30000){const response=await api.fetchApi("/object_info");if(!response.ok)throw new Error("Cannot validate workflow node definitions.");definitionsCache=await response.json();definitionsAt=Date.now();}
      validateDefinitions(executionGraph(graph,executionId,configuration),definitionsCache);
      return {switches,error:""};
    }catch(error){return {switches,error:error.message};}
  },
  async prepareConfiguration(id,selections={}) {
    const nodes=app.graph?._nodes?.filter(n=>n.comfyClass==="LongCasterTimelineExecute"||n.type==="LongCasterTimelineExecute")||[];
    if(nodes.length!==1)throw new Error(bridge.status().message);
    const report=await bridge.configurationSwitches(id,selections);if(report.error)throw new Error(report.error);
    return prepareConfiguration((await app.graphToPrompt()).output,String(nodes[0].id),id,selections);
  },
  async submit(request) {
    const nodes = app.graph?._nodes?.filter(n => n.comfyClass === "LongCasterTimelineExecute" || n.type === "LongCasterTimelineExecute") || [];
    if (nodes.length !== 1) throw new Error(bridge.status().message);
    const node = nodes[0];
    const required=request.operation==="preview"?["clip","video_vae","audio_vae"]:request.configuration?["configuration","clip","video_vae","audio_vae"]:["model","clip","video_vae","audio_vae","sampler","sigmas"];
    const missing = required.filter(name => node.inputs?.find(input => input.name === name)?.link == null);
    if (missing.length) throw new Error(`Connect execution inputs: ${missing.join(", ")}`);
    const token = node.widgets.find(w => w.name === "request_token");
    token.value = JSON.stringify({...request, nonce: crypto.randomUUID()});
    const serialized = await app.graphToPrompt();
    // Freeze and prune selection in this queued prompt; leave canvas widgets intact.
    const output = executionGraph(serialized.output,String(node.id),request.configuration||null,request.operation);
    const result = await api.queuePrompt(0, {output, workflow: serialized.workflow});
    lastPrompt = result.prompt_id;
    if (request.job_id) {
      jobPrompts.set(request.job_id, {promptId:result.prompt_id, request});
      void saveProgress({project_id:request.project_id,job_id:request.job_id,prompt_id:result.prompt_id,stage:executingPrompt===result.prompt_id?"loading_models":"queued"});
    }
    return result;
  },
  async cancel(request) {
    // Interrupt only our currently executing prompt; remove our queued item otherwise.
    const promptId = jobPrompts.get(request?.job_id)?.promptId;
    if (!promptId) throw new Error("This app connection cannot identify that job's ComfyUI prompt. Keep the original ComfyUI tab open.");
    const response = await api.fetchApi("/queue"); const queue = await response.json();
    if (queue.queue_running?.some(row => row[1] === promptId)) {await api.interrupt();return {queuedRemoved:false};}
    if (queue.queue_pending?.some(row => row[1] === promptId)) {
      await api.fetchApi("/queue", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({delete:[promptId]})});
      return {queuedRemoved:true};
    }
    return {queuedRemoved:false};
  },
  subscribe(callback) {listeners.add(callback); return () => listeners.delete(callback);},
};
window.longcasterTimelineBridge = bridge;
async function saveProgress(progress) {
  try{await api.fetchApi(`/longcaster-timeline/projects/${progress.project_id}/jobs/${progress.job_id}/progress`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(progress)});}catch(error){console.error("LongCaster progress update failed",error);}
}
let lastSaved=0;
api.addEventListener("execution_start",event=>{
  executingPrompt=event.detail.prompt_id||null;
  const entry=[...jobPrompts.values()].find(item=>item.promptId===executingPrompt);
  if(entry)void saveProgress({project_id:entry.request.project_id,job_id:entry.request.job_id,prompt_id:executingPrompt,stage:"loading_models"});
});
api.addEventListener("progress",event=>{
  const progress=routedProgress(event.detail,executingPrompt,jobPrompts);if(!progress)return;
  for(const listener of listeners)listener(progress);
  if(Date.now()-lastSaved>500||progress.value===progress.max){lastSaved=Date.now();void saveProgress({...progress,stage:"sampling"});}
});
for (const [eventName,stage] of [["execution_interrupted","cancelled"],["execution_error","failed"]]) {
  api.addEventListener(eventName,event=>{
    const entry=[...jobPrompts.values()].find(item=>item.promptId===event.detail.prompt_id);
    if(!entry)return;
    void saveProgress({project_id:entry.request.project_id,job_id:entry.request.job_id,prompt_id:entry.promptId,stage,
      message:event.detail.exception_message||(stage==="cancelled"?"Generation cancelled in ComfyUI.":"ComfyUI execution failed.")});
    if(executingPrompt===entry.promptId)executingPrompt=null;
  });
}
app.registerExtension({
  name: "LongCaster.Timeline.App",
  setup() {
    const button = document.createElement("button");
    button.textContent = "◈ LongCaster"; button.title = "Open LongCaster Timeline app";
    button.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:9999;background:#1671cd;color:white;border:1px solid #4999ed;border-radius:7px;padding:11px 18px;font:600 13px system-ui;cursor:pointer;box-shadow:0 4px 18px #0005";
    button.onclick = () => window.open(api.apiURL("/longcaster-timeline/app"), "longcaster_timeline_app");
    document.body.append(button);
  },
});
