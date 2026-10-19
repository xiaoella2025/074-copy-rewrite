/* Read existing library images into File objects. No upload, task or library mutations. */
(()=>{
 'use strict';
 const LIMIT=10000000,TYPES=new Set(['image/png','image/jpeg','image/webp']);let active=false;
 const PREFERENCE_KEY='app074:material-picker1250:preferences';let preferences={group:'*',search:''};
 function readPreferences(){try{const stored=JSON.parse(localStorage.getItem(PREFERENCE_KEY));if(stored&&typeof stored==='object')preferences={group:typeof stored.group==='string'?stored.group.slice(0,100):'*',search:typeof stored.search==='string'?stored.search.slice(0,200):''};}catch(_){}return preferences;}
 const node=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
 function safeMaterial(item){
  return item&&/^[a-f0-9]{12}$/.test(item.id)&&typeof item.url==='string'&&
   new RegExp('^/api/material/'+item.id+'\\.(png|jpg|jpeg|webp)$').test(item.url);
 }
 function style(){
  if(document.getElementById('material-picker1250-style'))return;
  const css=node('style');css.id='material-picker1250-style';css.textContent=`
 .material-picker1250{box-sizing:border-box;width:min(780px,94vw);max-height:90vh;padding:20px;border:1px solid var(--border,#555);border-radius:12px;background:var(--bg-elevated,#19191d);color:var(--text,#eee)}
 .material-picker1250::backdrop{background:#000a}.material-picker1250 h2{margin:0 0 14px;font-size:18px}.material-picker1250 .mp-toolbar,.material-picker1250 .mp-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}.material-picker1250 .mp-toolbar label{display:flex;gap:6px;align-items:center;font-size:12px}.material-picker1250 input[type=search]{width:220px;max-width:55vw}.material-picker1250 select{max-width:200px}.material-picker1250 .mp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;max-height:48vh;overflow:auto}.material-picker1250 .mp-card{border:1px solid var(--border,#555);border-radius:8px;overflow:hidden;min-width:0}.material-picker1250 .mp-card:has(input:checked){border-color:var(--brand,#8b5cf6)}.material-picker1250 .mp-card label{display:block;cursor:pointer;padding:8px}.material-picker1250 .mp-card img{display:block;width:100%;height:100px;object-fit:contain;margin-bottom:6px;background:var(--bg,#111)}.material-picker1250 .mp-card span{overflow-wrap:anywhere;font-size:12px}.material-picker1250 .mp-card small{display:block;color:var(--text-muted,#aaa);font-size:11px}.material-picker1250 .mp-card button{margin:0 8px 8px;font-size:11px;padding:4px 6px}.material-picker1250 .mp-status{font-size:12px;min-height:18px;white-space:pre-wrap}.material-picker1250 .mp-count{font-size:12px;color:var(--text-muted,#aaa);margin-right:auto}`;
  document.head.append(css);
 }
 async function request(url,options){const r=await fetch(url,options);if(!r.ok){let message;try{message=(await r.json()).error;}catch(_){}throw Error(message||'读取素材失败');}return r;}
 async function pick({max=3}={}){
  max=Math.max(0,Math.min(3,Math.floor(Number(max)||0)));if(!max)return [];
  if(active)throw Error('素材选择器已打开');active=true;style();
  const dialog=node('dialog',undefined,'material-picker1250');dialog.setAttribute('aria-label','从素材库选择参考图');
  const title=node('h2','从素材库选择参考图'),toolbar=node('div',undefined,'mp-toolbar'),search=node('input'),groups=node('select'),saved=readPreferences();
  search.type='search';search.maxLength=200;search.value=saved.search;search.placeholder='按文件名或素材组搜索';search.setAttribute('aria-label','搜索素材');groups.setAttribute('aria-label','素材组');
  const searchLabel=node('label','搜索素材 '),groupLabel=node('label','素材组 ');searchLabel.append(search);groupLabel.append(groups);toolbar.append(searchLabel,groupLabel);
  const grid=node('div',undefined,'mp-grid'),status=node('p','正在读取素材库…','mp-status');status.setAttribute('role','status');
  const actions=node('div',undefined,'mp-actions'),count=node('span','已选 0 / '+max,'mp-count'),openRoot=node('button','打开素材库文件夹'),cancel=node('button','取消'),confirm=node('button','添加选中');
  for(const b of [openRoot,cancel,confirm])b.type='button';confirm.className='primary';confirm.disabled=true;actions.append(count,openRoot,cancel,confirm);dialog.append(title,toolbar,grid,status,actions);document.body.append(dialog);
  const selected=new Set();let materials=[],reading=false,settled=false,finish;
  const result=new Promise(resolve=>finish=resolve);
  function close(files=[]){if(settled)return;settled=true;dialog.close();dialog.remove();active=false;finish(files);}
  cancel.onclick=()=>{if(!reading)close();};dialog.oncancel=e=>{e.preventDefault();if(!reading)close();};dialog.onclose=()=>{if(!settled)close();};
  async function openFolder(id){try{await request('/api/materials/open-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(id?{material_id:id}:{})});status.textContent='已打开来源文件夹';}catch(error){status.textContent=error.message;}}
  openRoot.onclick=()=>openFolder();
  function update(){count.textContent='已选 '+selected.size+' / '+max;confirm.textContent='添加选中（'+selected.size+'）';confirm.disabled=reading||!selected.size;for(const box of grid.querySelectorAll('input[type=checkbox]'))box.disabled=reading||(!box.checked&&selected.size>=max);}
  function render(){
   const query=search.value.trim().toLocaleLowerCase(),group=groups.value;grid.replaceChildren();
   const visible=materials.filter(item=>(group==='*'||String(item.group||'')===group)&&[item.name,item.filename,item.group].some(value=>String(value||'').toLocaleLowerCase().includes(query)));
   for(const item of visible){
    const card=node('article',undefined,'mp-card'),label=node('label'),box=node('input'),img=node('img'),name=String(item.name||item.filename||item.id);
    box.type='checkbox';box.checked=selected.has(item.id);box.setAttribute('aria-label','选择 '+name);box.onchange=()=>{if(box.checked&&selected.size<max)selected.add(item.id);else{selected.delete(item.id);box.checked=false;}update();};
    img.src=item.url;img.alt=name;img.loading='lazy';label.append(img,box,node('span',name),node('small',item.group||'未分组'));
    const open=node('button','打开来源文件夹');open.type='button';open.onclick=()=>openFolder(item.id);card.append(label,open);grid.append(card);
   }
   if(!visible.length)grid.append(node('p',materials.length?'没有匹配的素材':'素材库暂无可用图片'));
   update();
  }
  function remember(){preferences={group:groups.value,search:search.value.slice(0,200)};try{localStorage.setItem(PREFERENCE_KEY,JSON.stringify(preferences));}catch(_){}}
  search.oninput=groups.onchange=()=>{remember();render();};
  confirm.onclick=async()=>{
   if(reading||!selected.size)return;reading=true;search.disabled=groups.disabled=cancel.disabled=openRoot.disabled=true;for(const b of grid.querySelectorAll('button'))b.disabled=true;update();status.textContent='正在读取选中图片…';
   try{
    const files=[];
    for(const id of selected){
     const item=materials.find(row=>row.id===id);if(!safeMaterial(item))throw Error('素材来源无效');
     if(Number(item.size)>LIMIT)throw Error('请选择10MB以内的图片');
     const response=await request(item.url,{credentials:'same-origin',redirect:'error'});
     const blob=await response.blob();if(!TYPES.has(blob.type)||!blob.size||blob.size>LIMIT)throw Error('素材格式无效，请选择10MB以内PNG/JPG/WEBP图片');
     files.push(new File([blob],String(item.name||item.filename||id).split(/[\\/]/).pop(),{type:blob.type}));
    }
    close(files);
   }catch(error){status.textContent=error.message;}
   finally{reading=false;search.disabled=groups.disabled=cancel.disabled=openRoot.disabled=false;for(const b of grid.querySelectorAll('button'))b.disabled=false;update();}
  };
  dialog.showModal();search.focus();
  (async()=>{try{
   const listing=await(await request('/api/materials')).json();if(settled)return;
   materials=(Array.isArray(listing.materials)?listing.materials:[]).filter(safeMaterial);
   groups.append(new Option('全部素材组','*'));for(const group of new Set(materials.map(item=>String(item.group||''))))groups.append(new Option(group||'未分组',group));
   groups.value=Array.from(groups.options).some(option=>option.value===saved.group)?saved.group:'*';remember();
   status.textContent='最多选择 '+max+' 张 · 每张不超过10MB · PNG / JPG / WEBP';render();
  }catch(error){if(!settled)status.textContent=error.message;}})();
  return result;
 }
 window.MaterialPicker1250=Object.freeze({pick});
})();
