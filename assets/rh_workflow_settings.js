// Formal workflow settings share the existing member-account configuration.
(function(root){
 'use strict';
 function mount({onDefault,onSaved}={}){
  const $=id=>document.getElementById('rhw-'+id),base='/api/rh-coins-experiment';
  let state={candidates:[]},busy=false,loaded=false,dirty=false;
  const present=value=>value===null||value===undefined||['','none','null','undefined'].includes(String(value).toLowerCase())?'接口未返回':String(value);
  const notice=text=>$('status').textContent=text;
  async function request(path,body){
   const response=await fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const value=await response.json();if(!response.ok)throw Error(value.error||'RH币工作流配置请求失败');return value;
  }
  function controls(){
   for(const id of ['save','default','enabled','key','member','web','preset'])$(id).disabled=busy||!loaded;
   $('refresh').disabled=busy;
   $('check').disabled=busy||!loaded||dirty||!state.configured||!state.member_key_confirmed;
  }
  function link(){const candidate=(state.candidates||[]).find(item=>item.key===$('preset').value);$('workflow-link').href=candidate?.url||'https://www.runninghub.cn/call-api/workflow-api';}
  function draw(sync=false){
   if(sync){$('enabled').checked=!!state.enabled;$('member').checked=!!state.member_key_confirmed;$('web').checked=!!state.web_tested;
    $('preset').replaceChildren();for(const item of state.candidates||[]){const option=document.createElement('option');option.value=item.key;option.textContent=item.name;$('preset').append(option);}$('preset').value=state.preset||'';link();}
   const account=state.account||{};
   $('account').textContent=(state.configured?'国内站会员 Key 已保存，页面不回显。':'尚未配置国内站会员 Key。')+(state.checked?' 上次核对余额：'+present(account.remainCoins)+' RH币（不是单张费用）；钱包余额：'+present(account.remainMoney)+'；账户来源：runninghub.cn。':' 账户来源：runninghub.cn；请保存并核对账户与完整工作流。');
   $('workflow').textContent=dirty?'配置有未保存修改，请先保存，再核对。':state.checked?'完整工作流已核对，共 '+(state.workflow?.nodes||0)+' 个节点。实际画质与扣费可用「测试一张」验收。':'完整工作流尚未核对；核对只读取配置，不提交生图。';
   controls();
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
  refresh();return {save,refresh};
 }
 root.app074RhWorkflowSettings={mount};
})(window);
