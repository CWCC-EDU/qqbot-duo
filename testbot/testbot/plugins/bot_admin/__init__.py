"""Group-local marriage controls and explicit, superuser-only announcements."""
import asyncio
import re
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

MANAGERS=SUPERUSER | GROUP_ADMIN | GROUP_OWNER
NTR_ON={'开启NTR','开启ntr','开启ntr','本群开启NTR','本群开启ntr'}
NTR_OFF={'关闭NTR','关闭ntr','关闭ntr','本群关闭NTR','本群关闭ntr'}
ntr_on=on_command('开启NTR',aliases=NTR_ON,permission=MANAGERS,priority=4,block=True)
ntr_off=on_command('关闭NTR',aliases=NTR_OFF,permission=MANAGERS,priority=4,block=True)
ntr_status=on_command('NTR状态',aliases={'ntr状态','#NTR状态','#ntr状态'},priority=4,block=True)
divorce=on_command('离婚',aliases={'分手','离婚','分手'},priority=4,block=True)
announce=on_command('公告',aliases={'公告','发布公告','发布公告','.notice'},permission=SUPERUSER,priority=3,block=True)
group_list=on_command('公告群列表',aliases={'公告群列表'},permission=SUPERUSER,priority=3,block=True)
announce_help=on_command('公告帮助',aliases={'公告帮助'},permission=SUPERUSER,priority=3,block=True)
locks={}

def marriage_data():
    # Imported only after the framework has loaded the canonical upstream plugin.
    from clovers_groupmate_waifu import waifu_data
    return waifu_data

@ntr_on.handle()
async def enable_ntr(event: GroupMessageEvent):
    data=marriage_data();group=data.group(str(event.group_id));old=group.ntr_enabled
    try:group.ntr_enabled=True;data.save()
    except Exception:
        group.ntr_enabled=old
        await ntr_on.finish('没保存上，NTR开关没改。')
    await ntr_on.finish('本群NTR开好了。')

@ntr_off.handle()
async def disable_ntr(event: GroupMessageEvent):
    data=marriage_data();group=data.group(str(event.group_id));old=group.ntr_enabled
    try:group.ntr_enabled=False;data.save()
    except Exception:
        group.ntr_enabled=old
        await ntr_off.finish('没保存上，NTR开关没改。')
    await ntr_off.finish('本群NTR关好了。')

@ntr_status.handle()
async def show_ntr(event: GroupMessageEvent):
    enabled=marriage_data().group(str(event.group_id)).ntr_enabled
    await ntr_status.finish('本群NTR：'+('开启' if enabled else '关闭')+'。')

@divorce.handle()
async def do_divorce(event: GroupMessageEvent):
    from clovers_groupmate_waifu import daily_limits
    from clovers_groupmate_waifu.guards import group_lock
    async with group_lock(event.group_id):
        data=marriage_data();group=data.group(str(event.group_id));uid=str(event.user_id)
        partner=group.couple.get(uid)
        if partner is None or partner==uid:await divorce.finish('你在本群还没有搭档，不用离婚啦。')
        try:daily_limits.divorce(data,event.group_id,uid)
        except Exception:
            await divorce.finish('没能保存，原来的配对还在。等一下再试吧。')
        wait=daily_limits.remaining_wait(event.group_id,uid)
    import math
    tip=f' 你要等{math.ceil(wait/60)}分钟才能再娶，零点随当天刷新。' if wait else ''
    await divorce.finish(MessageSegment.at(event.user_id)+' 配对解开了，双方恢复单身。'+tip)

def parse_announcement(args: Message):
    if not args or args[0].type!='text':raise ValueError('先填写目标群号，再填写公告正文。')
    first=args[0].data['text']
    match=re.match(r'^\s*(\d+(?:\s*[,，、]\s*\d+)*)\s+([\s\S]*)$',first)
    if not match:raise ValueError('用法：公告 群号1,群号2 公告正文；必须明确指定目标群。')
    ids=list(dict.fromkeys(int(v.strip()) for v in re.split('[,，、]',match[1])))
    if any(gid<=0 for gid in ids):raise ValueError('群号必须为正整数。')
    body=Message()
    if match[2].strip():body+=MessageSegment.text(match[2].lstrip())
    body+=args[1:]
    if not body:raise ValueError('公告正文不能为空。')
    return ids,body

async def deliver(bot: Bot, ids, body: Message):
    groups=await asyncio.wait_for(bot.get_group_list(),15)
    available={int(g['group_id']) for g in groups}
    missing=[gid for gid in ids if gid not in available]
    if missing:raise ValueError('机器人不在这些群中，未发送任何公告：'+','.join(map(str,missing)))
    success=[];failed=[]
    for index,gid in enumerate(ids):
        if quiet.is_muted(bot,gid):
            failed.append(gid);continue
        try:
            await asyncio.wait_for(bot.send_group_msg(group_id=gid,message=body),15)
            success.append(gid)
        except Exception:failed.append(gid)
        if index+1<len(ids):await asyncio.sleep(1)
    return success,failed

@announce.handle()
async def send_announcement(bot: Bot,event: MessageEvent,args: Message=CommandArg()):
    try:ids,body=parse_announcement(args)
    except ValueError as error:await announce.finish(str(error))
    lock=locks.setdefault(bot.self_id,asyncio.Lock())
    if lock.locked():await announce.finish('上一条公告还没发完，等一下再发。')
    try:
        async with lock:success,failed=await deliver(bot,ids,body)
    except ValueError as error:await announce.finish(str(error))
    except Exception:await announce.finish('没读到群列表，这次公告没发出去。')
    lines=['公告发送完成。','成功：'+(','.join(map(str,success)) or '无')]
    muted=[gid for gid in failed if quiet.is_muted(bot,gid)]
    if muted:lines.append('因本群机器人禁言而跳过：'+','.join(map(str,muted)))
    if failed:lines.append('失败或发送结果未知：'+','.join(map(str,failed))+'。重发前先看一眼群里，别发重了。')
    await announce.finish('\n'.join(lines))

@group_list.handle()
async def show_groups(bot: Bot):
    try:groups=await asyncio.wait_for(bot.get_group_list(),15)
    except Exception:await group_list.finish('读取群列表失败，请检查协议端连接。')
    text='公告可选群（当前机器人已加入）：\n'+'\n'.join(str(g['group_id'])+' '+str(g.get('group_name','')) for g in groups)
    # Split long replies to remain usable when the bot is in many groups.
    for offset in range(0,len(text),2500):await group_list.send(text[offset:offset+2500])
    await group_list.finish()

@announce_help.handle()
async def show_announce_help():
    await announce_help.finish('仅机器人超管可发公告。\n公告群列表：查看当前机器人加入的群。\n公告 123456 通知内容\n公告 123456,234567 通知内容\n群号用逗号分隔，只发给列出的群，不会默认全群广播。支持正文附带图片；逐群报告成功或失败。')

# Group-local temporary silence, including scheduled and in-flight output.
from . import quiet as quiet

from . import waifu_controls as waifu_controls
