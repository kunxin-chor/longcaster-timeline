import {FIELDS, Field} from "./types";

export type ImportedPrompt = {sections: Partial<Record<Field,string>>; hasHeaders:boolean};

/** Import the authored six-section document, without compiling or renumbering it. */
export function parsePrompt(text:string):ImportedPrompt {
  let source=text.replace(/^\uFEFF/,"").replace(/\r\n?/g,"\n").trim();
  source=source.replace(/^```(?:text|plaintext|markdown)?\s*\n/i,"").replace(/\n```\s*$/,"");
  if(!source.trim())return {sections:{},hasHeaders:false};
  const names=FIELDS.map(name=>name.replaceAll("_","[ _]+" )).join("|");
  const xml=new RegExp(`<(${FIELDS.join("|")})\\s*>([\\s\\S]*?)<\\/\\1\\s*>`,"gi");
  const xmlMatches=[...source.matchAll(xml)];
  const sections:Partial<Record<Field,string>>={};
  const add=(name:string,value:string)=>{
    const field=name.toLowerCase().trim().replace(/[ _]+/g,"_") as Field;
    if(field in sections)throw new Error(`Duplicate ${field} section. Keep one heading per section.`);
    if(value.length>50000)throw new Error(`${field} exceeds 50,000 characters.`);
    sections[field]=value.trim();
  };
  if(xmlMatches.length){
    if(source.replace(xml,"").trim())throw new Error("Text outside the XML prompt sections would be lost. Put it inside a section.");
    for(const match of xmlMatches)add(match[1],match[2]);
    return {sections,hasHeaders:true};
  }
  const heading=new RegExp(`^[\\t ]*(?:#{1,6}[\\t ]+)?(?:\\*\\*)?(${names})(?:\\*\\*)?[\\t ]*:[\\t ]*(?:\\*\\*)?[\\t ]*`,"gmi");
  const matches=[...source.matchAll(heading)];
  if(!matches.length){add("detailed_description",source);return {sections,hasHeaders:false};}
  if(source.slice(0,matches[0].index).trim())throw new Error("Text before the first prompt section would be lost. Add a section heading above it.");
  for(let i=0;i<matches.length;i++){
    const match=matches[i];
    add(match[1],source.slice(match.index!+match[0].length,matches[i+1]?.index??source.length));
  }
  return {sections,hasHeaders:true};
}
