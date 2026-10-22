/* Recover the creation form without submitting tasks or changing providers. */
(function(root){
 'use strict';
 function draftRevision(raw){const value=JSON.parse(raw);delete value.savedAt;return JSON.stringify(value);}
 function referenceIssue({hasReference,source,provider}){
  if(!hasReference)return '';
  if(!['ai','external'].includes(source))return '已选择产品参考图，请把素材来源改为「AI 绘图」，或点「移除参考图」。文案和设置会保留。';
  if(['gpt_image','custom'].includes(provider))return '';
  const name={modelscope:'魔搭',runninghub:'RunningHub',jimeng:'即梦'}[provider]||'当前引擎';
  return '当前接入的内页绘图引擎「'+name+'」只接收文字提示，尚未接通产品参考图编辑。请把上方「绘图引擎」改为全能绘图或支持图片编辑的自定义平台，或移除参考图；封面引擎是独立设置。文案和参数已保留。';
 }
 function createRecovery({initialize,restore,save,shouldRestore=true,schedule=fn=>setTimeout(fn,350),cancel=clearTimeout}){
  let initialized=false,restoring=false,touched=false,timer=null;
  async function flush(){
   if(restoring)return;
   if(!initialized)await ready;
   if(timer!==null){cancel(timer);timer=null;}
   return save();
  }
  function changed(){
   if(restoring)return;
   touched=true;if(!initialized)return;
   if(timer!==null)cancel(timer);
   timer=schedule(()=>{timer=null;return flush();});
  }
  const ready=Promise.resolve(initialize).then(async()=>{
   if(shouldRestore&&!touched){restoring=true;try{await restore();}finally{restoring=false;}}
   initialized=true;if(touched)await flush();
  });
  return {ready,changed,flush};
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={referenceIssue,createRecovery,draftRevision};
 if(!root?.document)return;
 root.app074ReferenceIssue=referenceIssue;
 const fileIds=['prod-file','cover-file','tts-upload-file'];
 const fileIdentities=new WeakMap();
 root.app074DraftAttachments=()=>Object.fromEntries(fileIds.map(id=>[id,Array.from(document.getElementById(id)?.files||[]).map(file=>{
  if(!fileIdentities.has(file))fileIdentities.set(file,root.crypto.randomUUID());
  return {token:fileIdentities.get(file),name:file.name,size:file.size,type:file.type,lastModified:file.lastModified};
 })]));
 let fileStorePromise;
 function fileStore(){
  if(!fileStorePromise)fileStorePromise=new Promise((resolve,reject)=>{
   const request=indexedDB.open('app074-creation-files-v1',1);
   request.onupgradeneeded=()=>request.result.createObjectStore('draft');
   request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  });
  return fileStorePromise;
 }
 async function writeFiles(snapshot){
  const db=await fileStore();
  await new Promise((resolve,reject)=>{const tx=db.transaction('draft','readwrite');tx.objectStore('draft').put(snapshot,'current');tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});
 }
 async function restoreFiles(){
  const db=await fileStore(),snapshot=await new Promise((resolve,reject)=>{const request=db.transaction('draft').objectStore('draft').get('current');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  if(!snapshot||snapshot.revision!==draftRevision(localStorage.getItem(FORM_DRAFT_KEY))){
   if(Object.values(JSON.parse(localStorage.getItem(FORM_DRAFT_KEY)).attachments||{}).some(files=>files.length))throw Error('附件缓存未匹配当前草稿');
   return;
  }
  for(const [id,list] of Object.entries(snapshot.files||{})){
   const input=document.getElementById(id);if(!input||input.files.length||!list.length)continue;
   const transfer=new DataTransfer();for(const file of list)transfer.items.add(file);input.files=transfer.files;
   const identities=JSON.parse(localStorage.getItem(FORM_DRAFT_KEY)).attachments?.[id]||[];
   Array.from(input.files).forEach((file,index)=>{if(identities[index]?.token)fileIdentities.set(file,identities[index].token);});
   // Product preview is local; don't replay the cover uploader while restoring.
   if(id==='prod-file')input.dispatchEvent(new Event('change',{bubbles:true}));
  }
 }
 function updateReferenceNotice(){
  const input=document.getElementById('prod-file'),notice=document.getElementById('prod-compatibility');
  const source=document.querySelector('#img-source .active')?.dataset.imgSrc||'ai';
  const provider=source==='external'?'custom':document.getElementById('img-engine').value;
  const text=referenceIssue({hasReference:!!input.files?.length,source,provider});
  notice.textContent=text;notice.hidden=!text;
 }
 root.updateReferenceNotice=updateReferenceNotice;
 const queries=new URLSearchParams(location.search),plain=[...queries.keys()].every(key=>key==='new');
 const initialize=Promise.all([formSettingsReady,formLibrariesReady,root.taskReuseReady,root.benchmarkTransferReady,
  typeof selectionTransferReady==='undefined'?null:selectionTransferReady]);
 let saveChain=Promise.resolve();
 const controller=createRecovery({initialize,shouldRestore:plain,
  restore:async()=>{
   let saved=false;try{saved=!!localStorage.getItem(FORM_DRAFT_KEY);}catch(_){}
   if(!saved)return;
   await restoreFormDraft();
   try{await restoreFiles();}catch(_){document.getElementById('draft-message').textContent+=' 参考图、封面或配音文件如未恢复，请重新选择；文字参数已保留。';}
   document.getElementById('draft-banner').hidden=false;updateReferenceNotice();
  },
  save:()=>{
   if(queries.has('resume'))return Promise.resolve({textSaved:false,filesSaved:false});
   const textSaved=saveFormDraft({silent:true});
   if(!textSaved)return Promise.resolve({textSaved:false,filesSaved:false});
   const snapshot={revision:draftRevision(localStorage.getItem(FORM_DRAFT_KEY)),files:Object.fromEntries(fileIds.map(id=>[id,Array.from(document.getElementById(id)?.files||[])]))};
   let filesSaved=true;
   saveChain=saveChain.catch(()=>{}).then(()=>writeFiles(snapshot)).catch(()=>{
    filesSaved=false;
    document.getElementById('draft-message').textContent='文案和参数已自动保存；附件缓存失败，重新打开时请核对参考图、封面和配音文件。';
    document.getElementById('draft-banner').hidden=false;
   });
   return saveChain.then(()=>({textSaved,filesSaved}));
  }});
 root.app074FormDraft=controller;root.formDraftReady=controller.ready;
 for(const name of ['input','change','click'])document.addEventListener(name,event=>{
  if(!event.target.closest?.('#task-editor, .footer'))return;
  if(event.isTrusted)controller.changed();
  // Let existing chip/file handlers complete before reading their values.
  queueMicrotask(updateReferenceNotice);
 });
 root.addEventListener('pagehide',()=>{controller.flush().catch(()=>{});});
 controller.ready.then(updateReferenceNotice).catch(()=>{
  document.getElementById('draft-message').textContent='草稿恢复未完成，请勿刷新；可继续修改当前表单或手动恢复草稿。';
  document.getElementById('draft-banner').hidden=false;
 });
})(typeof window==='undefined'?null:window);
