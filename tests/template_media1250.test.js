const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.style={};this.value='';this.textContent='';this.disabled=false;}
 append(...items){for(const item of items){this.children.push(item);if(item instanceof Element)item.parent=this;}}
 replaceChildren(...items){this.children=[];this.append(...items);}
 setAttribute(k,v){this[k]=v;}
 click(){return this.onclick?.();}
}
function fixture(options={}){
 const window={},document={createElement:tag=>new Element(tag)};
 vm.runInNewContext(fs.readFileSync('assets/template_media1250.js','utf8'),{window,document,FileReader:class{readAsDataURL(file){this.result=file.data_url;this.onload();}},fetch:options.fetch||(async()=>{throw Error('unexpected network');})});
 const catalog=JSON.parse(fs.readFileSync('assets/draft_catalog1250.json','utf8'));
 let config={image:{effect:'Legacy'},audio:{},title:{font:''}};
 const host=new Element('div'),ctx={catalog,config,update(path,value){const [key,field]=path.split('.');config[key][field]=value;},refresh(){},error(e){throw e;}};
 return {api:window.DraftMedia1250,catalog,config,host,ctx};
}
function find(el,predicate){return el.children.flatMap(x=>x instanceof Element?[...(predicate(x)?[x]:[]),...find(x,predicate)]:[]);}
test('legacy effect fallback is read-only and explicit empty wins',()=>{
 const {api,config}=fixture();assert.equal(api.effectiveEffects(config.image)[0].name,'Legacy');assert.equal(config.image.effects,undefined);
 config.image.effects=[];assert.equal(api.effectiveEffects(config.image).length,0);
});
test('local multi-upload preserves each endpoint response and sound placements',async()=>{
 const calls=[],f=fixture({fetch:async(path,options)=>{const body=JSON.parse(options.body);calls.push({path,body});return {ok:true,json:async()=>({path:'C:/isolated/'+body.name,name:body.name})};}});
 f.api.soundsPanel(f.host,f.ctx);const file=find(f.host,x=>x.type==='file')[0];
 file.files=[{name:'a.wav',data_url:'data:audio/wav;base64,YQ=='},{name:'b.mp3',data_url:'data:audio/mpeg;base64,Yg=='}];await file.onchange();
 assert.equal(calls.length,2);assert.equal(calls[0].path,'/api/template-sound/upload');assert.deepEqual(calls[0].body,{name:'a.wav',data_url:'data:audio/wav;base64,YQ=='});
 assert.equal(f.config.audio.soundEffects.length,2);assert.equal(f.config.audio.soundEffects[1].path,'C:/isolated/b.mp3');assert.equal(f.config.audio.soundEffects[1].atSeconds,0);
});

