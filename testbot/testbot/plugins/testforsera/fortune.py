"""Explicit tier odds and uniform roles; Chidori project only."""
import asyncio,datetime,json,random,base64,time,threading
from collections import OrderedDict
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
from nonebot import on_fullmatch,logger
from nonebot.adapters.onebot.v11 import GROUP,GroupMessageEvent,MessageSegment

BASE=Path(__file__).parent
ASSETS=BASE/'fortune_cards'
MANIFEST=json.loads((ASSETS/'cards.json').read_text(encoding='utf-8-sig'))
TIERS=('大吉','中吉','小吉','吉','末吉','凶','大凶','彩蛋')
# Seven equal ordinary tiers: each 93/700. Easter egg: 49/700 = 7%.
WEIGHTS=(93,93,93,93,93,93,93,49)
ROLES=tuple(sorted({item['role'] for item in MANIFEST.values()}))
BY_PAIR={}
for name,item in MANIFEST.items():
    pair=(item['tier'],item['role'])
    if pair in BY_PAIR:raise ValueError('求签角色档位重复：'+str(pair))
    BY_PAIR[pair]=name
if not ROLES or set(BY_PAIR)!={(tier,role) for tier in TIERS for role in ROLES}:
    raise ValueError('求签映射必须包含每个角色各八档，不能缺档或重复')
CARDS=list(MANIFEST)
logger.info(f'千鸟求签新版｜{len(CARDS)}张｜{len(ROLES)}角色｜普通七档各93/700≈13.2857%｜彩蛋7%｜角色各1/{len(ROLES)}｜模块='+str(Path(__file__).resolve()))
missing=[name for name in CARDS if not (ASSETS/name).is_file()]
if missing:logger.error('千鸟求签图片缺失：'+'，'.join(missing))
record={}
lock=asyncio.Lock()
def today():return datetime.datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
def texts():return json.loads((BASE/'gacha.json').read_text(encoding='utf-8-sig'))
def notices():return json.loads((BASE/'fortune_notices.json').read_text(encoding='utf-8-sig'))
def choose():
    tier=random.choices(TIERS,weights=WEIGHTS,k=1)[0]
    role=random.choice(ROLES)
    return BY_PAIR[tier,role]
def cleanup(day):
    for uid,row in list(record.items()):
        if row['day']!=day:record.pop(uid,None)
def trace(action,event,row=None):
    detail=''
    if row:
        item=MANIFEST[row['card']]
        detail=f"｜角色={item['role']}｜签={item['tier']}｜第{row['count']}次｜图片={row['card']}"
    logger.info(f'千鸟求签｜{action}｜群={event.group_id}｜用户={event.user_id}'+detail)
# Cache only unchanged encoded file contents, not result messages or @ targets.
IMAGE_CACHE_BYTES=16_000_000
_image_cache=OrderedDict()
_cache_lock=threading.RLock()

def encoded_image(path):
    stat=path.stat();key=(str(path),stat.st_mtime_ns,stat.st_size)
    with _cache_lock:
        hit=_image_cache.get(key)
        if hit is not None:
            _image_cache.move_to_end(key);return hit,True
    raw=path.read_bytes()
    encoded='base64://'+base64.b64encode(raw).decode('ascii')
    if len(encoded)<=IMAGE_CACHE_BYTES:
        with _cache_lock:
            # Remove older versions of this file, preserving the byte bound.
            for old in list(_image_cache):
                if old[0]==str(path):_image_cache.pop(old,None)
            while _image_cache and sum(len(v) for v in _image_cache.values())+len(encoded)>IMAGE_CACHE_BYTES:
                _image_cache.popitem(last=False)
            _image_cache[key]=encoded
    return encoded,False

async def panel(row):
    began=time.perf_counter()
    encoded,hit=await asyncio.to_thread(encoded_image,ASSETS/row['card'])
    tier=MANIFEST[row['card']]['tier']
    wording=row['text'] if 'text' in row else random.choice(texts()[tier])
    logger.info(f"千鸟求签图片准备｜{row['card']}｜缓存={'命中' if hit else '未命中'}｜编码长度={len(encoded)}｜耗时={(time.perf_counter()-began)*1000:.1f}毫秒")
    return MessageSegment.text('你今天的运势是：\n')+MessageSegment.image(encoded)+MessageSegment.text(wording)

async def deliver(matcher,event,row):
    token=None;transport=None
    try:
        message=MessageSegment.at(event.user_id)+MessageSegment.text('\n')+await panel(row)
        # Existing media acceleration honours this scope. Do not decode/hash/
        # write/re-encode a static fortune PNG that is already ready to send.
        try:
            from qqbot_media.quote_archive import quote_transport
            transport=quote_transport;token=transport.set(True)
        except ImportError:pass
        trace('准备发送',event,row)
        began=time.perf_counter()
        await asyncio.wait_for(matcher.send(message),15)
        logger.info(f'千鸟求签发送接口返回｜群={event.group_id}｜用户={event.user_id}｜耗时={time.perf_counter()-began:.3f}秒｜跳过二次图片处理={transport is not None}')
    except Exception as exc:
        trace('读图或发送失败：'+type(exc).__name__,event,row);raise
    finally:
        if transport is not None and token is not None:transport.reset(token)
    trace('发送接口已返回成功',event,row)
    await matcher.finish()

gacha=on_fullmatch(('求签','抽签','运势','再求一次','再抽一次','改签'),permission=GROUP,priority=5,block=True)
regacha=gacha  # Preserve the parent plugin's imports; register only one handler.
@gacha.handle()
async def draw(event:GroupMessageEvent):
    async with lock:
        day=today();cleanup(day);uid=str(event.user_id)
        current=record.get(uid)
        if current and current['count']>=3:
            selected=None
            trace('次数用完，本次没有重新随机',event,current)
        else:
            selected={'day':day,'count':current['count']+1 if current else 1,'card':choose()}
            selected['text']=random.choice(texts()[MANIFEST[selected['card']]['tier']])
            record[uid]=selected.copy();trace('实际改签' if current else '实际新抽',event,selected)
    if selected is None:await gacha.finish(random.choice(notices()['次数用尽']))
    else:
        if selected['count']>1:
            try:await asyncio.wait_for(gacha.send(random.choice(notices()['改签中'])),3)
            except Exception as exc:logger.warning('改签过程提示未发出，继续发送签文：'+type(exc).__name__)
        await deliver(gacha,event,selected)

view=on_fullmatch(('查看求签','当前求签','查看签文'),permission=GROUP,priority=5,block=True)
@view.handle()
async def show(event:GroupMessageEvent):
    async with lock:
        day=today();cleanup(day);row=record.get(str(event.user_id))
        row=row.copy() if row else None
        trace('查看当前求签，不重新随机、不扣次数',event,row)
    if row is None:await view.finish('你今天还没有求过签呢，发“求签”抽一张吧。')
    else:await deliver(view,event,row)
