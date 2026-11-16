"""Small wording changes; CP rules, counters and cooldowns stay in their owners."""
import random
import asyncio

MUSICAL_ENDINGS = (
    '比翼从此添双翅，连理于今有合枝。\n琴瑟和鸣鸳鸯栖，同心结结永相系。',
    '金玉良缘，天作之合，郎才女貌，喜结同心。',
    '繁花簇锦迎新人，车水马龙贺新婚。',
    '火树银花不夜天，春归画栋双栖燕。',
    '红妆带绾同心结，碧树花开并蒂莲。',
    '笙韵谱成同生梦，烛光笑对含羞人。',
)


def failure_tips(tips):
    result=[str(text) for text in tips if not str(text).lstrip().startswith('智者不入爱河')]
    return result or ['这次没娶到，下次再试试。']


def musical_tip(text,name):
    if name=='千鸟酱' and text in MUSICAL_ENDINGS:return text[:-1]+'🎵'
    return text


def happy_tip(tips):
    from testbot.plugins.persona_utils import load_persona
    return musical_tip(random.choice(tips),load_persona().name)


async def ntr_sequence(user,old_name,old_avatar,new_name,new_avatar):
    from .clovers import at_text_image_result
    yield at_text_image_result(user,f'人家已经名花有主了~\nta的CP：{old_name}\n但是……',old_avatar)
    await asyncio.sleep(1)
    yield at_text_image_result(user,f'恭喜你娶到了群友！\n【{new_name}】',new_avatar)
