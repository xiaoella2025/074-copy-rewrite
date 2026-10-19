"""Explicit ordering and deferral; never discovers or submits new tasks."""
import time


def _defer(queue, job):
    if job.get('deferred'):return
    if job['status'] not in ('queued','running','paused'):
        raise ValueError('仅可暂缓排队、运行或等待确认的任务')
    batch=next((b for b in queue.batches if b['id']==job.get('batch_id')),None)
    was_manual_pause=job.get('manual_pause')
    if job['status']=='running' and job['kind']!='image':
        # Unlike cancel, defer is checked only after the current stage is saved.
        (queue.data_dir/'tasks'/job['task_id']/'defer').touch()
    job.update(status='pausing' if job['status']=='running' else 'paused',
               deferred=True,manual_pause=True,updated_at=time.time())
    if batch and batch['status']=='paused' and was_manual_pause and not any(
        j is not job and j.get('batch_id')==batch['id'] and j.get('manual_pause') and not j.get('deferred')
        for j in queue.jobs):
        batch['status']='running'


def control(queue, data):
    if not isinstance(data,dict) or set(data)-{'task_id','action'}:raise ValueError('调序参数无效')
    tid,action=data.get('task_id'),data.get('action')
    if action not in ('up','down','first','defer','resume'):raise ValueError('调序操作无效')
    with queue.backend.TASK_OPERATION_LOCK,queue.lock:
        job=queue._find(tid)
        if not job:raise ValueError('任务不在队列中')
        if action=='defer':_defer(queue,job)
        elif action=='resume':
            if not job.get('deferred') or job['status']!='paused':raise ValueError('请等当前阶段保存后再恢复')
            if job.get('pause_stage'):
                # Restoring a review stop must not implicitly approve its contents.
                job.update(deferred=False,manual_pause=False,updated_at=time.time())
                queue.jobs.remove(job);queue.jobs.append(job)
            else:
                batch=next((b for b in queue.batches if b['id']==job.get('batch_id')),None)
                if batch and batch['status'] not in ('running','paused','scheduled'):
                    raise ValueError('原批次已结束，请从任务详情续跑')
                queue.enqueue(tid,kind=job['kind'],config=queue.saved_config(job),batch_id=job.get('batch_id'),
                              from_step=None if job.get('rerun_prepared') else job.get('from_step'))
        else:
            if job['status']!='queued':raise ValueError('只能调整正在排队的任务')
            indices=[i for i,j in enumerate(queue.jobs) if j['status']=='queued']
            waiting=[queue.jobs[i] for i in indices];index=waiting.index(job)
            destination=0 if action=='first' else max(0,index-1) if action=='up' else min(len(waiting)-1,index+1)
            waiting.insert(destination,waiting.pop(index))
            for i,j in zip(indices,waiting):queue.jobs[i]=j
            batch=next((b for b in queue.batches if b['id']==job.get('batch_id')),None)
            if action=='first' and (not batch or batch['status']=='running'):
                for current in queue.jobs:
                    if current['status']=='running':_defer(queue,current)
        order={j['task_id']:i for i,j in enumerate(queue.jobs)}
        for batch in queue.batches:batch['task_ids'].sort(key=lambda tid:order.get(tid,len(order)))
        queue._save();queue.wake.set()
        return queue.get(tid)
