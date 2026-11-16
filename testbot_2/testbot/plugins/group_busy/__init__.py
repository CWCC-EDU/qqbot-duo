"""Group busy coalescing for the two existing OneBot v11 projects."""
import asyncio
import base64
import contextvars
import datetime
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from nonebot import get_bots, get_driver, logger, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, Message, MessageSegment
from nonebot.exception import IgnoredException, MockApiException
from nonebot.matcher import Matcher, current_event, current_matcher
from nonebot.message import event_postprocessor, run_postprocessor, run_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from .core import Heat, Settings, Spool, RollingLimit, slots, peer_ids
from .render import read_local, sheet

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT/'data/group_busy'
_settings = None
_spool = None
heat = Heat()
limits = RollingLimit()
_runner = None
_bots = {}
_peers = set()
_peer_checked = -1000
_claimed = {}
_handled = {}
_locks = {}
_last = {}
_send_tasks = {}
_stopping = False

FORTUNE = {'求签','抽签','运势','再求一次','再抽一次','改签','查看求签','当前求签','查看签文'}
CONTROLS = ('群忙合并','设置群忙阈值','设置群忙间隔','设置群忙汇总','设置群忙定时','群忙限流','设置群忙限流','群忙状态','群忙帮助','群忙立即发送','群忙补发')

def settings():
    global _settings
    if _settings is None:_settings=Settings(DATA)
    return _settings

def spool():
    global _spool
    if _spool is None:_spool=Spool(DATA)
    return _spool

def key(bot,event):return str(bot.self_id),str(event.group_id)
def identity(event):return f'{event.time}:{event.user_id}:{event.message_id}'

def category(module, text):
    if not any(x in module for x in ('testforsera','testforseraphim','testforsqlplugin','nonebot_plugin_clovers','groupmate_waifu')):
        return None
    if text in FORTUNE:return '求签'
    if text=='签到':return '签到'
    match=re.fullmatch(r'(娶群友|透群友)(?:\s*@?\d*)?\s*',text)
    return match[1] if match else None

def ensure(bot=None):
    global _runner
    if bot is not None:_bots[str(bot.self_id)]=bot
    if not _stopping and (_runner is None or _runner.done()):
        # A task created inside a matcher otherwise inherits its event and may
        # mistake a combined result sheet for another output of that command.
        _runner=asyncio.create_task(ticker(),name='群忙合并发送',context=contextvars.Context())

def ordinary_match(matcher,event):
    """Only recognized feature commands are excluded; passive listeners are not commands."""
    module=matcher.module_name or ''
    if 'group_busy' in module:return True
    if 'word_bank' in module:
        import sys
        source=sys.modules.get(module)
        if source and matcher.__class__ is getattr(source,'wb_matcher',None):return False
        return bool(matcher.rule.checkers)
    if any(x in module for x in ('learning_chat','antirecall','antiinsult','media_accel')):
        return False
    if 'nonebot_plugin_clovers' in module:
        import sys
        source=sys.modules.get('nonebot_plugin_clovers')
        if source and hasattr(source,'client'):
            for plugin in source.client.plugins:
                for handle in plugin.handles:
                    if getattr(handle,'command','') and handle.match(event.get_plaintext().strip()) is not None:return True
        return category(module,event.get_plaintext().strip()) is not None
    # Most existing passive listeners have no rule. Regex/fullmatch/on_command do.
    return bool(matcher.rule.checkers)

