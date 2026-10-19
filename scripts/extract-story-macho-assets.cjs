// Offline Mach-O counterpart to the existing PE asset extractor. Never runs code.
const fs=require('fs'),path=require('path'),zlib=require('zlib'),crypto=require('crypto');
const [source,destination]=process.argv.slice(2),bytes=fs.readFileSync(source);
if(bytes.readUInt32LE(0)!==0xfeedfacf)throw Error('Expected little-endian Mach-O 64');
const sections=[],pointerFormats=[];let command=32;
for(let n=0;n<bytes.readUInt32LE(16);n++){
 const kind=bytes.readUInt32LE(command),size=bytes.readUInt32LE(command+4);
 if(size<8||command+size>bytes.length)throw Error('Invalid load command');
 if(kind===0x19){
  const count=bytes.readUInt32LE(command+64);
  for(let j=0;j<count;j++){
   const p=command+72+j*80;if(p+80>command+size)throw Error('Invalid section');
   const str=o=>bytes.toString('ascii',o,o+16).replace(/\0.*$/,'');
   sections.push({name:str(p),segment:str(p+16),address:Number(bytes.readBigUInt64LE(p+32)),size:Number(bytes.readBigUInt64LE(p+40)),offset:bytes.readUInt32LE(p+48)});
  }
 }
 if(kind===0x80000034){
  const offset=bytes.readUInt32LE(command+8),starts=offset+bytes.readUInt32LE(offset+4),count=bytes.readUInt32LE(starts);
  for(let j=0;j<count;j++){const relative=bytes.readUInt32LE(starts+4+j*4);if(relative)pointerFormats.push(bytes.readUInt16LE(starts+relative+6));}
 }
 command+=size;
}
const raw=(encoded,len)=>{
 const pointer=BigInt(encoded);
 const candidates=[Number(pointer)];
 // This arm64 package uses DYLD_CHAINED_PTR_64_OFFSET (format 6).
 // Decode the 36-bit rebase target; high bits contain the next-chain offset.
 if(pointerFormats.includes(6)&&(pointer>>63n)===0n)candidates.push(Number(pointer&0xfffffffffn)+0x100000000);
 for(const va of candidates){const s=sections.find(s=>s.offset>0&&va>=s.address&&va+len<=s.address+s.size);if(s)return s.offset+va-s.address;}
 return null;
};
const assets=new Map();fs.mkdirSync(destination,{recursive:true});
for(const s of sections.filter(s=>s.offset>0&&['__const','__data'].includes(s.name))){
 for(let p=s.offset;p+32<=Math.min(bytes.length,s.offset+s.size);p+=8){
  const kp=bytes.readBigUInt64LE(p),kl=Number(bytes.readBigUInt64LE(p+8)),dp=bytes.readBigUInt64LE(p+16),dl=Number(bytes.readBigUInt64LE(p+24));
  if(kl<2||kl>512||dl<1||dl>bytes.length)continue;
  const k=raw(kp,kl),d=raw(dp,dl);if(k===null||d===null||bytes[k]!==47)continue;
  const key=bytes.toString('utf8',k,k+kl);
  if(!/^\/[\w./@% -]+\.(?:html|js|css|json|map|png|jpg|jpeg|svg|webp|ico|woff2?|ttf|mp3|wasm|txt|gif)$/i.test(key)||key.includes('..')||assets.has(key))continue;
  let output,compression='brotli';try{output=zlib.brotliDecompressSync(bytes.subarray(d,d+dl),{maxOutputLength:100*1024*1024});}catch{output=bytes.subarray(d,d+dl);compression='raw';}
  const target=path.resolve(destination,key.slice(1));if(!target.startsWith(path.resolve(destination)+path.sep))throw Error('Invalid path');
  fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,output);
  assets.set(key,{path:key,tableOffset:p,dataOffset:d,packedBytes:dl,bytes:output.length,compression});
 }
}
const result={source,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),applicationExecuted:false,sections,assets:[...assets.values()]};
fs.writeFileSync(path.join(destination,'asset-manifest.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({assets:assets.size,applicationExecuted:false}));
