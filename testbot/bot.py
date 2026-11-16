#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
if sys.version_info < (3, 12):
    raise SystemExit("当前Python版本过旧，请使用本目录的启动机器人.cmd切换到新版环境。")

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

# Custom your logger
# 
# from nonebot.log import logger, default_format
# logger.add("error.log",
#            rotation="00:00",
#            diagnose=False,
#            level="ERROR",
#            format=default_format)

# You can pass some keyword args config to init function
nonebot.init(localstore_use_cwd=True, clovers_using_adapters=["nonebot_plugin_clovers.adapters.onebot.v11"])
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)



#插件
nonebot.load_builtin_plugins("echo")#echo
nonebot.load_plugin("testbot.plugins.nonebot_plugin_namelist")#名单
nonebot.load_plugin("nonebot_plugin_imageutils")#petpet前置插件
nonebot.load_plugin("nonebot_plugin_memes")#表情包制作
# nonebot.load_plugin("nonebot_plugin_heweather") # 暂停：新版需要QWeather JWT三项配置，旧APIKEY不能替代。
nonebot.load_plugin("testbot.plugins.testforsqlplugin")#签到
nonebot.load_plugin("testbot.plugins.testforcollection")#藏品
nonebot.load_plugin("testbot.plugins.nonebot_plugin_word_bank2")#自定义回复
nonebot.load_plugin("nonebot_plugin_htmlrender")
nonebot.load_plugin("testbot.plugins.nonebot_plugin_crazy_thursday")#疯狂星期四
nonebot.load_plugin("testbot.plugins.nonebot_plugin_horserace")#赛马
nonebot.load_plugin("testbot.plugins.testforsera")#菲姆移植
nonebot.load_plugin("testbot.plugins.russian")#俄罗斯转盘
nonebot.load_plugin("testbot.plugins.nonebot_plugin_bottle")#漂流瓶
nonebot.load_plugin("nonebot_plugin_groupmate_waifu")#老婆
nonebot.load_plugin("testbot.plugins.nonebot_plugin_animalVoice")#切噜一下
nonebot.load_plugin("testbot.plugins.nonebot_plugin_morning")#早晚安
nonebot.load_plugin("testbot.plugins.nonebot_plugin_antiinsult")#反嘴臭
nonebot.load_plugin("testbot.plugins.nonebot_plugin_antirecall")#防撤回
nonebot.load_plugin("testbot.plugins.nonebot_plugin_quote")#群语录
nonebot.load_plugin("testbot.plugins.nonebot_plugin_learning_chat")#语言学习
nonebot.load_plugin("testbot.plugins.nonebot_plugin_batarot")#ba塔罗牌
nonebot.load_plugin("testbot.plugins.nonebot_plugin_poke")#戳一戳
nonebot.load_plugin("testbot.plugins.nonebot_plugin_homo_mathematician")#homo数学家
nonebot.load_plugin("testbot.plugins.testforFQJD")#新决斗
nonebot.load_plugin("testbot.plugins.nonebot_plugin_bread_shop")#面包小游戏
nonebot.load_plugin("testbot.plugins.nonebot_plugin_miao")#小尾巴
nonebot.load_plugin("testbot.plugins.nonebot_plugin_person")#随个人
nonebot.load_plugin("testbot.plugins.nonebot_plugin_send") # 保留原反馈功能，关闭旧全群广播
nonebot.load_plugin("testbot.plugins.bot_admin") # 定向公告、离婚与本群NTR开关





# 测试插件

# nonebot.load_plugin("testbot.plugins.testforfight")#老决斗
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_matcher_block")#指令阻断
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_bilibilibot")#B站up主关注
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_dialectlist")#发言排行
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_logo")#logo合成
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_RealESRGAN")#重建
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_caiyunai")#彩云小梦续写
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_hikarisearch")#搜图
# nonebot.load_plugin("nonebot_plugin_imageutils")#petpet前置插件
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_petpet")#表情包制作
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_savor")#图像分析
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_tts_gal")#语音合成：当前目录无该插件，保持停用
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_reborn")#重生
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_follow_withdraw")#撤回跟随
# nonebot.load_plugin("testbot.plugins.testapscheduler")#定时任务
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_trace_moe")#动画场景
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_makemidi")#编曲
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_antiflash")#防闪照
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_CyberSensoji")#求签
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_localstore")#水群
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_guild_patch")#水群
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_datastore")#水群
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_dialectlist")#水群
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_repeater")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_pixiv")
# nonebot.load_plugin("testbot.plugins.YetAnotherPicSearch")
nonebot.load_plugin("testbot.plugins.nonebot_plugin_what2eat")
# nonebot.load_plugin("testbot.plugins.testapscheduler")
# nonebot.load_plugin('nonebot_plugin_picsearcher')
# nonebot.load_plugin("nonebot_plugin_remake")
# nonebot.load_plugin("testbot.plugins.testplugin")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_asoulcnki")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_emojimix")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_datastore")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_chatrecorder")
# nonebot.load_plugin("testbot.plugins.nonebot_plugin_wordcloud")


# Please DO NOT modify this file unless you know what you are doing!
# As an alternative, you should use command `nb` or modify `pyproject.toml` to load plugins
#nonebot.load_from_toml("pyproject.toml")

# Modify some config / config depends on loaded configs
#
# config = driver.config
# do something...


nonebot.load_plugin("testbot.plugins.rollpig_local")  # 今日小猪、收藏与烤群友
nonebot.load_plugin("testbot.plugins.help_center")  # 按权限显示的图片帮助

nonebot.load_plugin("testbot.plugins.media_accel")  # 共享头像缓存与无损图片发送

nonebot.load_plugin("testbot.plugins.feature_controls")  # 超管图像切换、群内分钟上限

nonebot.load_plugin("testbot.plugins.group_stats")

nonebot.load_plugin("testbot.plugins.group_busy")

if __name__ == "__main__":
    nonebot.run()
