import {FIELDS,Field,Reference} from './types';
export const assetToken=(r:Reference)=>`${r.kind==='image'?'picture':r.kind}.${r.token_name}`;
export function renameAssetFields(fields:Record<Field,string>,reference:Reference,name:string,references:Reference[]){
  const escape=(s:string)=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const qualified=new RegExp(`<${escape(assetToken(reference))}>`,'gi');
  const bare=new RegExp(`<${escape(reference.token_name)}>`,'gi');
  const unambiguous=references.filter(r=>r.token_name.toLowerCase()===reference.token_name.toLowerCase()).length===1;
  return Object.fromEntries(FIELDS.map(field=>{
    let text=fields[field].replace(qualified,`<${assetToken({...reference,token_name:name})}>`);
    if(unambiguous)text=text.replace(bare,`<${name}>`);
    return [field,text];
  })) as Record<Field,string>;
}
