const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.env.APP074_TEST_RESOURCES||process.cwd();
async function fixture(run){
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://fixture.local/initial',r=>r.fulfill({body:'<html><body><div id="host"></div></body></html>',contentType:'text/html'}));
  await page.goto('http://fixture.local/initial');
  for(const asset of ['workflow_view.css','bgm_library.css'])await page.addStyleTag({path:path.join(root,'assets',asset)});
  await page.evaluate(()=>{
   window.coverInfo={title:'隔离测试',subtitle:[],template:'cinematic-poster',templates:[{id:'cinematic-poster',name:'电影海报',directions:[{label:'方向一'}]}],directions:['窗前'],direction:0,ratio:'9:16',withTitle:true,mode:'titled',cover:{},prompt:'隔离提示词',provider:'modelscope',job:{}};
   window.detail={info:{task_id:'isolated_polling',title:'隔离测试',completed_steps:[0,1,2,5,3,4],queue:{status:'pausing',stage:'cover'},progress:{step:'6',status:'pausing'}},steps:{rewrite:'完整正文',meta:{title:'隔离测试'},shots:[],images:[]},client_config:{generate:{},tts:{},image:{provider:'modelscope'},cover:{mode:'title',provider:''}}};
   window.calls=[];window.fetch=async(url,opts={})=>{calls.push({url,body:opts.body?JSON.parse(opts.body):null});if(url.startsWith('/api/task-cover/')){if(opts.body)Object.assign(coverInfo,JSON.parse(opts.body));return{ok:true,json:async()=>structuredClone(coverInfo)};}return{ok:true,json:async()=>structuredClone(detail)};};
   window.alerts=[];window.alert=s=>alerts.push(s);
  });
  for(const asset of ['bgm_library.js','task_cover.js','workflow_view.js'])await page.addScriptTag({path:path.join(root,'assets',asset)});
  await run(page);assert.deepEqual(errors,[]);
 }finally{await browser.close();}
}

test('polling preserves the cover selector and unsaved prompt while progress changes',()=>fixture(async page=>{
 await page.evaluate(()=>{window.view=WorkflowView.mount(document.getElementById('host'),{});view.renderTask(detail);});
 await page.getByRole('combobox',{name:'封面绘图提供商'}).waitFor();
 await page.getByRole('button',{name:'编辑提示词',exact:true}).click();
 await page.getByRole('textbox',{name:'完整的封面海报提示词'}).fill('正在编辑的提示词');
 await page.evaluate(()=>{window.originalSelect=document.querySelector('[aria-label="封面绘图提供商"]');for(let i=0;i<20;i++){detail.info.elapsed_sec=i;detail.steps.shots=[{idx:1,text:'新到达的分镜 '+i}];view.renderTask(structuredClone(detail));}});
 assert.equal(await page.evaluate(()=>originalSelect.isConnected&&originalSelect===document.querySelector('[aria-label="封面绘图提供商"]')),true);
 assert.equal(await page.getByRole('textbox',{name:'完整的封面海报提示词'}).inputValue(),'正在编辑的提示词');
 assert.equal(await page.evaluate(()=>calls.filter(c=>c.url.startsWith('/api/task-cover/')&&!c.body).length),1);
}));

test('cover engine save survives subsequent polls and clears explicitly to follow system',()=>fixture(async page=>{
 await page.evaluate(()=>{detail.info.queue.status='paused';window.view=WorkflowView.mount(document.getElementById('host'),{});view.renderTask(detail);});
 const select=page.getByRole('combobox',{name:'封面绘图提供商'});await select.selectOption('runninghub');
 await page.waitForFunction(()=>document.querySelector('[aria-label="封面绘图提供商"]').disabled===false);
 await page.evaluate(()=>{for(let i=0;i<10;i++)view.renderTask(structuredClone(detail));});
 assert.equal(await select.inputValue(),'runninghub');
 await select.selectOption('');await page.waitForFunction(()=>document.querySelector('[aria-label="封面绘图提供商"]').disabled===false);
 assert.equal(await select.inputValue(),'');
 assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.url.endsWith('/save')).map(c=>c.body.provider)),['runninghub','']);
}));

test('gallery query and refresh stay visible outside collapsed settings and never generate',()=>fixture(async page=>{
 await page.evaluate(()=>{
  coverInfo.job={status:'pending',taskId:'existing-platform-task',error:'poll timed out'};
  window.fetch=async(url,opts={})=>{
   calls.push({url,body:opts.body?JSON.parse(opts.body):null});
   if(url.endsWith('/query')){coverInfo.job={status:'ok',taskId:'existing-platform-task'};coverInfo.cover={url:'/retrieved.png'};}
   return{ok:true,json:async()=>structuredClone(coverInfo)};
  };
  window.cover=app074TaskCover.render(document.getElementById('host'),{taskId:'isolated_polling',gallery:true});
 });
 await page.getByRole('button',{name:'查图取回',exact:true}).waitFor({state:'visible',timeout:3000});
 assert.equal(await page.locator('details[open]').count(),0);
 await page.getByRole('button',{name:'查图取回',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('img[alt="封面海报"]')?.src.includes('retrieved.png'));
 await page.evaluate(()=>{coverInfo.cover.url='/refreshed.png';});
 await page.getByRole('button',{name:'刷新状态',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('img[alt="封面海报"]')?.src.includes('refreshed.png'));
 assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.body).map(c=>c.url)),['/api/task-cover/isolated_polling/query']);
}));

test('paused unfinished cover and draft editor saves then resumes without destructive rerun',()=>fixture(async page=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
 const writes=[],alerts=[];
 await page.exposeFunction('recordWrite',value=>writes.push(value));
 await page.exposeFunction('recordAlert',value=>alerts.push(value));
 await page.evaluate(html=>{
  detail.info.queue.status='paused';detail.client_config.image.templateId='default-portrait-9-16';window.creationForm=html;
  window.fetch=async(url,opts={})=>{calls.push({url,body:opts.body?JSON.parse(opts.body):null});return{ok:true,text:async()=>creationForm,json:async()=>url==='/api/templates/drafts'?{templates:[]}:structuredClone(detail)};};
  window.api=async(url,method,body)=>{await recordWrite({url,body});if(url.endsWith('/config'))detail.client_config=body;return{};};
  window.alert=value=>recordAlert(value);
 },html);
 await page.addScriptTag({path:path.join(root,'assets/workflow_actions.js')});
 await page.evaluate(()=>openStepEditor('isolated_polling','6'));
 const save=page.getByRole('button',{name:'保存并从断点续跑',exact:true});assert.equal(await save.count(),1);
 await page.locator('[data-host="cover.provider"] select').selectOption('runninghub');
 // Capture navigation while retaining the real save/confirm sequence.
 await page.route('**/result.html?task=isolated_polling',r=>r.fulfill({body:'<html>resumed</html>',contentType:'text/html'}));
 await save.click();
 await page.waitForURL('**/result.html?task=isolated_polling');
 assert.deepEqual(alerts,[]);
 assert.equal(writes[0].body.cover.provider,'runninghub');
 assert.deepEqual(writes.map(c=>({url:c.url,from_step:c.body.from_step})),[
  {url:'/api/task/isolated_polling/config',from_step:undefined},{url:'/api/task/isolated_polling/confirm',from_step:undefined}
 ]);
}));
