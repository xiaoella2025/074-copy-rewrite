const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('workflow script load failure does not empty model settings and retries loading workflows',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage(),errors=[],writes=[];let workflowScripts=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());if(req.method()!=='GET')writes.push(url.pathname);
   if(url.pathname==='/settings.html')return route.fulfill({path:'settings.html',contentType:'text/html'});
   if(url.pathname==='/assets/rh_workflow_settings.js'&&++workflowScripts===1)return route.abort('failed');
   if(url.pathname.startsWith('/assets/')&&fs.existsSync('.'+url.pathname))return route.fulfill({path:'.'+url.pathname});
   const value=url.pathname==='/api/settings'?{image:{provider:'runninghub'},runninghub:{model:'rh-image-x'},tts:{},asr:{},jianying:{},ima:{},obsidian:{}}:
    url.pathname==='/api/rh-coins-experiment'?{enabled:true,configured:true,preset:'flux-native',candidates:[{key:'flux-native',name:'FLUX 文生图',api_tested:true,api_test_cost:6}],jobs:[]}:{profiles:[]};
   return route.fulfill({json:value});
  });
  await page.goto('http://localhost/settings.html#image');
  await page.waitForFunction(()=>document.querySelector('#rh-models').children.length===3&&document.querySelector('#rhw-workflows').children.length===1,{},{timeout:3000});
  assert.deepEqual(errors,[]);assert.equal(writes.length,0);assert.equal(workflowScripts,2);
 }finally{await browser.close();}
});
