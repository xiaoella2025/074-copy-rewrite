"""Bounded, local-inference-only Qwen graphs. Never execute arbitrary workflows."""
import copy
import hashlib
import json
import math
import re

RATIOS={'9:16':(576,1024),'3:4':(768,1024),'1:1':(1024,1024),'16:9':(1024,576)}
FIELDS={
 'UNETLoader':({'unet_name','weight_dtype'},set()),
 'CLIPLoader':({'clip_name','type'},{'device'}),
 'VAELoader':({'vae_name'},set()),
 'CLIPTextEncode':({'text','clip'},set()),
 'EmptySD3LatentImage':({'width','height','batch_size'},set()),
 'KSampler':({'seed','steps','cfg','sampler_name','scheduler','denoise','model','positive','negative','latent_image'},set()),
 'VAEDecode':({'samples','vae'},set()),
 'SaveImage':({'images','filename_prefix'},set()),
 'ModelSamplingAuraFlow':({'model','shift'},set()),
 'CFGNorm':({'model','strength'},set()),
 'LoraLoaderModelOnly':({'model','lora_name','strength_model'},set()),
 'RH_QwenImage21Diffusers':({'prompt','negative_prompt','true_cfg_scale','num_inference_steps','output_resolution','width','height','seed','use_kv_cache'},set()),
}


