// Formal workflow settings share the existing member-account configuration.
(function(root){
 'use strict';
 function mount({onDefault,onSaved}={}){
  const $=id=>document.getElementById('rhw-'+id),base='/api/rh-coins-experiment';
  let state={candidates:[]},busy=false,loaded=false,dirty=false,cardViews=[];
  const present=value=>value===null||value===undefined||['','none','null','undefined'].includes(String(value).toLowerCase())?'接口未返回':String(value);
  const notice=text=>$('status').textContent=text;
  async function request(path,body){
   const response=await fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const value=await response.json();if(!response.ok)throw Error(value.error||'RH币工作流配置请求失败');return value;
  }
  function controls(){
   for(const id of ['save','default','enabled','key','member','web','preset'])$(id).disabled=busy||!loaded;
   for(const view of cardViews)view.button.disabled=busy||!loaded;
   $('refresh').disabled=busy;
   if($('add'))$('add').disabled=busy||!loaded||dirty||!state.configured||!state.member_key_confirmed;
   $('check').disabled=busy||!loaded||dirty||!state.configured||!state.member_key_confirmed;
  }
  function price(item){
   if(item.api_tested&&item.api_test_cost!=null&&Number.isFinite(Number(item.api_test_cost))){
    const range=item.api_test_cost_range,estimate=Array.isArray(range)&&range.length===2&&range[0]!==range[1]?range[0]+'～'+range[1]:item.api_test_cost;
    return {label:'约 '+estimate+' RH币/张',detail:'已完成单张 API 实测；费用随运行耗时变化，以平台账单为准',kind:'reference'};
   }
   return item.key==='qwen-simple'||item.id==='1955160402595233794'
    ?{label:'历史约12 RH币/张',detail:'你此前反馈的参考值，非固定报价',kind:'reference'}
    :{label:'费用待实测',detail:'按实际耗时计费，以平台账单为准',kind:'unknown'};
  }
  function updateCards(){
   const selected=$('preset').value;
   for(const view of cardViews){const active=view.key===selected;view.button.classList.toggle('active',active);view.button.setAttribute('aria-pressed',String(active));view.badge.textContent=active?(dirty?'待保存':'已选中'):view.key===state.preset?'已保存':'';view.badge.hidden=!view.badge.textContent;}
  }
  function buildCards(){
   const host=$('workflows');if(!host)return;host.replaceChildren();cardViews=[];
   const make=(tag,cls,text)=>{const node=document.createElement(tag);node.className=cls;if(text!==undefined)node.textContent=text;return node;};
   const descriptions={'qwen-simple':'通用文生图 · 已有历史参考','qwen-native':'原生千问 · 基础备选','flux-native':'通用背景与分镜 · 热门','qwen-chinese':'中文海报 · 优选','sdxl-native':'写实单图 · 基础备选'};
   for(const item of state.candidates||[]){
    const cost=price(item),button=make('button','image-provider-tab rh-workflow-card'),top=make('div','rh-model-top'),badge=make('span','image-provider-tab-badge');
    button.type='button';button.dataset.workflowKey=item.key;button.title=(item.note?item.note+'。':'')+cost.detail;
    top.append(make('strong','rh-model-name',item.name),make('span','rh-workflow-price '+cost.kind,cost.label),badge);
    button.append(top,make('span','rh-model-desc',descriptions[item.key]||'自定义单图工作流'),make('span','rh-workflow-cost-note',cost.detail),make('span','rh-model-desc',item.api_tested?'API 已实际出图':item.checked?'完整图已核对':'待核对完整图'));
    button.onclick=()=>{if(busy||!loaded)return;$('preset').value=item.key;$('preset').onchange();};
    cardViews.push({key:item.key,button,badge});host.append(button);
   }
  }
  function link(){const candidate=(state.candidates||[]).find(item=>item.key===$('preset').value);$('workflow-link').href=candidate?.url||'https://www.runninghub.cn/call-api/workflow-api';if($('selection'))$('selection').textContent=(candidate?.note||'')+' '+(candidate?.family?candidate.family.toUpperCase()+' · ':'')+(candidate?.api_tested?price(candidate).label+'（单张 API 实测参考）；后续以平台账单为准。':'单张费用未实测，以平台任务账单为准。');}
  function draw(sync=false){
   if(sync){$('enabled').checked=!!state.enabled;$('member').checked=!!state.member_key_confirmed;$('web').checked=!!state.web_tested;
    $('preset').replaceChildren();for(const item of state.candidates||[]){const option=document.createElement('option');option.value=item.key;option.textContent=item.name;$('preset').append(option);}$('preset').value=state.preset||'';link();buildCards();}
   const account=state.account||{};
   $('account').textContent=(state.configured?'国内站会员 Key 已保存，页面不回显。':'尚未配置国内站会员 Key。')+(state.checked?' 上次核对余额：'+present(account.remainCoins)+' RH币（不是单张费用）；钱包余额：'+present(account.remainMoney)+'；账户来源：runninghub.cn。':' 账户来源：runninghub.cn；请保存并核对账户与完整工作流。');
   $('workflow').textContent=dirty?'配置有未保存修改，请先保存，再核对。':state.checked?'完整工作流已核对，共 '+(state.workflow?.nodes||0)+' 个生图节点。'+(state.workflow?.removedNodes?'已直连提示词/尺寸，省去 '+state.workflow.removedNodes+' 个辅助节点。':'')+'实际画质与扣费可用「测试一张」验收。':'完整工作流尚未核对；核对只读取配置，不提交生图。';
   updateCards();controls();
  }
  async function refresh(){if(busy)return;busy=true;controls();try{state=await request('');loaded=true;dirty=false;draw(true);}catch(error){loaded=false;notice(error.message);}finally{busy=false;controls();}}
  async function save(makeDefault=false){
   if(busy||!loaded)return false;busy=true;controls();
   try{state=await request('/config',{enabled:$('enabled').checked,api_key:$('key').value.trim(),member_key_confirmed:$('member').checked,web_tested:$('web').checked,preset:$('preset').value});
    $('key').value='';dirty=false;draw(true);if(makeDefault)await onDefault?.();await onSaved?.();notice(makeDefault?'配置已保存，已设为默认绘图引擎；未提交生成。':'共享配置已保存；未切换默认引擎，未提交生成。');return true;
   }catch(error){notice(error.message);return false;}finally{busy=false;controls();}
  }
  for(const id of ['key','enabled','member','web','preset'])$(id)[id==='key'?'oninput':'onchange']=()=>{dirty=true;if(id==='preset'){$('web').checked=false;link();}draw();};
  $('save').onclick=()=>save(false);$('default').onclick=()=>save(true);$('refresh').onclick=refresh;
  $('check').onclick=async()=>{if($('check').disabled)return;busy=true;controls();notice('正在核对账户与完整工作流，不提交生图…');try{state=await request('/check',{});draw(true);await onSaved?.();notice('账户与工作流已核对；未提交生成。');}catch(error){state.checked=false;draw();notice(error.message);}finally{busy=false;controls();}};
  if($('add'))$('add').onclick=async()=>{if($('add').disabled)return;busy=true;controls();notice('正在读取并核对完整工作流，不提交生图…');try{const value=await request('/workflows/add',{name:$('add-name').value.trim(),url:$('add-url').value.trim()});state=await request('');draw(true);$('add-name').value='';$('add-url').value='';await onSaved?.();notice(value.message);}catch(error){notice(error.message);}finally{busy=false;controls();}};
  refresh();return {save,refresh};
 }
 root.app074RhWorkflowSettings={mount};
})(window);
