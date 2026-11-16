"""Timed, group-local bot silence; independent of QQ's member mute permission."""
import asyncio
from contextvars import ContextVar
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from nonebot import logger,on_message
from nonebot.adapters.onebot.v11 import Bot,Event,GroupMessageEvent
from nonebot.exception import IgnoredException,MockApiException
from nonebot.message import event_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN,GROUP_OWNER
from nonebot.rule import Rule

START=('禁言机器人','暂时禁言机器人','机器人禁言')
STOP=('解除禁言机器人','取消禁言机器人','恢复机器人')
STATUS=('机器人禁言状态',)
CONTROL=ContextVar('quiet_control_reply',default=None)

class QuietStore:
    def __init__(self,path=Path('data/bot_admin/quiet.json'),clock=time.time):
        self.path=Path(path);self.clock=clock;self.lock=threading.RLock();self.entries={}
        if self.path.exists():
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw,dict):raise ValueError('机器人禁言配置格式错误')
            for key,value in raw.items():
                if not re.fullmatch(r'\d+:\d+',key) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError('机器人禁言配置含有无效记录')
                if value>self.clock():self.entries[key]=float(value)

    def key(self,bot_id,group_id):return f'{int(bot_id)}:{int(group_id)}'

    def remaining(self,bot_id,group_id):
        with self.lock:return max(0,self.entries.get(self.key(bot_id,group_id),0)-self.clock())

    def set(self,bot_id,group_id,seconds):
        with self.lock:
            current=self.clock()
            updated={k:v for k,v in self.entries.items() if v>current}
            key=self.key(bot_id,group_id)
            if seconds:updated[key]=current+seconds
            else:updated.pop(key,None)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,prefix='quiet-',suffix='.tmp',delete=False) as stream:
                    temporary=Path(stream.name)
                    json.dump(updated,stream,ensure_ascii=False,indent=2)
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,self.path)
            finally:
                if temporary is not None and temporary.exists():temporary.unlink()
            self.entries=updated

store=QuietStore()
locks={}

def parse_control(text):
    text=text.strip()
    if text in STOP:return 'stop',''
    if text in STATUS:return 'status',''
    for command in START:
        if text.startswith(command):return 'start',text[len(command):].strip()
    return None

def duration(text):
    if not text:return 30*60
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(秒钟|秒|s|sec|分钟|min|m|分|小时|时|h|天|d)?',text,re.I)
    if not match:raise ValueError('时间可以写：30、30min、30分钟、1h 或 10秒；不填默认30分钟。')
    unit=(match[2] or '分钟').lower()
    factor={'秒钟':1,'秒':1,'s':1,'sec':1,'分钟':60,'min':60,'m':60,'分':60,'小时':3600,'时':3600,'h':3600,'天':86400,'d':86400}[unit]
    seconds=float(match[1])*factor
    if not math.isfinite(seconds) or not 1<=seconds<=30*86400:
        raise ValueError('禁言时长请填写1秒～30天；解除请发“解除禁言机器人”。')
    return math.ceil(seconds)

def describe(seconds):
    seconds=math.ceil(seconds)
    if seconds%86400==0:return f'{seconds//86400}天'
    if seconds%3600==0:return f'{seconds//3600}小时'
    if seconds%60==0:return f'{seconds//60}分钟'
    return f'{seconds//60}分{seconds%60}秒' if seconds>=60 else f'{seconds}秒'

def is_muted(bot,group_id):return store.remaining(bot.self_id,group_id)>0

async def allowed(bot,event):
    return await SUPERUSER(bot,event) or event.sender.role in ('admin','owner')

async def is_control(event:GroupMessageEvent):return parse_control(event.get_plaintext()) is not None
control=on_message(rule=Rule(is_control),permission=SUPERUSER|GROUP_ADMIN|GROUP_OWNER,priority=0,block=True)

async def reply(bot,event,text):
    token=CONTROL.set((str(bot.self_id),str(event.group_id)))
    try:await asyncio.wait_for(bot.send(event,text),15)
    finally:CONTROL.reset(token)

@control.handle()
async def manage_quiet(bot:Bot,event:GroupMessageEvent):
    operation,value=parse_control(event.get_plaintext())
    # The same instance can service multiple bots; serialize persistence edits.
    lock=locks.setdefault('control',asyncio.Lock())
    async with lock:
        try:
            if operation=='start':
                seconds=duration(value)
                await asyncio.to_thread(store.set,bot.self_id,event.group_id,seconds)
                text=f'好，我安静{describe(seconds)}。'
            elif operation=='stop':
                active=is_muted(bot,event.group_id)
                await asyncio.to_thread(store.set,bot.self_id,event.group_id,0)
                text='我回来啦。' if active else '我现在能说话。'
            else:
                remaining=store.remaining(bot.self_id,event.group_id)
                text='本群机器人禁言剩余：'+describe(remaining)+'。' if remaining else '本群机器人没有被禁言。'
        except ValueError as error:text=str(error)
        except OSError:
            logger.exception('机器人禁言设置保存失败，原状态保留')
            text='没保存上，禁言设置没改。'
        await reply(bot,event,text)

@event_preprocessor
async def block_muted_event(bot:Bot,event:Event):
    group_id=getattr(event,'group_id',None)
    if group_id is None or not is_muted(bot,group_id):return
    if isinstance(event,GroupMessageEvent) and parse_control(event.get_plaintext()) and await allowed(bot,event):return
    # Avoid plugin side effects and cloud charges for new muted-group input.
    raise IgnoredException('机器人在本群暂时禁言中')

@Bot.on_calling_api
async def block_muted_send(bot:Bot,api:str,data:dict):
    group_id=data.get('group_id')
    if group_id is None or data.get('message_type')=='private' or api.startswith('send_private_'):return
    sends=api.startswith('send_group_') or api in ('send_msg','send_message','group_poke','send_poke')
    if not sends or not is_muted(bot,group_id):return
    if CONTROL.get()==(str(bot.self_id),str(group_id)):return
    # NoneBot's supported cancellation hook skips the actual adapter call.
    # No queue/retry: messages generated during silence are discarded.
    raise MockApiException(result={'message_id':0,'muted':True})
