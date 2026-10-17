// Missing prompt IDs are accepted only when execution_start identified the runner.
export function routedProgress(detail, executingPrompt, jobs) {
  const promptId=detail.prompt_id||executingPrompt;
  if(!promptId)return null;
  const entry=[...jobs.values()].find(item=>item.promptId===promptId);
  if(!entry)return null;
  const {value,max}=detail;
  if(!Number.isFinite(value)||!Number.isFinite(max)||max<=0||value<0||value>max)return null;
  return {value,max,prompt_id:promptId,job_id:entry.request.job_id,project_id:entry.request.project_id};
}
