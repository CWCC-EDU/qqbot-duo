from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, Bot
from typing import Optional, Tuple, Union, List, Dict
from datetime import datetime
from nonebot.log import logger
from pathlib import Path
import nonebot
import asyncio
import random
import time
import os
from .config import Config

try:
    import ujson as json
except ModuleNotFoundError:
    import json


global_config = nonebot.get_driver().config
russian_config = Config.parse_obj(global_config.dict())

# bot昵称
bot_name = list(global_config.nickname)[0] if global_config.nickname else "本裁判"





class RussianManager:
    def __init__(self):
        self._current_player = {}



    def accept(self, event: GroupMessageEvent) -> Union[str, Message]:
        """
        接受决斗请求
        :param event: event
        """
        try:
            if (
                self._current_player[event.group_id]["at"] != 0
                and self._current_player[event.group_id]["at"] == event.user_id
                and self._current_player[event.group_id][1] != self._current_player[event.group_id][2]
            ):

                if time.time() - self._current_player[event.group_id]["time"] > 30:
                    self._current_player[event.group_id] = {}
                    return "这场对决邀请已经过时了，请重新发起快速决斗..."
                self._current_player[event.group_id]["time"] = time.time()

                return Message(f"接受了对决！"),self._current_player[event.group_id]["player1"],self._current_player[event.group_id]["player2"],self._current_player[event.group_id][1],self._current_player[event.group_id][2]
        except KeyError:
            pass

    async def refuse(self, bot: Bot, event: GroupMessageEvent) -> Union[str, Message]:
        try:
            if self._current_player[event.group_id]["at"] == event.user_id:
                at_player_name = await bot.get_group_member_info(
                    group_id=event.group_id, user_id=event.user_id
                )
                at_player_name = (
                    at_player_name["card"]
                    if at_player_name["card"]
                    else at_player_name["nickname"]
                )
                inviter = self._current_player[event.group_id][1]
                self._current_player[event.group_id] = {}
                return Message(
                    f"{MessageSegment.at(inviter)}\n"
                    f"{at_player_name}拒绝了你的对决！"
                )
        except KeyError:
            pass


    def ready_game(
        self,
        event: GroupMessageEvent,
        msg: str,
        player1_name: str,
        at_: int,
        player2_name: str,
    ) -> Message:
        """
        发起游戏
        :param event: event
        :param msg: 提示消息
        :param player1_name: 玩家
        :param at_: at用户
        :param money: 赌注金额
        :param bullet_num: 装填子弹数量
        """
        self._current_player[event.group_id] = {
            1: event.user_id,
            "player1": player1_name,
            2: at_,
            "player2": player2_name,
            "at": at_,
            "time": time.time(),
        }
        return Message(msg)



    def check_game_is_start(self, group_id: int) -> bool:
        """
        检测群内游戏是否已经开始
        :param group_id: 群号
        """
        return self._current_player[group_id][1] != 0






russian_manager = RussianManager()