def operation_kind(matcher,bot,event,state):
    module=matcher.module_name or '';text=event.get_plaintext().strip()
    if any(x in module for x in ('group_busy','feature_controls','help_center')) or module.endswith('bot_admin.quiet'):return 'skip'
    if category(module,text):return 'count'
    command=((state.get('_prefix') or {}).get('command') or ('',))[0] or text.split(' ',1)[0]
    if 'nonebot_plugin_horserace' in module:
        if command in ('赛马暂停','赛马清空','赛马事件重载'):return 'skip'
        source=sys.modules.get('testbot.plugins.nonebot_plugin_horserace')
        if command in ('赛马加入','赛马开始','赛马重置') and source and event.group_id in source.race:return 'skip'
        return 'count'
    if 'testforFQJD' in module:
        source=sys.modules.get('testbot.plugins.testforFQJD')
        if not source:return 'skip'
        parsed=source.parse_command(bot,event)
        if not parsed:return 'skip'
        action=parsed[0]
        if action in ('取消','重载','开启决斗','关闭决斗','开启藏品','关闭藏品') or parsed[2]:return 'skip'
        game=source.russian_manager.games.get(source.russian_manager.key(bot,event))
        if game and action not in ('决斗','帮助','状态','战绩','胜榜','败榜'):
            uid=str(event.user_id);players={str(game.data.get(i)) for i in (1,2)}
            target=str(game.data.get('at',0))
            if uid in players or (game.phase=='invited' and action in ('接受','拒绝') and (target in ('0','None') or uid==target)):return 'skip'
        return 'count'
    if module.endswith('.russian'):
        source=sys.modules.get('testbot.plugins.russian')
        active=source.russian_manager._current_player.get(event.group_id,{}) if source else {}
        if command in ('接受','拒绝') and active and str(event.user_id) in {str(active.get(i)) for i in (1,2)}:return 'skip'
        return 'count'
    if 'word_bank' in module:
        source=sys.modules.get(module)
        if source and matcher.__class__ is getattr(source,'wb_matcher',None):return 'skip'
    controls=sys.modules.get('testbot.plugins.feature_controls')
    if controls is not None:return controls.classify(matcher,bot,event,state)
    if 'learning_chat' in module:
        source=sys.modules.get('testbot.plugins.nonebot_plugin_learning_chat')
        if source:
            direct,stripped=source.assistant.addressed(event)
            if stripped.lstrip('#\\').startswith(('智能','云聊','开启','关闭','设置','人格','画像','记忆')):return 'manage_group'
            return 'count' if direct else 'skip'
        return 'skip'
    return 'count' if ordinary_match(matcher,event) else 'skip'

async def limit_feature(bot,event,matcher,state):
    if not isinstance(event,GroupMessageEvent) or await SUPERUSER(bot,event):return True
    if operation_kind(matcher,bot,event,state)!='count':return True
    k=key(bot,event)
    row=await asyncio.to_thread(settings().get,*k)
    if not row['限流开启'] or not heat.active(k,row)[0]:return True
    return limits.admit(k,identity(event),row['限流秒'],row['限流次数'])

def release_feature(bot,event):
    limits.release(key(bot,event),identity(event))

@run_preprocessor
async def before(bot:Bot,event:GroupMessageEvent,matcher:Matcher,state:T_State):
    if not isinstance(event,GroupMessageEvent):return
    ensure(bot)
    k=key(bot,event)
    if ordinary_match(matcher,event):_claimed[(k,identity(event))]=time.monotonic()
    try:row=await asyncio.to_thread(settings().get,*k)
    except (OSError,ValueError,sqlite3.Error) as exc:
        logger.warning('群忙设置暂不可用，本次按原方式执行：'+type(exc).__name__)
        return
    if row['模式']=='关闭':return
    active,*_=heat.active(k,row)
    if not active or await SUPERUSER(bot,event):return
    controls=sys.modules.get('testbot.plugins.feature_controls')
    if not getattr(controls,'_GROUP_BUSY_LIMIT_V2',False):
        if not await limit_feature(bot,event,matcher,state):raise IgnoredException('本群群忙触发额度已满')
    if category(matcher.module_name or '',event.get_plaintext().strip()):
        ident=(k,identity(event));now=time.monotonic()
        for old,stamp in list(_handled.items()):
            if now-stamp>600:_handled.pop(old,None)
        if ident in _handled:
            raise IgnoredException('同一消息已进入群忙结果队列，不重复执行')
        _handled[ident]=now
        try:
            if await asyncio.to_thread(spool().contains,*k,identity(event)):
                raise IgnoredException('同一消息已有持久结果，不重复执行')
        except (OSError,sqlite3.Error) as exc:
            _handled.pop(ident,None)
            logger.warning('待发数据库暂不可用，本次按原方式执行：'+type(exc).__name__)
            return
        matcher.state['_group_busy_wanted']=True
    if 'nonebot_plugin_learning_chat' in (matcher.module_name or ''):
        source=sys.modules.get('testbot.plugins.nonebot_plugin_learning_chat')
        if source:
            direct,stripped=source.assistant.addressed(event)
            # Management commands stay available regardless of whether addressed.
            controls=sys.modules.get('testbot.plugins.feature_controls')
            is_control=getattr(controls,'learning_control',lambda x:x.lstrip('#\\').startswith(('智能','云聊','开启','关闭','设置','人格','画像','记忆')))
            if not direct and not is_control(stripped):
                raise IgnoredException('群忙时暂停被动接话，主动呼叫仍可用')
    if 'word_bank' in (matcher.module_name or ''):
        source=sys.modules.get(matcher.module_name)
        if source and matcher.__class__ is getattr(source,'wb_matcher',None) and not event.is_tome():
            raise IgnoredException('群忙时暂停未被点名的词库自动回复')