test('template reset cannot replace the configuration while a sound upload is pending',async()=>{
 let release;const gate=new Promise(resolve=>release=resolve);
 const f=fixture({fetch:async()=>{await gate;return {ok:true,json:async()=>({path:'C:/isolated/new.wav',name:'new'})};}});
 const elements=new Map(),old={audio:{soundEffects:[{name:'old',path:'C:/isolated/old.wav'}]},canvas:{ratio:'9:16'}};
 const document={getElementById:id=>{if(!elements.has(id))elements.set(id,new Element('div'));return elements.get(id);},addEventListener(){}};
 const context=vm.createContext({document,location:{search:''},URLSearchParams,DraftMedia1250:f.api,fetch:()=>new Promise(()=>{}),old,mediaCatalog:f.catalog,confirm:()=>true});
 vm.runInContext(fs.readFileSync('assets/template_editor.js','utf8'),context);
 vm.runInContext("config=old;catalog=mediaCatalog;original={config:{audio:{soundEffects:[]},canvas:{ratio:'9:16'}}};renderPanels=()=>{};paint=()=>{};loadBackground=async()=>{};",context);
 const ctx=vm.runInContext('mediaContext()',context);f.api.soundsPanel(f.host,ctx);
 const file=find(f.host,x=>x.type==='file')[0];file.files=[{name:'new.wav',data_url:'data:audio/wav;base64,YQ=='}];
 const pending=file.onchange();
 try{
  assert.equal(f.api.isUploading(),true);elements.get('reset').click();
  assert.equal(vm.runInContext('config===old',context),true);
 }finally{release();await pending;}
 assert.deepEqual([...vm.runInContext('config.audio.soundEffects.map(x=>x.name)',context)],['old','new']);
});
test('over-limit multi-upload never sends a request',async()=>{
 const errors=[],f=fixture();f.ctx.error=e=>errors.push(e.message);f.api.soundsPanel(f.host,f.ctx);
 const file=find(f.host,x=>x.type==='file')[0];file.files=Array.from({length:6},()=>({name:'a.wav',data_url:'data:audio/wav;base64,YQ=='}));await file.onchange();
 assert.equal(errors.length,1);assert.equal(f.config.audio.soundEffects,undefined);
});
test('partial upload failure keeps completed local files and reports error',async()=>{
 let calls=0;const errors=[],f=fixture({fetch:async()=>++calls===1?{ok:true,json:async()=>({path:'C:/isolated/a.wav',name:'a'})}:{ok:false,json:async()=>({error:'fixture failure'})}});f.ctx.error=e=>errors.push(e.message);f.api.soundsPanel(f.host,f.ctx);
 const file=find(f.host,x=>x.type==='file')[0];file.files=[{name:'a.wav',data_url:'data:audio/wav;base64,YQ=='},{name:'b.wav',data_url:'data:audio/wav;base64,Yg=='}];await file.onchange();
 assert.equal(f.config.audio.soundEffects.length,1);assert.deepEqual(errors,['fixture failure']);
});
test('catalog searches and membership filters preserve complete catalog',()=>{
 const {api,catalog}=fixture();assert.equal(api.filterCatalog(catalog,'fonts','all','').length,335);
 assert.equal(api.filterCatalog(catalog,'fonts','free','').length,219);assert.equal(api.filterCatalog(catalog,'fonts','vip','').length,116);
 assert.equal(api.filterCatalog(catalog,'effects','all','').length,913);assert.equal(api.filterCatalog(catalog,'effects','vip','').length,298);
 assert.ok(api.filterCatalog(catalog,'fonts','recommended','').length>0);
 assert.ok(api.filterCatalog(catalog,'fonts','all','mIsAnS').some(x=>x.name==='MiSans-Regular'));
 assert.ok(api.filterCatalog(catalog,'fonts','recommended','mIsAnS').some(x=>x.name==='MiSans-Regular'));
});
test('effects controls preserve independent mode/seconds and clear legacy explicitly',()=>{
 const f=fixture();f.api.effectsPanel(f.host,f.ctx);
 const clear=find(f.host,x=>x.textContent==='清除全部特效')[0];clear.click();assert.equal(f.config.image.effects.length,0);assert.equal(f.config.image.effect,'Legacy');
 const f2=fixture();f2.config.image.effects=[{name:'A',mode:'full'},{name:'B',mode:'full'}];f2.api.effectsPanel(f2.host,f2.ctx);
 const select=find(f2.host,x=>x['aria-label']==='B 时长')[0];select.value='head';select.onchange();
 assert.equal(f2.config.image.effects[0].mode,'full');assert.equal(f2.config.image.effects[1].mode,'head');assert.equal(f2.config.image.effects[1].seconds,3);
});
test('same sound may be added twice and each placement changes independently',()=>{
 const f=fixture();f.api.soundsPanel(f.host,f.ctx);
 const add=find(f.host,x=>x.dataset.soundId===f.catalog.sounds[0].id)[0];add.click();add.click();
 assert.equal(f.config.audio.soundEffects.length,2);
 const second=new Element('div');f.api.soundsPanel(second,f.ctx);
 const placement=find(second,x=>x['aria-label']==='音效 2 放置位置')[0];placement.value='every_scene';placement.onchange();
 assert.equal(f.config.audio.soundEffects[0].placement,'start');assert.equal(f.config.audio.soundEffects[1].placement,'every_scene');assert.equal(f.config.audio.soundEffects[1].everyN,1);
 for(let i=0;i<8;i++)add.click();assert.equal(f.config.audio.soundEffects.length,5);
});
test('four text layers persist names and clear to default using real font controls',()=>{
 for(const layer of ['title','subtitle','caption','disclaimer']){
  const f=fixture();f.config[layer]={font:'MiSans-Regular'};f.api.fontPicker(f.host,layer,f.ctx);
  const clear=find(f.host,x=>x.textContent==='默认字体（清除选择）')[0];clear.click();assert.equal(f.config[layer].font,'');
  const choose=find(f.host,x=>x.dataset.fontName===f.catalog.recommendedFonts[0])[0];choose.click();assert.equal(f.config[layer].font,f.catalog.recommendedFonts[0]);
 }
});
