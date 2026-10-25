"""Recover a verified completed archive after preserving the current edits as a paused task."""
import hashlib,json,shutil,sys,tempfile,time,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo))
import server,task_cover,task_queue,task_versions

def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

def recover(backend,task_id,archive_name,backup):
    root=backend.DATA_DIR/'tasks';source=root/task_id
    if source.resolve().parent!=root.resolve():raise ValueError('恢复路径无效')
    marker=task_cover.read(source/'restored-history.json',{})
    if task_versions.completed(source) and marker:return {**marker,'alreadyRestored':True}
    archive=source/'.reruns'/archive_name
    if archive.resolve().parent!=(source/'.reruns').resolve():raise ValueError('归档路径无效')
    meta=task_cover.read(archive/'06-draft-meta.json',{})
    draft=Path(meta.get('draft_content_path') or Path(meta.get('draft_dir',''))/'draft_content.json')
    if not meta.get('ok') or not draft.is_file() or not json.loads(draft.read_text('utf8')).get('tracks'):raise ValueError('没有可核验的原成品，不能标记完成')
    allowed={'01-review.json','02-meta.json','02-rewrite.txt','03-shots.json','03-character-card.json','04-prompts.json','04-intro-videos.json','04-video-meta.json','04-animation-meta.json','04-motion-prompts.json','05-tts-segments.json','05-tts-input.json','05-tts-progress.json','05-captions.json','05-podcast.json','podcast.mp3','audio','covers','image-jobs','videos','06-draft-meta.json','cover-meta.json','cover2-meta.json','cover-poster-1.png','cover-poster-2.png','cover-job-1.json','cover-job-2.json','run-meta.json'}
    if any(p.name not in allowed for p in archive.iterdir()):raise ValueError('归档包含未审核路径')
    queue_path=backend.DATA_DIR/'task-queue.json';queue_bytes=queue_path.read_bytes();queue=json.loads(queue_bytes)
    jobs=[j for j in queue['jobs'] if j['task_id']==task_id]
    if any(j['status'] in task_queue.ACTIVE for j in jobs):raise ValueError('请先暂停该任务并退出074')
    if backup.exists() or source.resolve() in backup.resolve().parents:raise ValueError('恢复备份路径无效')
    backup.mkdir(parents=True);shutil.copytree(source,backup/'current-task');(backup/'task-queue.json').write_bytes(queue_bytes)
    expected=hashes(archive);draft_hash=hashlib.sha256(draft.read_bytes()).hexdigest();new_id=None
    try:
        with patch.object(task_queue,'get_queue',return_value=SimpleNamespace(owns=lambda _:False)):
            new_id=task_versions.fork(backend,task_id,'recovered-working-version')
        target=root/new_id
        for item in archive.iterdir():
            dest=source/item.name
            if dest.resolve().parent!=source.resolve():raise ValueError('写入路径越界')
            if item.is_dir():
                if dest.exists():shutil.rmtree(dest)
                shutil.copytree(item,dest)
            else:shutil.copy2(item,dest)
        old_meta=task_cover.read(archive/'02-meta.json',{})
        editors=task_cover.read(source/'cover-editor.json',{})
        for slot in (1,2):
            job=task_cover.read(archive/f'cover-job-{slot}.json',{})
            if job:
                previous=editors.get(str(slot),{})
                editors[str(slot)]={**previous,'title':old_meta.get('title',''),'subtitle':old_meta.get('subtitle',[]),'provider':job.get('provider',''),'template':job.get('template',previous.get('template','cinematic-poster')),'ratio':job.get('ratio','3:4'),'workflow_choices':False}
        task_cover.write(source/'cover-editor.json',editors)
        current=jobs[-1] if jobs else {'id':uuid.uuid4().hex,'kind':'image','status':'paused','config':{},'created_at':time.time()}
        position=queue['jobs'].index(current) if jobs else len(queue['jobs'])
        queue['jobs']=[j for j in queue['jobs'] if j['task_id']!=task_id]
        working=task_versions.rebase(current,source,target,task_id,new_id)
        working.update(task_id=new_id,status='paused',manual_pause=True,config=task_cover.read(target/'client_config.json',{}))
        queue['jobs'].insert(min(position,len(queue['jobs'])),working)
        queue['jobs'].append({'id':uuid.uuid4().hex,'task_id':task_id,'kind':'image','status':'completed','config':task_cover.read(source/'client_config.json',{}),'created_at':source.stat().st_ctime,'updated_at':(archive/'06-draft-meta.json').stat().st_mtime,'recovered_from_archive':archive_name})
        for batch in queue.get('batches',[]):
            if batch.get('id')==working.get('batch_id') and batch.get('status') in ('paused','running','scheduled'):
                batch['task_ids']=[new_id if x==task_id else x for x in batch['task_ids']]
                if task_id in batch.get('results',{}):batch['results'][new_id]=batch['results'].pop(task_id)
        task_cover.write(queue_path,queue)
        task_cover.write(source/'progress.json',{'step':'6','status':'done','recovered_from_archive':archive_name})
        progress=task_cover.read(backup/'current-task/progress.json',{})
        task_cover.write(target/'progress.json',{**progress,'status':'paused'})
        assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in expected.items())
        assert hashlib.sha256(draft.read_bytes()).hexdigest()==draft_hash
        assert not (target/'06-draft-meta.json').exists()
        result={'original_task_id':task_id,'working_task_id':new_id,'archive':archive_name,'originalCompleted':True,'workingPaused':True,'archivedFilesVerified':len(expected),'externalDraftUnchanged':True,'originalConfigSnapshotAvailable':False,'realGenerationSubmissions':0}
        task_cover.write(source/'restored-history.json',result)
        return result
    except BaseException:
        if source.resolve().parent!=root.resolve():raise
        shutil.rmtree(source);shutil.copytree(backup/'current-task',source);queue_path.write_bytes(queue_bytes)
        if new_id and (root/new_id).resolve().parent==root.resolve():shutil.rmtree(root/new_id)
        raise

