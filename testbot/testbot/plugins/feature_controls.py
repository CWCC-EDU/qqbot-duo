"""Superuser controls; count input activations, never count outgoing messages."""
import asyncio,re,sys
from nonebot import on_command,logger
from nonebot.adapters.onebot.v11 import Bot,GroupMessageEvent,MessageEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot.adapters.onebot.v11 import Message
from qqbot_media.controls import controls

image_control=on_command('图像模式',permission=SUPERUSER,priority=0,block=True)
rate_control=on_command('每分钟上限',permission=SUPERUSER,priority=0,block=True)

@image_control.handle()
async def change_image(bot:Bot,event:MessageEvent,args:Message=CommandArg()):
    pieces=args.extract_plain_text().strip().split()
    gid=getattr(event,'group_id',None)
    if len(pieces)==2 and pieces[0].isdigit():gid=int(pieces.pop(0))
    if gid is None or int(gid)<=0:
        return await image_control.finish('请在目标群设置，或发送：图像模式 群号 旧版 / 快速 / 查看。')
    value=pieces[0] if len(pieces)==1 else '查看' if not pieces else ''
    aliases={'旧':'旧版','原版':'旧版','新':'快速','新版':'快速'};value=aliases.get(value,value)
    if not value or value in ('查看','状态'):
        mode=await asyncio.to_thread(controls().mode,bot.self_id,gid)
        return await image_control.finish(f'群{gid}的图像模式：{mode}。')
    if value not in ('快速','旧版'):return await image_control.finish('图像模式 快速 / 图像模式 旧版')
    try:await asyncio.to_thread(controls().set_mode,value,bot.self_id,gid)
    except (OSError,ValueError) as exc:
        logger.warning('图像模式未保存：'+type(exc).__name__);return await image_control.finish('没保存上，图像模式没改。')
    await image_control.finish(f'本机器人在群{gid}已用{value}图像。')

@rate_control.handle()
async def change_rate(bot:Bot,event:MessageEvent,args:Message=CommandArg()):
    pieces=args.extract_plain_text().strip().split()
    gid=getattr(event,'group_id',None)
    if len(pieces)==2 and pieces[0].isdigit():gid=int(pieces.pop(0))
    if gid is None:return await rate_control.finish('请在目标群设置，或发送：每分钟上限 群号 开 / 关 / 次数。')
    value=pieces[0] if len(pieces)==1 else '查看' if not pieces else ''
    try:
        if value in ('开','开启'):row=await asyncio.to_thread(controls().configure,bot.self_id,gid,enabled=True)
        elif value in ('关','关闭'):row=await asyncio.to_thread(controls().configure,bot.self_id,gid,enabled=False)
        elif value.isdigit():row=await asyncio.to_thread(controls().configure,bot.self_id,gid,limit=int(value))
        elif value in ('查看','状态'):row=await asyncio.to_thread(controls().group,bot.self_id,gid)
        else:return await rate_control.finish('每分钟上限 开 / 关 / 次数 / 查看')
    except ValueError:return await rate_control.finish('次数填1～10000。')
    except OSError:return await rate_control.finish('没保存上，原设置没改。')
    await rate_control.finish(f"本机器人在本群：每分钟{row['次数']}次，{'开启' if row['开启'] else '关闭'}。")

async def permitted(bot,event,notice=True):
    if not isinstance(event,GroupMessageEvent):return True
    if await SUPERUSER(bot,event):return True
    try:
        accepted=await asyncio.to_thread(controls().admit,bot.self_id,event.group_id,event.user_id,event.message_id,event.time)
        if accepted:return True
        if notice and await asyncio.to_thread(controls().notice,bot.self_id,event.group_id):
            await asyncio.wait_for(bot.send_group_msg(group_id=event.group_id,message='这分钟先歇一会儿。'),10)
    except Exception as exc:
        logger.warning('群功能限额检查失败，已跳过本次触发：'+type(exc).__name__)
    return False

def learning_control(text):
    return text.lstrip('#\\').startswith(('问答概率','问答触发概率','设置问答','本群问答','当前群问答','本地问答','设置本群问答','设置当前群问答','设置本地问答','模型分工','模型配置','开启群聊上下文','关闭群聊上下文','清空群聊上下文','群聊上下文状态','人格','查看人格','画像','我的画像','我的性格','学到的知识','知识详情','确认知识','删除知识','开启画像记录','关闭画像记录','清空我的画像','开启本群画像记录','关闭本群画像记录','群友画像','智能','云聊','开启云聊','关闭云聊','开启主动接话','关闭主动接话','主动接话状态','清空智能上下文','我的记忆','记住','忘记记忆','清空我的记忆'))

