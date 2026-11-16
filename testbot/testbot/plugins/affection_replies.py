"""Send one affection entry in its original line order, without retrying."""
import asyncio
from weakref import WeakValueDictionary

from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.log import logger

_locks = WeakValueDictionary()
LINE_INTERVAL = 1.0
SEND_TIMEOUT = 12.0


async def send_love_lines(bot, group_id, text):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    key = (str(bot.self_id), int(group_id))
    lock = _locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        return False
    async with lock:
        for index, line in enumerate(lines):
            try:
                result = await asyncio.wait_for(
                    bot.send_group_msg(group_id=group_id, message=MessageSegment.text(line)),
                    timeout=SEND_TIMEOUT,
                )
            except Exception as exc:
                logger.warning(f'好感词条发送中止（{type(exc).__name__}），本条不重发，后续请求仍可处理。')
                return False
            if isinstance(result, dict) and result.get('muted'):
                return False
            if index + 1 < len(lines):
                await asyncio.sleep(LINE_INTERVAL)
    return True
