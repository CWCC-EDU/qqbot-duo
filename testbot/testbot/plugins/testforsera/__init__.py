# -*- coding = utf-8 -*-
# @Time : 2022/8/9 18:27
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
from testbot.plugins.persona_utils import load_persona,affection_reply
import base64
import asyncio
import datetime
import json
import os
import random
import re
import PIL
from testbot.plugins.database import dbcontrol,getcollection

import apscheduler.job
from PIL import Image
from nonebot import on_command, require, on_regex, on_fullmatch, on_message
from nonebot.adapters.onebot.v11 import (
    GROUP,
    Bot,
    GroupMessageEvent,
    MessageSegment,
    Message,
)
from nonebot.permission import MESSAGE
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.params import Depends, CommandArg,  RegexGroup, RawCommand, EventPlainText, EventMessage
from nonebot.log import logger


ill = on_command("发病", permission=MESSAGE, priority=5, block=True)


@ill.handle()
async def _(bot: Bot, arg: Message = EventMessage()):
    who = str(arg)[2::]
    if len(who) <= 50:
        with open("testbot/plugins/testforsera/ill.json", 'r+', encoding="utf-8") as f:
            file = json.load(f)
            # print(file)
            line = random.choice(file)
            line = str(line)
            line = line.replace("【内容】", "{}".format(who)).replace("【现行日期-年】",
                                                                  "{}".format(datetime.datetime.now().year)).replace(
                "【现行日期-月】", "{}".format(datetime.datetime.now().month)).replace("【现行日期-日】", "{}".format(
                datetime.datetime.now().day))
            line = Message(line)
            await ill.finish(line)
    else:
        line = Message(random.choice(["别在这里发癫！", "就算你是汉谟拉比，你也不能在这立法典", "别冲了，注意身体", "？"]))
        await ill.finish(line)


help1 = on_fullmatch(("帮助", "菜单", "功能"), permission=MESSAGE, priority=12, block=True)


@help1.handle()
async def _():
    msg = (
        """功能列表（[方括号中为自定义内容，不需要真的加上方括号]）
基础功能：
签到
当前好感
排行
好感位次
查看藏品[名字]
藏品列表

问答：
[全局（可不填）][模糊|正则|@] 问 [xx] 答 [xx]
[开启|关闭|删除][全局（可不填）][模糊|正则|@]词条 [xx]

菲姆移植：
发病[内容]
决斗[@xxx]
发起决斗[@xxx]
发起决斗帮助
求签

开源功能：
表情包制作
疯狂[星期四|星期五 等等]
赛马创建/赛马加入[名称]/赛马开始/赛马重置
扔瓶子 xx|捡瓶子|查看瓶子 id|举报瓶子 id|评论瓶子 id xx
娶群友|娶群友@|本群cp|群友卡池|透群友|涩涩记录
离婚|NTR状态|开启NTR|关闭NTR（开关仅超管、群主、群管）
公告帮助|公告群列表（仅超管）
离婚|NTR状态|开启NTR|关闭NTR（开关仅超管、群主、群管）
公告帮助|公告群列表（仅超管）
早安/晚安
"""
    )
    await help1.finish(msg)


qn = on_message(rule=to_me(), priority=12, block=False)


@qn.handle()
async def _qn(msg: str = EventPlainText()):
    if str(msg) == "":
        await qn.finish(Message(load_persona().greeting))


# help2 = on_fullmatch("发起决斗帮助", permission=GROUP, priority=12, block=True)
# @help2.handle()

# async def _():
#     msg = (
#         """克制表：
# （属性：克制|被克）
# 水：火？|草
# 火：草？|水
# 草：水？|火
# 暗：光|火
# 光：暗|草
# ？：普？|水火草

# 状态表
# （状态将会被下一状态覆盖）
# 普通：正常状态
# 疲惫：跳过一回合（-）
# 防御：下回合内减伤（+）
# 流血：持续时间内扣除血量约90/回合（-）
# 顽强：受到致命伤害保留1点体力（+）
# 荆棘：反伤30%（+）
# 易伤：受到伤害增加40%（-）
# 混乱：40%命中错误自己且禁用技能效果（-）
# 时滞：此状态不会被覆盖
# 迷惑：你将使用技能库中随机一个技能
# """
#     )
#     await help2.finish(msg)

# Chidori fortune assets and wording are kept separate from other features.
from .fortune import gacha,regacha


def parse_string_to_dict(input_string):
    items = input_string.split()
    result_dict = {}

    if len(items) > 10:
        return None,1

    for item in items:
        parts = re.split(r'[：:]', item)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            if value.isdigit():
                result_dict[key] = int(value)
            else:
                return None,2
        else:
            return None,2

    return result_dict,0


def random_choice_weighted_key(input_dict):
    keys = list(input_dict.keys())
    weights = list(input_dict.values())

    chosen_key = random.choices(keys, weights=weights)[0]
    return chosen_key

Cybercoin = on_command("赛博硬币",aliases={"硬币", "抛硬币"}, permission=MESSAGE, priority=5, block=True)


@Cybercoin.handle()
async def _(bot: Bot, arg: Message = CommandArg()):
    input_string = str(arg)
    if len(input_string) <= 100:
        result_dict, state = parse_string_to_dict(input_string)
        if state == 1:
            line = Message(random.choice(["哪有那么多事情要决定","你太贪心啦","千鸟要算不过来啦","海王也没有这么多鱼啊哥"]))
            await Cybercoin.finish(line)
        elif state ==2:
            line = Message(random.choice(["格式不正确，正确格式为：事物1：数字 事物2：数字……"]))
            await Cybercoin.finish(line)
        elif result_dict is not None:
            random_key = random_choice_weighted_key(result_dict)
            line = Message(f"叮~投硬币的结果是：{random_key}\n")
            rad = random.choice(["合你的心意吗？","要再来一次吗？","不错哦","加油"])
            line = line + rad
            await Cybercoin.finish(line)
    else:
        line = Message(random.choice(["太长啦","？你莫不是特地过来消遣洒家","？在写小作文？"]))
        await Cybercoin.finish(line)


love = on_fullmatch("我爱你", rule=to_me(), permission=GROUP, priority=12, block=True)


@love.handle()
async def _love(bot: Bot,event: GroupMessageEvent):
    # 读取JSON文件
    user_like = -1
    user_id = event.user_id
    result = await dbcontrol(r"SELECT * FROM user_sign WHERE user_id = {}".format(user_id))
    try:
        user_like = result[0][0][2]
    except:
        if user_like == -1:
            user_like = 0


    await love.finish(MessageSegment.text(affection_reply(user_like)))
