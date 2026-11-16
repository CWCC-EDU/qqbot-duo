"""Load the upstream pig game with its normal, unprefixed commands."""
from nonebot import require
require('nonebot_plugin_rollpig_plus')
# Local pigs, pictures and roast templates are bundled. Fetch the optional
# remote PigHub index only when somebody explicitly uses random/search.
from nonebot_plugin_rollpig_plus.pighub_service import pighub_service
pighub_service.schedule_startup_refresh = lambda: None
