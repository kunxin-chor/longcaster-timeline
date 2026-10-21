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
const dimensions=(format:typeof formats[number],megapixels:number)=>{
 const ratio=format.width/format.height,pixels=megapixels*1_000_000;
 return {width:Math.round(Math.sqrt(pixels*ratio)/32)*32,height:Math.round(Math.sqrt(pixels/ratio)/32)*32};
};
export const validGenerationSize=(width:number,height:number)=>[width,height].every(value=>Number.isInteger(value)&&value>=256&&value<=2048&&value%32===0);

export function ResolutionSelector({width,height,onChange}:{width:number;height:number;onChange:(width:number,height:number)=>void}){
 const initialMegapixels=Number((width*height/1_000_000).toFixed(3));
 const initial=formats.find(format=>{const size=dimensions(format,initialMegapixels);return size.width===width&&size.height===height;});
 const [formatId,setFormatId]=useState(initial?.id||'custom');
 const [megapixels,setMegapixels]=useState(initialMegapixels);
 const format=formats.find(item=>item.id===formatId);
 function apply(id:string,target:number){setFormatId(id);setMegapixels(target);const next=formats.find(item=>item.id===id);if(next&&Number.isFinite(target)&&target>=0){const size=dimensions(next,target);onChange(size.width,size.height);}}
 return <div className="resolution-selector">
  <div className="resolution-format-controls">
   <label className="field-label">Format<select aria-label="Generation format" value={formatId} onChange={event=>apply(event.target.value,megapixels)}>
    {formats.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}<option value="custom">Custom dimensions</option>
   </select></label>
   <label className="field-label">Megapixels<input aria-label="Generation megapixels" type="number" min={0.01} max={4.2} step={0.05} disabled={!format} value={megapixels} onChange={event=>apply(formatId,Number(event.target.value))}/></label>
  </div>
  <p className="resolution-result"><strong>{width} &times; {height}</strong> &middot; {(width*height/1_000_000).toFixed(3)} MP actual</p>
  <div className="dimension-inputs">
   <label className="field-label">Width<input aria-label="Generation width" type="number" min={256} max={2048} step={32} value={width} onChange={event=>{setFormatId('custom');onChange(Number(event.target.value),height);}}/></label>
   <label className="field-label">Height<input aria-label="Generation height" type="number" min={256} max={2048} step={32} value={height} onChange={event=>{setFormatId('custom');onChange(width,Number(event.target.value));}}/></label>
  </div>
  <p>Dimensions round to multiples of 32 pixels. Each side must be 256&ndash;2048 pixels.</p>
  {!validGenerationSize(width,height)&&<p className="warning" role="alert">Adjust the megapixel target or enter dimensions within the supported range.</p>}
 </div>;
}
