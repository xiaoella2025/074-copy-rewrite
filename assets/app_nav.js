/* One fixed primary navigation for every 074 page. */
(() => {
const groups = [
[['queue','☷','任务队列','/tasks.html'],['active','◐','进行中','/tasks.html?filter=active'],['history','◷','历史任务','/tasks.html?filter=done']],
[['image','◇','画图实验室','/image-lab.html'],['tts','♫','配音实验室','/voice-lab.html'],['materials','▧','素材库','/library.html?type=materials']],
[['copy','✎','文案工作台','/workbench.html'],['cover','▧','封面海报','/image-lab.html?mode=cover'],['prompts','✦','提示词模板','/library.html?type=prompts'],['drafts','▤','草稿模板','/library.html?type=drafts']]
];
const host=document.getElementById('app-nav');
const brand=document.createElement('div');brand.className='app-nav-brand';brand.innerHTML='<span class="app-nav-logo">07</span><span><b>app074</b><small>图文创作工作台</small></span>';host.append(brand);
function link(key,icon,name,href){const a=document.createElement('a');a.className='app-nav-link';a.dataset.nav=key;if(['queue','history'].includes(key))a.dataset.side=key;a.href=href;const i=document.createElement('span');i.className='app-nav-icon';i.textContent=icon;const text=document.createElement('span');text.textContent=name;a.append(i,text);return a;}
const create=link('new','＋','新建任务','/index.html');create.classList.add('app-nav-new');host.append(create);
for(const entries of groups){const group=document.createElement('div');group.className='app-nav-group';for(const entry of entries)group.append(link(...entry));host.append(group);}
const bottom=document.createElement('div');bottom.className='app-nav-bottom';bottom.append(link('settings','⚙','系统设置','/settings.html'));host.append(bottom);
function active(){const q=new URLSearchParams(location.search),page=location.pathname;let key='new';if(page.endsWith('tasks.html')){const f=q.get('filter');key=f==='done'?'history':f==='active'?'active':'queue';}else if(page.endsWith('result.html'))key='history';else if(page.endsWith('image-lab.html'))key=q.get('mode')==='cover'?'cover':'image';else if(page.endsWith('workbench.html'))key='copy';else if(page.endsWith('voice-lab.html'))key='tts';else if(page.endsWith('settings.html'))key='settings';else if(page.endsWith('template-editor.html'))key='drafts';else if(page.endsWith('prompt-editor.html'))key='prompts';else if(page.endsWith('library.html'))key=q.get('type')||'drafts';else if(location.hash)key={'#reference-section':'copy','#image-section':'image','#tts-section':'tts','#cover-section':'cover'}[location.hash]||'new';for(const a of host.querySelectorAll('[data-nav]')){a.classList.toggle('active',a.dataset.nav===key);if(a.dataset.nav===key)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');}}
active();window.addEventListener('hashchange',active);
const bar=document.createElement('div');bar.id='app-nav-titlebar';bar.textContent='▣　app074 · 图文创作';document.body.prepend(bar);
document.body.dataset.appPage=location.pathname.split('/').pop()||'index.html';
})();
