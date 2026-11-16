import contextlib
import random
from typing import Dict, Any

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.plugin import PluginMetadata

from .config import config, Config
from .tail import append_tail

__plugin_meta__ = PluginMetadata(
    name="口癖",
    description="让Bot的发言添加口癖",
    usage="被动技能",
    type="application",
    homepage="https://github.com/CMHopeSunshine/nonebot-plugin-miao",
    config=Config,
    supported_adapters=None
)


@Bot.on_calling_api
async def handle_miao(bot: Bot, api: str, data: Dict[str, Any]):
    with contextlib.suppress(Exception):
        if api not in ['send_msg', 'send_message', 'send_group_msg', 'send_private_msg']:
            return
        message=Message(data.get('message',''))
        if len(message) != 1 or message[0].type != 'text':
            return
        count = 0
        word = random.choice(config.miao_words)
        text = str(message[0].data['text'])
        while count < config.miao_count and random.random() < config.miao_probability:
            if config.miao_position == 'start':
                text = word + text
            elif config.miao_position == 'end':
                text = append_tail(text, word)
            elif config.miao_position == 'random':
                pos = random.randint(0, len(text))
                text = text[:pos] + word + text[pos:]
            count += 1
            data['message'] = text
