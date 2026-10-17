"""One durable benchmark operation, reusing existing business writes/receipts."""
import benchmark
from benchmark_ai_receipts import fingerprint


def execute_item(backend, kind, row, mark=None):
    identity={key:row[key] for key in ('accountId','feedId')}
    item=next((x for x in benchmark.state(backend)['feeds']
               if all(x.get(k)==v for k,v in identity.items())),None)
    if item is None:raise ValueError('作品已删除，未执行此项')
    if kind=='mark':
        benchmark.edit(backend,{**identity,'changes':{'createdTask':mark}})
        return {'marked':mark}
    if kind=='promo':
        if fingerprint(item)!=row.get('source_fingerprint'):
            raise ValueError('文案或标题已修改，旧批次不再发起判定；请按新文案重新选择')
        if item.get('promo'):return {'reused':True}
        benchmark.ai_action(backend,{**identity,'action':'promo','source_fingerprint':row['source_fingerprint']})
        return {'classified':True}
    if kind not in ('extract','download'):raise ValueError('批量操作无效')
    cached=bool(item.get('transcriptReviewed') or item.get('transcript'))
    if not cached:
        if str(item.get('mediaType'))=='2':raise ValueError('图文作品不支持语音识别')
        benchmark.transcribe(backend,{**identity,'source':'original'})
    if kind=='download':return benchmark.export_transcript(backend,identity)
    return {'reused':cached}
