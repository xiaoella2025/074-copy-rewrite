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

test('saved custom character template loads into the creation picker and selected snapshot is submitted',async()=>{
 const optionList=[],pick={value:'',append:option=>optionList.push(option)};
 const custom={id:'custom-fixture',name:'my character template',baseTrack:'character-story',step1RewriteSystemPrompt:'edited rules'};
 const chips={querySelectorAll:()=>[],addEventListener(){}};
 const nodes={'draft-templates':chips,'prompt-template':pick,tracks:chips};
 const context={URLSearchParams,location:{search:''},$:id=>nodes[id],api:async path=>({templates:path.endsWith('prompts')?[custom]:[]}),
  document:{createElement:()=>({}),querySelector:()=>null},setChipsActive:()=>{},console};
 vm.createContext(context);vm.runInContext(fs.readFileSync('assets/form_libraries.js','utf8'),context);
 await vm.runInContext('formLibrariesReady',context);
 assert.equal(optionList.length,1);assert.equal(optionList[0].value,custom.id);
 pick.value=custom.id;pick.onchange();
 const request=vm.runInContext('promptTemplateRequest()',context);
 assert.equal(request.prompt_template_id,custom.id);assert.equal(request.prompt_template.step1RewriteSystemPrompt,'edited rules');
});
