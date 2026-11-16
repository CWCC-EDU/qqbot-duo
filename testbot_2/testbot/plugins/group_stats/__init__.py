"""群词云和发言排行：后台聚合、独立分群、无需模型。"""
import asyncio,re,time
from collections import OrderedDict
from pathlib import Path
from nonebot import get_driver,get_bots,on_message,logger
from nonebot.message import event_preprocessor
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot,GroupMessageEvent,MessageSegment
from .store import Store,PERIODS
from .render import render

ROOT=Path(__file__).resolve().parents[3]/'data/group_stats'
_store=None;_queue=None;_worker=None;_busy=set();_last={};_dropped=0
_cache=OrderedDict()
def store():
    global _store
    if _store is None:_store=Store(ROOT)
    return _store
def parse(text):
    text=text.strip();plain=text.startswith('文字');text=text[2:] if plain else text
    match=re.fullmatch(r'(今日|今天|日|昨日|昨天|本周|周|上周|本月|月|上月|今年|本年|年度|年|去年)?(词云|群词云|发言排行|发言排行榜|发言排名)',text)
    if not match:return None
    label={'今天':'今日','日':'今日','昨天':'昨日','周':'本周','月':'本月','本年':'今年','年度':'今年','年':'今年'}.get(match[1],match[1] or '今日')
    return label,match[2] in ('词云','群词云'),plain
async def work():
    global _dropped
    while True:
        first=await _queue.get();batch=[first]
        if not isinstance(first,asyncio.Future):await asyncio.sleep(.2)
        while len(batch)<60:
            try:batch.append(_queue.get_nowait())
            except asyncio.QueueEmpty:break
        events=[item for item in batch if isinstance(item,tuple)]
        try:
            if events:await asyncio.to_thread(store().add,events)
            for item in batch:
                if isinstance(item,asyncio.Future) and not item.done():item.set_result(None)
        except Exception as exc:
            _dropped+=len(events);logger.error('群统计写入失败，本批未保存：'+type(exc).__name__)
            for item in batch:
                if isinstance(item,asyncio.Future) and not item.done():item.set_exception(exc)
        finally:
            for _ in batch:_queue.task_done()
def ensure_worker():
    global _queue,_worker
    if _queue is None:_queue=asyncio.Queue(maxsize=2000)
    if _worker is None or _worker.done():_worker=asyncio.create_task(work())
async def flush():
    ensure_worker();future=asyncio.get_running_loop().create_future();await _queue.put(future);await future
@event_preprocessor
async def collect(bot:Bot,event:GroupMessageEvent):
    global _dropped
    try:
        if str(event.user_id) in {*get_bots(),str(bot.self_id)}:return
        if parse(event.get_plaintext()) or event.get_plaintext().strip() in ('词云帮助','统计帮助','开启群统计','关闭群统计','群统计状态'):return
        # Only text segments enter tokenisation; photos/CQ codes never become
        # fake words, while every ordinary message counts as one utterance.
        text=event.get_plaintext()[:2500]
        name=event.sender.card or event.sender.nickname or str(event.user_id)
        ensure_worker()
        _queue.put_nowait((str(event.group_id),str(event.user_id),str(event.message_id),event.time,str(name),text))
    except asyncio.QueueFull:
        _dropped+=1
        if _dropped%100==1:logger.warning('群统计队列已满，部分消息未记录；可查询群统计状态')
    except Exception as exc:logger.warning('群统计收集跳过：'+type(exc).__name__)
async def query_rule(event:GroupMessageEvent):return parse(event.get_plaintext()) is not None or event.get_plaintext().strip() in ('词云帮助','统计帮助')
query=on_message(rule=Rule(query_rule),priority=5,block=True)
HELP='今日词云 / 本周词云 / 本月词云 / 年度词云\n今日发言排行 / 本周发言排行 / 本月发言排行 / 年度发言排行\n也支持昨日、上周、上月、去年；加“文字”看词频或文字榜。\n群管或超管：开启群统计 / 关闭群统计 / 群统计状态。\n从安装后开始，默认记录普通群消息；只保存每日计数，不存原句。'
@query.handle()
async def show(bot:Bot,event:GroupMessageEvent):
    text=event.get_plaintext().strip()
    if text in ('词云帮助','统计帮助'):await query.finish(HELP);return
    label,cloud,plain=parse(text);key=(bot.self_id,event.group_id)
    if key in _busy:return
    if time.monotonic()-_last.get(key,-100)<8:return
    _busy.add(key);_last[key]=time.monotonic()
    try:
        await asyncio.wait_for(flush(),12)
        data=await asyncio.to_thread(store().query,event.group_id,label)
        if not data['messages']:await query.send('这段时间还没有记录，先聊一会儿吧。');return
        if cloud and not data['words']:await query.send('有发言记录，不过还没有适合画词云的词。');return
        if plain:
            rows=[f'{w}：{n}' for w,n in list(data['words'].items())[:30]] if cloud else [f"{i}. {data['names'][uid]}：{n}条 / {chars}字" for i,(uid,n,chars) in enumerate(data['ranking'],1)]
            await query.send(f'{label}'+('词频' if cloud else '发言排行')+'\n'+'\n'.join(rows));return
        signature=(event.group_id,label,cloud,repr(data))
        if signature in _cache:raw=_cache[signature];_cache.move_to_end(signature)
        else:
            raw=await asyncio.wait_for(asyncio.to_thread(render,data,cloud),30)
            while _cache and sum(len(v) for v in _cache.values())+len(raw)>8_000_000:_cache.popitem(last=False)
            if len(raw)<=8_000_000:_cache[signature]=raw
        await asyncio.wait_for(query.send(MessageSegment.image(raw)),15)
    except Exception as exc:
        logger.warning('群统计图片生成或发送失败：'+type(exc).__name__)
        try:await asyncio.wait_for(query.send('统计图暂时没发出来，可以试试“文字'+text+'”。'),3)
        except Exception:pass
    finally:_busy.discard(key)
async def manage_rule(event:GroupMessageEvent):return event.get_plaintext().strip() in ('开启群统计','关闭群统计','群统计状态')
manage=on_message(rule=Rule(manage_rule),priority=4,block=True)
@manage.handle()
async def change(bot:Bot,event:GroupMessageEvent):
    if not (await SUPERUSER(bot,event) or event.sender.role in ('admin','owner')):await manage.finish('这个请群管来设置。');return
    command=event.get_plaintext().strip()
    await flush()
    if command!='群统计状态':await asyncio.to_thread(store().configure,event.group_id,command=='开启群统计')
    status='开着' if store().enabled(event.group_id) else '关着'
    await manage.finish(f'本群统计{status}。'+(f'\n本次进程未保存消息：{_dropped}条。\n数据：{store().db.stat().st_size//1024}KB' if command=='群统计状态' else ''))
@get_driver().on_shutdown
async def shutdown():
    if _queue is not None:
        try:await asyncio.wait_for(_queue.join(),10)
        except asyncio.TimeoutError:logger.warning('群统计退出时仍有未保存消息')
    if _worker is not None:
        _worker.cancel()
        try:await _worker
        except asyncio.CancelledError:pass
