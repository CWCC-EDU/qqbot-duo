from qqbot_media import render_mode,render_scoped
"""Permission-aware help for the actual complete bot, with text fallback."""
import asyncio
from collections import OrderedDict
from pathlib import Path
import re,time,sys
from nonebot import on_message,get_loaded_plugins,logger
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot,MessageEvent,GroupMessageEvent,MessageSegment
from testbot.plugins.persona_utils import load_persona
from .help_ui import render_help
from .compact_help import compact_sections

cache=OrderedDict()
locks={}
last={}

def request(text):
    text=text.strip()
    aliases={'智能帮助':'聊天','云聊帮助':'聊天','画像帮助':'聊天','公告帮助':'管理','赛马帮助':'赛马','小猪帮助':'小猪','语录帮助':'语录','防撤回管理':'管理'}
    if text.lstrip('#\\') in aliases:return aliases[text.lstrip('#\\')],False
    match=re.fullmatch(r'(文字)?(?:帮助|菜单|功能|机器人帮助|使用帮助)(?:\s+(决斗|聊天|小猪|管理|其他|赛马|日常|语录))?',text)
    if match:return match[2] or '全部',bool(match[1])
    if text in ('发起决斗帮助','决斗帮助'):return '决斗',False
    if text=='小猪帮助':return '小猪',False
    return None

