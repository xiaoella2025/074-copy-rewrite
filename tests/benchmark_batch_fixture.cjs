const {create}=require('../assets/benchmark_batch.js');
function fixture(shared={}){
 const feeds=[{accountId:'v2_one',feedId:'same',transcript:'cached'},{accountId:'v2_two',feedId:'same'},{accountId:'v2_two',feedId:'picture',mediaType:2}],calls=[],notices=[],downloads=[];
 const root={children:[],append(...x){this.children.push(...x);},replaceChildren(...x){this.children=x;}};
 const el=(tag,cls,text)=>({tagName:tag,className:cls,textContent:text,children:[],append(...x){this.children.push(...x);}});
 shared.store||=new Map();shared.jobs||=[];
 const storage={getItem:k=>shared.store.get(k),setItem:(k,v)=>shared.store.set(k,v),removeItem:k=>shared.store.delete(k)};
 let visible=feeds,tab='works',fail=false,lost=false,replyHold=null;
 const batch=create({root,el,storage,id:()=> 'a'.repeat(32),button:(text,fn)=>({...el('button','',text),onclick:fn}),notice:x=>notices.push(x),render:()=>batch.render(visible,tab),
  refresh:async()=>{if(fail)throw Error('offline');batch.sync(shared.jobs);batch.render(visible,tab);},
  api:async(path,data)=>{calls.push({path,data});if(path.endsWith('batch-start')){if(!shared.jobs.some(x=>x.id===data.id))shared.jobs.push({...data,status:'running',total:data.items.length,rows:data.items.map(x=>({...x,status:'pending',error:'',result:{}}))});const snapshot=JSON.parse(JSON.stringify(shared.jobs[0]));if(replyHold)await replyHold;if(lost)throw Error('lost');return {job:snapshot};}return {job:shared.jobs.find(x=>x.id===data.id)};},
  download:async(...x)=>downloads.push(x),reveal:async x=>downloads.push(x)});
 batch.render(feeds,'works');
 return {batch,feeds,calls,notices,root,downloads,shared,select(item=feeds[0]){batch.pick(item).children[0].onchange({target:{checked:true}});},show(items,next='works'){visible=items;tab=next;batch.render(items,next);},failRead(){fail=true;},loseReply(){lost=true;},holdReply(value){replyHold=value;}};
}
module.exports={fixture};
