# -*- coding = utf-8 -*-
# @Time : 2022/8/9 18:27
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
from testbot.plugins.persona_utils import load_persona,affection_reply
import base64
import datetime
import json
import os
import random
import re
import PIL

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
求签
赛博硬币 目标1：权重 目标2：权重……
决斗@
发起决斗@
娶群友

问答：
[全局（可不填）][模糊|正则|@] 问 [xx] 答 [xx]
[开启|关闭|删除][全局（可不填）][模糊|正则|@]词条 [xx]

开源功能：
表情包制作
疯狂星期四
扔瓶子 xx|捡瓶子|查看瓶子 id|举报瓶子 id|评论瓶子 id xx
"""
    )
    await help1.finish(msg)


qn = on_message(rule=to_me(), priority=12, block=False)


@qn.handle()
async def _qn(msg: str = EventPlainText()):
    if str(msg) == "":
        await qn.finish(Message(load_persona().greeting))


record = {}
path = "data/gacha"
file_name_list = os.listdir(path)

gacha = on_fullmatch(("求签", "抽签", "运势"), permission=GROUP, priority=5, block=True)


@gacha.handle()
async def _(event: GroupMessageEvent):
    global record
    global file_name_list
    global path
    rand = random.choice(file_name_list)
    rand_ = path + '\\' + rand
    path_ = os.path.abspath(rand_)
    await gacha.finish(
        MessageSegment.at(event.user_id) + MessageSegment.text('\n') +
        MessageSegment.image(file=rf"file:///{path_}")
    )


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
            line = Message(random.choice(["哪有那么多事情要决定","你太贪心啦","菲姆要算不过来啦","海王也没有这么多鱼啊哥"]))
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