def sections_for(name,level,topic,prefix='#',loaded=(),owner=False,quote=None,horse=None):
    loaded=set(loaded)
    sections=[]
    quote=quote or {}
    horse=horse or {}
    if topic=='全部':
        sections.append(('分项查看',['帮助 日常／帮助 小猪／帮助 决斗／帮助 聊天','帮助 赛马／帮助 语录／帮助 其他／帮助 管理','文字帮助｜图片发不出来时用这一条。']))
    if topic in ('全部','日常'):
        sections.append(('日常与群友',[
            '签到｜每天来打个招呼，积攒好感。',
            '当前好感／好感位次／排行｜看看相处进度。',
            f'@{name} 我爱你｜和我说一句悄悄话。',
            '求签／抽签／运势｜今日运势；改签／再求一次 重新求签。',
            '赛博硬币／抛硬币｜也能写“硬币 吃面条：2 吃米饭：1”。',
            '娶群友／本群cp／群友卡池｜今日搭档。',
            '离婚／分手｜解除配对；主动一方等2小时或零点刷新后再娶。',
            '透群友／群友设置｜查看本群每日上限与自己已用次数。',
            'NTR状态｜查看本群是否允许抢已有搭档。',
            '发病 名字｜给指定对象来一段发病文学。',
        ]))
        if 'testforseraphim' in loaded:
            sections.append(('菲姆酱的互动',['捕捉菲姆酱／刷礼物｜保留原来的互动与好感规则。']))
        if 'nonebot_plugin_morning' in loaded:
            sections.append(('早晚安与作息',['早安／晚安｜记录起床和入睡。','我的作息／群友作息／早晚安设置｜查看作息与当前规则。']))
        if 'testforcollection' in loaded:
            sections.append(('藏品',['藏品列表｜看看已经收集了什么。','查看藏品名字｜把“名字”换成实际藏品名。']))
        sections.append(('群内问答',[
            '问 问题 答 回答｜教我一组本群问答。',
            '模糊问 问题 答 回答／正则问 表达式 答 回答',
            '开启词条 问题／关闭词条 问题｜控制原词库中的回答。',
            '这套保留原词库；智能聊天的人工问答由管理员教学。',
        ]))
        sections.append(('表情与漂流瓶',[
            '表情包制作／表情详情 名字／表情搜索 词语',
            '扔瓶子 内容／捡瓶子／查看瓶子 编号',
            '评论瓶子 编号 内容／举报瓶子 编号',
            '我的瓶子／点赞瓶子 编号／删除瓶子 编号（自己的瓶子）',
        ]))
        if 'russian' in loaded:
            sections.append(('原来的快速决斗',['快速决斗 @群友｜接受／拒绝；由随机剧情直接决定胜负。','技能选招对战请用“发起决斗”，这是两个不同的玩法。']))
        sections.append(('决斗入口',[
            '发起决斗 @群友｜不指定对手时为开放邀请。',
            '接受／拒绝｜默认不要求前缀，以本群设置为准。',
            f'{prefix}0～{prefix}4｜按面板选招；{prefix}随机 随机选招。',
            f'{prefix}认输／{prefix}结算／{prefix}继续',
            '发起决斗帮助｜查看完整机制和本群设置。',
            '只有决斗使用各自的群内前缀，其他功能直接发指令。',
        ]))
    if topic in ('全部','赛马'):
        if 'nonebot_plugin_horserace' in loaded:
            sections.append(('赛马',[
                '赛马创建｜先在本群开一场比赛。',
                '赛马加入 小白｜每人给自己的马起名，每场只能加入一次。',
                f"赛马开始｜凑齐 {horse.get('min_player',2)}～{horse.get('max_player',8)} 人后开跑。",
                '随机事件会影响马匹；跑到终点决出胜者，也可能全员出局。',
                f"赛马重置｜距离比赛记录的时间满 {horse.get('setting_over_time',120)} 秒后可重置。",
                '赛马帮助／帮助 赛马｜只看这一项玩法。',
            ]))
            if level>=2:
                sections.append(('赛马管理 · 仅超管',['赛马暂停／赛马清空／赛马事件重载']))
        elif topic=='赛马':
            sections.append(('赛马',['这台机器人没有启用赛马，请找已启用赛马的千鸟酱。']))
    if topic in ('全部','语录'):
        if 'nonebot_plugin_quote' in loaded:
            q=quote.get('prefix','')
            lead='先 @机器人，再发下面的指令。' if quote.get('needat',True) else '直接发送下面的指令。'
            sections.append(('群聊语录',[
                lead,
                f'{q}上传｜回复一张聊天截图，把它收进本群语录。',
                f'{q}语录／{q}语录 关键词｜随机查看或搜索。',
                f'{q}标签｜回复语录图片，查看它的标签。',
                f'{q}addtag 标签／{q}deltag 标签｜回复语录图片，添加或移除标签。',
                '自动识字与批量识字目前停用；可以手动给图片加标签再搜索。',
            ]))
            if quote.get('fonts_ready'):
                sections.append(('制作语录卡',[f'{q}记录／{q}生成｜回复一条文字消息，制作语录图片。']))
            if quote.get('can_delete'):
                sections.append(('语录库管理',[f'{q}删除｜回复要移除的语录图片；你拥有本群语录删除权限。']))
        elif topic=='语录':
            sections.append(('群聊语录',['这台机器人没有启用群聊语录库。']))
    if topic in ('全部','小猪'):
        sections.append(('今日小猪',[
            '今日小猪｜每天固定一只，重复查看不会重抽。',
            '我的猪圈／小猪图鉴 页码｜收集进度与图片图鉴。',
            '昨日小猪／明日小猪／本周小猪',
            '今日烤猪｜把自己的今日小猪变成料理。',
            '烤群友 @群友／随机烤猪｜先抽自己的小猪。',
            '加急生火 @群友｜使用每天有限的加急机会。',
            '烤箱续火｜和当天参与的群友投票补充次数。',
            '随机小猪／找猪 关键词｜从外部图库找图，需要网络。',
            '猪圈日报｜查看已经出刊的群内日报。',
        ]))
    if topic in ('全部','其他'):
        extra=[]
        options={
            'nonebot_plugin_bread_shop':'买面包／吃面包／抢面包／送面包／面包猜拳；面包记录／查看面包／面包排行／面包帮助',
            'nonebot_plugin_batarot':'塔罗牌／占卜／塔罗牌解读',
            'nonebot_plugin_what2eat':'今天吃什么／今天喝什么／群菜单／基础菜单',
            'nonebot_plugin_homo_mathematician':'找规律 一串数字／臭数字 一个数字',
            'nonebot_plugin_person':'随个人｜从群友中随机挑一个人。',
            'nonebot_plugin_animalVoice':'兽音加密 内容／兽音解密 内容；切噜一下 内容／切噜～ 内容',
            'nonebot_plugin_crazy_thursday':'疯狂星期四｜也可以换成其他星期。',
        }
        for plugin,row in options.items():
            if plugin in loaded:extra.append(row)
        if extra:sections.append(('其他玩法',extra))
        interaction=[]
        if 'nonebot_plugin_poke' in loaded:interaction.extend(['戳一戳机器人｜试试原来的戳戳回复。','抓图 + 图片｜也可以回复图片发送抓图，补充戳戳图库。'])
        if 'echo' in loaded:interaction.append(f'@{name} echo 内容｜原样复述这段内容。')
        if 'nonebot_plugin_send' in loaded:interaction.append('.send 内容｜向超管反馈，会附上群名和发送者信息。')
        if interaction:sections.append(('小互动与反馈',interaction))
        passive=[]
        if 'nonebot_plugin_antiinsult' in loaded:passive.append('反嘴臭｜对发给机器人的屏蔽词作出回应，无需开启口令。')
        if 'nonebot_plugin_antirecall' in loaded:passive.append('防撤回｜群主或超管开启后，按原有设置保留撤回消息。')
        if 'nonebot_plugin_miao' in loaded:passive.append('回复口癖｜部分文字会带上原来的小尾巴，无需指令。')
        if passive:sections.append(('自动触发的功能',passive))
    if topic in ('全部','聊天'):
        sections.append(('聊天开关怎么选',['智能开启：聊天总开关，学过的问答和云聊都受它控制。','开启云聊：允许用 DeepSeek 回答，不会单独打开聊天总开关。','开启主动接话：顺带开启云聊并切到自然模式；聊天总开关仍需开启。','只想点名回复：智能开启 + 开启云聊；不需要开启主动接话。']))
        sections.append(('和我聊天',[
            f'@{name} 一句话｜也可以叫名字，或回复我的消息。',
            '智能状态／云聊状态／主动接话状态｜查看开关与调用情况。',
            '人格｜看看我的简单介绍。',
            '我的画像／我的性格 自我介绍｜查看或补充交流偏好。',
            '关闭画像记录／开启画像记录／清空我的画像',
            '记住 昵称=小明／我的记忆／忘记记忆 昵称',
            '清空我的记忆／清空智能上下文',
            '学到的知识／知识详情 编号｜本群记录的问答。',
            '计算 (12+8)*3／今天星期几｜@我即可。',
        ]))
    if level>=1 and topic in ('全部','聊天','管理'):
        sections.append(('群主、群管与超管',[
            '禁言机器人 [时长]｜本群暂时停止回复，默认30分钟；支持30min、1h、10秒。',
            '解除禁言机器人／机器人禁言状态｜提前恢复或查看剩余时间。',
            '开启云聊／关闭云聊｜只控制当前群。',
            '开启群聊上下文／关闭群聊上下文／清空群聊上下文｜本群近期文字参考。',
            '开启主动接话／关闭主动接话｜是否偶尔接群里的话。',
            '智能开启／智能关闭／智能模式 安静／智能模式 自然',
            '智能教学 问题 => 回答／智能删除 问题',
            '智能词库／智能重建索引／智能恢复',
            '确认知识 编号／删除知识 编号',
            '群友画像 @群友／开启本群画像记录／关闭本群画像记录',
            '开启NTR／关闭NTR｜只控制本群。',
            '设置娶群友上限 3／设置透群友上限 10｜每人每天，失败抽取也计数；0为关闭。',
            '设置离婚等待 120｜单位分钟，遇到北京时间零点刷新。',
            '删除词条 问题／查询词库 关键词｜管理原本的本群词库。',
            '删除词库｜清空当前词库，需按提示再次确认。',
        ]))
    if level>=1 and topic in ('全部','管理'):
        if 'nonebot_plugin_morning' in loaded:
            sections.append(('早晚安管理',['早安开启／早安关闭／晚安开启／晚安关闭','早安设置／晚安设置｜查看当前配置。']))
        if 'nonebot_plugin_what2eat' in loaded:
            sections.append(('吃喝小助手管理',['添加 菜名／移除 菜名｜管理本群菜单。','开启小助手／关闭小助手｜本群定时问候开关。','添加问候／删除问候｜按提示选择时段与内容。']))
    if (owner or level>=2) and topic in ('全部','管理') and 'nonebot_plugin_antirecall' in loaded:
        sections.append(('防撤回 · 仅群主与超管',['开启本群防撤回／关闭本群防撤回','开启绕过管理层／关闭绕过管理层｜是否跳过管理员的撤回。']))
    if level>=1 and topic in ('全部','小猪','管理'):
        sections.append(('小猪日报设置',['小猪日报 开启／小猪日报 关闭／小猪日报 状态｜只控制本群推送。']))
    if level>=1 and topic in ('全部','管理'):
        sections.append(('决斗的群内设置',[
            f'{prefix}开启决斗／{prefix}关闭决斗',
            f'{prefix}开启藏品／{prefix}关闭藏品',
            f'{prefix}设置前缀 !｜换成一个可见符号。',
            f'{prefix}邀请前缀 开／关；{prefix}应答前缀 开／关',
        ]))
    if level>=2 and topic in ('全部','管理','聊天','小猪'):
        sections.append(('仅机器人超管',[
            '公告群列表｜查看机器人已经加入的群。',
            '公告 群号1,群号2 正文｜只发给写出的群。',
            '公告帮助｜查看公告格式。',
            '云聊用量｜查看两台共享的调用次数与预算估算。',
            '同步小猪资源｜手动检查新增的小猪素材。',
            '图像模式 快速／旧版／查看｜本机器人在本群的绘图方式，默认快速。',
            '每分钟上限 开／关／次数／查看｜本机器人在本群的共享额度，默认关。',
            f'{prefix}重载决斗／{prefix}取消决斗',
        ]))
    if level>=2 and topic in ('全部','管理'):
        sections.append(('好感与词库 · 仅超管',[
            '增加好感 @群友 10／减少好感 @群友 10（也保留 @群友增加好感10）。',
            '删除全局词条 问题／查询全局词库 关键词',
            '开启全局词条 问题／关闭全局词条 问题',
            '删除全局词库／删除全部词库｜需要再次确认。',
            '审核｜进入原词库的逐条审核。',
        ]))
        if 'testforcollection' in loaded:sections.append(('藏品管理 · 仅超管',['授予藏品 @群友 名称 [数量]（也保留 @群友授予藏品名称）。','新增藏品 名称 | 别名 | 介绍 | 获得文案｜创建图鉴种类，不覆盖同名。']))
        if 'nonebot_plugin_namelist' in loaded:
            sections.append(('名单管理 · 仅超管',[
                '添加黑名单 @群友／删除黑名单 @群友／查看黑名单',
                '添加白名单 @群友／删除白名单 @群友／查看白名单',
                '切换名单｜在黑名单、白名单模式之间切换。',
            ]))
        if 'nonebot_plugin_antiinsult' in loaded:
            sections.append(('反嘴臭管理 · 仅超管',[
                '添加屏蔽词 词语／删除屏蔽词 词语',
                '启用飞妈令／禁用飞妈令｜切换原反嘴臭处理方式。',
                '解除屏蔽 账号／查看临时黑名单',
            ]))
        if 'nonebot_plugin_bottle' in loaded:
            sections.append(('漂流瓶管理 · 仅超管',[
                '漂流瓶详情 编号／恢复漂流瓶 编号',
                '删除瓶子评论 编号 QQ号／清空漂流瓶｜清空需再次确认。',
                '漂流瓶黑名单 QQ 账号／漂流瓶白名单 QQ 账号（也支持“群聊 群号”）',
            ]))
        if 'nonebot_plugin_what2eat' in loaded:sections.append(('基础菜单管理 · 仅超管',['加菜 菜名｜补充基础菜单。']))
        if 'nonebot_plugin_antirecall' in loaded:
            sections.append(('防撤回全局管理 · 仅超管',[
                '开启防撤回 群号／关闭防撤回 群号／查看防撤回群聊',
                '开启防撤回私聊／关闭防撤回私聊／查看防撤回私聊',
                '开启防撤回监听 转发目标群号／关闭防撤回监听',
                '添加防撤回监听 QQ号／删除防撤回监听 QQ号／查看防撤回监听',
                '重置开启名单｜清空防撤回开启列表。',
            ]))
    if topic=='管理' and level==0:
        return [('暂时打不开这一页',['这页留给群主、群管和超管。普通功能可以直接发「帮助」查看。'])]
    return sections

