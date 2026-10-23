"""User initiated, local-only syntax repair. Never completes truncated output."""
import json,os,re,uuid
from pathlib import Path

def parse(text):
    text=text.strip()
    if text.startswith('```'):
        lines=text.splitlines()
        if len(lines)>2 and lines[-1].strip()=='```':text='\n'.join(lines[1:-1]).strip()
    try:return json.loads(text)
    except ValueError:pass
    if not text.startswith(('[','{')):raise ValueError('返回内容不是完整 JSON，无法安全修复')
    out=[];inside=False;escaped=False
    for i,char in enumerate(text):
        if escaped:out.append(char);escaped=False;continue
        if inside and char=='\\':out.append(char);escaped=True;continue
        if char=='"':
            if inside:
                tail=text[i+1:].lstrip()
                if tail and tail[0] not in ',:}]':
                    if tail[0] in '"[{':raise ValueError('引号边界不明确，无法安全修复')
                    out.append('\\"');continue
            inside=not inside
        if inside and ord(char)<32:out.append(json.dumps(char)[1:-1])
        else:out.append(char)
    try:return json.loads(''.join(out))
    except ValueError as error:raise ValueError('完整返回仍有结构缺失或歧义，未修改原提示词') from error

def save_source(folder,shots,responses,track,prefix,allow_color,reference_kind,suffix=''):
    identity=uuid.uuid4().hex;directory=Path(folder)/'04-prompt-repair';directory.mkdir(parents=True,exist_ok=True)
    value={'shots':shots,'responses':responses,'track':track,'prefix':prefix,'suffix':suffix,'allow_color':allow_color,'reference_kind':reference_kind}
    (directory/(identity+'.json')).write_text(json.dumps(value,ensure_ascii=False),'utf8')
    return identity

def apply(backend,tid,data):
    from task_cover import folder_for
    from story_prompt_validation import normalize_batch
    identity=data.get('repair_id')
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('修复记录无效')
    with backend.task_operation(tid):
        folder=folder_for(backend,tid);directory=folder/'04-prompt-repair';record=directory/(identity+'.json')
        if directory.is_symlink() or getattr(directory,'is_junction',lambda:False)() or record.is_symlink():raise ValueError('修复记录路径无效')
        if not record.is_file():raise ValueError('没有保存完整模型返回，无法本地修复；不会重新调用模型或生图')
        source=json.loads(record.read_text('utf8'));path=folder/'04-prompts.json';original=path.read_bytes();prompts=json.loads(original)
        selected=[p for p in prompts if p.get('diagnostic',{}).get('repairId')==identity and p.get('diagnostic',{}).get('fellBackToSkeleton')]
        if not selected:
            if any(p.get('diagnostic',{}).get('repairId')==identity and p.get('diagnostic',{}).get('formatRepaired') for p in prompts):return {'ok':True,'repaired':0}
            raise ValueError('提示词已被修改，请重新打开任务核对；未覆盖现有内容')
        shots=source['shots'];current=json.loads((folder/'03-shots.json').read_text('utf8'))
        if any(p.get('desc_prompt')!=p['diagnostic'].get('fallbackPrompt') for p in selected):raise ValueError('提示词已被手工修改，未覆盖现有内容')
        expected={s['idx']:s['text'] for s in shots}
        if {p['idx']:p['text'] for p in selected}!=expected or any(next((s.get('text') for s in current if s['idx']==idx),None)!=text for idx,text in expected.items()):raise ValueError('分镜或提示词已修改，未覆盖现有内容')
        policy=(backend.story_workflow_reference()['tracks'].get(source['track']) or {}).get('step3Policy') or {}
        repaired=None
        for raw in reversed(source['responses']):
            try:
                candidate=parse(raw)
                if not isinstance(candidate,list) or len(candidate)!=len(shots):continue
                for item,shot in zip(candidate,shots):
                    if not isinstance(item,dict) or type(item.get('id')) is not int or item['id']!=shot['idx'] or not isinstance(item.get('desc_prompt'),str) or not item['desc_prompt'].strip():raise ValueError('分镜结构仍不完整')
                    if source['reference_kind'] and not isinstance(item.get('use_reference'),bool):raise ValueError('缺少参考图判断')
                repaired=normalize_batch(candidate,source['reference_kind'],source['prefix'],source['suffix'],policy,3);break
            except ValueError:continue
        if repaired is None:raise ValueError('格式仍有歧义、数据缺失或画面规则未通过，未修改原提示词；不会重新调用模型或生图')
        by_id={p['id']:p for p in repaired}
        for p in selected:
            value=by_id[p['idx']]['desc_prompt']
            if not source['allow_color']:value=backend.story_grayscale_prompt(value,backend.story_workflow_reference())
            import visual_requirements
            value=visual_requirements.apply(value,visual_requirements.load(folder))
            p['desc_prompt']=value
            if source['reference_kind']:p['use_reference']=by_id[p['idx']]['use_reference']
            p['diagnostic']={**p['diagnostic'],'fellBackToSkeleton':False,'formatRepaired':True}
        temporary=directory/(identity+'.tmp');backup=directory/(identity+'.before.json')
        try:
            temporary.write_text(json.dumps(prompts,ensure_ascii=False,indent=2),'utf8')
            if path.read_bytes()!=original:raise ValueError('提示词已变化，未覆盖现有内容')
            if backup.exists():
                if backup.read_bytes()!=original:raise ValueError('已有不同版本的修复备份，未覆盖现有内容')
            else:
                with backup.open('xb') as output:output.write(original)
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
        return {'ok':True,'repaired':len(selected)}