def digest(graph):
    return hashlib.sha256(json.dumps(graph,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def number(value,low,high,integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high or (integer and type(value) is not int):
        raise ValueError('工作流数值参数超出单图实验范围')


def local_model(value):
    if (not isinstance(value,str) or not 1<=len(value)<=200 or 'qwen' not in value.lower()
        or not re.fullmatch(r'[\w .()/+\-]+\.safetensors',value,re.UNICODE) or '..' in value or value.startswith('/')):
        raise ValueError('只接受已核对的本地 Qwen 模型文件，不调用第三方模型 API')


def audit_graph(graph):
    if not isinstance(graph,dict) or not 2<=len(graph)<=25:raise ValueError('未取得完整的单图工作流，不能生成')
    for key,node in graph.items():
        if not isinstance(key,str) or not re.fullmatch(r'\d{1,8}',key) or not isinstance(node,dict):raise ValueError('工作流节点格式无效')
        kind=node.get('class_type');inputs=node.get('inputs')
        if not isinstance(kind,str) or kind not in FIELDS:raise ValueError('工作流含未经核对的节点：'+str(kind)[:80]+'；未提交生成')
        required,optional=FIELDS[kind]
        if not isinstance(inputs,dict) or not required<=inputs.keys() or inputs.keys()-required-optional:raise ValueError('节点字段与已核对版本不一致：'+kind)
        if set(node)-{'class_type','inputs','_meta'}:raise ValueError('工作流含未经核对的节点属性')
        for value in inputs.values():
            if isinstance(value,list):
                if len(value)!=2 or not isinstance(value[0],str) or value[0] not in graph or type(value[1]) is not int or not 0<=value[1]<=2:raise ValueError('工作流接线无效')
            elif type(value) not in (str,int,float,bool):raise ValueError('工作流包含未核对的复合输入')
    def nodes(kind):return [key for key,node in graph.items() if node['class_type']==kind]
    def only(kind):
        values=nodes(kind)
        if len(values)!=1:raise ValueError('单图实验需要且仅支持一个 '+kind+' 节点')
        return values[0]
    def linked(key,field,target,slot=0):
        if graph[key]['inputs'][field]!=[target,slot]:raise ValueError('工作流接线不符合单图生成结构：'+field)
    output=only('SaveImage');visited=set();visiting=set()
    def visit(key):
        if key in visiting:raise ValueError('工作流存在循环')
        if key in visited:return
        visiting.add(key)
        for value in graph[key]['inputs'].values():
            if isinstance(value,list):visit(value[0])
        visiting.remove(key);visited.add(key)
    visit(output)
    if visited!=set(graph):raise ValueError('工作流含额外生成分支或未连接节点，暂不执行')
    if nodes('RH_QwenImage21Diffusers'):
        source=only('RH_QwenImage21Diffusers')
        if len(graph)!=2:raise ValueError('Qwen 2.1 只接受原生单图和保存两节点版本')
        linked(output,'images',source);values=graph[source]['inputs']
        number(values['true_cfg_scale'],1,1);number(values['num_inference_steps'],1,50,True)
        number(values['output_resolution'],256,2048,True)
        number(values['width'],0,2752,True);number(values['height'],0,2752,True)
        number(values['seed'],0,2**64-1,True)
        if type(values['use_kv_cache']) is not bool or not isinstance(values['prompt'],str) or values['negative_prompt']!='':raise ValueError('Qwen 2.1 单图参数无效')
        return {'kind':'qwen21','promptNode':source,'sizeNode':source,'seedNode':source,'outputNode':output,'nodes':len(graph)}
    sampler=only('KSampler');latent=only('EmptySD3LatentImage');decode=only('VAEDecode');clip=only('CLIPLoader');vae=only('VAELoader');unet=only('UNETLoader')
    linked(output,'images',decode);linked(decode,'samples',sampler);linked(decode,'vae',vae)
    linked(sampler,'latent_image',latent)
    values=graph[sampler]['inputs']
    positive,negative=values['positive'],values['negative']
    for link in (positive,negative):
        if not isinstance(link,list) or link[1]!=0 or graph[link[0]]['class_type']!='CLIPTextEncode':raise ValueError('无法确定原生正负提示词输入')
        linked(link[0],'clip',clip)
        if not isinstance(graph[link[0]]['inputs']['text'],str):raise ValueError('提示词输入必须为文字')
    if positive==negative or len(nodes('CLIPTextEncode'))!=2:raise ValueError('正负提示词必须独立，不能存在额外提示词分支')
    model=values['model'];chain=set()
    while isinstance(model,list) and model[1]==0 and model[0]!=unet:
        key=model[0]
        if key in chain:raise ValueError('模型链存在循环')
        chain.add(key);kind=graph[key]['class_type'];inputs=graph[key]['inputs']
        if kind=='ModelSamplingAuraFlow':number(inputs['shift'],0,10)
        elif kind=='CFGNorm':number(inputs['strength'],0,1)
        elif kind=='LoraLoaderModelOnly':local_model(inputs['lora_name']);number(inputs['strength_model'],-2,2)
        else:raise ValueError('模型链含未核对的处理节点')
        model=inputs['model']
    if model!=[unet,0]:raise ValueError('模型链未连接本地 Qwen 模型')
    for key,field in [(unet,'unet_name'),(clip,'clip_name'),(vae,'vae_name')]:local_model(graph[key]['inputs'][field])
    if graph[clip]['inputs']['type']!='qwen_image':raise ValueError('只支持原生 Qwen 图像编码器')
    if graph[clip]['inputs'].get('device','default') not in ('default','cpu'):raise ValueError('编码器设备无效')
    if graph[unet]['inputs']['weight_dtype'] not in ('default','fp8_e4m3fn','fp8_e4m3fn_fast','fp8_e5m2'):raise ValueError('模型精度无效')
    sizes=graph[latent]['inputs']
    number(sizes['width'],64,4096,True);number(sizes['height'],64,4096,True)
    if sizes['batch_size']!=1 or type(sizes['batch_size']) is not int:raise ValueError('候选工作流会批量出图，单图实验不执行')
    number(values['steps'],1,50,True);number(values['cfg'],0,20);number(values['denoise'],1,1);number(values['seed'],0,2**64-1,True)
    if values['sampler_name'] not in ('euler','euler_ancestral','dpmpp_2m','res_multistep'):raise ValueError('采样器未经核对')
    if values['scheduler'] not in ('simple','normal','beta','karras','sgm_uniform'):raise ValueError('调度器未经核对')
    return {'kind':'qwen','promptNode':positive[0],'sizeNode':latent,'seedNode':sampler,'outputNode':output,'nodes':len(graph)}


def build_graph(graph,prompt,ratio,seed):
    info=audit_graph(graph)
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>8000:raise ValueError('请填写1至8000字画面描述')
    if not isinstance(ratio,str) or ratio not in RATIOS:raise ValueError('请选择一种支持的画面比例')
    number(seed,0,2**32-1,True)
    result=copy.deepcopy(graph);width,height=RATIOS[ratio]
    result[info['promptNode']]['inputs']['prompt' if info['kind']=='qwen21' else 'text']=prompt.strip()
    result[info['sizeNode']]['inputs'].update(width=width,height=height)
    result[info['seedNode']]['inputs']['seed']=seed
    if info['kind']=='qwen21':result[info['sizeNode']]['inputs']['output_resolution']=1024
    else:result[info['sizeNode']]['inputs']['batch_size']=1
    result[info['outputNode']]['inputs']['filename_prefix']='074_rh_coins'
    audit_graph(result)
    return result