def manual_sections(manager,bot,event,level):
    from .testforFQJD.mechanics import help_text
    game=manager.games.get(manager.key(bot,event))
    if not game:manager.reload_rules()
    text=help_text(manager._rules(game) if game else manager.rule_store.current)
    prefix=manager.group_options(bot,event)['prefix']
    # The plain manual uses # as a template; actual group symbols are inserted.
    text=text.replace('#',prefix)
    result=[];title='决斗手册';rows=[];skip=False
    for line in text.splitlines():
        if line.startswith('【') and line.endswith('】'):
            if rows:result.append((title,rows));rows=[]
            title=line.strip('【】');skip=title=='群内管理' and level<1
        elif line and not skip:
            if line.startswith('管理员可用') and level<2:continue
            rows.append(line)
    if rows:result.append((title,rows))
    result.append(('本群设置',manager.group_status(bot,event).splitlines()))
    return result

async def permission_level(bot,event):
    if await SUPERUSER(bot,event):return 2
    if isinstance(event,GroupMessageEvent) and event.sender.role in ('admin','owner'):return 1
    return 0

async def send_help(bot,event,topic='全部',as_text=False,manager=None):
    level=await permission_level(bot,event)
    p=load_persona()
    if manager is None and isinstance(event,GroupMessageEvent):
        from .testforFQJD.data_source import russian_manager
        manager=russian_manager
    prefix=manager.group_options(bot,event)['prefix'] if manager else '#'
    loaded={plugin.name for plugin in get_loaded_plugins()}
    quote={};horse={};owner=isinstance(event,GroupMessageEvent) and event.sender.role=='owner'
    if topic=='决斗' and manager:
        sections=manual_sections(manager,bot,event,level)
    elif topic=='决斗':
        sections=[('决斗',['请到群里查看决斗帮助。'])]
    else:
        quote={}
        module=sys.modules.get('testbot.plugins.nonebot_plugin_quote')
        if module:
            config=module.plugin_config
            uid=str(event.user_id)
            group=str(getattr(event,'group_id',''))
            quote={'prefix':config.quote_startcmd,'needat':config.quote_needat,
                'fonts_ready':module.check_font(module.font_path,module.author_font_path),
                'can_delete':uid in config.global_superuser or uid in config.quote_superuser.get(group,[])}
        module=sys.modules.get('testbot.plugins.nonebot_plugin_horserace')
        horse={key:getattr(module,key) for key in ('min_player','max_player','setting_over_time')} if module else {}
        owner=isinstance(event,GroupMessageEvent) and event.sender.role=='owner'
        sections=sections_for(p.name,level,topic,prefix,loaded,owner,quote,horse)
    if not as_text:
        sections=compact_sections(p.name,level,topic,prefix,loaded,owner,quote,horse)
    text='\n\n'.join('【'+title+'】\n'+'\n'.join(rows) for title,rows in sections)
    async def send_text():
        for offset in range(0,len(text),1600):
            await asyncio.wait_for(bot.send(event,MessageSegment.text(text[offset:offset+1600])),15)
    if as_text:
        await send_text();return
    key=(render_mode(bot.self_id,getattr(event,'group_id',None)),p.name,level,topic,prefix,text)
    try:
        if key not in cache:
            cache[key]=await asyncio.wait_for(asyncio.to_thread(render_scoped,render_help,bot.self_id,getattr(event,'group_id',None),p.name,level,topic,sections),30)
            if len(cache)>18:cache.popitem(last=False)
        for data in cache[key]:
            await asyncio.wait_for(bot.send(event,MessageSegment.image(data)),15)
    except Exception as error:
        logger.warning('帮助图片未发送完成，改用文字（'+type(error).__name__+'）')
        await send_text()

async def is_help(event:MessageEvent):return request(event.get_plaintext()) is not None

help_command=on_message(rule=Rule(is_help),priority=1,block=True)

@help_command.handle()
async def show_help(bot:Bot,event:MessageEvent):
    topic,as_text=request(event.get_plaintext())
    key=(bot.self_id,event.get_session_id())
    # At most one help delivery per session; keep the small lock map bounded.
    if key not in locks:
        if len(locks)>=128:
            for old,lock in list(locks.items()):
                if not lock.locked():locks.pop(old);last.pop(old,None);break
        locks[key]=asyncio.Lock()
    if locks[key].locked() or time.monotonic()-last.get(key,-1e20)<3:return
    async with locks[key]:
        last[key]=time.monotonic()
        await send_help(bot,event,topic,as_text)
