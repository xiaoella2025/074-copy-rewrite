const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

test('custom prompt selector remains visible in half and live task modes',()=>{
 function element(parent=null){return {parentElement:parent,children:[],hidden:false,classList:{remove(){}},append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}},before(){},after(){},closest(){return this;},addEventListener(){}};}
 const trackSection=element(),row=element(),rewrite=element(row),picker=element(rewrite),viewpoint=element(row),tracks=element(trackSection);
 tracks.closest=()=>trackSection;
 const process=element();let mode='half';
 const nodes={'rewrite-section':rewrite,'prompt-template':{parentElement:picker},tracks,'viewpoints':{parentElement:viewpoint},'process-mode':process};
 const document={getElementById:id=>nodes[id],querySelector:selector=>selector==='#process-mode .active'?{dataset:{pm:mode}}:null,createElement:()=>row};
 vm.runInNewContext(fs.readFileSync('assets/story_form_layout.js','utf8'),{document,window:{},setTimeout:fn=>fn()});
 assert.equal(picker.parentElement,trackSection,'template picker must be outside hidden rewrite controls');
 assert.equal(row.hidden,true);mode='live';
 assert.equal(trackSection.hidden,false);
});

async function formFixture(source='assets/form_libraries.js'){
 class Element{
  constructor(){this.children=[];this.dataset={};this.value='';this.style={};this.listeners={};const flags=new Set();this.classList={toggle:(name,on)=>on?flags.add(name):flags.delete(name),contains:name=>flags.has(name)};}
  append(child){child.parent=this;this.children.push(child);}get options(){return this.children;}
  remove(){this.parent.children=this.parent.children.filter(x=>x!==this);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(selector){return this.children.filter(c=>selector==='[data-prompt-template]'?c.dataset.promptTemplate:selector==='.chip.active'?c.classList.contains('active'):true);}
  click(){this.onclick?.();}
 }
 const builtin={id:'character-story',name:'system',builtin:true,baseTrack:'character-story'},
  custom={id:'custom-fixture',name:'my character template',baseTrack:'character-story',step1RewriteSystemPrompt:'edited rules',styleId:'fixture-style'};
 let templates=[builtin,custom];const tracks=new Element(),original=new Element(),pick=new Element();
 original.dataset.track='character-story';original.classList.toggle('active',true);tracks.append(original);
 const nodes={'draft-templates':new Element(),'prompt-template':pick,tracks};let styles=0;
 const context={URLSearchParams,location:{search:''},$:id=>nodes[id],api:async path=>({templates:path.endsWith('prompts')?templates:[]}),
  document:{createElement:()=>new Element(),querySelector:selector=>selector.startsWith('.style-chip')?{click:()=>styles++}:null},setChipsActive(){},console};
 vm.createContext(context);vm.runInContext(fs.readFileSync(source,'utf8'),context);await vm.runInContext('formLibrariesReady',context);
 return {context,tracks,pick,custom,original,styles:()=>styles,setTemplates:value=>templates=value,request:()=>vm.runInContext('promptTemplateRequest()',context)};
}

test('saved template automatically appears beside system tracks and selecting it submits its own rules',async()=>{
 const f=await formFixture(process.env.FORM_LIBRARY_SOURCE);
 const chip=f.tracks.children.find(x=>x.dataset.promptTemplate===f.custom.id);assert.ok(chip,'saved custom template appears as a track chip');
 chip.click();assert.equal(chip.classList.contains('active'),true);assert.equal(f.original.classList.contains('active'),false);
 assert.equal(f.request().prompt_template_id,f.custom.id);assert.equal(f.request().prompt_template.step1RewriteSystemPrompt,'edited rules');assert.ok(f.styles()>0);
 f.tracks.listeners.click({target:{closest:()=>f.original}});
 assert.equal(f.request().prompt_template_id,'character-story','switching back to system track clears custom selection');
});

test('returning from template management adds newly saved chips without duplicate or automatic selection',async()=>{
 const f=await formFixture();const later={...f.custom,id:'custom-later',name:'later'};
 f.setTemplates([later]);await vm.runInContext('refreshPromptTemplateChips()',f.context);
 await vm.runInContext('refreshPromptTemplateChips()',f.context);
 assert.equal(f.tracks.children.filter(x=>x.dataset.promptTemplate===later.id).length,1);
 assert.equal(f.original.classList.contains('active'),true,'saving a template must not silently choose it');
 f.tracks.children.find(x=>x.dataset.promptTemplate===later.id).click();assert.equal(f.request().prompt_template_id,later.id);
});
