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

test('only active scene cards spin, completed images win, refresh clears activity',()=>{
 const win={},host=new Element('div');
 vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,document:{createElement:t=>new Element(t)}});
 const renderer=win.WorkflowView.mount(host,{});
 const detail={info:{task_id:'fixture',progress:{},queue:{status:'running',stage:'images'}},steps:{shots:[1,2,3,4].map(idx=>({idx,text:'fixture'})),image_generating:[1,2],images:[]}};
 renderer.renderTask(detail);
 assert.equal(host.querySelectorAll('.wv-image-spinner').length,2);
 assert.equal(host.querySelectorAll('.wv-image-generating').length,2);
 detail.steps.images=[{name:'1.png',url:'/fixture/1.png',size:8}];
 renderer.renderTask(detail);
 assert.equal(host.querySelectorAll('.wv-image-spinner').length,1);
 detail.steps.image_generating=[];renderer.renderTask(detail);
 assert.equal(host.querySelectorAll('.wv-image-spinner').length,0);
});