@event_postprocessor
async def observe(bot:Bot,event:GroupMessageEvent):
    global _peers,_peer_checked
    if not isinstance(event,GroupMessageEvent):return
    ensure(bot);k=key(bot,event)
    now=time.monotonic();event_key=(k,identity(event))
    claimed=_claimed.pop(event_key,None)
    for old,stamp in list(_claimed.items()):
        if now-stamp>300:_claimed.pop(old,None)
    if claimed is not None:return
    if event.get_plaintext().strip().startswith(CONTROLS):return
    excluded={str(x) for x in settings().read().get('排除账号',[])}
    if now-_peer_checked>10:
        try:_peers=await asyncio.to_thread(peer_ids,ROOT,bot.self_id);_peer_checked=now
        except (OSError,sqlite3.Error):pass
    excluded.update(_peers)
    excluded.update(_bots);excluded.update(get_bots());excluded.add(str(bot.self_id))
    if str(event.user_id) in excluded:return
    row=await asyncio.to_thread(settings().get,*k)
    if row['模式']=='关闭':return
    heat.add(k,identity(event),event.user_id)
    heat.status(k,row)

async def fragments(message):
    result=[]
    for segment in Message(message):
        if segment.type=='text':
            if segment.data['text'].strip():result.append({'type':'text','text':segment.data['text']})
        elif segment.type=='at':
            result.append({'type':'text','text':'@'+str(segment.data['qq'])})
        elif segment.type=='image':
            value=str(segment.data.get('file') or segment.data.get('url') or '')
            if not value:raise ValueError('没有图片来源')
            if not value.startswith(('http://','https://','base64://')):
                # Snapshot local images now; a plugin may delete a temporary file later.
                raw=await asyncio.to_thread(read_local,value,ROOT)
                if raw is None:raise ValueError('本地图片无法读取，保留原发送')
                value='base64://'+base64.b64encode(raw).decode('ascii')
            result.append({'type':'image','file':value})
        elif segment.type=='reply':continue
        elif segment.type=='face':result.append({'type':'text','text':'〔表情〕'})
        else:raise ValueError('该消息类型不合并：'+segment.type)
    return result

@Bot.on_calling_api
async def collect(bot:Bot,api:str,data:dict):
    if api not in ('send_group_msg','send_msg') or data.get('group_id') is None:return
    try:event=current_event.get();matcher=current_matcher.get()
    except LookupError:return
    if not isinstance(event,GroupMessageEvent) or str(data['group_id'])!=str(event.group_id):return
    kind=category(matcher.module_name or '',event.get_plaintext().strip())
    if not kind:return
    k=key(bot,event)
    row=await asyncio.to_thread(settings().get,*k)
    active,*_=heat.active(k,row)
    # A command already being captured must stay together if a time slot ends mid-command.
    started=matcher.state.get('_group_busy_capture') or matcher.state.get('_group_busy_wanted')
    if not active and not started:return
    if await SUPERUSER(bot,event):return
    try:
        parts=await fragments(data.get('message',''))
        if not parts:return
        rid=await asyncio.to_thread(spool().append,*k,identity(event),str(event.user_id),
            event.sender.card or event.sender.nickname or str(event.user_id),kind,parts)
        matcher.state['_group_busy_capture']=True
        ensure(bot)
    except Exception as exc:
        logger.warning('群忙结果未入库，保留原发送：'+type(exc).__name__+': '+str(exc))
        return
    # Queued delivery receipt, never reused for recall/forward by these four features.
    raise MockApiException(result={'message_id':-int(rid),'group_busy_queued':True})

