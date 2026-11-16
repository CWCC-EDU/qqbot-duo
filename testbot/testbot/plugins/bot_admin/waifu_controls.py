"""Group-local limits, editable by the same managers as the NTR switch."""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.params import CommandArg
from . import MANAGERS

marry_limit = on_command('设置娶群友上限', permission=MANAGERS, priority=4, block=True)
touch_limit = on_command('设置透群友上限', permission=MANAGERS, priority=4, block=True)
wait_limit = on_command('设置离婚等待', aliases={'设置离婚冷却'}, permission=MANAGERS, priority=4, block=True)
status = on_command('群友设置', aliases={'群友次数', '娶群友设置'}, priority=4, block=True)


async def change(matcher, event, args, key):
    raw = args.extract_plain_text().strip()
    maximum = 10080 if key == '离婚后等待分钟' else 1000
    if not raw.isascii() or not raw.isdigit() or not 0 <= int(raw) <= maximum:
        await matcher.finish(f'填一个0～{maximum}的整数吧。' + ('单位是分钟。' if key == '离婚后等待分钟' else '0表示关闭这项玩法。'))
    from clovers_groupmate_waifu import daily_limits
    try:
        daily_limits.set_group(event.group_id, key, int(raw))
    except Exception:
        await matcher.finish('没保存上，原来的设置没改。')
    if key == '离婚后等待分钟':
        await matcher.finish(f'本群离婚后等{int(raw)}分钟；遇到零点就随当天刷新。已经开始的等待不变。')
    await matcher.finish(f'本群{key}改成{int(raw)}次了。')


@marry_limit.handle()
async def set_marry(event: GroupMessageEvent, args: Message = CommandArg()):
    await change(marry_limit, event, args, '每日娶群友次数')


@touch_limit.handle()
async def set_touch(event: GroupMessageEvent, args: Message = CommandArg()):
    await change(touch_limit, event, args, '每日透群友次数')


@wait_limit.handle()
async def set_wait(event: GroupMessageEvent, args: Message = CommandArg()):
    await change(wait_limit, event, args, '离婚后等待分钟')


@status.handle()
async def show_status(event: GroupMessageEvent):
    from clovers_groupmate_waifu import daily_limits
    import math
    cfg = daily_limits.settings(event.group_id)
    married = daily_limits.used(event.group_id, event.user_id, 'marry')
    touched = daily_limits.used(event.group_id, event.user_id, 'touch')
    lines = [f"本群每日上限：娶{cfg['每日娶群友次数']}次，透{cfg['每日透群友次数']}次。",
             f'你今天已用：娶{married}次，透{touched}次。',
             f"主动离婚后等{cfg['离婚后等待分钟']}分钟；北京时间零点刷新。"]
    wait = daily_limits.remaining_wait(event.group_id, event.user_id)
    if wait:
        lines.append(f'你还要等{math.ceil(wait / 60)}分钟才能再娶。')
    await status.finish('\n'.join(lines))
