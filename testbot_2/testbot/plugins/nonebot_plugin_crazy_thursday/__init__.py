import json
import random
from pathlib import Path
from typing import Annotated

from nonebot import on_regex
from nonebot.matcher import Matcher
from nonebot.params import Depends, RegexStr
from nonebot.plugin import PluginMetadata

__plugin_version__ = "v0.2.8"
__plugin_usages__ = f"""
KFC疯狂星期四 {__plugin_version__}
[疯狂星期X] 随机输出KFC疯狂星期四文案
[狂乱X曜日] 随机输出KFC疯狂星期四文案""".strip()

__plugin_meta__ = PluginMetadata(
    name="疯狂星期四",
    description="持续疯狂！KFC疯狂星期四🍗",
    usage=__plugin_usages__,
    type="application",
    homepage="https://github.com/MinatoAquaCrews/nonebot_plugin_crazy_thursday",
    extra={
        "author": "KafCoppelia <k740677208@gmail.com>",
        "version": __plugin_version__,
    },
)

crazy_cn = on_regex(pattern=r"^疯狂星期\S$", priority=15)
crazy_jp = on_regex(pattern=r"^狂乱\S曜日$", priority=15)


async def get_weekday_cn(arg: Annotated[str, RegexStr()]) -> str:
    return arg[-1].replace("天", "日")


async def get_weekday_jp(arg: Annotated[str, RegexStr()]) -> str:
    return arg[2]


@crazy_cn.handle()
async def _(matcher: Matcher, weekday: Annotated[str, Depends(get_weekday_cn)]):
    await matcher.finish(randomKFC(weekday))


@crazy_jp.handle()
async def _(matcher: Matcher, weekday: Annotated[str, Depends(get_weekday_jp)]):
    await matcher.finish(randomKFC(weekday))


# jp en cn
weekday_table = [
    "月",
    "Monday",
    "一",
    "火",
    "Tuesday",
    "二",
    "水",
    "Wednesday",
    "三",
    "木",
    "Thursday",
    "四",
    "金",
    "Friday",
    "五",
    "土",
    "Saturday",
    "六",
    "日",
    "Sunday",
    "日",
]


def randomKFC(day: str) -> str:
    if day not in weekday_table:
        return "给个准确时间，OK?"

    # Get the weekday group index
    idx = int(weekday_table.index(day) / 3) * 3

    # 将json对象加载到数组
    with open(Path(__file__).parent / "post.json", "r", encoding="utf-8") as f:
        kfc = json.load(f).get("post", None)
        if kfc is None:
            raise KeyError("Key 'post' is missing.")

        # 随机选取数组中的一个对象，并替换日期
        return (
            random.choice(kfc)
            .replace("木曜日", weekday_table[idx] + "曜日")
            .replace("Thursday", weekday_table[idx + 1])
            .replace("thursday", weekday_table[idx + 1])
            .replace("星期四", "星期" + weekday_table[idx + 2])
            .replace("周四", "周" + weekday_table[idx + 2])
            .replace("礼拜四", "礼拜" + weekday_table[idx + 2])
        )
