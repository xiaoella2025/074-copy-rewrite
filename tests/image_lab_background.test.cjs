const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('navigate away during generation, restore draft and pending receipt, show completion without a second POST',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();let running=false,done=false,posts=0;const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const p=new URL(route.request().url()).pathname;
   if(p==='/api/image_lab'&&route.request().method()==='POST'){
    posts++;const data=route.request().postDataJSON();assert.equal(data.background,true);assert.match(data.request_id,/^[a-f0-9]{32}$/);running=true;
    return route.fulfill({json:{accepted:true,job_id:'test',items:[]}});
   }
   if(p==='/api/image_lab')return route.fulfill({json:{folder:'offline',items:done?[{id:'result',ok:true,url:'/covers/test.png',prompt:'持久任务',provider:'modelscope',ratio:'9:16'}]:running?[{kind:'lab-job',id:'test',status:'running',prompt:'持久任务',provider:'modelscope',ratio:'9:16'}]:[]}});
   if(p==='/api/settings')return route.fulfill({json:{image:{provider:'gpt_image'},runninghub_workflow:{candidates:[{key:'chosen',name:'新工作流'}]}}});
   if(p.startsWith('/api/'))return route.fulfill({json:{}});
   if(p==='/tasks.html')return route.fulfill({body:'<p>其他页面</p>',contentType:'text/html'});
   if(p.startsWith('/covers/'))return route.fulfill({body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7S0AAAAASUVORK5CYII=','base64'),contentType:'image/png'});
   const file=path.join(process.env.LAB_STATIC_ROOT||process.cwd(),p.slice(1));
   if(fs.existsSync(file))return route.fulfill({body:fs.readFileSync(file),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':p.endsWith('.json')?'application/json':'text/html'});
   return route.abort();
  });
  await page.goto('https://fixture.local/image-lab.html?mode=cover');
  await page.getByRole('button',{name:'刷新进度和结果',exact:true}).waitFor();
  await page.locator('#lab-prompt').fill('持久任务');await page.locator('#lab-title').fill('保留主标题');
  await page.locator('#lab-provider').selectOption('runninghub_workflow');await page.locator('#lab-workflow').selectOption('chosen');
  await page.locator('#lab-reference').setInputFiles({name:'ref.png',mimeType:'image/png',buffer:Buffer.from('fake-reference')});
  await page.locator('#lab-generate').click();await page.waitForFunction(()=>document.querySelector('#lab-notice').textContent.includes('可以切换页面'));
  await page.goto('https://fixture.local/tasks.html');
  await page.goto('https://fixture.local/image-lab.html');
  await page.waitForFunction(()=>document.querySelector('#lab-notice').textContent.includes('可以切换页面'));
  assert.equal(await page.locator('#lab-prompt').inputValue(),'持久任务');
  assert.equal(await page.locator('#lab-title').inputValue(),'保留主标题');
  assert.equal(await page.locator('#lab-provider').inputValue(),'runninghub_workflow');
  assert.equal(await page.locator('#lab-workflow').inputValue(),'chosen');
  assert.equal(await page.locator('.pg-reference-thumb').count(),1);
  assert.equal(await page.locator('#lab-generate').isDisabled(),true);assert.equal(posts,1);
  done=true;await page.waitForFunction(()=>document.querySelector('#lab-results img'));
  assert.equal(await page.locator('#lab-generate').isDisabled(),false);assert.equal(posts,1);
  await page.reload();await page.locator('#lab-results img').waitFor();assert.equal(posts,1);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
