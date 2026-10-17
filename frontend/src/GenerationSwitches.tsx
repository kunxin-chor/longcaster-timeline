import {useEffect,useState} from 'react';
import {Bridge,GenerationDefaults,GenerationSwitch} from './types';

export function defaultsCompatibility(saved:GenerationDefaults|undefined,live:GenerationSwitch[]){
 for(const expected of saved?.schema||[]){
  const actual=live.find(item=>item.id===expected.id);
  if(!actual)return `Production default switch "${expected.name}" is missing from this workflow.`;
  if(actual.kind!==expected.kind||actual.name!==expected.name)return `Production default switch "${expected.name}" is incompatible with this workflow.`;
  for(const option of expected.options)if(!actual.options.some(item=>item.value===option.value&&item.label===option.label))return `Production default switch "${expected.name}" has changed sources. Review and save new defaults in Production.`;
 }
 return '';
}

export function GenerationSwitches({bridge,configurationId,selections,defaults,disabled,onChange,onValidation}:{bridge:Bridge|undefined;configurationId:string;selections:Record<string,string>;defaults?:GenerationDefaults;disabled:boolean;onChange:(id:string,selections:Record<string,string>)=>void;onValidation:(switches:GenerationSwitch[],error:string)=>void}){
 const [switches,setSwitches]=useState<GenerationSwitch[]>([]),[error,setError]=useState('Checking workflow switches...');
 const key=JSON.stringify(selections),defaultsKey=JSON.stringify(defaults);
 useEffect(()=>{
  let current=true,busy=false;
  setError('Checking workflow switches...');onValidation([],'Checking workflow switches...');
  async function update(){if(busy)return;busy=true;try{
   if(!bridge?.configurationSwitches)throw new Error('Open this production from an updated LongCaster workflow to validate its switches.');
   const result=await bridge.configurationSwitches(configurationId,JSON.parse(key));if(!current)return;
   const warning=result.error||defaultsCompatibility(defaults,result.switches);
   setSwitches(result.switches);setError(warning);onValidation(result.switches,warning);
  }catch(exc){if(current){setError((exc as Error).message);onValidation([],(exc as Error).message);}}finally{busy=false;}}
  void update();const timer=setInterval(()=>void update(),2500);return()=>{current=false;clearInterval(timer);};
 },[bridge,configurationId,key,defaultsKey]);
 return <div className="generation-switches">{switches.map(item=><label className="field-label" key={item.id}>{item.name}<select aria-label={item.name} value={item.select} disabled={disabled} onChange={event=>{const option=item.options.find(option=>option.value===event.target.value)!;onChange(option.configuration_id||configurationId,{...selections,[item.id]:option.value});}}>{item.options.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>)}{error&&<p className="warning" role="alert">{error}</p>}</div>;
}
