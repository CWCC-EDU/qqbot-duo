"""每台机器人仅接收自己的完整决斗指令，管理操作在服务端校验权限。"""
import re
from nonebot import on_message
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import GROUP, GROUP_ADMIN, GROUP_OWNER, Bot, GroupMessageEvent
from .data_source import russian_manager
from .duel_manager import PlainText

GROUP_CONTROL=SUPERUSER | GROUP_ADMIN | GROUP_OWNER
ALIASES={'发起决斗':'决斗','发起决斗帮助':'帮助','决斗帮助':'帮助','发起决斗 帮助':'帮助',
         '决斗 帮助':'帮助','我的战绩':'战绩','胜场排行':'胜榜','胜利排行':'胜榜',
         '败场排行':'败榜','失败排行':'败榜','决斗文字':'文字','决斗图片':'图片',
         '文字模式':'文字','图片模式':'图片','重载决斗':'重载','决斗配置':'状态','取消决斗':'取消'}

def parse_command(bot,event):
    plain=event.get_plaintext().strip()
    options=russian_manager.group_options(bot,event)
    prefix=options['prefix']
    prefixed=plain.startswith(prefix)
    body=plain[len(prefix):].strip() if prefixed else plain
    if body == "决斗":return None  # Use 发起决斗; 快速决斗 has its own plugin.
    action=ALIASES.get(body,body)
    if not prefixed:
        if action=='决斗' and not options['invite_prefix']:pass
        elif action in ('接受','拒绝') and not options['reply_prefix']:pass
        else:return None
    # Directly addressing a robot lets same-prefix group settings be changed independently.
    mentions={str(segment.data.get('qq')) for segment in event.get_message() if segment.type=='at'}
    if mentions and str(bot.self_id) not in mentions and action!='决斗':return None
    if not prefixed and action in ('接受','拒绝') and russian_manager.key(bot,event) not in russian_manager.games:return None
    known=set(ALIASES)|set(ALIASES.values())|{'接受','拒绝','认输','结算','继续','随机','',
        '文字','图片','开启决斗','关闭决斗','开启藏品','关闭藏品','帮助','状态','重载','取消'}
    management=re.fullmatch(r'(设置前缀|邀请前缀|应答前缀)(?:\s+(\S+))?',body)
    if body in known or re.fullmatch(r'(?:使用|用)?\s*[0-9]+',body) is not None or management:
        return action,prefix,management
    return None

async def is_duel_command(bot:Bot,event:GroupMessageEvent):return parse_command(bot,event) is not None

duel_command=on_message(rule=Rule(is_duel_command),permission=GROUP,priority=4,block=True)

@duel_command.handle()
async def dispatch_duel(bot:Bot,event:GroupMessageEvent):
    parsed=parse_command(bot,event)
    if parsed is None:return
    action,prefix,management=parsed
    manager=russian_manager
    if management:
        if not await GROUP_CONTROL(bot,event):
            return await manager.reply(bot,event,PlainText('只有机器人超管、群主或群管理员可以设置前缀及前缀要求。'))
        command,value=management.groups()
        if command=='设置前缀':
            from .group_settings import valid_prefix
            if not valid_prefix(value):
                return await manager.reply(bot,event,PlainText(f'用法：{prefix}设置前缀 !；请输入单个可见符号，例如#、!或反斜杠。'))
            return await manager.set_group_option(bot,event,'prefix',value,authorized=True)
        if value not in ('开','关','开启','关闭','是','否'):
            return await manager.reply(bot,event,PlainText(f'用法：{prefix}{command} 开 或 {prefix}{command} 关。'))
        return await manager.set_group_option(bot,event,'invite_prefix' if command=='邀请前缀' else 'reply_prefix',value in ('开','开启','是'),authorized=True)
    controls={'开启决斗':('enabled',True),'关闭决斗':('enabled',False),
              '开启藏品':('collections',True),'关闭藏品':('collections',False)}
    if action in controls:
        allowed=await GROUP_CONTROL(bot,event)
        return await manager.set_group_option(bot,event,*controls[action],authorized=allowed)
    if action in ('重载','取消'):
        if not await SUPERUSER(bot,event):
            return await manager.reply(bot,event,PlainText('只有机器人超管可重载配置或强制取消决斗。'))
        if action=='重载':return await manager.reply(bot,event,PlainText(manager.rule_status()))
        return await manager.cancel_for_admin(bot,event)
    if action=='帮助':return await manager.help(bot,event)
    if action=='状态':return await manager.reply(bot,event,PlainText(manager.group_status(bot,event)))
    if action in ('文字','图片'):
        return await manager.set_display_mode(bot,event,'text' if action=='文字' else 'image')
    if not manager.group_options(bot,event)['enabled']:
        return await manager.reply(bot,event,PlainText('本群决斗已关闭，请超管、群主或群管理员使用 #开启决斗。'))
    if action=='决斗':
        targets=[segment.data.get('qq') for segment in event.get_message() if segment.type=='at' and str(segment.data.get('qq'))!=str(bot.self_id)]
        if len(targets)>1 or (targets and not str(targets[0]).isdigit()):
            return await manager.reply(bot,event,PlainText('请只@一位群友，不能邀请全体成员。'))
        return await manager.invite(bot,event,int(targets[0]) if targets else 0)
    if action=='接受':return await manager.accept(bot,event)
    if action=='拒绝':return await manager.refuse(bot,event)
    if action=='认输':return await manager.settle(bot,event,surrender=True)
    if action=='结算':return await manager.settle(bot,event)
    if action=='继续':return await manager.resume(bot,event)
    if action=='战绩':
        user=manager.get_user_data(event)
        return await manager.reply(bot,event,f"决斗\n胜利场次：{user['win_count']}\n失败场次：{user['lose_count']}")
    if action in ('胜榜','败榜'):
        return await manager.reply(bot,event,await manager.rank('败场排行' if action=='败榜' else '胜场排行',event.group_id))
    if action in ('','随机'):
        return await manager.shot(bot,event,None)
    if re.fullmatch(r'(?:使用|用)?\s*[0-4]',action):
        return await manager.shot(bot,event,int(action[-1]))
    return await manager.reply(bot,event,PlainText(f'请使用 {prefix}帮助 查看指令；选招为 {prefix}0～{prefix}4，随机为 {prefix}随机。'))
