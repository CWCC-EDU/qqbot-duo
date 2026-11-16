from testbot.plugins.persona_utils import affinity_status
# -*- coding = utf-8 -*-
# @Time : 2022/7/28 9:25
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
import re

import nonebot
import sqlite3
from nonebot import on_fullmatch, on_regex
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent
from nonebot.params import RegexGroup
from nonebot.permission import SUPERUSER

from nonebot.adapters.onebot.v11 import Message
from testbot.plugins.database import dbcontrol,getcollection
# from testbot.testbot.plugins.database import dbcontrol,getcollection#pycharm
import datetime
import random
from nonebot import get_bot

driver: nonebot.Driver = nonebot.get_driver()
config: nonebot.config.Config = driver.config
# print("driver={},config={}".format(driver, config))


@driver.on_startup
async def connect_to_sqlite():
    con = sqlite3.connect(r"database\\user.db")
    print("数据库创建成功!")
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_sign(
    _id INTEGER PRIMARY KEY NOT NULL ,
    user_id INTEGER NOT NULL DEFAULT 0,
    user_like INTEGER DEFAULT 0,
    user_new_sign_time TEXT NOT NULL DEFAULT '0',
    user_new_sign_month TEXT NOT NULL DEFAULT '0',
    user_new_sign_week TEXT NOT NULL DEFAULT '0',
    user_month_sign INTEGER NOT NULL DEFAULT 0,
    user_week_sign INTEGER NOT NULL DEFAULT 0,
    user_all_sign INTEGER NOT NULL DEFAULT 0,
    user_sign_group INTEGER NOT NULL DEFAULT 0)
    """)
    print("签到表创建成功！")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_collection(
    _id INTEGER PRIMARY KEY NOT NULL ,
    user_id INTEGER NOT NULL DEFAULT 0,
    user_collection TEXT NOT NULL DEFAULT "{}")
    """)
    print("藏品表创建成功！")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_blacklist(
    _id INTEGER PRIMARY KEY NOT NULL ,
    user_id INTEGER NOT NULL DEFAULT 0,
    user_blacklist INTEGER NOT NULL DEFAULT 0,
    user_blackhouse TEXT NOT NULL DEFAULT '0' )
    """)
    print("黑名单表创建成功！")
    cur.close()
    con.commit()
    con.close()





sign = on_fullmatch("签到",permission=GROUP,priority=6,block=True)

@sign.handle()
async def _(event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id
    rand = random.randint(1,10)
    date = datetime.date.today().strftime("%Y%m%d")
    month_now = datetime.datetime.now().strftime('%Y%m')
    week_now = date_week(date)
    # print(date)
    result = await dbcontrol(r"SELECT * FROM user_sign WHERE user_id = {}".format(user_id))
    if result[-1]:
        if result[-1]>1:
            await dbcontrol(r"DELETE FROM user_sign WHERE user_id = {}".format(user_id))
        user_like = result[0][0][2]
        user_new_sign_time = result[0][0][3]
        user_new_sign_month = result[0][0][4]
        user_new_sign_week = result[0][0][5]
        user_month_time = result[0][0][6]
        user_week_time = result[0][0][7]
        user_all_time = result[0][0][8]
        if date == user_new_sign_time:
            await sign.finish("今天已经记录过啦，千鸟酱可没有忘记你哦。")
        else:
            if month_now != user_new_sign_month:
                user_month_time = 1
                user_new_sign_month = month_now
            else:
                user_month_time += 1
            if week_now != user_new_sign_week:
                user_week_time = 1
                user_new_sign_week = week_now
            else:
                user_week_time += 1
            user_like = user_like + rand
            user_all_time += 1
            await dbcontrol(r"UPDATE user_sign SET user_like={},user_new_sign_time={},user_month_sign={},user_week_sign={},user_all_sign={},user_sign_group={},user_new_sign_month={},user_new_sign_week={} WHERE user_id={}".format(user_like,date,user_month_time,user_week_time,user_all_time,group_id,user_new_sign_month,user_new_sign_week,user_id))
            await sign.send(Message("[CQ:at,qq={}]\n今天也见到你啦，千鸟酱把这份开心记下来啦！\n获得{}好感\n现有好感为{}\n周签到次数为{}\n月签到次数为{}\n总签到次数为{}".format(user_id,rand,user_like, user_week_time, user_month_time, user_all_time)))
            # await sign.send("今天也见到你啦，千鸟酱把这份开心记下来啦！\n获得{}好感\n现有好感为{}\n周签到次数为{}\n月签到次数为{}\n总签到次数为{}".format(rand,user_like, user_week_time, user_month_time, user_all_time))
            # if user_like >= 10:
                # print("hello")
                # result =await getcollection(user_id,"测试2")
                # if result:
                #     await sign.send("{}".format(result))
            if user_like >= 100:
                result =await getcollection(user_id, "初见，单推")
                if result:
                    await sign.send("{}".format(result))
                if user_like >= 600:
                    result =await getcollection(user_id, "初见")
                    if result:
                        await sign.send("{}".format(result))
                    if user_like >= 1000:
                        result =await getcollection(user_id, "单推")
                        if result:
                            await sign.send("{}".format(result))
            await sign.finish()
    else:
        await dbcontrol(r"INSERT INTO user_sign (user_id,user_like,user_new_sign_time,user_month_sign,user_week_sign,user_all_sign,user_sign_group,user_new_sign_month,user_new_sign_week) values ({},{},{},{},{},{},{},{},{})".format(user_id,rand,date,1,1,1,group_id,month_now,week_now))
        await sign.finish(Message("[CQ:at,qq={}]\n今天也见到你啦，千鸟酱把这份开心记下来啦！\n获得{}好感\n现有好感为{}\n周签到次数为{}\n月签到次数为{}\n总签到次数为{}".format(user_id,rand,rand,1,1,1)))



see = on_fullmatch("当前好感",permission=GROUP,priority=6,block=True)

@see.handle()
async def _(event: GroupMessageEvent):
    user_like = -1
    user_id = event.user_id
    result = await dbcontrol(r"SELECT * FROM user_sign WHERE user_id = {}".format(user_id))
    try:
        user_like = result[0][0][2]
        await see.finish(affinity_status(user_like))
    except:
        if user_like == -1:
            await see.finish("您签过到么")


rank = on_fullmatch("排行",permission=GROUP,priority=6,block=True)
@rank.handle()
async def _():
    reply = ""
    try:
        result = await dbcontrol("SELECT user_id, user_like FROM user_sign ORDER BY user_like DESC LIMIT 20 OFFSET 0")
        print(result)
        for i in range(0,result[-1]):
            user_id = result[0][i][0]
            user_like = result[0][i][1]
            nickname = await  get_bot().get_stranger_info(user_id=user_id)
            nickname = nickname["nickname"]
            reply = reply + "{}、{}，{}好感\n".format(i+1,nickname,user_like)
            # print(reply)
        if reply:
            reply = "排行如下：\n"+reply + "好耶！"
            await rank.finish("{}".format(reply))
        else:
            await rank.finish("empty")
    except:
        if reply:
            pass

# Manual changes are atomic and share the original affinity table.
from ..local_game_store import adjust_affinity
import asyncio
from nonebot import logger

givelike = on_regex(r"^(?:(增加|减少)好感\s*(?:\[CQ:at,qq=(\d+)(?:,[^\]]*)?\]|@(\d+)|(\d+))\s+(\d+)|(?:\[CQ:at,qq=(\d+)(?:,[^\]]*)?\]|@(\d+))\s*(增加|减少)好感\s*(\d+))$", permission=SUPERUSER, priority=4, block=True)
@givelike.handle()
async def change_affinity(event: GroupMessageEvent,args=RegexGroup()):
    if args[0]:operation=args[0];user=int(next(x for x in args[1:4] if x));amount=int(args[4])
    else:operation=args[7];user=int(args[5] or args[6]);amount=int(args[8])
    try:
        before,after=await asyncio.to_thread(adjust_affinity,user,amount if operation=='增加' else -amount,event.group_id)
    except (ValueError,sqlite3.Error) as error:
        logger.warning('手动好感修改失败：'+str(error))
        await givelike.finish(str(error) if isinstance(error,ValueError) else '这次好感没有改成功，稍后再试。');return
    await givelike.finish(Message(f"[CQ:at,qq={user}] 好感已{operation}{amount}，{before} → {after}。"))

seerank = on_fullmatch("好感位次",permission=GROUP,priority=6,block=True)

@seerank.handle()
async def _(event: GroupMessageEvent):
    user_rank = -1
    user_id = event.user_id
    user_like = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(user_id))
    try:
        user_like = user_like[0][0][0]
        print(user_like)
        result = await dbcontrol(r"SELECT COUNT(*) FROM user_sign WHERE user_like >{}".format(user_like))
        print(result)
        user_rank = result[0][0][0]
        await seerank.finish("您的排行是{}！".format(user_rank+1))
    except:
        if user_rank == -1:
            await seerank.finish("您签过到么")





def date_week(date):
    week = ''
    if isinstance(date, str):
        week = datetime.datetime.strptime(date, '%Y%m%d').strftime('%W')
        if week == '00':
            year = datetime.datetime.strptime(date, '%Y%m%d').year - 1
            week = str(year) + '52'
        else:
            week = datetime.datetime.strptime(date, '%Y%m%d').strftime('%Y%W')
    elif isinstance(date, datetime.datetime):
        week = date.strftime('%W')
        if week == '00':
            year = date.year - 1
            week = str(year) + '52'
        else:
            week = date.strftime('%Y%W')
    else:
        raise ValueError('{} 需要包含（年月日），字符串日期或者日期格式'.format(date))
    return week