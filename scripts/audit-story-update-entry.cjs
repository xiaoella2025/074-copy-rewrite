/* Static updater entry lookup. Never executes recovered scripts or calls HTTP. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(process.argv[2]||'.desktop-tools/story1250-audit/frontend');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const scripts=[...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+\.js)["']/g)].map(x=>x[1]);
if(!scripts.length)throw Error('No script entry in frontend/index.html');
const result={frontend:root,networkRequests:0,recoveredCodeExecuted:false,entries:[],notesSource:'Unproven until entry evidence identifies it'};
const visited=new Set(),pending=[];const manualLinks=[];
for(const url of scripts){
 if(/^[a-z]+:/i.test(url))continue;
 const file=path.resolve(root,url.replace(/^\//,''));
 if(!file.startsWith(root+path.sep))throw Error('Entry escapes frontend directory');
 const text=fs.readFileSync(file,'utf8');const snippets=[];
 pending.push(file);
 for(const term of ['check_update','notesMd','hasUpdate','检查更新','/v1/announcements']){
  const found=[...text.matchAll(new RegExp(term,'g'))];
  snippets.push({term,count:found.length,examples:found.slice(0,2).map(m=>text.slice(Math.max(0,m.index-100),m.index+term.length+180))});
 }
 result.entries.push({file:path.relative(root,file),sha256:crypto.createHash('sha256').update(text).digest('hex'),snippets});
 if(snippets.some(s=>s.term==='notesMd'&&s.count)&&snippets.some(s=>s.term==='check_update'&&s.count))result.notesSource='notesMd supplied by native check_update; static locator does not claim body is embedded';
}
while(pending.length){
 const file=pending.pop();if(visited.has(file))continue;visited.add(file);
 const text=fs.readFileSync(file,'utf8');
 if(path.basename(file).startsWith('manual-url-')){
  for(const match of text.matchAll(/https:\/\/[^\s"'`<>\\]+/g))manualLinks.push({source:path.relative(root,file),url:match[0]});
 }
 for(const match of text.matchAll(/(?:from|import\()\s*["']([^"']+\.js)["']/g)){
  if(!match[1].startsWith('.'))continue;
  const child=path.resolve(path.dirname(file),match[1]);
  if(child.startsWith(root+path.sep)&&fs.existsSync(child))pending.push(child);
 }
}
result.importedModulesChecked=visited.size;result.officialManualLinks=manualLinks;
process.stdout.write(JSON.stringify(result,null,2)+'\n');
