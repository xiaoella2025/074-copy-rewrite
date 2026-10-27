// Cover failure notices follow CoverPosterCard-D4jaNnXf.js (1.24.5).
(function(root){
 const ratios=[['3:4','3:4 封面'],['9:16','9:16 全屏'],['1:1','1:1 方形'],['4:3','4:3 横版'],['16:9','16:9 宽屏']];
 const providers=[['','跟随系统'],['gpt_image','全能绘图'],['runninghub','RunningHub'],['custom_image','自定义'],['modelscope','魔搭'],['jimeng','即梦'],['runninghub_workflow','RH币工作流']];
 const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),v=await r.json();if(!r.ok){const error=Error(v.error||'HTTP '+r.status);error.task_id=v.task_id;throw error;}return v;}
 function failure(error){const text=String(error||'');
  if(/content[_ ]policy|moderation|safety|sensitive|image_generation_user_error|did not (?:follow|pass)|inappropriate|nsfw|unsafe|copyright|trademark|\b(?:4001|2038)\b|违规|敏感|不允许|不通过|政策|审核|违法|侵权|色情|暴力|涉嫌|公众人物|版权|安全策略|安全检测/i.test(text))return {kind:'moderation',title:'封面没出来：触发了绘图平台的内容审核（违规/审核未通过）',body:'可以换一个构图方向，或点「编辑提示词」删掉敏感描述后再出图，也可以换个模板。'};
  if(/超时|timeout|timed out/i.test(text))return {kind:'timeout',title:'封面出图超时',body:'平台排队较久，图可能已经在生成。稍后点「查图」免费取回，不要重新提交或急着重画，重画会再次计费。没有任务编号时请先核对供应商记录。'};
  return {kind:'failed',title:'封面出图失败',body:'请检查绘图设置。有任务编号或已返回结果时，可稍后点「查图」取回；确认上游失败后，再修改提示词或上传本地图。'};
 }
 function render(host,options){
  const {taskId,slot=1,onChanged}=options;let info,busy=false,videoBusy=false,edited=false,showPrompt=false,expanded=false,active=true,refreshing=null,drawnSignature='',notice=null,actionError=null;
  let operationId=root.crypto?.randomUUID?.()||'cover-'+Date.now()+'-'+Math.random().toString(16).slice(2);
  host.replaceChildren(node('p','cover-result-message','正在读取封面…'));
  const base='/api/task-cover/'+encodeURIComponent(taskId);
  async function refresh(force=false){
   if(!active||busy)return;if(refreshing){await refreshing;if(force&&active&&host.isConnected&&!busy&&info)draw();return;}
   refreshing=(async()=>{const next=await api(base+'?slot='+slot);if(!active||!host.isConnected||busy)return;info=next;if(info.job.status==='ok')actionError=null;
    if((force||JSON.stringify(info)!==drawnSignature)&&(force||!host.contains?.(document.activeElement)))draw();
   })();try{await refreshing;}finally{refreshing=null;}
  }
  function readFailure(){if(!active||!host.isConnected)return;host.replaceChildren(node('p','cover-result-message error','读取封面失败，可刷新状态重试。'),button('刷新状态',refreshStatus));}
  async function refreshStatus(){
   if(busy)return;
   try{await refresh(true);await onChanged?.();report('已刷新封面状态。');}
   catch(e){if(!info)readFailure();else report('刷新封面状态失败，请稍后重试。',true);}
  }
  function report(text,error=false){notice={text,error};const p=host.querySelector('.cover-result-message');if(p){p.textContent=text;p.classList.toggle('error',error);}}
  function goRevision(value){if(value?.task_id&&value.task_id!==taskId&&/^[A-Za-z0-9_-]{1,100}$/.test(value.task_id)){root.location.href='/result.html?task='+encodeURIComponent(value.task_id);return true;}return false;}
  async function act(name,body={},changes=false){if(busy)return;busy=true;draw();try{info=await api(base+'/'+name,{slot,...body});if(goRevision(info))return;if(['generate','query','upload'].includes(name)&&info.job.status==='ok'||name==='upload')actionError=null;if(name==='generate')operationId=root.crypto?.randomUUID?.()||'cover-'+Date.now();if(changes&&onChanged){try{await onChanged();}catch(e){report('封面已保存，页面刷新失败，请稍后刷新页面。',true);}}if(host.isConnected){edited=false;draw();report(info.message||(['generate','query','upload'].includes(name)?'封面已更新，已有草稿请点「重新打包」':'已保存'));}}catch(e){if(goRevision(e))return;try{info=await api(base+'?slot='+slot);}catch(_){}if(host.isConnected){if(['generate','query'].includes(name)){actionError=failure(e.message);notice=null;draw();}else report('封面操作失败，请检查输入和设置后重试。',true);}}finally{busy=false;if(host.isConnected)draw();}}
  function button(label,click,disabled=false,primary=false){const b=node('button','btn '+(primary?'btn-primary':'btn-ghost'),label);b.type='button';b.disabled=busy||videoBusy||disabled;b.onclick=click;return b;}
  function chips(label,values,key){const row=node('div','cover-result-chips'),caption=node('span','',label);row.append(caption);for(const [value,text]of values){const b=button(text,()=>{edited=true;act('save',{[key]:value});},false,info[key]===value);b.classList.add('cover-result-chip');row.append(b);}return row;}
  function upload(){const input=node('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.onchange=()=>{const file=input.files[0];if(!file)return;if(file.size>10_000_000){report('封面图片超过10MB',true);return;}const reader=new FileReader();reader.onload=()=>act('upload',{data_url:reader.result},true);reader.onerror=()=>report('读取封面失败',true);reader.readAsDataURL(file);};input.click();}
  function zoom(source){const overlay=node('div','cover-result-zoom'),img=node('img');img.src=source;img.alt='封面海报大图';overlay.tabIndex=-1;const close=()=>overlay.remove();overlay.onclick=close;overlay.onkeydown=e=>{if(e.key==='Escape')close();};overlay.append(img);document.body.append(overlay);overlay.focus();}
  function titleEditor(body){const area=node('div','cover-result-editor'),title=node('textarea'),subs=node('textarea');title.value=info.title;title.rows=2;title.maxLength=200;title.setAttribute('aria-label','封面主标题，可回车换行');subs.value=info.subtitle.join('\n');subs.rows=3;subs.setAttribute('aria-label','副标题，每行一段，可回车换行');area.append(node('label','','封面主标题（可回车换行）'),title,node('label','','副标题（每行一段，可回车换行）'),subs,button('保存',()=>act('save',{title:title.value,subtitle:subs.value.split(/\r?\n/).filter(x=>x.trim())},true)),button('取消',()=>area.remove()));body.prepend(area);title.focus();}
  function templateEditor(body){
   const selected=info.template_snapshot||info.templates.find(t=>t.id===info.template),area=node('div','cover-result-editor cover-template-editor'),fields={};
   for(const[key,label]of [['name','模板名称'],['compositionRule','构图要求'],['titleLayout','主标题排版（{{TITLE}} 表示标题）'],['subtitleLayout','副标题排版（{{SUBTITLE}} 表示副标题）'],['plainHint','不带文字时的画面要求'],['presets','构图预设（每行：名称｜说明）']]){
    const input=node(key==='name'?'input':'textarea');input.setAttribute('aria-label',label);
    input.value=key==='presets'?(selected?.directions||[]).map(d=>d.label+'｜'+d.hint).join('\n'):selected?.[key]||'';
    if(key==='name')input.value+=' · 自定义';fields[key]=input;area.append(node('label','',label),input);
   }
   area.append(node('p','cover-result-hint','保存为可复用的新模板，当前封面保留独立快照；不调用模型、不出图。'),button('保存为新模板',()=>{
    const template={};for(const key of ['name','compositionRule','titleLayout','subtitleLayout','plainHint'])template[key]=fields[key].value;
    template.directions=fields.presets.value.split(/\r?\n/).filter(x=>x.trim()).map(line=>{const at=line.indexOf('｜');return {label:at<0?line:line.slice(0,at),hint:at<0?'':line.slice(at+1)};});
    return act('save-template',{template});
   }),button('取消',()=>area.remove()));body.prepend(area);fields.name.focus();
  }
  async function copy(text){try{await navigator.clipboard.writeText(text);report('已复制');}catch(e){report('复制失败：'+e.message,true);}}
  async function coverMotion(name,body={}){
   if(videoBusy)return;videoBusy=true;draw();
   try{const result=await api('/api/cover-motion/'+encodeURIComponent(taskId)+'/'+slot+'/'+name,body);if(goRevision(result))return null;await refresh();return result;}
   finally{videoBusy=false;if(host.isConnected)draw();}
  }
  function aiCoverVideo(){
   const job=info.imageInfo?.motion?.job||{},restoring=info.imageInfo?.motion?.restoring,continuing=restoring||['pending','unknown','submitting','download_pending'].includes(job.status),request=job.request||{};
   if(continuing)return coverMotion('query',{}).catch(e=>{if(!goRevision(e))report(e.message,true);});
   const videoOperation=root.crypto?.randomUUID?.()||'video-'+Date.now();
   root.app074VideoPrompt?.open({title:'生成封面 AI 图生视频',message:'使用 RunningHub 全能视频 X，消耗钱包余额（不是RH币）。支持的比例沿用分镜视频；3:4、4:3封面的视频使用9:16。只有点击确认才提交生成。生成的封面视频可预览、下载，不替换正片分镜。',initialDurationSec:6,standalone:true,durationHint:'封面独立视频，默认6秒，不跟随正文配音。',
    loadPrompt:async()=> (await api('/api/cover-motion/'+encodeURIComponent(taskId)+'/'+slot+'/prompt',{})).prompt,
    onConfirm:async(prompt,seconds)=>{try{await coverMotion('generate',{operation_id:videoOperation,prompt,duration_sec:seconds,regenerate:['ok','failed'].includes(job.status)});}catch(e){if(!goRevision(e))throw e;}}});
  }
  function galleryDetails(card,pending){
   if(!options.gallery)return;
   const block=node('div','cover-gallery-details'),image=info.imageInfo||{};
   block.append(node('b','','当前图片使用的提示词'),node('pre','cover-gallery-prompt',image.actualPrompt||((image.current||info.cover.url)?'这张封面未保存出图提示词。':'尚无封面图片。')));
   if(image.actualPrompt)block.append(button('复制图片提示词',()=>copy(image.actualPrompt)));
   if(info.prompt&&info.prompt!==image.actualPrompt)block.append(node('b','','当前参数准备出图的提示词'),node('pre','cover-gallery-prompt',info.prompt));
   else if(!image.actualPrompt&&info.lastPrompt)block.append(node('b','','上次保存的提示词（仅供参考）'),node('pre','cover-gallery-prompt',info.lastPrompt));
   if(info.prompt)block.append(button('复制待出图提示词',()=>copy(info.prompt)));
   if(image.provider)block.append(node('small','cover-result-hint','当前图片来源：'+(providers.find(x=>x[0]===image.provider)?.[1]||image.provider)));
   const actions=node('div','wv-gallery-actions');
   if(root.app074SceneImages){for(const [label,name] of [['裁剪','open'],['参考图编辑','reference'],['图片历史','history'],['替换图片','replace']]){
    const disabled=pending&&name!=='reference'||!(image.current||info.cover.url)&&name!=='history';
    actions.append(button(label,()=>root.app074SceneImages[name]({taskId,index:slot,coverSlot:slot,caption:[info.title,...info.subtitle].join('\n'),onChanged:async()=>{await refresh();await onChanged?.();}}).catch(error=>report(error.message,true)),disabled));
   }}
   const videoActions=node('div','cover-gallery-video-actions'),videoJob=image.motion?.job||{},videoPending=['pending','unknown','submitting','download_pending'].includes(videoJob.status);
   videoActions.append(button('生成动画版视频',async()=>{try{await coverMotion('animation',{operation_id:operationId});}catch(e){if(!goRevision(e))report(e.message,true);}},pending||!image.current));
   videoActions.append(button(image.motion?.restoring?'使用已有 AI 视频':videoPending?'继续查询 AI 视频':'生成 AI 图生视频',aiCoverVideo,(!videoPending&&pending)||!image.current||!root.app074VideoPrompt));
   if(image.motion?.result?.video_url){const video=node('video','wv-gallery-video');video.src=image.motion.result.video_url;video.controls=true;video.preload='metadata';videoActions.append(video);const download=node('a','btn btn-ghost','下载封面视频');download.href=video.src;download.download='封面'+slot+'.mp4';videoActions.append(download);}
   block.prepend(actions,videoActions);card.append(block);
  }
  function draw(){
   if(!active||!info)return;drawnSignature=JSON.stringify(info);const previous=notice?.text||'',message=()=>node('p','cover-result-message'+(notice?.error?' error':''),previous);
   host.replaceChildren();const card=node('section','cover-result-card'+(options.gallery?' cover-gallery-tile':'')),head=node('div','cover-result-head'),body=node('div','cover-result-body'+(options.gallery?' cover-gallery-body':''));
   if(info.completed)card.append(node('p','cover-result-message','原任务已完成；修改封面会另建新任务，历史成品保留。'));
   const errorInfo=info.errorInfo||(info.job.error?failure(info.job.error):null)||actionError;
   if(errorInfo){const alert=node('div','cover-result-error cover-result-error-'+errorInfo.kind);alert.setAttribute('role','alert');alert.append(node('b','',errorInfo.title),node('p','',errorInfo.body));card.append(alert);}
   const canQuery=!!(info.job.taskId||info.job.result);
   if(options.gallery){const recovery=node('div','cover-result-head cover-result-recovery');recovery.append(button('查图取回',()=>act('query',{},true),!canQuery),button('刷新状态',refreshStatus),node('small','cover-result-hint',canQuery?'查图只查询原任务并取回图片，不重新生成。':'没有平台任务编号或结果，暂不能查图；可先刷新状态。'));card.append(recovery);}
   const pending=['submitting','unknown','pending','download_pending'].includes(info.job.status)||['submitting','unknown','pending','download_pending'].includes(info.imageInfo?.referenceJob?.status)||['pending','unknown','submitting','download_pending'].includes(info.imageInfo?.motion?.job?.status)||info.imageInfo?.recoveryNeeded,local=['local','upload'].includes(info.mode);
   const imageURL=options.gallery?(info.imageInfo?.current||info.cover.url):info.cover.url;
   const source=imageURL?imageURL+(imageURL.includes('?')?'&':'?')+'v='+(info.cover.updatedAt||Date.now()):'';
   head.append(node('b','',slot===2?'封面海报 · 第二张':'封面海报'),node('span','cover-result-hint',local?'本地上传的封面 · 发布时上传用，已自动带入草稿（不占出图费用）':'发布时上传封面用 · 选好模板/构图方向/标题/比例后点「出图」（一张图费用）'));
   if(info.imageInfo?.recoveryNeeded){head.append(button('恢复封面保存',()=>act('recover',{},true)));card.append(head,node('p','cover-result-message','上次封面保存未完成，点击恢复可取回本地结果，不重新生成。'));host.append(card);return;}
   if(local){
    if(source){const download=node('a','btn btn-ghost','下载');download.href=source;download.download='封面.png';head.append(download);}
    head.append(button('换本地图',upload,pending),button('改用 AI 出图',()=>act('save',{mode:'titled'}),pending||!info.directions.length));
    const thumb=node('div','cover-result-thumb');if(source){const img=node('img');img.src=source;img.alt='本地上传的封面';img.onclick=()=>zoom(source);thumb.append(img);}else thumb.append(node('div','cover-result-empty','本地封面缺失\n点「换本地图」补一张'));
    if(options.gallery)thumb.append(node('small','','封面'+slot+'.png'));body.append(thumb);if(options.gallery)galleryDetails(body,pending);else body.append(node('p','cover-result-hint','这张封面来自本地图片，未使用 AI 出图。想换图点「换本地图」；想让 AI 按模板重新设计，点「改用 AI 出图」。'));
    if(options.gallery){const settings=node('details','cover-gallery-settings');settings.append(node('summary','','封面设置'),head);card.append(body,settings,message());}else card.append(head,body,message());host.append(card);return;
   }
   const provider=node('select');provider.setAttribute('aria-label','封面绘图提供商');for(const[v,t]of providers){const o=node('option','',t);o.value=v;provider.append(o);}provider.value=info.provider;provider.disabled=busy||pending;provider.onchange=()=>act('save',{provider:provider.value});head.append(provider);
   if(info.provider==='runninghub_workflow'){const choice=node('select');choice.setAttribute('aria-label','RH币工作流选择');choice.append(new Option('跟随系统工作流',''));for(const item of info.workflows||[])choice.append(new Option(item.name,item.key));choice.value=info.workflow||'';choice.disabled=busy||pending;choice.onchange=()=>act('save',{workflow:choice.value});head.append(choice);}
   const current=(info.profiles||[]).find(p=>p.id===info.profile_id),model=node('a','btn btn-ghost','文字：跟随系统'+(current?' · '+current.name:''));
   model.href='/settings.html';model.setAttribute('aria-label','封面文字模型（跟随系统）');model.title='到系统设置切换当前模型；下一次文字请求生效';head.append(model);
   if(info.mode==='off'&&!source&&!expanded){head.append(button('生成封面海报',()=>{expanded=true;draw();}));card.append(head,node('p','cover-result-message',previous||'未生成 · 建任务时选了不生成'));galleryDetails(card,pending);host.append(card);return;}
   head.append(button(source?(edited?'重新生成封面（参数已改）':'重新生成封面'):'生成封面',()=>act('generate',{operation_id:operationId}),pending||!info.prompt));
   if(source){const download=node('a','btn btn-ghost','下载');download.href=source;download.download='封面'+(slot===2?'2':'')+'.png';head.append(download);}
   const visiblePrompt=info.prompt||info.lastPrompt||'';
   head.append(button(source?'换本地图':'上传图片',upload,pending),button('编辑提示词',()=>{showPrompt=!showPrompt;draw();}),button('复制提示词',()=>copy(visiblePrompt),!visiblePrompt),button('编辑封面文字',()=>titleEditor(body),pending));
   if(info.job.taskId)head.append(button('复制 TaskID',()=>copy(info.job.taskId)));if(!options.gallery){if(canQuery)head.append(button('查图',()=>act('query',{},true)));head.append(button('刷新状态',refreshStatus));}
   if(!options.gallery)card.append(head);if(showPrompt){const editor=node('div','cover-result-editor'),text=node('textarea'),historical=!info.prompt&&!!info.lastPrompt;text.value=visiblePrompt;text.rows=6;text.readOnly=pending;text.setAttribute('aria-label','完整的封面海报提示词');const submit=button('出图（用修改的提示词）',()=>act('generate',{operation_id:operationId,prompt:text.value}),pending||historical||!visiblePrompt,true);text.oninput=()=>{submit.disabled=busy||pending||!text.value.trim()||(historical&&text.value===visiblePrompt);};editor.append(node('p','',historical?'上次保存的提示词：当前参数已变化，仅供参考。请先在这里改正文字，再明确点击出图；不会自动使用旧词重新生成。':visiblePrompt?'编辑本次出图用的完整提示词（已含画面风格与标题文字指令）。本次一次性，不改动构图方向 / 风格 / 模板设置。':'尚无已保存的提示词。可先生成构图方向，或在这里填写完整提示词。'),node('small','',pending?'封面生成期间可查看、复制，不能修改或再次出图。':'点击出图会提交一次新的生图请求，按所选平台计费；保存封面文字不会直接修改已有图片。'),text,button('取消',()=>{showPrompt=false;draw();}),submit);card.append(editor);}
   const thumb=node('div','cover-result-thumb');if(source){const img=node('img');img.src=source;img.alt='封面海报';img.title='点击放大预览';img.onclick=()=>zoom(source);thumb.append(img);}else thumb.append(node('div','cover-result-empty',pending?'封面生成中…':'未生成\n点上方「生成封面」'));
   const controls=node('div','cover-result-options');controls.append(node('div','cover-result-label','封面模板'));const templates=node('div','cover-result-chips');for(const t of info.templates)templates.append(button(t.name,()=>act('save',{template:t.id}),pending,info.template===t.id));templates.append(button('自定义模板',()=>templateEditor(controls),pending));controls.append(templates,node('div','cover-result-label','构图方向'));
   if(info.directions.length)controls.append(chips('',info.directions.map((d,i)=>[i,info.templates.find(t=>t.id===info.template)?.directions?.[i]?.label||'方向 '+(i+1)]),'direction'));
   controls.append(button('生成构图方向',()=>act('directions'),pending));
   controls.append(chips('标题文字',[[true,'带主/副标题'],[false,'留白']],'withTitle'),chips('比例',ratios,'ratio'),node('p','cover-result-direction',info.directions[info.direction]||''));
   if(options.gallery)thumb.append(node('small','','封面'+slot+'.png'));body.append(thumb);if(options.gallery){galleryDetails(body,pending);const settings=node('details','cover-gallery-settings');settings.append(node('summary','','封面设置与重新生成'),head,controls);card.append(body,settings,message());}else{body.append(controls);card.append(body,message());}host.append(card);
  }
  refresh().catch(readFailure);
  return {refresh:()=>refresh().catch(e=>{if(active&&host.isConnected)report('读取封面失败，请稍后刷新页面。',true);}),dispose:()=>{active=false;}};
 }
 root.app074TaskCover={render};
})(window);

