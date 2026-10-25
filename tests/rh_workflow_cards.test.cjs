const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 class El{constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.checked=false;this.disabled=false;this.textContent='';this.style={};this.dataset={};this.attrs={};this.className='';this.classList={toggle:(name,on)=>{let values=this.className.split(' ').filter(x=>x&&x!==name);if(on)values.push(name);this.className=values.join(' ');}};}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}setAttribute(key,value){this.attrs[key]=String(value);} }
 const ids=['key','enabled','member','web','preset','save','default','check','refresh','account','workflow','status','workflow-link','selection','workflows'];const nodes=Object.fromEntries(ids.map(id=>['rhw-'+id,new El()]));
 let state={enabled:true,configured:true,checked:true,member_key_confirmed:true,web_tested:true,preset:'qwen-simple',candidates:[{key:'qwen-simple',id:'1955160402595233794',name:'Qwen 原生'},{key:'flux-native',id:'1819583592967110658',name:'FLUX 热门'},{key:'sdxl-native',name:'SDXL'},{key:'custom-1234567890',name:'我的模型'}],workflow:{nodes:11},account:{remainCoins:'937'}};
 const calls=[],ctx={window:{},document:{getElementById:id=>nodes[id],createElement:tag=>new El(tag)},fetch:async(path,options={})=>{const body=options.body&&JSON.parse(options.body);calls.push({path,body});if(path.endsWith('/config'))state={...state,...body};return {ok:true,json:async()=>state};}};
 vm.runInNewContext(fs.readFileSync('assets/rh_workflow_settings.js','utf8'),ctx);ctx.window.app074RhWorkflowSettings.mount({onDefault:async()=>calls.push({path:'default'})});
 const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};const text=el=>el.textContent+' '+el.children.map(text).join(' ');
 return {nodes,calls,tick,text,cards:()=>nodes['rhw-workflows'].children};
}
test('each workflow is a native button with a price state and honest historical reference',async()=>{
 const f=fixture();await f.tick();assert.equal(f.cards().length,4);
 const first=f.cards()[0];assert.equal(first.tag,'button');assert.equal(first.attrs['aria-pressed'],'true');assert.match(f.text(first),/12.*RH币/);assert.match(f.text(first),/历史|参考/);
 for(const card of f.cards().slice(1)){assert.match(f.text(card),/待实测/);assert.ok(!/12/.test(f.text(card)),'unknown workflows do not inherit the previous workflow cost');}
});
test('choosing a card only updates local selection and saving retains the chosen workflow',async()=>{
 const f=fixture();await f.tick();const before=f.calls.length;f.cards()[1].onclick();assert.equal(f.nodes['rhw-preset'].value,'flux-native');assert.equal(f.nodes['rhw-web'].checked,false);assert.equal(f.calls.length,before);
 assert.equal(f.cards()[1].attrs['aria-pressed'],'true');assert.equal(f.cards()[0].attrs['aria-pressed'],'false');
 await f.nodes['rhw-save'].onclick();assert.equal(f.calls.find(c=>c.path.endsWith('/config')).body.preset,'flux-native');assert.ok(!f.calls.some(c=>c.path==='default'||c.path.endsWith('/generate')));
});
test('unknown pricing is not inferred from account balance and visible dropdown is removed',async()=>{
 const f=fixture();await f.tick();assert.ok(!f.cards().some(c=>f.text(c).includes('937')));
 const html=fs.readFileSync('settings.html','utf8');assert.ok(/id="rhw-workflows"/.test(html));assert.ok(/id="rhw-preset"[^>]*hidden/.test(html));assert.match(html,/\.rh-workflow-card \.image-provider-tab-badge\[hidden\]\{display:none;\}/);
});
