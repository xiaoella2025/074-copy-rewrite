const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7S0AAAAASUVORK5CYII=','base64');
const metadata={title:'旧桥新生',short_title:'村民修旧桥',summary:'村民用旧木料修桥，保留记忆也改善出行。',tags:['#旧桥','#木料'],comments:['雨天旧木桥面怎么防滑？','村民一起修桥的细节很打动我','保留旧木料也留住了记忆','修桥后推车过河方便多了','这座桥以后由谁来维护？']};
async function screenshot(page,name){if(!process.env.STORY1250_SCREENSHOTS)return;const directory=path.resolve(process.env.STORY1250_SCREENSHOTS);fs.mkdirSync(directory,{recursive:true});await page.screenshot({path:path.join(directory,name+'.png'),fullPage:true});}
async function fixture(run,{history=[],materials=[],holdGeneration=false,holdImage=false,holdListing=false,oversizedImage=false}={}){
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();page.setDefaultTimeout(1800);const writes=[],errors=[];let releaseGeneration,releaseImage,releaseListing;
  const generationGate=new Promise(r=>releaseGeneration=r),imageGate=new Promise(r=>releaseImage=r),listingGate=new Promise(r=>releaseListing=r);
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
   const p=new URL(route.request().url()).pathname;
   if(route.request().method()==='POST'){
    writes.push({path:p,body:route.request().postDataJSON()});
    if(p==='/api/image_lab/delete'){const index=history.findIndex(item=>item.id===route.request().postDataJSON().id);if(index>=0)history.splice(index,1);return route.fulfill({json:{ok:true}});}
    if(p==='/api/image_lab'){if(holdGeneration)await generationGate;return route.fulfill({json:{items:[{id:'fresh',mode:'cover',ok:true,url:'/covers/fake.png',title:metadata.title,prompt:'封面构图',provider:'gpt_image',ratio:'3:4',metadata}]}});}
    return route.fulfill({json:{ok:true}});
   }
   if(p==='/api/materials'){if(holdListing)await listingGate;return route.fulfill({json:{materials,groups:[{name:'旧桥',count:materials.length}]}});}
   if(p.startsWith('/api/material/')){if(holdImage)await imageGate;return route.fulfill({body:oversizedImage?Buffer.alloc(10000001):Buffer.concat([png,Buffer.from(p)]),contentType:p.endsWith('.webp')?'text/html':'image/png'});}
   if(p==='/api/settings')return route.fulfill({json:{image:{provider:'gpt_image'}}});
   if(p==='/api/image_lab')return route.fulfill({json:{items:history,folder:'isolated'}});
   if(p.startsWith('/api/'))return route.fulfill({json:{}});
   if(p.startsWith('/covers/'))return route.fulfill({body:png,contentType:'image/png'});
   const file=path.join(root,p.slice(1));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':p.endsWith('.json')?'application/json':'text/html'});
   return route.abort();
  });
  await page.addInitScript(()=>{window.copied=[];Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>copied.push(text)}});});
  await page.goto('https://fixture.local/image-lab.html?mode=cover');await page.waitForFunction(()=>document.querySelector('#lab-provider').options.length>0);
  await run(page,writes,{releaseGeneration,releaseImage,releaseListing});assert.deepEqual(errors,[]);
 }finally{await browser.close();}
}
test('next cover confirms once, clears composition and references, preserves controls and generated history',()=>fixture(async(page,writes)=>{
 await page.locator('#lab-prompt').fill('村民用旧木料修桥');await page.locator('#lab-generate').click();await page.locator('.lab-item').waitFor();
 await page.locator('#lab-title').fill('自定义主标题');await page.locator('#lab-subtitle').fill('副标题');
 await page.locator('#lab-reference').setInputFiles({name:'ref.png',mimeType:'image/png',buffer:png});
 await page.getByRole('button',{name:'16:9 · 横屏',exact:true}).click();await page.getByRole('button',{name:'2K · 质量更高',exact:true}).click();await page.locator('#lab-count').fill('2');
 let confirmations=0;page.on('dialog',d=>{confirmations++;d.accept();});
 await page.locator('#lab-next-cover').click();assert.equal(confirmations,1);
 for(const id of ['lab-prompt','lab-title','lab-subtitle'])assert.equal(await page.locator('#'+id).inputValue(),'');
 assert.equal(await page.locator('.pg-reference-thumb').count(),0);assert.equal(await page.locator('.lab-item').count(),1);
 assert.equal(await page.locator('#lab-count').inputValue(),'2');assert.equal(await page.locator('#lab-provider').inputValue(),'gpt_image');
 assert.equal(await page.getByRole('button',{name:'16:9 · 横屏',exact:true}).getAttribute('aria-pressed'),'true');assert.equal(await page.getByRole('button',{name:'2K · 质量更高',exact:true}).getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('#lab-modes [data-mode=cover]').getAttribute('aria-selected'),'true');assert.equal(await page.locator('#lab-publication').isVisible(),false);assert.equal(writes.length,1);
}));
test('next cover cancellation preserves text; generation blocks reset',()=>fixture(async(page,writes,{releaseGeneration})=>{
 await page.locator('#lab-prompt').fill('保留原文');page.once('dialog',d=>d.dismiss());await page.locator('#lab-next-cover').click();assert.equal(await page.locator('#lab-prompt').inputValue(),'保留原文');
 await page.locator('#lab-generate').click();assert.equal(await page.locator('#lab-next-cover').isDisabled(),true);releaseGeneration();await page.locator('.lab-item').waitFor();
},{holdGeneration:true}));

