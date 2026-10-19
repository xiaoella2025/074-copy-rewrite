const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.listeners = {}; this.value = ''; this.validityMessage = ''; }
  append(...items) { this.children.push(...items); }
  prepend(...items) { this.children.unshift(...items); }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setCustomValidity(value) { this.validityMessage = value; }
  insertAdjacentElement(_, element) { this.after = element; }
}
function fixture(fetcher) {
  const body = new Element('body'), head = new Element('head'), input = new Element('input');
  const document = {readyState: 'loading', body, head, createElement: tag => new Element(tag),
    getElementById: id => id === 'jy-draft-path' ? input : null,
    addEventListener(name, callback) { this[name] = callback; }};
  const calls = [], window = {};
  vm.runInNewContext(fs.readFileSync('assets/runtime_health1250.js', 'utf8'), {
    window, document, setTimeout, clearTimeout, URLSearchParams,
    fetch: async (path, options) => { calls.push({path, options}); return fetcher(path, options); }
  });
  return {body, head, input, document, window, calls, api: window.RuntimeHealth1250};
}
const healthy = {ok:true, draft_generator:{status:'ready',message:'通过'},ffmpeg:{status:'ready',message:'可用'}};
const response = value => ({ok:true,json:async()=>value});

test('component warning persists with accessible retry and never disables other work', async () => {
  const state={ok:false,draft_generator:{status:'missing',message:'缺少草稿生成组件'},ffmpeg:{status:'ready',message:'可用'}};
  const f = fixture(async()=>response(state));
  await f.api.mount();
  assert.equal(f.body.children.length, 1);
  const banner = f.body.children[0];
  assert.equal(banner.role, 'status');
  assert.equal(banner.hidden, false);
  assert.match(banner.children[0].textContent, /缺少草稿生成组件/);
  assert.equal(banner.children[1].tagName, 'button');
  assert.equal(f.input.disabled, undefined);
  assert.equal(f.calls[0].path, '/api/runtime/health');
  assert.equal(f.calls[0].options.credentials, 'same-origin');
});

test('successful retry hides the warning and duplicate mounts reuse banner', async () => {
  let current = {ok:false,draft_generator:{status:'invalid',message:'校验失败'},ffmpeg:healthy.ffmpeg};
  const f = fixture(async()=>response(current));
  await f.api.mount();
  current = healthy;
  await f.body.children[0].children[1].listeners.click();
  assert.equal(f.body.children[0].hidden,true);
  await f.api.mount();
  assert.equal(f.body.children.length,1);
});

test('health request failure stays actionable without asserting component absence', async () => {
  const f = fixture(async()=>{throw Error('untrusted backend exception');});
  await f.api.mount();
  const message=f.body.children[0].children[0].textContent;
  assert.match(message,/检查.*失败|无法.*检查/);
  assert.doesNotMatch(message,/untrusted|缺少/);
});

test('draft validator sends only proposed draft path to fixed authenticated route', async () => {
  const f = fixture(async()=>response({valid:false,error:'目录重叠'}));
  const result=await f.api.validateDraftPath('D:/草稿目录');
  assert.equal(result.valid,false);
  const parsed=new URL(f.calls[0].path,'http://fixture');
  assert.equal(parsed.pathname,'/api/runtime/draft-path-check');
  assert.deepEqual([...parsed.searchParams.keys()],['path']);
  assert.equal(parsed.searchParams.get('path'),'D:/草稿目录');
});

test('draft input shows server validation as form feedback and ignores stale reply', async () => {
  let resolveOld;
  const f=fixture(path=>{
    if(path==='/api/runtime/health')return response(healthy);
    if(path.includes('old'))return new Promise(resolve=>{resolveOld=resolve;});
    return response({valid:true});
  });
  await f.api.mount();
  f.input.value='D:/old';
  const old=f.input.listeners.change();
  f.input.value='D:/new';
  await f.input.listeners.change();
  resolveOld(response({valid:false,error:'old conflict'}));
  await old;
  assert.equal(f.input.validityMessage,'');
  assert.equal(f.input.after.textContent,'');
});

test('conflicting draft input displays the error as form validation feedback', async () => {
  const f=fixture(async path=>response(path==='/api/runtime/health' ? healthy : {valid:false,error:'目录重叠'}));
  await f.api.mount();
  f.input.value='D:/conflict';
  await f.input.listeners.change();
  assert.equal(f.input.validityMessage,'目录重叠');
  assert.equal(f.input.after.textContent,'目录重叠');
});