@run_postprocessor
async def completed(bot:Bot,event:GroupMessageEvent,matcher:Matcher):
    if not isinstance(event,GroupMessageEvent) or not matcher.state.get('_group_busy_capture'):return
    await asyncio.to_thread(spool().ready,*key(bot,event),identity(event))

async def image_inputs(rows):
    images={};sem=asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=3,follow_redirects=True) as client:
        async def load(row,index,part):
            async with sem:
                try:
                    value=part['file']
                    if value.startswith(('http://','https://')):
                        # Reuse the existing bounded QQ avatar cache when available.
                        try:
                            from qqbot_media import service,avatar_id
                            if avatar_id(value):
                                raw=await service().avatar(value)
                                if raw:images[row['id'],index]=raw;return
                        except ImportError:pass
                        async with client.stream('GET',value) as response:
                            response.raise_for_status();data=bytearray()
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data)>12_000_000:raise ValueError('图片超过12MB')
                            raw=bytes(data)
                    else:raw=await asyncio.to_thread(read_local,value,ROOT)
                    if raw:images[row['id'],index]=raw
                except Exception as exc:logger.warning('汇总图片读取失败：'+type(exc).__name__)
        await asyncio.gather(*(load(row,index,part) for row in rows
            for index,part in enumerate(json.loads(row['payload'])) if part['type']=='image'))
    return images

async def flush_group(sid,gid,force=False):
    k=(sid,gid);lock=_locks.setdefault(k,asyncio.Lock())
    if lock.locked():return False
    async with lock:
        bot=_bots.get(sid) or get_bots().get(sid)
        if not bot:return False
        row=await asyncio.to_thread(settings().get,sid,gid)
        pending=next((x for x in await asyncio.to_thread(spool().pending) if (x['sid'],x['gid'])==k),None)
        if not pending:return False
        elapsed=time.time()-pending['first']
        if not force and elapsed<row['汇总秒'] and pending['n']<row['汇总次数']:return False
        if time.monotonic()-_last.get(k,-1000)<5:return False
        batch,rows=await asyncio.to_thread(spool().take,sid,gid,row['汇总次数'])
        if not rows:return False
        _last[k]=time.monotonic()
        try:
            images=await asyncio.wait_for(image_inputs(rows),20)
            title='千鸟酱' if ROOT.name=='testbot' else '菲姆酱'
            raw=await asyncio.wait_for(asyncio.to_thread(sheet,rows,images,title),20)
            # No matcher context in this sender: cannot recapture the combined sheet.
            await asyncio.wait_for(bot.send_group_msg(group_id=int(gid),message=MessageSegment.image(raw)),15)
        except Exception as exc:
            await asyncio.to_thread(spool().finish,batch,'uncertain')
            logger.error(f'群忙汇总未确认发出｜群={gid}｜批次={batch}｜{type(exc).__name__}；结果已保留，用“群忙补发”重试')
            return False
        except BaseException:
            await asyncio.to_thread(spool().finish,batch,'uncertain')
            raise
        await asyncio.to_thread(spool().finish,batch,'sent')
        logger.info(f'群忙汇总已发送｜群={gid}｜{len(rows)}次操作')
        return True

