"""Carry saved user requirements to visual planning and new image submissions."""
import json,re
from pathlib import Path

MARKER='【用户补充要求】'
def load(folder):
    folder=Path(folder)
    for filename,nested in [('client_config.json',True),('request.json',False)]:
        path=folder/filename
        if not path.exists():continue
        value=json.loads(path.read_text('utf8'));value=value.get('generate',{}) if nested else value
        if 'extra' in value:return str(value.get('extra') or '').strip()
    return ''

def no_face(extra):
    return bool(re.search(r'不露脸|不露(?:人脸|正脸|侧脸|面部)|(?:不要|禁止|不得|避免|不能)[^，。；;\n]{0,16}(?:人脸|正脸|侧脸|面部|五官)',extra))

def block(extra):
    if not extra:return ''
    rule=''
    if no_face(extra):rule='画面以环境、物品和剧情场景为主体；如出现人物，只画完全背对镜头的背影，不出现正脸、侧脸或可辨认五官，不画人物肖像或面部特写。\n'
    return MARKER+'\n'+extra+'\n'+rule+'与画面有关的补充要求优先于默认人物档案、画风和模板构图。'

def apply(prompt,extra):
    if not extra:return prompt
    prompt=prompt.split(MARKER,1)[0].rstrip()
    if no_face(extra):
        clauses=re.split(r'[，,。；;\n]+',prompt)
        prompt='，'.join(part for part in clauses if part and (re.search(r'不|无|禁止|避免',part) or not re.search(r'半身肖像|人物肖像|人物特写|面部特写|面容|面庞|五官|正脸|侧脸|正面|眼神|神情|眼镜|胡须|眉眼',part)))
    return prompt.rstrip()+'\n'+block(extra)
