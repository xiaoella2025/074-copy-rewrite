const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.className = ''; this.textContent = '';
    this.classList = {add: name => {this.className += ' ' + name;}, toggle: () => {}};
  }
  append(...children) {this.children.push(...children);}
  prepend(child) {this.children.unshift(child);}
  replaceChildren(...children) {this.children = children;}
  setAttribute() {}
  addEventListener() {}
  querySelectorAll(selector) {
    const className = selector.slice(1), matches = [];
    for (const child of this.children) {
      if (!(child instanceof Element)) continue;
      if (child.className.split(' ').includes(className)) matches.push(child);
      matches.push(...child.querySelectorAll(selector));
    }
    return matches;
  }
}

test('pausing allows opening parameter edits but still blocks destructive reruns',()=>{
 const win={},host=new Element('div');let edited;
 vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,document:{createElement:t=>new Element(t)}});
 const renderer=win.WorkflowView.mount(host,{onEditStep:(...args)=>edited=args,onRerunStep:()=>{}});
 renderer.renderTask({info:{task_id:'fixture',progress:{step:'1',status:'running'},queue:{status:'pausing',manual_pause:true}},steps:{}});
 const edit=host.querySelectorAll('.wv-node-edit')[1];assert.equal(edit.disabled,false);edit.onclick({stopPropagation(){}});assert.deepEqual(edited,['1','fixture']);
 assert.ok(host.querySelectorAll('.wv-node-retry').every(b=>b.disabled));
 renderer.renderTask({info:{task_id:'fixture',progress:{},queue:{status:'running'}},steps:{}});
 assert.ok(host.querySelectorAll('.wv-node-edit').every(b=>b.disabled));
});

test('detail page polling preserves component edit and rerun gates',()=>{
 const html=fs.readFileSync('result.html','utf8'),start=html.indexOf('function renderQueue(detail)'),end=html.indexOf('async function api(',start);
 const edit={disabled:false},retry={disabled:true},elements=new Map();
 const context={workflow:{},host:{querySelectorAll:()=>[retry,edit]},QUEUE_LABELS:{pausing:'暂停中'},
  WorkflowView:{imageCompletion:()=>({})},document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{replaceChildren(){}});return elements.get(id);}}};
 vm.runInNewContext(html.slice(start,end)+";renderQueue({info:{queue:{status:'pausing'}}});",context);
 assert.equal(edit.disabled,false);assert.equal(retry.disabled,true);
});
