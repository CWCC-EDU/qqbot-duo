import random

import apscheduler.job
from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import (
    GROUP,
    Bot,
    GroupMessageEvent,
    MessageSegment,
    Message,
)
from nonebot.typing import T_State
from nonebot.params import Depends, CommandArg
from .utils import is_number, get_message_at
from nonebot.log import logger
from .data_source import russian_manager


__zx_plugin_name__ = "决斗"

__plugin_usage__ = """发起决斗帮助：
    开启游戏：发起决斗[at](指定决斗对象，为空则所有群友都可接受决斗)
        示例：发起决斗@xxx
    接受对决：接受/拒绝
    开始对决：#[技能序号](默认随机)（轮流使用技能，30秒未使用另一方可使用‘结算’命令结束对决并胜利）
    认输：发送#认输
    结算：结算（当某一方30秒未开枪，可使用该命令强行结束对决并胜利）
    我的战绩：我的战绩
    排行榜：胜场排行/败场排行
    【注：同一时间群内只能有一场对决】

    克制表：
    （属性：克制|被克）
    水：火？|草
    火：草？|水
    草：水？|火
    暗：光|火
    光：暗|草
    ？：普？|水火草

    状态表
    （状态将会被下一状态覆盖）
    普通：正常状态
    疲惫：跳过一回合（-）
    防御：下回合内减伤（+）
    流血：持续时间内扣除血量约90/回合（-）
    顽强：受到致命伤害保留1点体力（+）
    荆棘：反伤30%（+）
    易伤：受到伤害增加40%（-）
    混乱：40%命中错误自己且禁用技能效果（-）
    时滞：此状态不会被覆盖
    迷惑：你将使用技能库中随机一个技能
"""

scheduler = require("nonebot_plugin_apscheduler").scheduler



russian = on_command(
    "发起决斗", permission=GROUP, priority=5, block=True
)

accept = on_command(
    "接受", permission=GROUP, priority=5, block=False
)

refuse = on_command(
    "拒绝", permission=GROUP, priority=5, block=False
)

shot = on_command(
    "#", aliases={"#使用", "#用","#",}, permission=GROUP, priority=5, block=True
)

settlement = on_command("#结算", aliases={"#认输"},permission=GROUP, priority=5, block=True)

record = on_command("我的战绩", permission=GROUP, priority=5, block=True)

russian_rank = on_command(
    "胜场排行",
    aliases={"胜利排行", "败场排行", "失败排行"},
    permission=GROUP,
    priority=5,
    block=True,
)




@accept.handle()
async def _(event: GroupMessageEvent):
    msg1,msg2 = await russian_manager.accept(event)
    if msg1:
        await accept.send(msg1)
        await accept.send(msg2)


@refuse.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = await russian_manager.refuse(bot, event)
    if msg :
        await refuse.send(msg)


@settlement.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = russian_manager.settlement(event)
    await settlement.send(msg)
    await russian_manager.end_game(bot, event)


# async def get_bullet_num(
#     event: GroupMessageEvent, arg: Message = CommandArg(), state: T_State = State()
# ):
#     msg = arg.extract_plain_text().strip()
#     if state["bullet_num"]:
#         return state
#     if msg in ["取消", "算了"]:
#         await russian.finish("已取消操作...")
#     try:
#         if russian_manager.check_game_is_start(event.group_id):
#             await russian.finish("决斗已开始...", at_sender=True)
#     except KeyError:
#         pass
#     if not is_number(msg):
#         await russian.reject("输入子弹数量必须是数字啊喂！")
#     if int(msg) < 1 or int(msg) > 6:
#         await russian.reject("子弹数量必须大于0小于7！")
#     return {**state, "bullet_num": int(msg)}


@russian.handle()
async def _(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State ,
    arg: Message = CommandArg(),
):
    msg = arg.extract_plain_text().strip()
    if msg == "帮助":
        await russian.finish(__plugin_usage__)
    try:
        if _msg := await russian_manager.check_current_game(bot, event):
            await russian.finish(_msg)
    except KeyError:
        pass
    # if msg:
    #     msg = msg.split()
    #     print(msg)
    #     if len(msg) == 1:
    #         msg = msg[0]
    #         if is_number(msg) and not (int(msg) < 1 or int(msg) > 6):
    #             state["bullet_num"] = int(msg)
    #     else:
    #         money = msg[1].strip()
    #         msg = msg[0].strip()
    #         if is_number(msg) and not (int(msg) < 1 or int(msg) > 6):
    #             state["bullet_num"] = int(msg)
    #         if is_number(money) and 0 < int(money) :
    #             state["money"] = int(money)
    state["at"] = get_message_at(event.json())


    at_ = state["at"]
    player1_name = event.sender.card or event.sender.nickname

    if at_:
        at_ = at_[0]
        at_player_name = await bot.get_group_member_info(
            group_id=event.group_id, user_id=int(at_)
        )
        at_player_name = (
            at_player_name["card"]
            if at_player_name["card"]
            else at_player_name["nickname"]
        )
        msg = (
            f"{player1_name} 向 {MessageSegment.at(at_)} 发起了决斗！请 {at_player_name} 在30秒内回"
            f"复‘接受’ or ‘拒绝’，超时此次决斗作废！"
        )
    else:
        at_ = 0
        msg = "若30秒内无人接受挑战则此次对决作废"

    _msg = russian_manager.ready_game(event, msg, player1_name, at_)
    await russian.send(_msg)


@shot.handle()
async def _(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    count = arg.extract_plain_text().strip()
    if is_number(count):
        count = int(count)
        if count > 4 or count < 0:
            await shot.finish(
                f"你不能使用{count}"
            )
    else:
        count = random.randint(0,4)
    await russian_manager.shot(bot, event, count)


@record.handle()
async def _(event: GroupMessageEvent):
    user = russian_manager.get_user_data(event)
    await record.send(
        f"决斗\n"
        f'胜利场次：{user["win_count"]}\n'
        f'失败场次：{user["lose_count"]}\n',
        at_sender=True,
    )


@russian_rank.handle()
async def _(event: GroupMessageEvent, state: T_State ):
    msg = await russian_manager.rank(state["_prefix"]["raw_command"], event.group_id)
    await russian_rank.send(msg)

# # 重置每日签到
# @scheduler.scheduled_job(
#     "cron",
#     hour=0,
#     minute=0,
# )
# async def _():
#     russian_manager.reset_gold()
#     logger.info("每日轮盘签到重置成功...")
# scheduler.add_job(run_every_day_from_program_start, "interval", days=1, id="xxx")
# apscheduler.job.Job.remove("xxx")