test('editing the composition during generation keeps returned publication in history only',()=>fixture(async(page,writes,{releaseGeneration})=>{
 await page.locator('#lab-prompt').fill('第一篇：村民用旧木料修桥');await page.locator('#lab-generate').click();
 await page.locator('#lab-prompt').fill('第二篇：为图书馆选择新书');releaseGeneration();
 await page.locator('.lab-item').waitFor();
 assert.equal(await page.locator('#lab-prompt').inputValue(),'第二篇：为图书馆选择新书');
 assert.equal(await page.locator('#lab-publication').isVisible(),false);
 assert.match(await page.locator('.lab-publication-history').textContent(),/旧木料/);
 assert.equal(await page.locator('.lab-publication-history li').count(),5);assert.equal(writes.length,1);
},{holdGeneration:true}));
test('publication panel copies summary and tags from returned metadata without another request; history keeps comments',()=>fixture(async(page,writes)=>{
 await page.locator('#lab-prompt').fill('村民用旧木料修桥');await page.locator('#lab-generate').click();await page.locator('#lab-publication').waitFor();
 await page.locator('#lab-publication summary').click();assert.match(await page.locator('#lab-publication').textContent(),/旧木料/);assert.equal(await page.locator('#lab-publication li').count(),5);
 await screenshot(page,'lab1250-publication');
 await page.locator('#lab-publication').getByRole('button',{name:'复制简介＋标签',exact:true}).click();assert.equal(await page.evaluate(()=>copied.at(-1)),metadata.summary+'\n\n#旧桥 #木料');
 assert.equal(writes.length,1);await page.reload();
 assert.equal(await page.locator('.lab-publication-history li').count(),5);
},{history:[{id:'old',mode:'cover',ok:true,url:'/covers/fake.png',prompt:'旧构图',provider:'gpt_image',ratio:'3:4',metadata}]}));
test('each publication field and every comment copies independently without extra generation requests',()=>fixture(async(page,writes)=>{
 await page.locator('#lab-prompt').fill('村民用旧木料修桥');await page.locator('#lab-generate').click();const panel=page.locator('#lab-publication');await panel.locator('summary').click();
 for(const [name,text] of [['复制短标题',metadata.short_title],['复制简介',metadata.summary],['复制标签','#旧桥 #木料'],['复制全部评论',metadata.comments.join('\n')],...metadata.comments.map((text,i)=>['复制评论 '+(i+1),text])]){
  await panel.getByRole('button',{name,exact:true}).click();assert.equal(await page.evaluate(()=>copied.at(-1)),text);
 }
 assert.equal(writes.length,1);await screenshot(page,'lab1250-publication-fields');
}));
test('failed-card delete stays visible at 220px and removes only that failed history record',()=>fixture(async(page,writes)=>{
 const failed=page.locator('.lab-item').filter({hasText:'离线模拟失败'});await failed.evaluate(node=>node.style.width='220px');const remove=failed.getByRole('button',{name:'删除失败记录',exact:true});await remove.waitFor();
 await failed.locator('.lab-publication summary').click();
 const [cardBounds,buttonBounds]=await Promise.all([failed.boundingBox(),remove.boundingBox()]);assert.ok(buttonBounds.x>=cardBounds.x&&buttonBounds.x+buttonBounds.width<=cardBounds.x+cardBounds.width);assert.ok(buttonBounds.y+buttonBounds.height<=cardBounds.y+cardBounds.height);assert.equal(await failed.evaluate(node=>node.scrollWidth<=node.clientWidth),true);
 await screenshot(page,'lab1250-failed-card');
 await remove.click();await page.waitForFunction(()=>document.querySelectorAll('.lab-item').length===1);assert.deepEqual(writes,[{path:'/api/image_lab/delete',body:{id:'a'.repeat(32)}}]);await page.reload();assert.equal(await page.locator('.lab-item').count(),1);assert.match(await page.locator('.lab-item').textContent(),/保留成功图片/);
},{history:[{id:'a'.repeat(32),ok:false,error:'离线模拟失败'.repeat(10),provider:'gpt_image',ratio:'3:4',metadata},{id:'b'.repeat(32),ok:true,url:'/covers/fake.png',prompt:'保留成功图片',provider:'gpt_image',ratio:'3:4'}]}));
test('material picker remembers group and search across reopen/reload, forgets selection, and falls back when group disappears',async()=>{
 const library=[{id:'a'.repeat(12),name:'桥.png',group:'旧桥',url:'/api/material/'+('a'.repeat(12))+'.png',size:png.length}];
 await fixture(async(page,writes)=>{
  const open=async()=>{await page.locator('#lab-reference-library').click();const dialog=page.locator('dialog.material-picker1250');await dialog.getByLabel('素材组',{exact:true}).locator('option').first().waitFor({state:'attached'});return dialog;};
  let dialog=await open();await dialog.getByLabel('素材组',{exact:true}).selectOption('旧桥');await dialog.getByLabel('搜索素材',{exact:true}).fill('桥');await dialog.getByRole('checkbox').check();await dialog.getByRole('button',{name:'取消',exact:true}).click();
  dialog=await open();assert.equal(await dialog.getByLabel('素材组',{exact:true}).inputValue(),'旧桥');assert.equal(await dialog.getByLabel('搜索素材',{exact:true}).inputValue(),'桥');assert.equal(await dialog.getByRole('checkbox').isChecked(),false);await dialog.getByRole('button',{name:'取消',exact:true}).click();
  await page.reload();dialog=await open();assert.equal(await dialog.getByLabel('素材组',{exact:true}).inputValue(),'旧桥');assert.equal(await dialog.getByLabel('搜索素材',{exact:true}).inputValue(),'桥');await dialog.getByRole('button',{name:'取消',exact:true}).click();
  library[0].group='新组';dialog=await open();assert.equal(await dialog.getByLabel('素材组',{exact:true}).inputValue(),'*');assert.equal(await dialog.getByLabel('搜索素材',{exact:true}).inputValue(),'桥');assert.equal(await dialog.getByRole('checkbox').isChecked(),false);
  const preferences=await page.evaluate(()=>JSON.parse(localStorage.getItem('app074:material-picker1250:preferences')));assert.deepEqual(preferences,{group:'*',search:'桥'});assert.equal(writes.length,0);
 },{materials:library});
});
test('material picker filters by group/search, honors remaining slots, and opens only selected source folder',()=>fixture(async(page,writes)=>{
 await page.locator('#lab-reference').setInputFiles({name:'ref.png',mimeType:'image/png',buffer:png});
 await page.locator('#lab-reference-library').click();const dialog=page.locator('dialog.material-picker1250');await dialog.waitFor();
 await dialog.getByLabel('素材组',{exact:true}).selectOption('旧桥');await dialog.getByLabel('搜索素材',{exact:true}).fill('桥');
 const choices=dialog.getByRole('checkbox');assert.equal(await choices.count(),3);await choices.nth(0).check();await choices.nth(1).check();assert.equal(await choices.nth(2).isDisabled(),true);
 await screenshot(page,'lab1250-material-picker');
 await dialog.getByRole('button',{name:'打开来源文件夹',exact:true}).first().click();assert.deepEqual(writes[0],{path:'/api/materials/open-folder',body:{material_id:'aaaaaaaaaaaa'}});
 await dialog.getByRole('button',{name:/添加选中/}).click();await page.waitForFunction(()=>document.querySelectorAll('.pg-reference-thumb').length===3);assert.equal(await page.locator('#lab-reference-library').isDisabled(),true);
},{materials:['a','b','c'].map((x,i)=>({id:x.repeat(12),name:`桥${i}.png`,group:'旧桥',url:`/api/material/${x.repeat(12)}.png`,size:png.length}))}));
test('material picker rejects external URLs and invalid MIME without mutating tasks; reading blocks reset',()=>fixture(async(page,writes,{releaseImage})=>{
 await page.locator('#lab-reference-library').click();const dialog=page.locator('dialog.material-picker1250');await dialog.getByRole('checkbox').first().waitFor();assert.equal(await dialog.getByRole('checkbox').count(),1);
 await dialog.getByRole('checkbox').check();await dialog.getByRole('button',{name:/添加选中/}).click();assert.equal(await page.locator('#lab-next-cover').isDisabled(),true);releaseImage();
 await dialog.getByRole('status').filter({hasText:'格式'}).waitFor();assert.equal(await page.locator('.pg-reference-thumb').count(),0);assert.equal(writes.length,0);
},{holdImage:true,materials:[{id:'aaaaaaaaaaaa',name:'invalid.webp',group:'旧桥',url:'/api/material/aaaaaaaaaaaa.webp',size:10},{id:'bbbbbbbbbbbb',name:'external.png',url:'https://attacker.invalid/x.png',size:10}]}));
test('material picker checks actual oversized response even when listing size is small',()=>fixture(async(page,writes)=>{
 await page.locator('#lab-reference-library').click();const dialog=page.locator('dialog.material-picker1250');await dialog.getByRole('checkbox').waitFor();await dialog.getByRole('checkbox').check();await dialog.getByRole('button',{name:/添加选中/}).click();await dialog.getByRole('status').filter({hasText:/素材格式无效.*10MB/}).waitFor();assert.equal(await page.locator('.pg-reference-thumb').count(),0);assert.equal(writes.length,0);
},{oversizedImage:true,materials:[{id:'aaaaaaaaaaaa',name:'too-big.png',url:'/api/material/aaaaaaaaaaaa.png',size:10}]}));
test('material picker cancellation releases lab before a slow listing resolves',()=>fixture(async(page,writes,{releaseListing})=>{
 try{await page.locator('#lab-reference-library').click();await page.locator('dialog.material-picker1250').getByRole('button',{name:'取消',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#lab-next-cover').disabled);assert.equal(await page.locator('.pg-reference-thumb').count(),0);assert.equal(writes.length,0);}finally{releaseListing();}
},{holdListing:true}));
