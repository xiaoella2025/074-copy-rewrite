const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.env.APP074_TEST_RESOURCES||process.cwd();
async function fixture(run){
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{const page=await browser.newPage();page.setDefaultTimeout(3000);
  await page.route('**/*',r=>r.fulfill({body:'<html><div id="one"></div><div id="two"></div></html>',contentType:'text/html'}));await page.goto('http://fixture.local/');
  await page.evaluate(()=>{
   window.rows=[{id:'a',number:1,name:'待删除',duration:1},{id:'b',number:2,name:'保留',duration:2}];window.writes=[];window.confirm=()=>true;
   HTMLMediaElement.prototype.pause=function(){};HTMLMediaElement.prototype.load=function(){};
   window.fetch=async(url,options={})=>{
    if(url==='/api/music/delete'){writes.push(JSON.parse(options.body));rows=rows.filter(x=>x.id!==JSON.parse(options.body).id);return{ok:true,json:async()=>({ok:true,retainedFile:true})};}
    if(url==='/api/music/upload'){await new Promise(resolve=>window.releaseUpload=resolve);rows.push({id:'c',number:3,name:'新音乐',duration:1});return{ok:true,json:async()=>({track:rows.at(-1)})};}
    return{ok:true,json:async()=>({tracks:structuredClone(rows)})};
   };
  });
  await page.addScriptTag({path:path.join(root,'assets/bgm_library.js')});
  await page.evaluate(async()=>{window.first=BgmLibrary.mount(document.querySelector('#one'));window.second=BgmLibrary.mount(document.querySelector('#two'));await Promise.all([first.ready,second.ready]);});
  await run(page);
 }finally{await browser.close();}
}
test('delete clears selected row in both mounted pickers and cancellation does not submit',()=>fixture(async page=>{
 await page.locator('#two').getByRole('radio',{name:'待删除',exact:true}).check();
 await page.evaluate(()=>window.confirm=()=>false);await page.locator('#one').getByRole('button',{name:'删除音乐 待删除',exact:true}).click();assert.equal(await page.evaluate(()=>writes.length),0);
 await page.evaluate(()=>window.confirm=()=>true);await page.locator('#one').getByRole('button',{name:'删除音乐 待删除',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('#two input[value="a"]'));
 assert.equal(await page.evaluate(()=>second.value().mode),'none');assert.deepEqual(await page.evaluate(()=>writes),[{id:'a'}]);
 assert.match(await page.locator('#one [role=status]').textContent(),/旧任务引用.*已保留/);
}));
test('refresh received during upload is replayed after successful import',()=>fixture(async page=>{
 await page.locator('#two').getByRole('radio',{name:'待删除',exact:true}).check();
 await page.locator('#two input[type=file]').setInputFiles({name:'new.wav',mimeType:'audio/wav',buffer:Buffer.from('fixture')});
 await page.waitForFunction(()=>typeof releaseUpload==='function');
 await page.locator('#one').getByRole('button',{name:'删除音乐 待删除',exact:true}).click();await page.evaluate(()=>releaseUpload());
 await page.waitForFunction(()=>!document.querySelector('#two input[value="a"]')&&document.querySelector('#two input[value="c"]'));
 assert.equal(await page.locator('#two input[type=radio]').count(),2);assert.equal(await page.evaluate(()=>second.value().id),'c');
}));