def main():
    data=Path.home()/'AppData/Local/com.app074.desktop/data'
    task_id='task_1792923206112_a839d17d2dcd';archive='1792926947080888800-0'
    audit=repo/'.desktop-tools/completed-task-revisions-20261025'
    if '--apply' in sys.argv:
        import subprocess
        check="@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'app074-desktop.exe' -or ($_.Name -eq 'python.exe' -and $_.ExecutablePath -like '*074 创作工作台*') }).Count"
        count=subprocess.check_output(['powershell','-NoProfile','-Command',check],text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert count.strip()=='0','074 must remain closed during recovery'
        server.DATA_DIR=data
        result=recover(server,task_id,archive,audit/('recovery-backup-'+str(time.time_ns())))
        task_cover.write(audit/'recovery-installed.json',result);print(json.dumps(result))
    else:
        with tempfile.TemporaryDirectory(prefix='074-history-recovery-') as tmp:
            cloned=Path(tmp)/'data';(cloned/'tasks').mkdir(parents=True)
            before=hashes(data/'tasks'/task_id)
            shutil.copytree(data/'tasks'/task_id,cloned/'tasks'/task_id)
            shutil.copy2(data/'task-queue.json',cloned/'task-queue.json')
            assert hashes(data/'tasks'/task_id)==before,'Source changed while copying; retry after pausing'
            server.DATA_DIR=cloned
            result=recover(server,task_id,archive,Path(tmp)/'backup')
            assert hashes(data/'tasks'/task_id)==before,'Production source changed during replay'
            result.update(success=True,productionFilesChanged=0,isolatedReplay=True)
            task_cover.write(audit/'recovery-replay-results.json',result);print(json.dumps(result))

if __name__=='__main__':main()