def classify(matcher,bot,event,state):
    module=matcher.module_name or '';text=event.get_plaintext().strip()
    if 'feature_controls' in module:return 'skip'
    if 'group_busy' in module:return 'skip'
    if module.endswith('bot_admin.quiet'):return 'skip'
    if 'nonebot_plugin_learning_chat' in module:
        source=sys.modules.get('testbot.plugins.nonebot_plugin_learning_chat')
        if not source:return 'skip'
        direct,stripped=source.assistant.addressed(event)
        if learning_control(stripped):return 'manage_group'
        return 'count' if direct else 'peek'
    if 'nonebot_plugin_clovers' in module:
        from nonebot_plugin_clovers import client
        # Its unconditional listener records @ statistics too. Only command
        # handles are feature activations; passive statistics must not count.
        for plugin in client.plugins:
            for handle in plugin.handles:
                if getattr(handle,'command','') and handle.match(text) is not None:return 'count'
        return 'skip'
    if 'testforFQJD' in module:
        duel=sys.modules.get('testbot.plugins.testforFQJD')
        if not duel:return 'skip'
        parsed=duel.parse_command(bot,event)
        if not parsed:return 'skip'
        action=parsed[0];manager=duel.russian_manager
        if action in ('取消','重载'):return 'manage_super'
        if action in ('开启决斗','关闭决斗','开启藏品','关闭藏品') or parsed[2]:return 'manage_group'
        game=manager.games.get(manager.key(bot,event))
        if game and action not in ('决斗','帮助','状态','战绩','胜榜','败榜'):
            uid=str(event.user_id);players={str(game.data.get(i)) for i in (1,2)}
            invited_target=str(game.data.get('at',0))
            if uid in players or (game.phase=='invited' and action in ('接受','拒绝') and (invited_target in ('0','None') or uid==invited_target)):return 'skip'
        return 'count'
    if '.russian' in module:
        command=state.get('_prefix',{}).get('command',('',))[0]
        source=sys.modules.get('testbot.plugins.russian')
        active=source.russian_manager._current_player.get(event.group_id,{}) if source else {}
        if command in ('接受','拒绝') and active and str(event.user_id) in {str(active.get(i)) for i in (1,2)}:return 'skip'
        return 'count'
    if 'nonebot_plugin_horserace' in module:
        command=state.get('_prefix',{}).get('command',('',))[0]
        source=sys.modules.get('testbot.plugins.nonebot_plugin_horserace')
        if command in ('赛马暂停','赛马清空','赛马事件重载'):return 'skip'
        if command in ('赛马加入','赛马开始','赛马重置') and source and event.group_id in source.race:return 'skip'
        return 'count'
    if module.endswith('testforsera') or module.endswith('testforseraphim'):
        source=sys.modules.get(module)
        if source and matcher.__class__ is getattr(source,'qn',None) and text:return 'skip'
    if 'nonebot_plugin_antiinsult' in module:
        source=sys.modules.get(module)
        if source and matcher.__class__ is getattr(source,'anti_abuse',None):
            return 'count' if any(word in text for word in source.curse_list['curse']) else 'skip'
    if not matcher.rule.checkers:return 'skip'
    return 'count'

@run_preprocessor
async def gate(bot:Bot,event:MessageEvent,matcher:Matcher,state:T_State):
    if not isinstance(event,GroupMessageEvent):return
    if await SUPERUSER(bot,event):return
    action=classify(matcher,bot,event,state)
    if action in ('manage_group','manage_super'):
        if await SUPERUSER(bot,event) or (action=='manage_group' and event.sender.role in ('admin','owner')):return
        action='count'
    if action=='skip':return
    if action=='peek':
        try:remaining=await asyncio.to_thread(controls().remaining,bot.self_id,event.group_id)
        except Exception:raise IgnoredException('本群功能限额暂不可用')
        if remaining==0:raise IgnoredException('本群当前分钟上限')
        return
    # Group busy limits run before the old independent minute quota.
    from testbot.plugins.group_busy import limit_feature, release_feature
    if not await limit_feature(bot,event,matcher,state):
        raise IgnoredException('本群群忙触发额度已满')
    if not await permitted(bot,event):
        release_feature(bot,event)
        raise IgnoredException('本群当前分钟上限')

_GROUP_BUSY_LIMIT_V2 = True
