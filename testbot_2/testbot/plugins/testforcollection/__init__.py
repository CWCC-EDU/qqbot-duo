# -*- coding = utf-8 -*-
# @Time : 2022/7/29 23:22
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
import json

import nonebot
import sqlite3
import nonebot
import sqlite3
from nonebot import on_fullmatch, on_command, on_regex
from nonebot.adapters import Message
from nonebot.params import EventMessage, CommandArg, RegexMatched, RegexGroup
import re
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent
from nonebot.permission import SUPERUSER
from testbot.plugins.database import dbcontrol,givecollection,getcollection
import datetime
import random
from nonebot import get_bot

driver: nonebot.Driver = nonebot.get_driver()
config: nonebot.config.Config = driver.config


@driver.on_startup
async def connect_to_coll_sqlite():
    con = sqlite3.connect(r"database\collection.db")
    print("数据库创建成功!")
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS collection(
    _id INTEGER PRIMARY KEY NOT NULL ,
    collection_id INTEGER NOT NULL DEFAULT 0,
    collection_name TEXT NOT NULL DEFAULT '',
    collection_nickname TEXT NOT NULL DEFAULT '',
    collection_introduction TEXT NOT NULL DEFAULT '',
    collection_get TEXT NOT NULL DEFAULT '')
    """)
    print("藏品映射表创建成功！")
    cur.close()
    con.commit()
    con.close()


# test = on_command("测试", rule=None, priority=7)
# @test.handle()
# async def _(message: Message = EventMessage()):
#     # cqcode = Message(message)
#     # print(cqcode)
#     # user_id = 0
#     # givecollection(user_id,"测试2")
#     pass


getcollection_ = on_regex(r"(\[CQ:at,qq=\d+\]\s?|@\d+)授予藏品(\S+)", rule=None,permission=SUPERUSER, priority=7)
@getcollection_.handle()
async def _(message: Message = EventMessage(), args=RegexGroup()):
    user_id = 0
    user_get = 0
    # try:
    # print(args)
    user_id = re.findall(r"\d+",args[0])
    user_id = int(user_id[0])
    user_get = str(args[1])
    # print(user_collection)
    nickname = await  get_bot().get_stranger_info(user_id=user_id)
    nickname = nickname["nickname"]
    if nickname:
        # user_collection = dbcontrol('SELECT user_collection FROM user_collection WHERE user_id = {}'.format(user_id))
        # if user_collection[0]:
        #     # print(user_collection[0][0][0])
        #     collection_dict = eval(user_collection[0][0][0])
        #     collection_id = dbcontrol('SELECT collection_id FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(user_get,user_get),"collection.db")
        #     # print(collection_id)
        #     if collection_id[-1]:
        #         collection_id = collection_id[0][0][0]
        #         collection_num = str(collection_id) + "number"
        #         collection_day = str(collection_id) + "day"
        #         collection_exist = collection_dict.get(collection_num)
        #         # print(collection_exist)
        #         if collection_exist:
        #             collection_dict[collection_num] =collection_exist + 1
        #         else:
        #             collection_dict[collection_num] = 1
        #             collection_dict[collection_day] = date
        #         collection_dict = json.dumps(collection_dict)
        #         dbcontrol(r"UPDATE user_collection SET user_collection = '{}' WHERE user_id={}".format(collection_dict,user_id))
        #         await getcollection_.finish("给{}{}成功！".format(nickname, user_get))
        #     else:
        #         await getcollection_.finish("您输对了吗")
        # else:
        #     collection_dict = dict()
        #     collection_id = dbcontrol(
        #         'SELECT collection_id FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(
        #             user_get, user_get), "collection.db")
        #     collection_id = collection_id[0][0][0]
        #     # print(collection_id)
        #     collection_num = str(collection_id) + "number"
        #     collection_day = str(collection_id) + "day"
        #     if collection_id[-1]:
        #         collection_exist = collection_dict.get(collection_num)
        #         if collection_exist:
        #             collection_dict[collection_num] = collection_exist + 1
        #         else:
        #             collection_dict[collection_num] = 1
        #             collection_dict[collection_day] = date
        #         collection_dict = json.dumps(collection_dict)
        #         print(collection_dict)
        #         dbcontrol(r"INSERT INTO user_collection (user_id,user_collection) values ({},'{}')".format(user_id,collection_dict))
        #         await getcollection_.finish("给{}{}成功！".format(nickname,user_get))
        #     else:
        #         await getcollection_.finish("您输对了吗")
        result = await getcollection(user_id, user_get,if_can_reget= True)
        # print(result)
        if result:
            await getcollection_.finish("给{}{}成功！".format(nickname,user_get))
        else:
            await getcollection_.finish("您输对了吗")
    else:
        await getcollection_.finish("您真的输对qq号了吗")
    # except:
    #     pass

seecollection = on_regex(r"查看藏品(\S+)", rule=None, priority=7)
@seecollection.handle()
async def _(event: GroupMessageEvent,message: Message = EventMessage(), args=RegexGroup()):
    user_id = event.user_id
    user_get = str(args[0])
    # print(user_get)
    user_collection = await dbcontrol('SELECT user_collection FROM user_collection WHERE user_id = {}'.format(user_id))
    print(user_collection[-1])
    if user_collection[-1]:
        collection_dict = eval(user_collection[0][0][0])
        collection_id = await dbcontrol('SELECT collection_id,collection_introduction,collection_name FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(user_get,user_get),"collection.db")
        # print(collection_id)
        if collection_id[-1]:
            collection_introduction =collection_id[0][0][1]
            collection_name = collection_id[0][0][2]
            collection_id = collection_id[0][0][0]
            collection_num = str(collection_id) + "number"
            collection_day = str(collection_id) + "day"
            collection_exist = collection_dict.get(collection_num)
            collection_date = collection_dict.get(collection_day)
            # print(collection_exist)
            if collection_exist:
                await seecollection.finish("「{}」\n{}\n拥有{}\n首次获得{}".format(collection_name,collection_introduction,collection_exist,collection_date))
            else:
                await seecollection.finish("you have no this")

        else:
            await seecollection.finish("您输对了吗")
    else:
        await seecollection.finish("no result")


seecollections = on_regex(r"藏品列表", rule=None, priority=7)
@seecollections.handle()
async def _(event: GroupMessageEvent,message: Message = EventMessage(), args=RegexGroup()):
    user_id = event.user_id
    # print(user_get)
    user_collection = await dbcontrol('SELECT user_collection FROM user_collection WHERE user_id = {}'.format(user_id))
    # print("user_collection:{}".format(user_collection))
    if user_collection[-1]:
        collection_dict = eval(user_collection[0][0][0])
        # print("collection_dir:{}".format(collection_dict))
        # print(collection_id)
        num = await dbcontrol('SELECT collection_id FROM collection',"collection.db")
        if num[-1]:
            # print(num)
            num = num[0]
            # print("num:{}".format(num))
            reply = ""
            for i in num:
                i = i[0]
                collection_name = await dbcontrol('SELECT collection_name FROM collection WHERE collection_id = {}'.format(i),"collection.db")
                collection_name = collection_name[0][0][0]
                # print(collection_name)
                collection_num = str(i) + "number"
                collection_exist = collection_dict.get(collection_num)
                if collection_exist:
                    reply = reply + "\n{}：{}个".format(collection_name,collection_exist)
            # print(reply)
            if reply:
                reply = "你的藏品有："+reply
                await seecollections.finish("{}".format(reply))
            else:
                await seecollections.finish("{}".format(reply))
        else:
            await seecollections.finish("empty")
    else:
        await seecollections.finish("no result")