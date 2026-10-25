"""Adapt bounded single-image local FLUX/SDXL graphs, without executing helpers."""
import copy
import re

FIELDS={
 'DualCLIPLoader':({'clip_name1','clip_name2','type'},{'device'}),
 'UNETLoader':({'unet_name','weight_dtype'},set()),
 'VAELoader':({'vae_name'},set()),
 'CheckpointLoaderSimple':({'ckpt_name'},set()),
 'CLIPTextEncode':({'text','clip'},set()),
 'EmptyLatentImage':({'width','height','batch_size'},set()),
 'KSampler':({'seed','steps','cfg','sampler_name','scheduler','denoise','model','positive','negative','latent_image'},set()),
 'SamplerCustomAdvanced':({'noise','guider','sampler','sigmas','latent_image'},set()),
 'BasicGuider':({'model','conditioning'},set()),
 'BasicScheduler':({'model','scheduler','steps','denoise'},set()),
 'RandomNoise':({'noise_seed'},set()),
 'KSamplerSelect':({'sampler_name'},set()),
 'FluxGuidance':({'conditioning','guidance'},set()),
 'VAEDecode':({'samples','vae'},set()),
 'SaveImage':({'images','filename_prefix'},set()),
}


def structure(graph):
    if not isinstance(graph,dict) or not 2<=len(graph)<=80:raise ValueError('需要2至80节点的完整单图工作流')
    for key,node in graph.items():
        if not isinstance(key,str) or not re.fullmatch(r'\d{1,8}',key) or not isinstance(node,dict):raise ValueError('工作流节点格式无效')
        if not isinstance(node.get('class_type'),str) or not isinstance(node.get('inputs'),dict):raise ValueError('工作流节点缺少类型或输入')
        if set(node)-{'class_type','inputs','_meta'}:raise ValueError('工作流有未经核对的节点属性')
        for value in node['inputs'].values():
            if isinstance(value,list):
                if len(value)!=2 or not isinstance(value[0],str) or value[0] not in graph or type(value[1]) is not int or not 0<=value[1]<=2:raise ValueError('工作流节点接线无效')
            elif type(value) not in (str,int,float,bool):raise ValueError('工作流有未经核对的复合输入')


def local_file(value):
    if (not isinstance(value,str) or not 1<=len(value)<=250 or '..' in value or value.startswith(('/','\\'))
            or not re.fullmatch(r'[\w .()/+\-\[\]（）]+\.(?:safetensors|sft|ckpt)',value,re.UNICODE)):
        raise ValueError('模型必须是本地模型文件，不能调用外部API或远程文件')


def only(graph,kind):
    keys=[key for key,node in graph.items() if node['class_type']==kind]
    if len(keys)!=1:raise ValueError('需要唯一的 '+kind+' 节点，暂不支持多分支出图')
    return keys[0]


def ancestors(graph,output):
    seen=set();visiting=set()
    def visit(key):
        if key in visiting:raise ValueError('工作流存在循环接线')
        if key in seen:return
        visiting.add(key)
        for value in graph[key]['inputs'].values():
            if isinstance(value,list):visit(value[0])
        visiting.remove(key);seen.add(key)
    visit(output);return seen


def text_value(graph,value,seen=None):
    if isinstance(value,str):return value
    seen=set() if seen is None else set(seen)
    if not isinstance(value,list) or value[1]!=0 or value[0] in seen:raise ValueError('负向提示词辅助接线无法识别')
    seen.add(value[0]);node=graph[value[0]];kind=node['class_type'];fields=node['inputs']
    if kind in ('CR Text','TextInputBasic','JjkText') and set(fields)=={'text'}:result=text_value(graph,fields['text'],seen)
    elif kind=='CR Text Concatenate' and set(fields)=={'text1','text2','separator'}:
        separator=fields['separator']
        if not isinstance(separator,str) or len(separator)>20:raise ValueError('文本分隔符无效')
        result=separator.join(text_value(graph,fields[key],seen) for key in ('text1','text2'))
    else:raise ValueError('负向提示词含未经支持的处理节点：'+kind)
    if len(result)>8000:raise ValueError('负向提示词过长')
    return result


