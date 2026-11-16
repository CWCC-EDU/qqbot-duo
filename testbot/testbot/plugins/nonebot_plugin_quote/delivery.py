"""Bounded quote delivery; busy groups never enqueue repeated commands."""
import asyncio,random,time
from collections import OrderedDict
from pathlib import Path
from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment
from qqbot_media.quote_archive import Archive,quote_transport
from .quote_identity import download

BOT_ROOT=Path(__file__).resolve().parents[3]
SEND_TIMEOUT=15
LOAD_TIMEOUT=6
COOLDOWN=30
_active=set();_cooldown={};_seen=OrderedDict();_missing=OrderedDict()

def claim(bot,event):
    now=time.monotonic();key=(str(bot.self_id),str(event.group_id))
    identity=(*key,str(event.user_id),str(event.message_id),str(event.time))
    for cache in (_seen,_missing):
        while cache and next(iter(cache.values()))<now:cache.popitem(last=False)
    for old,until in list(_cooldown.items()):
        if until<now:_cooldown.pop(old,None)
    if identity in _seen or key in _active or key in _cooldown or len(_active)>=4:return None
    _seen[identity]=now+600
    while len(_seen)>4096:_seen.popitem(last=False)
    _active.add(key);return key

async def tell(bot,event,text):
    try:await asyncio.wait_for(bot.send(event,MessageSegment.text(text)),3)
    except Exception as exc:logger.warning('语录提示未发出：'+type(exc).__name__)

async def load(archive,ref):
    try:return await asyncio.to_thread(archive.load,ref)
    except FileNotFoundError:
        if str(ref).startswith('https://'):
            raw=await download(ref)
            return await asyncio.to_thread(archive.store,ref,raw)
        raise

async def send_quote(bot,event,record,index,query,quote_root,search='',automatic=False):
    key=claim(bot,event)
    if key is None:return
    try:
        group=str(event.group_id);prefix=''
        if search:
            result=query(search,group,index)
            if result['status']==1:pool=[result['msg']]
            elif result['status']==2 and not automatic:
                pool=list(record.get(group,[]));prefix='当前查询无结果，为你随机发一条。\n'
            else:pool=[]
        else:pool=list(record.get(group,[]))
        if not pool:
            if not automatic:await tell(bot,event,'当前无语录库' if not search else '没有找到这条语录。')
            return
        archive=await asyncio.to_thread(Archive,BOT_ROOT,quote_root)
        candidates=list(dict.fromkeys(str(ref) for ref in pool))
        candidates=[ref for ref in candidates if (str(BOT_ROOT),ref) not in _missing]
        selected=random.sample(candidates,min(16,len(candidates)))
        raw=None
        async def choose():
            for ref in selected:
                try:return (await load(archive,ref))[1]
                except (FileNotFoundError,ValueError) as exc:
                    _missing[(str(BOT_ROOT),ref)]=time.monotonic()+300
                    while len(_missing)>4096:_missing.popitem(last=False)
                    logger.warning('语录图片暂不可用，索引保留：'+str(ref)+'；'+type(exc).__name__)
            return None
        try:raw=await asyncio.wait_for(choose(),LOAD_TIMEOUT)
        except asyncio.TimeoutError:
            _cooldown[key]=time.monotonic()+COOLDOWN
            if not automatic:await tell(bot,event,'取语录有点慢，这次先停一下，稍后再试。')
            return
        except Exception as exc:
            logger.warning('语录归档读取失败：'+type(exc).__name__)
            if not automatic:await tell(bot,event,'语录暂时没取出来，原记录还在。')
            return
        if raw is None:
            if not automatic:await tell(bot,event,'这批语录的图片暂时没找到，请管理员检查一下。')
            return
        message=MessageSegment.text(prefix)+MessageSegment.image(raw)
        token=quote_transport.set(True)
        try:await asyncio.wait_for(bot.send(event,message),SEND_TIMEOUT)
        except asyncio.TimeoutError:
            _cooldown[key]=time.monotonic()+COOLDOWN
            logger.warning('语录发送超过15秒，停止等待；不重发，群内语录暂缓30秒。')
            if not automatic:await tell(bot,event,'这次发图超时了，先别连发，我不会自动重发。')
        except Exception as exc:
            _cooldown[key]=time.monotonic()+3
            logger.warning('语录发送失败，不重试：'+type(exc).__name__)
            if not automatic:await tell(bot,event,'这张语录没发出去，图片存档还在。')
        finally:quote_transport.reset(token)
    finally:_active.discard(key)
