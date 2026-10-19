/* Story 1.25.0 catalog controls. Catalog provenance is stored beside the literals. */
(function () {
 'use strict';
 let uploading = false;
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(text,action)=>{const n=make('button','tpl-card-btn',text);n.type='button';n.onclick=action;return n;};
 const note=(parent,text)=>parent.append(make('div','hint',text));
 const badge=(parent,vip)=>{if(vip)parent.append(make('span','tpl1250-vip','会员'));};
 const apply=(ctx,path,value,redraw=true)=>{ctx.update(path,value);if(redraw)ctx.refresh();};
 function effectiveEffects(image){
  if(Array.isArray(image.effects))return image.effects;
  const legacy=typeof image.effect==='string'?image.effect.trim():'';
  return legacy&&legacy!=='none'?[{name:legacy,mode:'full'}]:[];
 }
 function filterCatalog(catalog,type,filter='recommended',query=''){
  let items=catalog[type]||[];
  // Story searches the entire catalog even when the recommendation tab is active.
  const needle=query.trim().toLocaleLowerCase();
  if(needle)return items.filter(x=>x.name.toLocaleLowerCase().includes(needle));
  if(filter==='free')items=items.filter(x=>!x.vip);
  else if(filter==='vip')items=items.filter(x=>x.vip);
  else if(filter==='recommended'){
   const recommended=type==='fonts'?catalog.recommendedFonts:catalog.recommendedEffects.flatMap(x=>x.items);
   const byName=new Map(items.map(x=>[x.name,x]));items=recommended.map(name=>byName.get(name)).filter(Boolean);
  }
  return items;
 }
 function catalogPicker(parent,{catalog,type,title,onSelect,selected=()=>false,disabled=()=>false}){
  const details=make('details','tpl1250-picker'),summary=make('summary',null,title),body=make('div','tpl1250-picker-body');details.append(summary,body);parent.append(details);
  const search=make('input','tpl1250-search');search.type='search';search.placeholder='搜索名称';search.setAttribute('aria-label',title+'搜索');
  const tabs=make('div','tpl1250-tabs'),status=make('div','hint'),list=make('div','tpl1250-catalog');body.append(search,tabs,status,list);
  let filter='recommended';const tabButtons=[];
  const render=()=>{
   list.replaceChildren();const items=filterCatalog(catalog,type,filter,search.value);
   status.textContent=(search.value.trim()?'搜索全部资源 · ':'')+`${items.length} 项`;
   for(const [value,b] of tabButtons){b.setAttribute('aria-pressed',String(value===filter));b.dataset.variant=value===filter?'primary':'';}
   for(const item of items){const b=button(item.name,()=>onSelect(item));b.dataset[type==='fonts'?'fontName':'effectName']=item.name;b.disabled=disabled(item);b.setAttribute('aria-pressed',String(selected(item)));badge(b,item.vip);list.append(b);}
   if(!items.length)list.append(make('div','hint','没有匹配项'));
  };
  for(const [value,label]of[['recommended','推荐'],['free','免费'],['vip','会员'],['all','全部']]){const b=button(label,()=>{filter=value;render();});tabs.append(b);tabButtons.push([value,b]);}
  search.oninput=render;render();return details;
 }
 function fontPicker(parent,key,ctx){
  const current=ctx.config[key].font||'',line=make('div','tpl1250-selected');line.append(make('span',null,'字体：'+(current||'默认')));badge(line,ctx.catalog.fonts.find(x=>x.name===current)?.vip);parent.append(line);
  parent.append(button('默认字体（清除选择）',()=>apply(ctx,key+'.font','')));
  catalogPicker(parent,{catalog:ctx.catalog,type:'fonts',title:'选择字体',selected:item=>ctx.config[key].font===item.name,onSelect:item=>apply(ctx,key+'.font',item.name)});
  note(parent,'字体名称写入剪映草稿；会员字体导出需要剪映会员。预览仅使用本机已有字体，未安装时显示回退字体。');
 }
 function selectControl(parent,label,value,options,onchange){
  const wrap=make('label','tpl1250-control');wrap.append(make('span',null,label));const select=make('select','tpl-field-input');select.setAttribute('aria-label',label);
  for(const [v,text]of options){const option=make('option',null,text);option.value=v;select.append(option);}select.value=value;select.onchange=()=>onchange(select.value);wrap.append(select);parent.append(wrap);return select;
 }
 function numeric(parent,label,value,min,step,change,{max,type='number',suffix=''}={}){
  const wrap=make('label','tpl1250-control');wrap.append(make('span',null,label));const input=make('input',type==='range'?'tpl-slider':'tpl-field-input');input.type=type;input.min=min;if(max!==undefined)input.max=max;input.step=step;input.value=value;input.setAttribute('aria-label',label);wrap.append(input);
  const display=make('span','hint',value+suffix);if(type==='range')wrap.append(display);
  input.oninput=()=>{if(input.value==='')return;const n=Number(input.value);if(Number.isFinite(n)&&n>=min&&(max===undefined||n<=max)){display.textContent=n+suffix;change(n);}};parent.append(wrap);return input;
 }
 function effectsPanel(parent,ctx){
  const selected=effectiveEffects(ctx.config.image),wrap=make('div','tpl1250-media');wrap.append(make('strong',null,`画面特效 ${selected.length}/3`));parent.append(wrap);
  const change=(index,patch)=>apply(ctx,'image.effects',effectiveEffects(ctx.config.image).map((x,i)=>i===index?{...x,...patch}:x));
  selected.forEach((effect,index)=>{
   const card=make('div','tpl1250-card');card.append(make('strong',null,effect.name));badge(card,ctx.catalog.effects.find(x=>x.name===effect.name)?.vip);
   selectControl(card,effect.name+' 时长',effect.mode,[['full','铺满全片'],['head','仅开头']],mode=>{const patch={mode};if(mode==='head')patch.seconds=effect.seconds??3;change(index,patch);});
   if(effect.mode==='head')numeric(card,effect.name+' 秒数',effect.seconds??3,.5,.5,seconds=>apply(ctx,'image.effects',effectiveEffects(ctx.config.image).map((x,i)=>i===index?{...x,seconds}:x),false));
   card.append(button('移除此特效',()=>apply(ctx,'image.effects',effectiveEffects(ctx.config.image).filter((_,i)=>i!==index))));wrap.append(card);
  });
  const clear=button('清除全部特效',()=>apply(ctx,'image.effects',[]));clear.disabled=!selected.length;wrap.append(clear);
  catalogPicker(wrap,{catalog:ctx.catalog,type:'effects',title:'添加画面特效',selected:item=>effectiveEffects(ctx.config.image).some(x=>x.name===item.name),disabled:item=>effectiveEffects(ctx.config.image).length>=3||effectiveEffects(ctx.config.image).some(x=>x.name===item.name),onSelect:item=>{const current=effectiveEffects(ctx.config.image);if(current.length<3&&!current.some(x=>x.name===item.name))apply(ctx,'image.effects',[...current,{name:item.name,mode:'full'}]);}});
  note(wrap,'最多叠加3个特效，各有独立轨道。雨雪等循环特效可铺满全片；开幕、云雾消散等建议仅开头。会员特效导出需要剪映会员。');
 }
 const readDataUrl=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('读取音效文件失败'));reader.readAsDataURL(file);});
 function soundsPanel(parent,ctx){
  const limit=ctx.catalog.limits.soundEffects,current=()=>ctx.config.audio.soundEffects||[],wrap=make('div','tpl1250-media');wrap.append(make('strong',null,`音效 ${current().length}/${limit}`));parent.append(wrap);
  const change=(index,patch,redraw=true)=>apply(ctx,'audio.soundEffects',current().map((x,i)=>i===index?{...x,...patch}:x),redraw);
  current().forEach((sound,index)=>{
   const label='音效 '+(index+1),card=make('div','tpl1250-card');card.append(make('strong',null,sound.name||'未命名音效'));badge(card,sound.vip);note(card,sound.jianyingId?'剪映音效 · 打开草稿时需联网下载':'本地音效 · 打包时复制到草稿');
   selectControl(card,label+' 放置位置',sound.placement||'start',[['start','开头第N秒'],['every_scene','每次切镜'],['end','片尾']],placement=>{const patch={placement};if(placement==='start')patch.atSeconds=sound.atSeconds??0;if(placement==='every_scene')patch.everyN=sound.everyN??1;change(index,patch);});
   if((sound.placement||'start')==='start')numeric(card,label+' 第几秒',sound.atSeconds??0,0,.5,atSeconds=>change(index,{atSeconds},false));
   if(sound.placement==='every_scene')numeric(card,label+' 每隔几次切镜',sound.everyN??1,1,1,everyN=>change(index,{everyN:Math.floor(everyN)},false));
   const db=sound.volume<=0?-10:Math.round(20*Math.log10(sound.volume??1)*2)/2;
   numeric(card,label+' 音量',db,-10,.5,db=>change(index,{volume:Math.pow(10,db/20)},false),{max:20,type:'range',suffix:'dB'});
   card.append(button('移除此音效',()=>apply(ctx,'audio.soundEffects',current().filter((_,i)=>i!==index))));wrap.append(card);
  });
  const details=make('details','tpl1250-picker');details.append(make('summary',null,'添加剪映音效'));const search=make('input','tpl1250-search');search.type='search';search.placeholder='搜索音效名称';search.setAttribute('aria-label','音效搜索');const list=make('div','tpl1250-catalog');details.append(search,list);wrap.append(details);
  const render=()=>{list.replaceChildren();for(const sound of ctx.catalog.sounds.filter(x=>x.name.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()))){const b=button(sound.name+' · '+sound.duration+'秒',()=>{if(current().length<limit&&!uploading)apply(ctx,'audio.soundEffects',[...current(),{path:'',jianyingId:sound.id,duration:sound.duration,vip:sound.vip,name:sound.name,volume:1,placement:'start',atSeconds:0}]);});b.dataset.soundId=sound.id;b.disabled=current().length>=limit||uploading;badge(b,sound.vip);list.append(b);}if(!list.children.length)list.append(make('div','hint','没有匹配音效'));};search.oninput=render;render();
  const file=make('input');file.type='file';file.multiple=true;file.hidden=true;file.accept=ctx.catalog.soundExtensions.map(x=>'.'+x).join(',');file.setAttribute('aria-label','选择本地音效文件');
  const upload=button(uploading?'正在上传音效…':'上传本地音效（可多选）',()=>file.click());upload.disabled=current().length>=limit||uploading;wrap.append(upload,file);
  file.onchange=async()=>{
   if(uploading)return;const files=Array.from(file.files||[]);if(!files.length)return;
   if(files.length>limit-current().length){ctx.error(Error(`最多添加${limit}个音效，请减少所选文件`));return;}
   uploading=true;ctx.refresh();let failure;
   try{for(const item of files){
    if(!ctx.catalog.soundExtensions.includes(item.name.split('.').pop().toLowerCase()))throw Error('不支持的音效格式：'+item.name);
    const response=await fetch('/api/template-sound/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:item.name,data_url:await readDataUrl(item)})});
    const result=await response.json();if(!response.ok)throw Error(result.error||'上传音效失败');
    if(!result.path||!result.name)throw Error('上传接口未返回音效路径和名称');
    apply(ctx,'audio.soundEffects',[...current(),{path:result.path,name:result.name,volume:1,placement:'start',atSeconds:0}],false);
   }}catch(e){failure=e;}finally{uploading=false;ctx.refresh();if(failure)ctx.error(failure);}
  };
  note(wrap,`最多${limit}条，可重复选择同一音效并分别设置位置。「每次切镜」从第2个分镜起按间隔触发；片尾音效贴合末尾。剪映音效需联网下载，会员资源导出需会员。`);
 }
 window.DraftMedia1250={effectiveEffects,filterCatalog,fontPicker,effectsPanel,soundsPanel,isUploading:()=>uploading};
})();
