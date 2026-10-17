const test=require('node:test'),assert=require('node:assert/strict');
const {fixture}=require('./benchmark_batch_fixture.cjs');
test('reload reads original backend batch even with no visible feeds',async()=>{
 const a=fixture();a.select();await a.batch.run('download');assert.equal(a.calls.length,1);
 const b=fixture(a.shared);b.batch.sync(a.shared.jobs);b.show([]);
 assert.equal(b.batch.running,true);assert.equal(b.root.hidden,false);assert.match(b.root.children.map(x=>x.textContent||'').join(' '),/下载.*0\/1/);
 assert.equal(b.calls.length,0);
});
test('lost reply and failed readback persist the request and retry same id and identities',async()=>{
 const a=fixture();a.select();a.loseReply();a.failRead();await a.batch.run('promo');
 const b=fixture(a.shared);b.show([]);const retry=b.root.children.find(x=>x.textContent==='重试提交同一批次');assert.ok(retry);await retry.onclick();
 assert.equal(a.calls[0].data.id,b.calls[0].data.id);assert.deepEqual(a.calls[0].data.items,b.calls[0].data.items);assert.equal(a.shared.jobs.length,1);
});
test('sync errors do not cancel or restart the backend and stop/resume use controls only',async()=>{
 const f=fixture();f.select(f.feeds[1]);await f.batch.run('extract');f.failRead();await f.batch.stop();
 assert.equal(f.batch.running,true);assert.equal(f.calls.at(-1).path,'/api/benchmark/batch-control');assert.equal(f.calls.at(-1).data.action,'stop');
 f.shared.jobs[0].status='interrupted';f.batch.sync(f.shared.jobs);f.show([]);assert.ok(f.root.children.some(x=>x.textContent==='继续未完成项'));
 await f.batch.resume('a'.repeat(32));assert.equal(f.calls.at(-1).data.action,'resume');assert.equal(f.calls.filter(x=>x.path.endsWith('batch-start')).length,1);
});
test('export actions only run on click and row failures remain visible',()=>{
 const f=fixture();f.batch.sync([{id:'b'.repeat(32),kind:'download',status:'completed',rows:[{...f.feeds[0],status:'succeeded',result:{path:'/fixture/document.md',download_url:'/fixture'}},{...f.feeds[1],status:'failed',error:'fixture validation failed',result:{}}]}]);f.show([]);
 assert.equal(f.downloads.length,0);assert.match(f.root.children.map(x=>x.textContent||'').join(' '),/成功 1.*失败 1/);
 const open=f.root.children.flatMap(x=>[x,...(x.children||[])]).find(x=>x.textContent==='文案 1 · 显示文件位置');assert.ok(open);open.onclick();assert.equal(f.downloads.length,1);
});
test('polling preserves an expanded result panel',()=>{
 const f=fixture();const job={id:'c'.repeat(32),kind:'download',status:'completed',rows:[{status:'succeeded',result:{download_url:'/fixture'}}]};
 f.batch.sync([job]);f.show([]);const details=f.root.children.find(x=>x.tagName==='details');details.open=true;details.ontoggle();
 f.batch.sync([job]);f.show([]);assert.equal(f.root.children.find(x=>x.tagName==='details').open,true);
});

