# -*- coding = utf-8 -*-
# @Time : 2024/2/11 15:10
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
from testbot.plugins.persona_utils import affection_reply
import asyncio
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
from nonebot.params import Depends, CommandArg, RegexGroup, RawCommand, EventPlainText, EventMessage
from nonebot.log import logger

from testbot.plugins.database import dbcontrol

catch = on_fullmatch("捕捉菲姆酱",  permission=MESSAGE, priority=12, block=True)


@catch.handle()
async def _catch(msg: str = EventPlainText()):
    # 读取JSON文件
    with open('catch.json', 'r', encoding='utf-8') as file:
        texts = json.load(file)

    def random_choice_from_list(text_list):
        return random.choice(text_list) if text_list else None

    thresholds = sorted(map(int, texts.keys()))

    rand = random.randint(0, 100)

    for threshold in thresholds:
        if threshold >= rand:
            selected_text = random_choice_from_list(texts[str(threshold)])
            if selected_text:
                await catch.finish(selected_text)
                break
    else:
        selected_text = "哎呀，出错了"
        await catch.finish(selected_text)


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


# user_like = 2000
#
# with open('love.json', 'r', encoding='utf-8') as file:
#     texts = json.load(file)
#
# def random_choice_from_list(text_list):
#     return random.choice(text_list) if text_list else None
#
# thresholds_ = sorted(map(int, texts.keys()))
# thresholds = thresholds_[::-1]
#
# rand = user_like
#
# ran = random.randint(1, 100)
# if ran <= 25 and rand >= int(thresholds[-1]):
#     rand = random.randint(1, 1999)
#
# print(rand)
#
# for threshold in thresholds:
#     if rand >= threshold:
#         selected_text = random_choice_from_list(texts[str(threshold)])
#         if selected_text:
#             split_strings = selected_text.split('\n')
#             for msg in split_strings:
#                print(msg)
#             break
# else:
#     selected_text = "哎呀，出错了"
#     print(selected_text)


record = {}
gift = on_fullmatch(("刷礼物"), permission=GROUP, priority=5, block=True)
path_ = os.path.abspath("testbot/plugins/testforseraphim/99.jpg")
@gift.handle()
async def _gift(event: GroupMessageEvent):
    global record
    global file_name_list
    global path
    date = datetime.date.today().strftime("%Y%m%d")
    with open('gift.txt', 'r') as file:
        # 读取文件中的第一行并转换为整数
        gifts = int(file.readline().strip())

    if record.__contains__(f"{event.user_id}"):
        if int(record[f"{event.user_id}"][-1]) <=5:
            randd = random.randint(1000,2000)
            gifts = gifts + randd
            with open('gift.txt', 'w') as file:
                # 将数字转换为字符串并写入文件
                file.write(str(gifts))
            rec = int(record[f"{event.user_id}"][-1])+1
            axis = {f"{event.user_id}": date + f"{rec}"}
            record.update(axis)
            await gift.finish(
                MessageSegment.image(file=rf"file:///{path_}") +
                "谢谢支持！菲姆酱爱你哟！\n人气增加：{}\n当前人气：{}".format(randd, gifts)
            )

        else:
            await gift.finish(
                "你今天已经使用过该功能了！"
            )

    else:
        randd = random.randint(1000, 2000)
        gifts = gifts + randd
        with open('gift.txt', 'w') as file:
            # 将数字转换为字符串并写入文件
            file.write(str(gifts))
        axis = {f"{event.user_id}": date + "1"}
        record.update(axis)
        await gift.finish(
            MessageSegment.image(file=rf"file:///{path_}")+
            "谢谢支持！菲姆酱爱你哟！\n人气增加：{}\n当前人气：{}".format(randd,gifts)
        )