def audit_graph(graph):
    from rh_coins_workflow import number
    structure(graph)
    for node in graph.values():
        kind=node['class_type'];inputs=node['inputs']
        if kind not in FIELDS:raise ValueError('工作流含未经核对的节点：'+kind)
        required,optional=FIELDS[kind]
        if not required<=inputs.keys() or inputs.keys()-required-optional:raise ValueError('节点字段无法识别：'+kind)
    output=only(graph,'SaveImage');decode=only(graph,'VAEDecode');latent=only(graph,'EmptyLatentImage')
    if ancestors(graph,output)!=set(graph):raise ValueError('工作流含额外分支')
    def link(key,field,target,slot=0):
        if graph[key]['inputs'][field]!=[target,slot]:raise ValueError('工作流接线无法识别：'+field)
    def text(key,clip,slot):
        if graph[key]['class_type']!='CLIPTextEncode':raise ValueError('提示词编码节点无法识别')
        link(key,'clip',clip,slot)
        if not isinstance(graph[key]['inputs']['text'],str):raise ValueError('提示词需要直接传入文字')
    link(output,'images',decode)
    size=graph[latent]['inputs'];number(size['width'],64,2048,True);number(size['height'],64,2048,True)
    if type(size['batch_size']) is not int or size['batch_size']!=1:raise ValueError('只支持单张图片，不能批量输出')
    family='sdxl' if any(n['class_type']=='CheckpointLoaderSimple' for n in graph.values()) else 'flux'
    if family=='sdxl':
        checkpoint=only(graph,'CheckpointLoaderSimple');sampler=only(graph,'KSampler');v=graph[sampler]['inputs']
        local_file(graph[checkpoint]['inputs']['ckpt_name'])
        link(sampler,'model',checkpoint);link(decode,'vae',checkpoint,2)
        for field in ('positive','negative'):
            value=v[field]
            if not isinstance(value,list) or value[1]!=0:raise ValueError('正负提示词连接无效')
            text(value[0],checkpoint,1)
        if v['positive']==v['negative'] or len([n for n in graph.values() if n['class_type']=='CLIPTextEncode'])!=2:raise ValueError('正负提示词需要独立')
        number(v['cfg'],0,20);number(v['seed'],0,2**64-1,True)
        positive=v['positive'][0];seed_node=sampler;seed_field='seed';schedule=v
    else:
        unet=only(graph,'UNETLoader');clip=only(graph,'DualCLIPLoader');vae=only(graph,'VAELoader')
        sampler=only(graph,'SamplerCustomAdvanced');guider=only(graph,'BasicGuider');scheduler=only(graph,'BasicScheduler')
        seed_node=only(graph,'RandomNoise');seed_field='noise_seed';selection=only(graph,'KSamplerSelect')
        for key,field in [(unet,'unet_name'),(clip,'clip_name1'),(clip,'clip_name2'),(vae,'vae_name')]:local_file(graph[key]['inputs'][field])
        cv=graph[clip]['inputs'];uv=graph[unet]['inputs']
        if cv['type']!='flux' or cv.get('device','default') not in ('default','cpu'):raise ValueError('需要FLUX本地双编码器')
        if uv['weight_dtype'] not in ('default','fp8_e4m3fn','fp8_e4m3fn_fast','fp8_e5m2'):raise ValueError('模型精度无法识别')
        link(sampler,'guider',guider);link(sampler,'noise',seed_node);link(sampler,'sigmas',scheduler);link(sampler,'sampler',selection)
        link(guider,'model',unet);link(scheduler,'model',unet);link(decode,'vae',vae)
        conditioning=graph[guider]['inputs']['conditioning']
        if not isinstance(conditioning,list) or conditioning[1]!=0:raise ValueError('FLUX提示词连接无效')
        positive=conditioning[0]
        if graph[positive]['class_type']=='FluxGuidance':
            number(graph[positive]['inputs']['guidance'],0,25)
            conditioning=graph[positive]['inputs']['conditioning']
            if not isinstance(conditioning,list) or conditioning[1]!=0:raise ValueError('FLUX引导接线无效')
            positive=conditioning[0]
        text(positive,clip,0)
        if len([n for n in graph.values() if n['class_type']=='CLIPTextEncode'])!=1:raise ValueError('FLUX需要唯一正向提示词')
        number(graph[seed_node]['inputs'][seed_field],0,2**64-1,True)
        schedule=graph[scheduler]['inputs']
        if graph[selection]['inputs']['sampler_name'] not in ('euler','euler_ancestral','dpmpp_2m','res_multistep'):raise ValueError('采样器无法识别')
    link(decode,'samples',sampler);link(sampler,'latent_image',latent)
    number(schedule['steps'],1,50,True);number(schedule['denoise'],1,1)
    if schedule['scheduler'] not in ('simple','normal','beta','karras','sgm_uniform'):raise ValueError('调度器无法识别')
    if family=='sdxl' and schedule['sampler_name'] not in ('euler','euler_ancestral','dpmpp_2m','res_multistep'):raise ValueError('采样器无法识别')
    return {'kind':family,'promptNode':positive,'sizeNode':latent,'seedNode':seed_node,'seedField':seed_field,'outputNode':output,'nodes':len(graph)}


