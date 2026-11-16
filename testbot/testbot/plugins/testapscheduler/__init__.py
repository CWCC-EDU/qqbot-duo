# -*- coding = utf-8 -*-
# @Time : 2022/7/28 21:38
# @Author : CCW
# @File : __init__.py.py
# @Software : PyCharm
# import asyncio
# import random
# from nonebot import require, get_bot, get_driver
# from nonebot.log import logger
#
#
# try:
#     scheduler = require("nonebot_plugin_apscheduler").scheduler
# except BaseException:
#     scheduler = None
#
# logger.opt(colors=True).info(
#     "已检测到软依赖<y>nonebot_plugin_apscheduler</y>, <g>开启定时任务功能</g>"
#     if scheduler
#     else "未检测到软依赖<y>nonebot_plugin_apscheduler</y>，<r>禁用定时任务功能</r>"
# )
#
# try:
#     fire_user_id = 0
# except Exception as e:
#     logger.error("ValueError:{}", e)
#     logger.error("请配置fire_user_id")
#
#
# async def fire_scheduler():
#         try:
#             await asyncio.sleep(random.randint(1, 10))
#             await get_bot().send_private_msg(user_id=fire_user_id, message="/echo 花花")  # 当未连接到onebot.v11协议端时会抛出异常
#             logger.info("发送火花")
#         except ValueError as e:
#             logger.error("ValueError:{}", e)
#             logger.error("续火花插件获取bot失败，1s后重试")
#             await asyncio.sleep(1)  # 重试前时延，防止阻塞
#
#
# if scheduler:
#     scheduler.add_job(fire_scheduler, "cron", hour="0", id="fire_scheduler")
import apscheduler
from apscheduler import job
from nonebot.matcher import Matcher
from nonebot.adapters import Message
from nonebot.params import Arg, CommandArg, ArgPlainText
from nonebot import require, on_command
from nonebot import get_bot
from nonebot.params import EventMessage
from nonebot.permission import Message

from testbot.testbot.plugins.database import dbcontrol



scheduler = require("nonebot_plugin_apscheduler").scheduler

# @scheduler.scheduled_job("cron", week= 1,hour = 0, id="week")
# async def run_every_week():
#     await dbcontrol(r"UPDATE user_sign SET user_week_sign=0")
#     await get_bot().send_private_msg(user_id=0, message="清空周签到次数")
#
# @scheduler.scheduled_job("cron", month= 1,hour = 0, id="month")
# async def run_every_week():
#     await dbcontrol(r"UPDATE user_sign SET user_month_sign=0")
#     await get_bot().send_private_msg(user_id=0, message="清空月签到次数")

# @scheduler.scheduled_job("cron", second= 1,id="test")
# async def run_every_week():
#     dbcontrol(r"UPDATE user_sign SET user_month_sign=0")
#     await get_bot().send_private_msg(user_id=0, message="清空月签到次数")


class sch:
    def __init__(self):
        self.job = {}

    # async def work(self):
    #     await get_bot().send_private_msg(user_id=0, message="测试")
    async def start(self):
        print("hello11")
        self.job[1] = scheduler.add_job(work, "cron", second='*/5', id="xxx")
        print("hello12")

    async def done(self):
        self.job[1].remove()

Sch = sch()

async def work():
    await get_bot().send_private_msg(user_id=0, message="测试")
# scheduler.add_job(work, "cron", second = '*/5', id="xxx")

done = on_command("结束", rule=None, priority=7)
@done.handle()
async def _():
    print("hello1")
    await Sch.done()
    print("hello2")
    await done.finish("done")


start = on_command("开始", rule=None, priority=7)
@start.handle()
async def _():
    print("hello1")
    await Sch.start()
    print("hello2")
    await start.finish("start")

# apscheduler.job.Job.remove("xxx")



