(function(){
 'use strict';
 const $=id=>document.getElementById('rh-'+id),base='/api/rh-coins-experiment',storageKey='app074-rh-coins-pending-v1';
 let state={enabled:false,configured:false,checked:false,jobs:[],candidates:[]},busy=false,loaded=false,dirty=false,poll=null,polls=0,uncertain=null;
 try{uncertain=JSON.parse(sessionStorage.getItem(storageKey)||'null');}catch(_){uncertain={operation_id:'未知'};}
 const active=job=>['submitting','pending','queued','running','unknown','download_pending'].includes(job.status);
 const node=(tag,value)=>{const element=document.createElement(tag);element.textContent=value;return element;};
 const notice=message=>$('status').textContent=message;
 async function request(path,body){
  const response=await fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok){const error=Error(value.error||'RH币独立实验请求失败');error.status=response.status;throw error;}return value;
 }
 function controls(){
  const pending=state.jobs.some(active)||!!uncertain;
  $('generate').disabled=!loaded||busy||dirty||!state.enabled||!state.configured||!state.checked||!state.member_key_confirmed||!state.web_tested||pending||!$('prompt').value.trim();
  for(const id of ['save','enabled','key','member','web','preset'])$(id).disabled=busy||!loaded;
  $('check').disabled=busy||!loaded||dirty||!state.configured||!state.member_key_confirmed;
  $('prompt').disabled=busy||pending;$('ratio').disabled=busy||pending;$('refresh').disabled=busy;
  $('choose').disabled=busy||!window.app074Desktop;
 }
 function link(){const selected=state.candidates.find(item=>item.key===$('preset').value);$('workflow-link').href=selected?.url||'https://www.runninghub.cn/call-api/workflow-api';}
 function sync(){
  $('enabled').checked=state.enabled;$('member').checked=state.member_key_confirmed;$('web').checked=state.web_tested;
  $('preset').replaceChildren();for(const item of state.candidates){const option=node('option',item.name);option.value=item.key;$('preset').append(option);}$('preset').value=state.preset;link();
  if(!$('directory').value)$('directory').value=state.exportDirectory||'';
 }
 function render(){
  controls();$('account').textContent=(state.configured?'会员 Key 已保存，页面不回显。':'尚未配置独立会员 Key。')+(state.checked?' RH币：'+(state.account.remainCoins??'未知')+'；钱包：'+(state.account.remainMoney??'未知')+' '+(state.account.currency||'')+'；平台类型：'+(state.account.apiType||'未返回'):'');
  $('workflow').textContent=dirty?'配置有未保存的修改，请先保存，再核对。':state.checked?'完整工作流已核对，共 '+state.workflow.nodes+' 个节点；待实际单张出图与账单验收。':'工作流尚未核对，不能提交生成。';
  const host=$('jobs');host.replaceChildren();
  const labels={submitting:'提交中',pending:'已受理，等待平台',queued:'排队中',running:'生成中',unknown:'状态待核对',download_pending:'图片取回中',ok:'已完成',failed:'平台确认失败',rejected:'平台拒绝提交'};
  for(const job of state.jobs){
   const card=document.createElement('article');card.className='rh-job';card.append(node('strong',labels[job.status]||job.status),node('p',job.prompt||''),node('small','本地操作：'+job.operationId));
   if(job.taskId)card.append(node('p','RH任务编号：'+job.taskId));if(job.error)card.append(node('p',job.error));
   if(job.url){const image=document.createElement('img');image.src=job.url;image.alt='RH币独立生图结果';const save=node('button','另存图片');save.type='button';save.disabled=busy;save.onclick=()=>action('/export',{operation_id:job.operationId,directory:$('directory').value},result=>'已保存：'+result.path);card.append(image,save);}
   if(job.taskId&&active(job)){const query=node('button','查询原任务');query.type='button';query.disabled=busy;query.onclick=()=>queryJob(job.operationId);card.append(query);}
   host.append(card);
  }
  if(!state.jobs.length)host.append(node('p','暂无独立测试记录。'));
 }
 function schedule(){
  clearTimeout(poll);poll=null;const job=state.jobs.find(item=>item.taskId&&active(item));
  if(job&&!busy&&polls<200)poll=setTimeout(()=>{polls++;queryJob(job.operationId);},5000);
 }
 async function refresh(syncInputs=false){
  state=await request('');loaded=true;
  if(uncertain&&state.jobs.some(job=>job.operationId===uncertain.operation_id)){uncertain=null;sessionStorage.removeItem(storageKey);}
  if(syncInputs)sync();render();schedule();
  if(uncertain)notice('上次提交响应尚未核对，本地操作：'+uncertain.operation_id+'。请刷新原任务记录并核对RH账单，暂不另开生成。');
 }
 async function action(path,body,message){
  if(busy)return;busy=true;render();clearTimeout(poll);
  try{const result=await request(path,body);notice(message(result));}
  catch(error){notice(error.message);}finally{busy=false;await refresh().catch(error=>{loaded=false;render();notice(error.message);});}
 }
 const queryJob=id=>action('/query',{operation_id:id},job=>job.error||(job.status==='ok'?'原图片已取回，可以另存。':'已查询原任务，等待平台完成。'));
 for(const id of ['key','member','web','preset']){
  $(id)[id==='key'?'oninput':'onchange']=()=>{dirty=true;if(id==='preset'){link();$('web').checked=false;}render();};
 }
 $('enabled').onchange=async()=>{
  if(busy)return;busy=true;clearTimeout(poll);const enabled=$('enabled').checked;controls();
  try{state=await request('/config',{enabled});notice(enabled?'已启用，核对并点击生成前不会提交任务。':'已关闭；原任务仍可查询和保存。');}
  catch(error){$('enabled').checked=state.enabled;notice(error.message);}finally{busy=false;render();schedule();}
 };
 $('save').onclick=async()=>{
  if(busy)return;busy=true;render();clearTimeout(poll);
  try{state=await request('/config',{enabled:$('enabled').checked,api_key:$('key').value,member_key_confirmed:$('member').checked,web_tested:$('web').checked,preset:$('preset').value});$('key').value='';dirty=false;sync();notice('独立配置已保存，请核对配置；未提交生成。');}
  catch(error){notice(error.message);}finally{busy=false;render();schedule();}
 };
 $('check').onclick=async()=>{
  if(busy||$('check').disabled)return;busy=true;render();clearTimeout(poll);notice('正在核对账户与完整工作流，不提交生成…');
  try{state=await request('/check',{});sync();notice('工作流结构已核对。实际画质和扣费仍待单张试用验收。');}
  catch(error){state.checked=false;notice(error.message);}finally{busy=false;render();schedule();}
 };
 $('prompt').oninput=controls;$('ratio').onchange=controls;
 $('generate').onclick=async()=>{
  if(busy||$('generate').disabled)return;
  const body={operation_id:crypto.randomUUID().replace(/-/g,''),prompt:$('prompt').value,ratio:$('ratio').value};
  try{sessionStorage.setItem(storageKey,JSON.stringify(body));}catch(_){notice('无法保存本次提交标记，请重新打开页面后再试；未提交生成。');return;}
  uncertain=body;busy=true;clearTimeout(poll);render();notice('正在提交1张图片，请勿重复点击…');
  try{const job=await request('/generate',body);uncertain=null;sessionStorage.removeItem(storageKey);notice(job.error||'平台已受理一张图片，正在等待结果。');polls=0;}
  catch(error){if(error.status===400){uncertain=null;sessionStorage.removeItem(storageKey);notice(error.message);}else notice(error.message+'；保留本次操作编号，请刷新原任务记录。');}
  finally{busy=false;await refresh().catch(error=>{loaded=false;render();notice(error.message);});}
 };
 $('refresh').onclick=async()=>{if(busy)return;busy=true;controls();try{await refresh();}catch(error){loaded=false;notice(error.message);}finally{busy=false;render();schedule();}};
 $('choose').onclick=async()=>{try{const directory=await window.app074Desktop.choosePath($('directory').value,false);if(directory)$('directory').value=directory;}catch(error){notice(error.message);}};
 window.addEventListener('pagehide',()=>clearTimeout(poll));
 refresh(true).catch(error=>{loaded=false;render();notice(error.message);});
})();