async def ticker():
    while True:
        try:
            if _spool is not None:
                groups=await asyncio.to_thread(spool().pending)
                for item in groups:
                    k=(item['sid'],item['gid'])
                    previous=_send_tasks.get(k)
                    if previous is not None and not previous.done():continue
                    if previous is not None and not previous.cancelled() and previous.exception():
                        logger.error('群忙分群任务失败，下一轮继续：'+str(previous.exception()))
                    _send_tasks[k]=asyncio.create_task(flush_group(*k),context=contextvars.Context())
                for k,task in list(_send_tasks.items()):
                    if task.done():
                        if not task.cancelled() and task.exception():logger.error('群忙任务失败：'+str(task.exception()))
                        _send_tasks.pop(k,None)
            # Evaluate cooldowns even when the group falls completely silent.
            for k in list(heat.states):heat.status(k,await asyncio.to_thread(settings().get,*k))
        except Exception:logger.exception('群忙后台任务本轮失败，下一轮继续')
        await asyncio.sleep(2)

@get_driver().on_bot_connect
async def connected(bot:Bot):
    # Opening the spool also recovers records left by an interrupted process.
    await asyncio.to_thread(spool)
    await asyncio.to_thread(peer_ids,ROOT,bot.self_id)
    ensure(bot)

@get_driver().on_bot_disconnect
async def disconnected(bot:Bot):_bots.pop(str(bot.self_id),None)

@get_driver().on_shutdown
async def shutdown():
    global _stopping
    _stopping=True
    if _runner is not None:
        _runner.cancel()
        try:await _runner
        except asyncio.CancelledError:pass
    tasks=list(_send_tasks.values())
    for task in tasks:task.cancel()
    if tasks:await asyncio.gather(*tasks,return_exceptions=True)

manage=on_regex(r'^(?:'+ '|'.join(CONTROLS)+r')(?:\s|$)',priority=0,block=True)

HELP='''群忙合并（仅群管、群主、超管设置）
群忙合并 自动 / 常开 / 定时 / 自动定时 / 关闭
设置群忙阈值 60 20 4（60秒内20条，至少4人，立即触发）
设置群忙汇总 60 10（60秒或10次操作，先到就发）
群忙合并 60 10（同上，不改变当前开关）
设置群忙限流 60 10（群忙时60秒内最多10次新触发）
群忙限流 开 / 关（仅在群忙生效）
设置群忙定时 12:00-14:00 18:00-23:00
设置群忙定时 清空
群忙状态 / 群忙立即发送 / 群忙补发
默认关闭。定时按北京时间，每天循环，支持跨午夜。
合并求签、娶群友、透群友、签到；默认60秒或10次，上限32次。
限流按本机器人本群共享；决斗/赛马只计开场，已有对局后续操作放行。
群忙时暂停被动接话，@或叫机器人名字仍可聊。
超管私聊可在指令后加群号，例如：群忙合并 123456 自动。'''

