(function(){
 'use strict';
 const $=id=>document.getElementById(id),base='/api/ms-reference-experiment';
 let state={enabled:false,configured:false,jobs:[]},busy=false,operation='',poll=null,polls=0,preview='';
 const active=job=>['submitting','pending','unknown','download_pending'].includes(job.status);
 const freshId=()=>crypto.randomUUID().replace(/-/g,'');
 const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node;};
 async function request(path,body){
  const response=await fetch(base+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'独立实验请求失败');return value;
 }
 function notice(message){$('experiment-status').textContent=message;}
 function controls(){
  $('experiment-enabled').checked=state.enabled;$('experiment-enabled').disabled=busy;
  $('experiment-account').textContent=state.configured?'魔搭Token已配置 · '+(state.enabled?'独立实验已启用':'独立实验未启用'):'请先到系统设置保存魔搭Token。';
  const pending=state.jobs.some(active);
  $('experiment-generate').disabled=busy||!state.enabled||!state.configured||pending||!$('experiment-reference').files.length||!$('experiment-prompt').value.trim();
  $('experiment-reference').disabled=busy||pending;$('experiment-prompt').disabled=busy||pending;
 }
 function render(){
  controls();const host=$('experiment-jobs');host.replaceChildren();
  const labels={submitting:'提交中',pending:'排队／生成中',unknown:'提交结果不明，请核对魔搭记录',download_pending:'图片取回中',ok:'已完成',failed:'平台确认失败',rejected:'平台拒绝提交'};
  for(const job of state.jobs){
   const card=document.createElement('article');card.className='experiment-job';card.append(text('strong',labels[job.status]||job.status),text('p',job.prompt||''));
   if(job.taskId)card.append(text('small','魔搭任务编号：'+job.taskId));
   if(job.error)card.append(text('p',job.error));
   if(job.url){const image=document.createElement('img');image.src=job.url;image.alt='魔搭参考图测试结果';image.style.cssText='display:block;max-width:100%;max-height:480px';const download=document.createElement('a');download.href=job.url;download.download='魔搭参考图测试.png';download.textContent='下载测试图';card.append(image,download);}
   if(job.taskId&&job.status!=='ok'&&!['failed','rejected'].includes(job.status)){
    const query=text('button','查询原任务（不重新生成）');query.type='button';query.disabled=busy;query.onclick=()=>queryJob(job.operationId);card.append(query);
   }
   host.append(card);
  }
  if(!state.jobs.length)host.append(text('p','还没有独立测试记录。'));
 }
 function schedule(){
  clearTimeout(poll);poll=null;
  const job=state.jobs.find(j=>j.taskId&&['pending','download_pending'].includes(j.status));
  if(state.enabled&&job&&polls<200)poll=setTimeout(()=>{polls++;queryJob(job.operationId);},3000);
 }
 async function refresh(){state=await request('');render();schedule();}
 async function queryJob(id){
  if(busy)return;busy=true;render();
  try{const job=await request('/query',{operation_id:id});notice(job.status==='ok'?'图片已取回，未重新提交生成。':job.error||'已查询原任务，请等平台完成。');}
  catch(error){notice(error.message);}
  finally{busy=false;await refresh().catch(error=>notice(error.message));}
 }
 $('experiment-enabled').onchange=async()=>{
  if(busy)return;busy=true;const enabled=$('experiment-enabled').checked;clearTimeout(poll);
  try{state=await request('/config',{enabled});notice(enabled?'独立实验已启用，点击生成前不会消耗额度。':'独立实验已关闭；已有测试记录保留。');}
  catch(error){notice(error.message);}finally{busy=false;render();schedule();}
 };
 $('experiment-reference').onchange=()=>{
  const file=$('experiment-reference').files[0];if(preview)URL.revokeObjectURL(preview);
  $('experiment-preview').hidden=!file;if(file){preview=URL.createObjectURL(file);$('experiment-preview').src=preview;}
  operation='';controls();
 };
 $('experiment-prompt').oninput=()=>{operation='';controls();};
 $('experiment-generate').onclick=async()=>{
  if(busy||$('experiment-generate').disabled)return;
  const file=$('experiment-reference').files[0];
  if(!file||file.size>10_000_000||!['image/png','image/jpeg','image/webp'].includes(file.type)){notice('请选择10MB以内的PNG/JPG/WEBP参考图');return;}
  if(!operation||state.jobs.some(job=>job.operationId===operation&&!active(job)))operation=freshId();busy=true;render();notice('正在提交本次单图测试，请勿重复点击…');
  try{
   const reference=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('参考图读取失败'));reader.readAsDataURL(file);});
   const job=await request('/generate',{operation_id:operation,prompt:$('experiment-prompt').value,reference});
   notice(job.error||'已提交一张测试图，正在等待魔搭返回结果。');polls=0;
  }catch(error){notice(error.message);}finally{busy=false;await refresh().catch(error=>notice(error.message));}
 };
 $('experiment-refresh').onclick=()=>refresh().catch(error=>notice(error.message));
 window.addEventListener('pagehide',()=>{clearTimeout(poll);if(preview)URL.revokeObjectURL(preview);});
 refresh().catch(error=>notice(error.message));
})();
