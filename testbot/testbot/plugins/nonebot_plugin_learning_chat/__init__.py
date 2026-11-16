from nonebot import require

require("nonebot_plugin_tortoise_orm")
require("nonebot_plugin_apscheduler")

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, GROUP
from nonebot.plugin import PluginMetadata
from . import web_api, web_page
from .smart import assistant

__plugin_meta__ = PluginMetadata(
    name="群聊学习", description="本地群聊学习、问答检索、上下文与个人记忆",
    usage="发送 #智能帮助；默认本地处理，可按群开启省钱云聊；保留原学习词库和后台。",
    type="application", homepage="https://github.com/CMHopeSunshine/nonebot-plugin-learning-chat",
    supported_adapters={"~onebot.v11"}, extra={"author": "惜月，本站本地智能扩展"},
)

learning_chat = on_message(priority=99, block=False, permission=GROUP,
    state={"pm_name": "群聊学习", "pm_description": "本地智能聊天，发送 #智能帮助",
           "pm_usage": "#智能帮助", "pm_priority": 1})


@learning_chat.handle()
async def handle_chat(bot: Bot, event: GroupMessageEvent):
    await assistant.handle(bot, event)


# Unsolicited timer speech used random global contexts and could loop between bots.
# Natural mode now provides bounded, relevant interjections on real group messages.


from nonebot import get_driver

@get_driver().on_bot_connect
async def register_chat_peer(bot: Bot):
    await assistant.remember_bot(bot.self_id)


@get_driver().on_startup
async def initialize_chat_files():
    import asyncio
    from nonebot import logger
    from .model_router import Router
    try:
        await asyncio.to_thread(assistant.files.initialize)
        await asyncio.to_thread(Router, assistant.cloud)
    except (OSError,ValueError,TypeError):
        logger.warning('聊天配置暂时读不出来，原文件保留，请检查格式。')