@manage.handle()
async def control(bot:Bot,event:MessageEvent):
    # MessageEvent annotation is required for private superuser configuration.
    text=event.get_plaintext().strip();parts=text.split();command=parts.pop(0)
    superuser=await SUPERUSER(bot,event)
    gid=getattr(event,'group_id',None)
    explicit=False
    if parts and parts[0].isdigit():
        if gid is None:explicit=True
        elif command=='群忙合并':explicit=len(parts)==3 or len(parts)==2 and not parts[1].isdigit()
        elif command=='设置群忙阈值':explicit=len(parts)==4
        elif command in ('设置群忙汇总','设置群忙限流'):explicit=len(parts)==3
        elif command in ('设置群忙间隔','群忙限流'):explicit=len(parts)==2
        elif command=='设置群忙定时':explicit=len(parts)>=2
        elif command in ('群忙状态','群忙帮助','群忙立即发送','群忙补发'):explicit=True
    if explicit:
        if not superuser:return
        gid=int(parts.pop(0))
    if not superuser and not (isinstance(event,GroupMessageEvent) and event.sender.role in ('admin','owner')):return
    if command=='群忙帮助':await manage.finish(HELP)
    if gid is None:await manage.finish('私聊请在指令后加目标群号，例如：群忙合并 123456 自动。')
    if int(gid)<=0:await manage.finish('群号应为正整数。')
    ensure(bot);sid=str(bot.self_id);gid=str(gid)
    try:
        if command in ('群忙合并','设置群忙汇总') and len(parts)==2 and all(x.isdigit() for x in parts):
            row=await asyncio.to_thread(settings().set,sid,gid,汇总秒=int(parts[0]),汇总次数=int(parts[1]))
        elif command=='群忙合并':
            value=parts[0] if len(parts)==1 else ''
            value={'开启':'自动','开':'自动','关':'关闭','始终':'常开'}.get(value,value)
            row=await asyncio.to_thread(settings().set,sid,gid,模式=value)
        elif command=='设置群忙阈值':
            if len(parts)!=3:raise ValueError('格式：设置群忙阈值 秒数 消息条数 发言人数，例如60 20 4')
            row=await asyncio.to_thread(settings().set,sid,gid,统计秒=int(parts[0]),消息条数=int(parts[1]),最少人数=int(parts[2]))
        elif command=='设置群忙汇总':raise ValueError('格式：设置群忙汇总 秒数 操作次数，例如60 10；操作次数1～32')
        elif command=='设置群忙限流':
            if len(parts)!=2:raise ValueError('格式：设置群忙限流 秒数 触发次数，例如60 10')
            row=await asyncio.to_thread(settings().set,sid,gid,限流秒=int(parts[0]),限流次数=int(parts[1]))
        elif command=='群忙限流':
            if parts in (['开'],['开启']):row=await asyncio.to_thread(settings().set,sid,gid,限流开启=True)
            elif parts in (['关'],['关闭']):row=await asyncio.to_thread(settings().set,sid,gid,限流开启=False)
            elif not parts or parts in (['查看'],['状态']):row=await asyncio.to_thread(settings().get,sid,gid)
            else:raise ValueError('格式：群忙限流 开 / 关 / 查看')
        elif command=='设置群忙间隔':
            if len(parts)!=1:raise ValueError('格式：设置群忙间隔 60')
            row=await asyncio.to_thread(settings().set,sid,gid,汇总秒=int(parts[0]))
        elif command=='设置群忙定时':
            values=[] if parts==['清空'] else slots(' '.join(parts))
            if not parts:raise ValueError('请填写时段，或发送：设置群忙定时 清空')
            row=await asyncio.to_thread(settings().set,sid,gid,时段=values)
        elif command=='群忙立即发送':
            ensure(bot)
            sent=await flush_group(sid,gid,True)
            await manage.finish('本群汇总已发出。' if sent else '本次没有发出，请用“群忙状态”查看待发和未确认结果。')
        elif command=='群忙补发':
            n=await asyncio.to_thread(spool().retry,sid,gid)
            await manage.finish(f'已把最早一批{n}次操作放回待发队列。若上一张其实已收到，这次会重复显示。' if n else '本群没有待补发的结果。')
        else:row=await asyncio.to_thread(settings().get,sid,gid)
    except (ValueError,OSError) as exc:await manage.finish('没改动：'+str(exc))
    active,hot,n,users=heat.active((sid,gid),row)
    pending=next((x['n'] for x in await asyncio.to_thread(spool().pending) if (x['sid'],x['gid'])==(sid,gid)),0)
    failed=len(await asyncio.to_thread(spool().failed,sid,gid))
    error=settings().error
    await manage.finish(f"群{gid}：{row['模式']}，当前{'正在合并' if active else '正常发送'}。\n"
        f"最近{row['统计秒']}秒：{n}条、{users}人；门槛：{row['消息条数']}条、{row['最少人数']}人，达到即触发。\n"
        f"每{row['汇总秒']}秒汇总，满{row['汇总次数']}次操作提前发。\n"
        f"群忙限流：{'开' if row['限流开启'] else '关'}，{row['限流秒']}秒最多{row['限流次数']}次；当前已用{limits.used((sid,gid),row['限流秒'])}次。\n"
        f"每天时段：{'、'.join(row['时段']) or '未设置'}。\n待发{pending}次，发送未确认{failed}次。"
        + ('\n设置文件有错误，正在沿用上次有效配置：'+error if error else ''))
