import asyncio
import random

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
from ..database import dbcontrol

scheduler = require("nonebot_plugin_apscheduler").scheduler


russian1 = on_command(
    "快速决斗", permission=GROUP, priority=5, block=False
)

accept1 = on_command(
    "接受", permission=GROUP, priority=5, block=False
)

refuse1 = on_command(
    "拒绝", permission=GROUP, priority=5, block=False
)

if_notfighted = 1

@accept1.handle()
async def _(event: GroupMessageEvent):
    global if_notfighted
    try:
        msg,player1,player2,user_id1,user_id2 = russian_manager.accept(event)
        if msg and if_notfighted:
            if_notfighted = 0
            ran = random.randint(0,4)
            await accept1.send(msg, at_sender=True)
            msg2 = ("决斗开始！")
            await accept1.send(msg2)
            msg2 = (f"{player1}露出了"+random.choice(['坚毅',"锐利","芒果","瓦库瓦库","智慧","恐怖","舍我其谁"])
                   +"的"+random.choice(["神色！","眼神！","目光！"]))
            await accept1.send(msg2)
            await asyncio.sleep(0.1)
            msg2 = (f"{player1}率先"+random.choice(["掏出了","拿出了","扔出了","飞出了","发射了","爆出了","滚出了"
            ,"嘤嘤嘤出了","让嘉然关注了"]))+"她的"+random.choice(["左轮！","派蒙！",
            "我趣 初音未来！","菲姆酱？什么菲姆酱？","瓜！","亚撒西捏！","超级百万奥美噶邪恶的风暴！","胖次！","E=mc^2！","狗修金！",
            "塑料袋头套！","劫哥不要啊！","向晚球！","群主！","电能冲锋枪！","背背背背起了行囊！"])
            await accept1.send(msg2)
            await asyncio.sleep(0.1)
            if ran == 0 or ran == 1:
                winner_id = user_id1
                winner_name = player1
                loser_id = user_id2
                msg2 = (f"砰！{player2}"+random.choice(["中枪了！","开始发病了！","重伤倒地！","摘花了！","的屏幕碎了！","吃了琪亚娜做的胡桃后中毒了！","被考哥制裁了！",
                "金橘子了！","被封号了！","变成了嘉心糖！","被弹飞了","歪七七了！"]))
                await accept1.send(msg2)
                await asyncio.sleep(0.1)
                msg2 = (f"{player1}取得了胜利！菲姆酱和你的好感增加了！")
                await accept1.send(msg2)
            else:
                msg2 = (f"砰！{player2}"+random.choice(["后空翻114514度，躲过了攻击！","及时把头踢飞了，躲开了攻击！",
                f"和{player1}贴贴，变成了密接躲过了攻击！","的胖次发挥了防弹衣的作用！",f"的魅惑攻击使{player1}马枪了！"]))
                await accept1.send(msg2)
                await asyncio.sleep(0.1)
                if ran == 2 or ran == 3:
                    winner_id = user_id2
                    winner_name = player2
                    loser_id = user_id1
                    msg2 = (f"{player2}不甘示弱，" + random.choice([
                    "榨干了","贴脸两满喷獒犬带走了","卖掉了","创似了","吸干了","川普手风琴杀了","劲腰裸舞了","让嘉然拉黑了"
                    ])+f"{player1}！")
                    await accept1.send(msg2)
                    await asyncio.sleep(0.1)
                    msg2 = (f"{player2}取得了胜利！你在菲姆酱心中的形象变得高大了起来！")
                    await accept1.send(msg2)
                else:
                    winner_id = None
                    loser_id = None
                    msg2 = (f"然而{player2}")+random.choice(["似乎没开伤害显示！",'正在发店！',"被致盲了！","被外星人带走了！","正在看皮套人！","沉迷黄油！",
                    "转晕了！","正在学习量子速读！"])
                    await accept1.send(msg2)
                    await asyncio.sleep(0.1)
                    msg2 = (f"平局！")
                    await accept1.send(msg2)
            if winner_id:
                # print("yes1")
                result_winner = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(winner_id))
                result_loser = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(loser_id))
                if result_winner[-1] and result_loser[-1]:
                    # print("yes2")
                    winner_like = result_winner[0][0][0]
                    loser_like = result_loser[0][0][0]
                    # print(winner_like,loser_like)
                    if loser_like - 5 > 0:
                        rad = random.randint(1,3)
                        await dbcontrol(
                            r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(winner_like + rad, winner_id))
                        await dbcontrol(
                            r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(loser_like - rad, loser_id))
            await accept1.finish()
    except:
        pass

@refuse1.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = await russian_manager.refuse(bot, event)
    if msg:
        await refuse1.send(msg, at_sender=True)



@russian1.handle()
async def _(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State,
    arg: Message = CommandArg(),
):
    global if_notfighted
    msg = arg.extract_plain_text().strip()
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
        if at_ != event.user_id:
            msg = (
                f"{player1_name} 向 {MessageSegment.at(at_)} 发起了决斗！请 {at_player_name} 在30秒内回"
                f"复‘接受’ or ‘拒绝’，超时此次决斗作废！"
            )
            _msg = russian_manager.ready_game(event, msg, player1_name, at_,at_player_name)
            if_notfighted = 1
            await russian1.send(_msg)

