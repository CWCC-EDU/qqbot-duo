from . import send  # 旧notice默认群发全部群，已由bot_admin的指定群公告取代
from nonebot.plugin import PluginMetadata
__plugin_meta__= PluginMetadata(
    name='send',
    description='通知和反馈基本功能',
    usage='',
)