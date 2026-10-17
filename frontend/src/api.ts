export const BASE = "/longcaster-timeline";
export async function request(path:string, body?:unknown, method=body?"POST":"GET") {
  const response = await fetch(BASE+path, {method,headers:body instanceof FormData?undefined:body?{"Content-Type":"application/json"}:undefined,body:body instanceof FormData?body:body?JSON.stringify(body):undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
export const media = (project:string, kind:string, id:string) => `${BASE}/projects/${project}/media/${kind}/${id}`;
