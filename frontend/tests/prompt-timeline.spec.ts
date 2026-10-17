import {test,expect} from "@playwright/test";
import {parsePrompt} from "../src/prompt";
import {locateFrame} from "../src/timeline";

test("imports every section without changing shots, names, dialogue or timestamps",()=>{
  const text="subject_definitions:\n<hero> is a traveller.\n\nsummary:\nA coastal journey.\n\nretention_analysis:\n<hero>: fully_preserved - preserve appearance.\n\ndetailed_description:\n[Shot 1] At 00:01.000 <hero> says <d>[Chinese] 我不知道！</d>\n\noverall_soundscape:\nWaves crash.\n\nnon_diegetic_music:\nNone.";
  const parsed=parsePrompt(text);
  expect(parsed.hasHeaders).toBe(true);
  expect(Object.keys(parsed.sections)).toHaveLength(6);
  expect(parsed.sections.detailed_description).toBe('[Shot 1] At 00:01.000 <hero> says <d>[Chinese] 我不知道！</d>');
  expect(parsed.sections.overall_soundscape).toBe('Waves crash.');
});

test("supports markdown and XML sections, plain prompts and explicit empty sections",()=>{
  expect(parsePrompt('```text\n## Subject Definitions:\n<hero> is a traveller.\n**Summary:** A journey.\ndetailed_description:\n[Shot 1] Walk.\nnon_diegetic_music:\n```').sections).toEqual({subject_definitions:'<hero> is a traveller.',summary:'A journey.',detailed_description:'[Shot 1] Walk.',non_diegetic_music:''});
  expect(parsePrompt('<summary>A journey.</summary><detailed_description>[Shot 1] Walk.</detailed_description>').sections.detailed_description).toBe('[Shot 1] Walk.');
  expect(parsePrompt('[Shot 1] A traveller walks.')).toEqual({hasHeaders:false,sections:{detailed_description:'[Shot 1] A traveller walks.'}});
});

test("rejects duplicate sections and content that would be discarded",()=>{
  expect(()=>parsePrompt('summary: one\nsummary: two')).toThrow('Duplicate');
  expect(()=>parsePrompt('Do not lose me\nsummary: one')).toThrow('before the first');
  expect(()=>parsePrompt('<summary>one</summary> Do not lose me')).toThrow('outside the XML');
});

test("scene frame lookup crosses segments, clamps to their last frame and uses local time",()=>{
  const blocks=[{id:'A',start:0,length:124/24},{id:'B',start:124/24,length:119/24}];
  expect(locateFrame(blocks,2.5)?.local).toBe(2.5);
  expect(locateFrame(blocks,124/24)?.block.id).toBe('B');
  expect(locateFrame(blocks,124/24+1.5)?.local).toBe(1.5);
  expect(locateFrame(blocks,999)?.local).toBeCloseTo(118/24,8);
  expect(locateFrame(blocks,-1)?.local).toBe(0);
});
