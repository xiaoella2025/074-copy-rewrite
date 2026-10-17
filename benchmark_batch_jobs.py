"""Explicit, durable benchmark batches. Startup never executes saved work."""
import copy
import json
from pathlib import Path
import re
import threading
import time

import benchmark
from benchmark_ai_receipts import fingerprint, UnconfirmedReceiptError
from benchmark_batch_actions import execute_item
from task_queue import atomic_json

ACTIVE={'queued','running','stopping'}
STATES=ACTIVE|{'interrupted','completed','stopped'}
ROW_STATES={'pending','running','succeeded','failed','unconfirmed'}
KINDS={'extract','download','mark','promo'}
ID=re.compile(r'[a-f0-9]{32}')


class BatchConflict(ValueError):pass


def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('批次 ID 无效')
    return value


def request(data):
    if not isinstance(data,dict):raise ValueError('请求必须是对象')
    job_id=identifier(data.get('id'));kind=data.get('kind');items=data.get('items')
    if not isinstance(kind,str) or kind not in KINDS:raise ValueError('批量操作无效')
    if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('请选择1至100条作品')
    clean=[];seen=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError('作品身份无效')
        account=benchmark._account_id(item.get('accountId'));feed=item.get('feedId')
        if not isinstance(feed,str) or not 1<=len(feed)<=256 or any(ord(c)<32 for c in feed):
            raise ValueError('作品身份无效')
        pair=(account,feed)
        if pair in seen:raise ValueError('作品不能重复')
        seen.add(pair);clean.append({'accountId':account,'feedId':feed})
    result={'id':job_id,'kind':kind,'items':clean}
    if kind=='mark':
        if type(data.get('mark')) is not bool:raise ValueError('标记值必须明确指定')
        result['mark']=data['mark']
    return result


class BatchJobs:
    def __init__(self,backend,executor=None):
        self.backend=backend;self.executor=executor or execute_item
        self.folder=Path(backend.DATA_DIR)/'benchmark/batch-jobs'
        self.lock=threading.RLock();self.jobs={};self.thread=None
        # Validate every record before changing any; never reset a damaged job.
        for path in sorted(self.folder.glob('*.json')):
            try:
                job=json.loads(path.read_text('utf8'))
                req=request(job)
                if job.get('version')!=1 or path.stem!=req['id'] or job.get('status') not in STATES:
                    raise ValueError('invalid job')
                rows=job.get('rows')
                if not isinstance(rows,list) or len(rows)!=len(req['items']):raise ValueError('invalid rows')
                for row,item in zip(rows,req['items']):
                    if not isinstance(row,dict) or row.get('status') not in ROW_STATES or any(row.get(k)!=v for k,v in item.items()):
                        raise ValueError('invalid row')
                    if req['kind']=='promo' and not re.fullmatch(r'[a-f0-9]{64}',str(row.get('source_fingerprint',''))):raise ValueError('invalid fingerprint')
                self.jobs[job['id']]=job
            except (ValueError,TypeError,KeyError,OSError) as error:
                raise ValueError('批次记录损坏或无法读取，已保留原文件，未自动执行') from error
        for job in self.jobs.values():
            if job['status'] in ACTIVE:
                job.update(status='interrupted',error='软件退出时尚未完成，请点击继续未完成项')
                for row in job['rows']:
                    if row['status']=='running':row['status']='pending'
                self._save(job)

    def _save(self,job):
        job['updated_at']=time.time()
        atomic_json(self.folder/(job['id']+'.json'),job)

    def _public(self,job):
        value=copy.deepcopy(job)
        statuses=[x['status'] for x in value['rows']]
        value.update(total=len(statuses),done=sum(s in {'succeeded','failed','unconfirmed'} for s in statuses),
                     succeeded=statuses.count('succeeded'),failed=statuses.count('failed'),unconfirmed=statuses.count('unconfirmed'))
        return value

    def list(self):
        with self.lock:return [self._public(x) for x in sorted(self.jobs.values(),key=lambda x:x.get('created_at',0),reverse=True)]

    def _active(self):return any(x['status'] in ACTIVE for x in self.jobs.values())

    def submit(self,data):
        req=request(data)
        with self.lock:
            old=self.jobs.get(req['id'])
            if old:
                if request(old)!=req:raise BatchConflict('同一请求 ID 对应不同内容，请先读取原批次')
                return self._public(old)
            if self._active():raise BatchConflict('已有批次正在执行，请等待或停止后再提交')
            feeds={(x['accountId'],x['feedId']):x for x in benchmark.state(self.backend)['feeds']}
            rows=[]
            for item in req['items']:
                feed=feeds.get((item['accountId'],item['feedId']))
                if feed is None:raise ValueError('作品不存在，请刷新列表后重新选择')
                row={**item,'status':'pending','error':'','result':{}}
                if req['kind']=='promo':row['source_fingerprint']=fingerprint(feed)
                rows.append(row)
            job={**req,'version':1,'rows':rows,'status':'queued','created_at':time.time(),'error':''}
            self._save(job);self.jobs[job['id']]=job
            self._launch(job)
            return self._public(job)

    def _launch(self,job):
        self.thread=threading.Thread(target=self._run,args=(job,),name='benchmark-batch',daemon=True)
        self.thread.start()

    def control(self,job_id,action):
        identifier(job_id)
        if action not in ('stop','resume'):raise ValueError('批次操作无效')
        with self.lock:
            job=self.jobs.get(job_id)
            if job is None:raise ValueError('批次不存在')
            if action=='stop':
                if job['status'] in ACTIVE:job['status']='stopping';self._save(job)
            else:
                if job['status'] in ACTIVE:return self._public(job)
                if self._active():raise BatchConflict('已有批次正在执行')
                retry=[x for x in job['rows'] if x['status'] in ('failed','pending')]
                if not retry:return self._public(job)
                for row in retry:row.update(status='pending',error='')
                job.update(status='queued',error='');self._save(job);self._launch(job)
            return self._public(job)

    def _run(self,job):
        try:
            for row in job['rows']:
                with self.lock:
                    if job['status']=='stopping':break
                    if row['status']!='pending':continue
                    job['status']='running';row.update(status='running',error='');self._save(job)
                try:
                    result=self.executor(self.backend,job['kind'],copy.deepcopy(row),job.get('mark'))
                    outcome=('succeeded','',result)
                except UnconfirmedReceiptError as error:outcome=('unconfirmed',str(error),{})
                except Exception as error:
                    # Provider errors may contain credentials/URLs; only existing
                    # business validation messages are safe to persist verbatim.
                    message=str(error)[:500] if isinstance(error,ValueError) else '此项执行失败，请检查对应功能后继续'
                    outcome=('failed',message,{})
                with self.lock:
                    row.update(status=outcome[0],error=outcome[1],result=outcome[2]);self._save(job)
            with self.lock:
                job['status']='stopped' if job['status']=='stopping' else 'completed';self._save(job)
        except Exception:
            # Disk-write failure must stop the worker, never advance to another
            # charged item. Saved running rows are reconciled on explicit resume.
            with self.lock:
                job.update(status='interrupted',error='批次进度保存失败，请保留记录并检查磁盘后重启软件')


_managers={};_lock=threading.Lock()


def get_manager(backend):
    root=str(Path(backend.DATA_DIR).resolve())
    with _lock:
        if root not in _managers:_managers[root]=BatchJobs(backend)
        return _managers[root]
