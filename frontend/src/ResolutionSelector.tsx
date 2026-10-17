import {useState} from 'react';

const formats = [
 {id:'widescreen',name:'Widescreen (16:9)',width:1024,height:576},
 {id:'portrait-widescreen',name:'Portrait widescreen (9:16)',width:576,height:1024},
 {id:'photo',name:'Photo (3:2)',width:768,height:512},
 {id:'portrait-photo',name:'Portrait photo (2:3)',width:512,height:768},
 {id:'standard',name:'Standard (4:3)',width:768,height:576},
 {id:'portrait',name:'Portrait (3:4)',width:576,height:768},
 {id:'square',name:'Square (1:1)',width:768,height:768},
 {id:'cinema',name:'Cinema (21:9)',width:1344,height:576},
];
const multipliers=[0.5,0.75,1,1.25,1.5,2];
const scaled=(value:number,multiplier:number)=>Math.round(value*multiplier/32)*32;
export const validGenerationSize=(width:number,height:number)=>[width,height].every(value=>Number.isInteger(value)&&value>=256&&value<=2048&&value%32===0);

export function ResolutionSelector({width,height,onChange}:{width:number;height:number;onChange:(width:number,height:number)=>void}){
 const initial=formats.flatMap(format=>multipliers.map(multiplier=>({format,multiplier}))).find(({format,multiplier})=>scaled(format.width,multiplier)===width&&scaled(format.height,multiplier)===height);
 const [formatId,setFormatId]=useState(initial?.format.id||'custom');
 const [multiplier,setMultiplier]=useState(initial?.multiplier||1);
 const format=formats.find(item=>item.id===formatId);
 function apply(id:string,multiple:number){setFormatId(id);setMultiplier(multiple);const next=formats.find(item=>item.id===id);if(next)onChange(scaled(next.width,multiple),scaled(next.height,multiple));}
 return <div className="resolution-selector">
  <div className="resolution-format-controls">
   <label className="field-label">Format<select aria-label="Generation format" value={formatId} onChange={event=>apply(event.target.value,multiplier)}>
    {formats.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}<option value="custom">Custom dimensions</option>
   </select></label>
   <label className="field-label">Multiplier<select aria-label="Generation resolution multiplier" disabled={!format} value={multiplier} onChange={event=>apply(formatId,Number(event.target.value))}>
    {multipliers.map(value=><option key={value} value={value}>{value}x</option>)}
   </select></label>
  </div>
  {format&&<p className="resolution-result">{format.width} &times; {format.height} at 1x &rarr; <strong>{width} &times; {height}</strong></p>}
  <div className="dimension-inputs">
   <label className="field-label">Width<input aria-label="Generation width" type="number" min={256} max={2048} step={32} value={width} onChange={event=>{setFormatId('custom');onChange(Number(event.target.value),height);}}/></label>
   <label className="field-label">Height<input aria-label="Generation height" type="number" min={256} max={2048} step={32} value={height} onChange={event=>{setFormatId('custom');onChange(width,Number(event.target.value));}}/></label>
  </div>
  <p>Dimensions round to multiples of 32 pixels. Each side must be 256&ndash;2048 pixels.</p>
  {!validGenerationSize(width,height)&&<p className="warning" role="alert">Choose a smaller multiplier or enter dimensions within the supported range.</p>}
 </div>;
}