def prepare(source):
    """Pin prompt/size directly, removing upstream helpers from submitted graph."""
    import rh_coins_workflow as workflow
    structure(source)
    kinds={n['class_type'] for n in source.values()}
    if 'RH_QwenImage21Diffusers' in kinds:
        return {'graph':copy.deepcopy(source),'summary':workflow.audit_graph(source)}
    graph=copy.deepcopy(source);output=only(graph,'SaveImage');connected=ancestors(graph,output)
    core={k:v for k,v in graph.items() if k in connected}
    sampler=only(core,'KSampler') if any(n['class_type']=='KSampler' for n in core.values()) else only(core,'SamplerCustomAdvanced')
    latent_link=graph[sampler]['inputs']['latent_image']
    if not isinstance(latent_link,list) or latent_link[1]!=0:raise ValueError('尺寸输入无法识别')
    latent=latent_link[0];node=graph[latent]
    if node['class_type'] not in ('EmptyLatentImage','EmptySD3LatentImage','SDXL Empty Latent Image (rgthree)'):raise ValueError('只支持文生图的空白尺寸输入')
    if node['inputs'].get('batch_size')!=1 or type(node['inputs'].get('batch_size')) is not int:raise ValueError('原工作流不是单张输出')
    graph[latent]={'class_type':'EmptySD3LatentImage' if node['class_type']=='EmptySD3LatentImage' else 'EmptyLatentImage','inputs':{'width':1024,'height':1024,'batch_size':1}}
    if graph[sampler]['class_type']=='KSampler':
        v=graph[sampler]['inputs'];positive=v['positive'];negative=v['negative']
        if not isinstance(positive,list) or not isinstance(negative,list):raise ValueError('正负提示词接线无效')
        graph[negative[0]]['inputs']['text']=text_value(graph,graph[negative[0]]['inputs']['text'])
    else:
        guider=only(core,'BasicGuider');positive=graph[guider]['inputs']['conditioning']
        if isinstance(positive,list) and graph[positive[0]]['class_type']=='FluxGuidance':positive=graph[positive[0]]['inputs']['conditioning']
    if not isinstance(positive,list) or positive[1]!=0 or graph[positive[0]]['class_type']!='CLIPTextEncode':raise ValueError('正向提示词需要文本编码节点')
    graph[positive[0]]['inputs']['text']='074完整画面提示词'
    keep=ancestors(graph,output);graph={k:v for k,v in graph.items() if k in keep}
    summary=workflow.audit_graph(graph);summary['removedNodes']=len(source)-len(graph)
    return {'graph':graph,'summary':summary}
