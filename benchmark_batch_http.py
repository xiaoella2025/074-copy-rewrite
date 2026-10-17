"""Small authenticated adapter; all existing handlers keep their own routes."""
from functools import wraps
import json
from urllib.parse import urlsplit

from benchmark_batch_jobs import get_manager, BatchConflict

GET='/api/benchmark/batch-jobs'
POST={'/api/benchmark/batch-start','/api/benchmark/batch-control'}


def install(backend):
    if getattr(backend.Handler,'_benchmark_batch_installed',False):return
    old_get,old_post=backend.Handler.do_GET,backend.Handler.do_POST

    @wraps(old_get)
    def do_get(handler):
        if urlsplit(handler.path).path!=GET:return old_get(handler)
        if not handler._desktop_authorized():return
        try:handler._json(200,{'jobs':get_manager(backend).list()})
        except (ValueError,OSError):
            handler._json(400,{'error':'批次记录无法读取，已保留原文件；请检查记录和磁盘'})

    @wraps(old_post)
    def do_post(handler):
        path=urlsplit(handler.path).path
        if path not in POST:return old_post(handler)
        if not handler._desktop_authorized():return
        try:
            size=int(handler.headers.get('content-length','0'))
            if not 0<=size<=128*1024:
                handler.close_connection=True;handler._json(413,{'error':'请求内容过大'});return
            data=json.loads(handler.rfile.read(size)) if size else {}
            if not isinstance(data,dict):raise ValueError('请求必须是 JSON 对象')
            manager=get_manager(backend)
            result=manager.submit(data) if path.endswith('batch-start') else manager.control(data.get('id'),data.get('action'))
            handler._json(200,{'job':result})
        except BatchConflict as error:handler._json(409,{'error':str(error)})
        except (ValueError,TypeError) as error:
            handler._json(400,{'error':str(error) if not isinstance(error,(json.JSONDecodeError,UnicodeError)) else '请求 JSON 无效'})
        except OSError:handler._json(400,{'error':'批次记录无法保存，请检查磁盘后重试同一批次'})

    backend.Handler.do_GET,backend.Handler.do_POST=do_get,do_post
    backend.Handler._benchmark_batch_installed=True
