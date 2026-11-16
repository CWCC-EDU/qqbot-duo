import re

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
from nonebot import require, on_command
from nonebot import get_bot
from .img_maker import img_maker

from ..database import dbcontrol, getcollection

try:
    import ujson as json
except ModuleNotFoundError:
    import json

scheduler = require("nonebot_plugin_apscheduler").scheduler



global_config = nonebot.get_driver().config
russian_config = Config.parse_obj(global_config.dict())
russian_path = russian_config.russian_path

# bot昵称
bot_name = list(global_config.nickname)[0] if global_config.nickname else "本裁判"

async def rank(player_data: dict, group_id: int, type_: str) -> str:
    """
    排行榜数据统计
    :param player_data: 玩家数据
    :param group_id: 群号
    :param type_: 排行榜类型
    """
    group_id = str(group_id)
    all_user = list(player_data[group_id].keys())

    if type_ == "win_rank":
        rank_name = "\t胜场排行榜\n"
        all_user_data = [player_data[group_id][x]["win_count"] for x in all_user]
    else:
        rank_name = "\t败场排行榜\n"
        all_user_data = [player_data[group_id][x]["lose_count"] for x in all_user]
    rst = ""
    if all_user:
        for _ in range(len(all_user) if len(all_user) < 10 else 10):
            _max = max(all_user_data)
            _max_id = all_user[all_user_data.index(_max)]
            name = player_data[group_id][_max_id]["nickname"]
            rst += f"{name}：{_max}\n"
            all_user_data.remove(_max)
            all_user.remove(_max_id)
        rst = rst[:-1]
    return rank_name + rst




class RussianManager:
    def __init__(self):
        self.ifcannotget = 0

        self.eventid = 0
        self.get = -1
        self.ifchoose = 1
        self.first = random.randint(1, 2)
        self.second = (1 if self.first == 2 else 2)
        self.used_num = 45
        self.play_num = 11
        self.first_blood = 600
        self.second_blood = 700
        self._player_data = {}
        self._current_player = {}
        self._group_list = []
        file = russian_path / "data" / "fight" / "fight_data.json"
        self.png_path = russian_path / "data" / "fight"
        self.skilljsonfile = russian_path / "data" / "fight" / "skill.json"
        self.skilljsonpath = russian_path / "data" / "fight" / "skill2.txt"
        self.collectionjsonpath = russian_path / "data" / "fight" / "collection.json"
        with open(self.collectionjsonpath, 'r+', encoding="utf-8") as f11:
            file1 = json.load(f11)
            # print(self.skilljsonfile)
            self.collection = file1[f"collection"]
        with open(self.skilljsonfile,'r+',encoding = "utf_8_sig") as f:
            # print(f.read())
            self.skilljson = json.load(f)
        self.file = file
        self.job = {}
        file.parent.mkdir(exist_ok=True, parents=True)
        if not file.exists():
            old_file = Path(os.path.dirname(__file__)) / "fight_data.json"
            if old_file.exists():
                os.rename(old_file, file)
        if file.exists():
            with open(file, "r", encoding="utf8") as f:
                self._player_data = json.load(f)


    async def accept(self, bot: Bot,event: GroupMessageEvent) -> Union[str, Message]:
        """
        接受决斗请求
        :param event: event
        """
        self._init_player_data(event)
        try:
            if self._current_player[event.group_id][1] == 0:
                return "",""
        except KeyError:
            return "",""
        if self._current_player[event.group_id][2] != 0:
            if (
                self._current_player[event.group_id][1] == event.user_id
                or self._current_player[event.group_id][2] == event.user_id
            ):
                return f"你已经身处决斗之中了啊，给我认真一点啊！"
            else:
                return "已经有人接受对决了，你还是乖乖等待下一场吧！"
        if self._current_player[event.group_id][1] == event.user_id:
            return "请不要自己打自己！换人来接受对决...",""
        if (
            self._current_player[event.group_id]["at"] != 0
            and self._current_player[event.group_id]["at"] != event.user_id
        ):
            return Message(
                f'这场对决是邀请 {MessageSegment.at(self._current_player[event.group_id]["at"])}的，不要捣乱！'
            )
        if time.time() - self._current_player[event.group_id]["time"] > 90:
            self._current_player[event.group_id] = {}
            return "这场对决邀请已经过时了，请重新发起决斗...",""


        self.eventid = event.user_id
        player2_name = event.sender.card if event.sender.card else event.sender.nickname
        self._current_player[event.group_id][2] = event.user_id
        self._current_player[event.group_id]["player2"] = player2_name
        self._current_player[event.group_id]["time"] = time.time()
        self._current_player[event.group_id][f"blood{self.first}"] = self.first_blood
        self._current_player[event.group_id][f"blood{self.second}"] = self.second_blood
        self._current_player[event.group_id]["next"] = self._current_player[event.group_id][self.first]
        self._group_list.append(event.group_id)
        ran = random.sample(range(1, self.used_num + 1), 4)
        await self.start(event.group_id)
        await bot.send(event, Message(
            f"{player2_name}接受了对决！\n"
            f"请双方轮流发送 #技能序号 以使用技能，或 #认输 认输！\n{MessageSegment.at(self._current_player[event.group_id][self.first])}取得先手！"
        ))
        # msg = await self.task_two(bot, event)
        self.job[event.group_id] = scheduler.add_job(self.task_two, "cron", second='*/5', id=f"{event.group_id}-2",args=[bot, event] )
        return "1",""




    async def task_two(self,bot: Bot, event: GroupMessageEvent):
        # 结算
        if self._current_player[event.group_id]["blood1"] <= 0 or self._current_player[event.group_id]["blood2"] <= 0:
            await self.end_game(bot, event)
            return

        # 回合前处理：优先级0，可以包括属性效果和状态效果
        fighter = (1 if self._current_player[event.group_id]["next"] == self._current_player[event.group_id][1] else 2)
        fighted = (2 if self._current_player[event.group_id]["next"] == self._current_player[event.group_id][1] else 1)
        if self._current_player[event.group_id][f"state{fighter}"] == 1:
            self._current_player[event.group_id][f"state{fighter}"] = 0
            self._current_player[event.group_id]["index"] += 1
            if self._current_player[event.group_id][f"state{fighted}"] == 3 and int(
                    self._current_player[event.group_id]["index"]) < self.play_num:
                blooding = int(random.normalvariate(95, 95 * 0.08))
                self._current_player[event.group_id][f"blood{fighted}"] -= blooding
                await bot.send(event, Message(
                    f"[CQ:at,qq={self._current_player[event.group_id]['next']}]你正在疲惫！对方因为流血损失了{blooding}点血量！"))
            else:
                await bot.send(event, Message(f"[CQ:at,qq={self._current_player[event.group_id]['next']}]你正在疲惫！"))
            self._current_player[event.group_id]["next"] = self._current_player[event.group_id][fighted]
            # asyncio.create_task(self.task_two(bot, event))  # Register task_two again
            scheduler.remove_job(f"{event.group_id}-2")
            self.job[event.group_id] = scheduler.add_job(self.task_two, "cron", second='*/5',
                                                               id=f"{event.group_id}-2", args=[bot, event])
            return

        if self._current_player[event.group_id][f"state{fighter}"] == 9:
            self.ifchoose = 0
            self._current_player[event.group_id][f"state{fighter}"] = 0
            self.skill = random.randint(0, int(self.used_num))
            self.get = self.skill
            with open(self.skilljsonfile, 'r+', encoding="utf-8") as f:
                file = json.load(f)
                file_skill = file[f"{self.skill}"]
                self.skill_hurt = file_skill["hurt"]
                self.skill_attribute = file_skill["attribute"]
                self.skill_function = file_skill["function"]
                self.skill_parameter = file_skill["parameter"]
                name = str(file_skill["name"])
            await bot.send(event, Message(f"[CQ:at,qq={self._current_player[event.group_id]['next']}]在疑惑中使用了{name}！"))





        #回合状态发送
        if self.ifchoose:
            attribute = ["普通", "水", "火", "草","暗","光","？"]
            state = ["无", "疲惫", "防御", "流血","顽强","荆棘","易伤","混乱","时滞","迷惑","失明"]
            msg = (f'{self._current_player[event.group_id][f"player{fighted}"]}:\n'
                   f'剩余血量:{self._current_player[event.group_id][f"blood{fighted}"]}\n'
                   f'当前属性:{attribute[self._current_player[event.group_id][f"attribute{fighted}"]]}\n'
                   f'攻击等级:{self._current_player[event.group_id][f"atk{fighted}"]-6}\n'
                   f'命中值:{int(self._current_player[event.group_id][f"accuracy{fighted}"]*100)}%\n'
                   f'当前状态:{state[self._current_player[event.group_id][f"state{fighted}"]]}\n'
                   f'{self._current_player[event.group_id][f"player{fighter}"]}:\n'
                   f'剩余血量:{self._current_player[event.group_id][f"blood{fighter}"]}\n'
                   f'当前属性:{attribute[self._current_player[event.group_id][f"attribute{fighter}"]]}\n'
                   f'攻击等级:{self._current_player[event.group_id][f"atk{fighter}"]-6}\n'
                   f'命中值:{int(self._current_player[event.group_id][f"accuracy{fighter}"]*100)}%\n'
                   f'当前状态:{state[self._current_player[event.group_id][f"state{fighter}"]]}\n'
                   f'回合数：{self._current_player[event.group_id]["index"]}')
            await bot.send(event, msg )
            # msg1 = [
            #     f'{self._current_player[event.group_id][f"player{self.first}"]}:',
            #            f'属性:{attribute[self._current_player[event.group_id][f"attribute{self.first}"]]}',
            #            f'攻击:{self._current_player[event.group_id][f"atk{self.first}"]-6}',
            #            f'命中:{int(self._current_player[event.group_id][f"accuracy{self.first}"]*100)}%',
            #            f'状态:{state[self._current_player[event.group_id][f"state{self.first}"]]}'
            # ]
            # msg2 = [
            #     f'{self._current_player[event.group_id][f"player{self.second}"]}:',
            #            f'属性:{attribute[self._current_player[event.group_id][f"attribute{self.second}"]]}',
            #            f'攻击:{self._current_player[event.group_id][f"atk{self.second}"]-6}',
            #            f'命中:{int(self._current_player[event.group_id][f"accuracy{self.second}"]*100)}%',
            #            f'状态:{state[self._current_player[event.group_id][f"state{self.second}"]]}'
            # ]
            ran = random.sample(range(1, self.used_num + 1), 4)
            for i in range(0, 4):
                self._current_player[event.group_id]["skill_choose"][i + 1] = ran[i]
            msg2 = Message(f"[CQ:at,qq={self._current_player[event.group_id]['next']}]你的选择是\n"
                           f"0.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][0])]['name']}:\n"
                           f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][0])]['effect']}\n"
                           f"1.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][1])]['name']}:\n"
                           f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][1])]['effect']}\n"
                           f"2.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][2])]['name']}:\n"
                           f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][2])]['effect']}\n"
                           f"3.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][3])]['name']}:\n"
                           f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][3])]['effect']}\n"
                           f"4.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][4])]['name']}:\n"
                           f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][4])]['effect']}"
                           )
            await bot.send(event, msg2)
            # msg_choice = [
            #                f"0.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][0])]['name']}:",
            #                f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][0])]['effect']}",
            #                f"1.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][1])]['name']}:",
            #                f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][1])]['effect']}",
            #                f"2.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][2])]['name']}:",
            #                f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][2])]['effect']}",
            #                f"3.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][3])]['name']}:",
            #                f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][3])]['effect']}",
            #                f"4.{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][4])]['name']}:",
            #                f"{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][4])]['effect']}"
            # ]
            # path = img_maker(msg1,msg2,self._current_player[event.group_id][f"blood{self.first}"],self._current_player[event.group_id][f"blood{self.second}"],self._current_player[event.group_id]["index"],msg_choice,group=event.group_id)
            # try:
            #     await bot.send(event,message=Message(f"[CQ:at,qq={self._current_player[event.group_id]['next']}]\n")+MessageSegment.image(file=rf"file:///{path}"))
            # except:
            #     pass
        #伤害结算和回合后处理
        while self.get == -1 :
            await asyncio.sleep(1)  # Allow other tasks to run
        await asyncio.sleep(0.5)  # Adjust the sleep time as needed
        if self.get != -1:
            if self.ifchoose:
                msg2 = f"{self._current_player[event.group_id][f'player{fighter}']}使用了{self.skilljson['{}'.format(self._current_player[event.group_id]['skill_choose'][self.get])]['name']}！"
                msg3 = await self.caculate(bot, event, fighter, fighted,
                                    self._current_player[event.group_id]["skill_choose"][self.get])
                try:
                    await bot.send(event, msg2+msg3)
                except:
                    pass
            else:
                self.ifchoose = 1
                msg3 = await self.caculate(bot, event, fighter, fighted,self.get)
                await bot.send(event, msg3)
            self._current_player[event.group_id]["time"] = time.time()
            self._current_player[event.group_id]["index"] += 1
            if int(self._current_player[event.group_id]["index"]) >= self.play_num:
                if self._current_player[event.group_id]["blood1"] > self._current_player[event.group_id]["blood2"]:
                    self._current_player[event.group_id]["blood2"] -= 9999
                else:
                    self._current_player[event.group_id]["blood1"] -= 9999
        self.get = -1

        #攻守切换
        self._current_player[event.group_id]["next"] = (
            self._current_player[event.group_id][1]
            if self._current_player[event.group_id]["next"] == self._current_player[event.group_id][2]
            else self._current_player[event.group_id][2])
        self.ifcannotget = 0
        scheduler.remove_job(f"{event.group_id}-2")
        self.job[event.group_id] = scheduler.add_job(self.task_two, "cron", second='*/5',
                                                     id=f"{event.group_id}-2", args=[bot, event])



    async def refuse(self, bot: Bot, event: GroupMessageEvent) -> Union[str, Message]:
        self._init_player_data(event)
        try:
            if self._current_player[event.group_id][1] == 0:
                # return "你要拒绝啥？明明都没有人发起对决的说！"
                return ""
        except KeyError:
            # return "目前没有进行的决斗，请发送 发起决斗 开启决斗吧！"
            return ""
        if (
            self._current_player[event.group_id]["at"] != 0
            and event.user_id != self._current_player[event.group_id]["at"]
        ):
            return "又不是找你决斗，你拒绝什么啊！气！"
        if self._current_player[event.group_id]["at"] == event.user_id:
            at_player_name = await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
            at_player_name = (
                at_player_name["card"]
                if at_player_name["card"]
                else at_player_name["nickname"]
            )
            self._current_player[event.group_id] = {}
            return Message(
                f"{at_player_name}拒绝了你的对决！"
            )

    def settlement(self, event: GroupMessageEvent) -> str:
        """
        结算检测
        :param event: event
        """
        self._init_player_data(event)
        if (
            not self._current_player.get(event.group_id)
            or self._current_player[event.group_id][1] == 0
            or self._current_player[event.group_id][2] == 0
        ):
            return "比赛并没有开始...无法结算..."
        if (
            event.user_id != self._current_player[event.group_id][1]
            and event.user_id != self._current_player[event.group_id][2]
        ):
            return "吃瓜群众不要捣乱！黄牌警告！"
        # if time.time() - self._current_player[event.group_id]["time"] <= 30:
        #     return (
        #         f'{self._current_player[event.group_id]["player1"]} '
        #         f'和 {self._current_player[event.group_id]["player2"]} 比赛并未超时，请继续比赛...'
        #     )
        win_name = (
            self._current_player[event.group_id]["player1"]
            if event.user_id
            == self._current_player[event.group_id][2]
            else self._current_player[event.group_id]["player2"]
        )
        loser = (
            2
            if event.user_id
            == self._current_player[event.group_id][2]
            else 1
        )
        self._current_player[event.group_id]["next"] = event.user_id
        self._current_player[event.group_id][f"blood{loser}"] -= 99999999
        return f"这场对决是 {win_name} 胜利了"

    async def check_current_game(
        self, bot: Bot, event: GroupMessageEvent
    ) -> Optional[str]:
        """
        检查当前是否有决斗存在
        """
        self._init_player_data(event)
        if (
            self._current_player[event.group_id][1]
            and not self._current_player[event.group_id][2]
            and time.time() - self._current_player[event.group_id]["time"] <= 90
        ):
            return f'现在是 {self._current_player[event.group_id]["player1"]} 发起的对决\n请等待比赛结束后再开始下一轮...'
        if (
            self._current_player[event.group_id][1]
            and self._current_player[event.group_id][2]
            and time.time() - self._current_player[event.group_id]["time"] <= 90
        ):
            return (
                f'{self._current_player[event.group_id]["player1"]} 和'
                f' {self._current_player[event.group_id]["player2"]}的对决还未结束！'
            )
        if (
            self._current_player[event.group_id][1]
            and self._current_player[event.group_id][2]
            and time.time() - self._current_player[event.group_id]["time"] > 90
        ):
            await bot.send(event, message="决斗已过时，强行结算...")
            await self.end_game(bot, event)
        if (
            not self._current_player[event.group_id][2]
            and time.time() - self._current_player[event.group_id]["time"] > 90
        ):
            self._current_player[event.group_id][1] = 0
            self._current_player[event.group_id][2] = 0
            self._current_player[event.group_id]["at"] = 0
        return None

    def ready_game(
        self,
        event: GroupMessageEvent,
        msg: str,
        player1_name: str,
        at_: int,
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
            2: 0,
            "player2": "",
            "at": at_,
            "next": event.user_id,
            "blood1": self.first_blood,
            "blood2": self.second_blood,
            "attribute1": 0,
            "attribute2": 0,
            "atk1":6,
            "atk2":6,
            "accuracy1":0.95,
            "accuracy2": 0.95,
            "state1":0,
            "state2":0,
            "index": 0,
            "time": time.time(),
            "skill_choose":{0:0,1:1,2:2,3:3,4:4}
        }
        return Message(msg)
    # ————————————————————————————————————————————————————————————————————————
    async def shot(self, bot: Bot, event: GroupMessageEvent, count: int):
        """
        开枪！！！
        :param bot: bot
        :param event: event
        :param count: 开枪次数
        """
        if self.ifcannotget == 0:
            self.ifcannotget = 1
            check_message = await self._shot_check(bot, event)
            if check_message:
                await bot.send(event, check_message)
                self.ifcannotget = 0
                return
            self.eventid = event.user_id
            self.get = count


    async def _shot_check(self, bot: Bot, event: GroupMessageEvent) -> Optional[str]:
        """
        开枪前检查游戏是否合法
        :param bot: bot
        :param event: event
        """
        try:
            if time.time() - self._current_player[event.group_id]["time"] > 90:
                if self._current_player[event.group_id][2] == 0:
                    self._current_player[event.group_id][1] = 0
                    return "这场对决已经过时了，请重新开始吧！"
                else:
                    await bot.send(event, "决斗已过时，强行结算...")
                    await self.end_game(bot, event)
                    return None
        except KeyError:
            return "目前没有进行的决斗，请发送 发起决斗 开启决斗吧！"
        if self._current_player[event.group_id][1] == 0:
            return "没有对决呢，请先输入 发起决斗 吧！"
        if (
            self._current_player[event.group_id][1] == event.user_id
            and self._current_player[event.group_id][2] == 0
        ):
            return "baka，你是要和自己决斗嘛笨蛋！"
        if self._current_player[event.group_id][2] == 0:
            return "请这位勇士先发送 接受 来站上擂台..."
        player1_name = self._current_player[event.group_id]["player1"]
        player2_name = self._current_player[event.group_id]["player2"]
        if self._current_player[event.group_id]["next"] != event.user_id:
            if (
                event.user_id != self._current_player[event.group_id][1]
                and event.user_id != self._current_player[event.group_id][2]
            ):
                nickname = (
                    event.sender.card if event.sender.card else event.sender.nickname
                )
                return random.choice(
                    [
                        f"不要打扰 {player1_name} 和 {player2_name} 的决斗啊！",
                        f"给我好好做好一个观众！不然{bot_name}就要生气了",
                        f"不要捣乱啊baka{nickname}！",
                    ]
                )
            nickname = (
                player1_name
                if self._current_player[event.group_id]["next"]
                == self._current_player[event.group_id][1]
                else player2_name
            )
            return f"该 {nickname} 了"
        return None

    def get_user_data(self, event: GroupMessageEvent) -> Dict[str, Union[str, int]]:
        """
        获取用户数据
        :param event:
        :return:
        """
        self._init_player_data(event)
        return self._player_data[str(event.group_id)][str(event.user_id)]



    async def rank(self, msg: str, group_id: int) -> str:
        """
        获取排行榜
        :param msg: 排行榜类型
        :param group_id: 群号
        """
        if msg in ["胜场排行", "胜利排行"]:
            return await rank(self._player_data, group_id, "win_rank")
        if msg in ["败场排行", "失败排行"]:
            return await rank(self._player_data, group_id, "lose_rank")

    def check_game_is_start(self, group_id: int) -> bool:
        """
        检测群内游戏是否已经开始
        :param group_id: 群号
        """
        return self._current_player[group_id][1] != 0



    def save(self):
        """
        保存数据
        """
        with open(self.file, "w", encoding="utf8") as f:
            json.dump(self._player_data, f, ensure_ascii=False, indent=4)

    def _init_player_data(self, event: GroupMessageEvent):
        """
        初始化用户数据
        :param event: event
        """
        user_id = str(event.user_id)
        group_id = str(event.group_id)
        nickname = event.sender.card if event.sender.card else event.sender.nickname
        if group_id not in self._player_data.keys():
            self._player_data[group_id] = {}
        if user_id not in self._player_data[group_id].keys():
            self._player_data[group_id][user_id] = {
                "user_id": user_id,
                "group_id": group_id,
                "nickname": nickname,
                "win_count": 0,
                "lose_count": 0,
                "is_sign": None,
            }

    async def end_game(self, bot: Bot, event: GroupMessageEvent):
        """
        游戏结束结算
        :param bot: Bot
        :param event: event
        :return:
        """
        await self.done(event.group_id)
        player1_name = self._current_player[event.group_id]["player1"]
        player2_name = self._current_player[event.group_id]["player2"]
        if (
            self._current_player[event.group_id]["blood1"] <= 0
        ):
            win_user_id = self._current_player[event.group_id][2]
            lose_user_id = self._current_player[event.group_id][1]
            win_name = player2_name
            lose_name = player1_name
            winfighter = 2
            losefighter = 1
        else:
            win_user_id = self._current_player[event.group_id][1]
            lose_user_id = self._current_player[event.group_id][2]
            win_name = player1_name
            lose_name = player2_name
            winfighter = 1
            losefighter = 2
        rand = random.randint(0, 5)
        self._end_data_handle(win_user_id, lose_user_id, event.group_id)
        win_user = self._player_data[str(event.group_id)][str(win_user_id)]
        lose_user = self._player_data[str(event.group_id)][str(lose_user_id)]
        logger.info(f"胜者：{win_name} - 败者：{lose_name} ")

        await bot.send(
            event,
            # Message(f'[CQ:at,qq={self._current_player[event.group_id][fighted]}]嘭！你的眼前一'+random.choice(
            Message(f'[CQ:at,qq={self._current_player[event.group_id][losefighter]}]嘭！你的眼前一' + random.choice(
                [
                    "黑",
                    "白",
                    "五彩斑斓的黑",
                    "布洛妮娅",
                    "你干嘛~哎呦~"
                ]
            ) + "\n" + random.choice(
                [
                    "你吃掉了比赛！",
                    "世界……咀嚼了你……",
                    "认真一点，下次不要再光顾着看{}的胖次了，好吗？".format(win_name)
                ]
            ))

        )
        await asyncio.sleep(0.5)
        # await bot.send(event, f"这场对决是 {winner} 胜利了")
        fightmsg = f"这场对决是 {win_name} 胜利了"
        # winner_id = self._current_player[event.group_id][fighter]
        # loser_id = self._current_player[event.group_id][fighted]
        winner_id = self._current_player[event.group_id][winfighter]
        loser_id = self._current_player[event.group_id][losefighter]
        result_winner = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(winner_id))
        result_loser = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(loser_id))
        if result_winner[-1] and result_loser[-1]:
            winner_like = result_winner[0][0][0]
            loser_like = result_loser[0][0][0]
            if loser_like - 5 > 0:
                await dbcontrol(
                    r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(winner_like + 5, winner_id))
                # await bot.send(event, f"这场对决是 {winner} 胜利了")
                fightmsg = fightmsg + "\n" + f"千鸟酱和对{win_name}的好感增加了！"
        ran2 = random.randint(1, 3)
        randomchoice = random.choice(self.collection)
        if ran2 == 1:
            resmsg = await getcollection(winner_id, randomchoice, if_can_reget=True)
            if resmsg:
                await bot.send(event,message=Message(f"[CQ:at,qq={winner_id}]"+resmsg))
                fightmsg = fightmsg + "\n" + f"[CQ:at,qq={winner_id}]" + resmsg
        # await bot.send(event, message=Message(fightmsg))
        self._current_player[event.group_id] = {}
        self._group_list.remove(event.group_id)
        result_loser = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(int(lose_user_id)))
        if result_loser[-1]:
            loser_like = result_loser[0][0][0]
            if loser_like - 5 > 0:
                await dbcontrol(
                    r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(loser_like - random.randint(3,5), lose_user_id))
                # await bot.send(event,message=f"千鸟酱对{lose_name}的好感降低了...")
        await bot.send(
            event,
            message=f"结算：\n"
            f"\t胜者：{win_name}\n"
            f'\t累计胜场：{win_user["win_count"]}\n'
            f"-------------------\n"
            f"\t败者：{lose_name}\n"
            f'\t累计败场：{lose_user["lose_count"]}\n'
        )
        if int(win_user["win_count"]) >= 20:
            resmsg =await getcollection(win_user_id,"金牌训练家", if_can_reget=False)
            if resmsg:
                await bot.send(event,message=Message(f"[CQ:at,qq={win_user_id}]" + resmsg))
            if int(win_user["win_count"]) >= 100:
                resmsg =await getcollection(win_user_id, "决斗的王", if_can_reget=False)
                if resmsg:
                    await bot.send(event, message=Message(f"[CQ:at,qq={win_user_id}]" + resmsg))
        if int(lose_user["lose_count"]) >= 20:
            resmsg =await getcollection(lose_user_id,"慈善家", if_can_reget=False)
            if resmsg:
                await bot.send(event,message=Message(f"[CQ:at,qq={lose_user_id}]" + resmsg))
            if int(lose_user["lose_count"]) >= 100:
                resmsg =await getcollection(lose_user_id, "决斗的神", if_can_reget=False)
                if resmsg:
                    await bot.send(event, message=Message(f"[CQ:at,qq={lose_user_id}]" + resmsg))


    def _end_data_handle(
        self,
        win_user_id: int,
        lose_user_id,
        group_id: int,
    ):
        """
        结算数据处理保存
        :param win_user_id: 胜利玩家id
        :param lose_user_id: 失败玩家id
        :param group_id: 群聊
        :param gold: 赌注金币
        :param fee: 手续费
        """
        win_user_id = str(win_user_id)
        lose_user_id = str(lose_user_id)
        group_id = str(group_id)
        self._player_data[group_id][win_user_id]["win_count"] += 1
        self._player_data[group_id][lose_user_id]["lose_count"] += 1

        self.save()

    async def check (self,group_id):
        try:
            if time.time() - self._current_player[group_id]["time"] > 90:
                await self.done(group_id)
                player1_name = self._current_player[group_id]["player1"]
                player2_name = self._current_player[group_id]["player2"]
                if (
                        self._current_player[group_id]["next"]
                        == self._current_player[group_id][1]
                ):
                    win_user_id = self._current_player[group_id][2]
                    lose_user_id = self._current_player[group_id][1]
                    win_name = player2_name
                    lose_name = player1_name
                else:
                    win_user_id = self._current_player[group_id][1]
                    lose_user_id = self._current_player[group_id][2]
                    win_name = player1_name
                    lose_name = player2_name
                self._end_data_handle(win_user_id, lose_user_id, group_id)
                win_user = self._player_data[str(group_id)][str(win_user_id)]
                lose_user = self._player_data[str(group_id)][str(lose_user_id)]
                logger.info(f"胜者：{win_name} - 败者：{lose_name} ")
                # print(group_id)
                group_id = int(group_id)
                result_loser = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(int(lose_user_id)))
                if result_loser[-1]:
                    loser_like = result_loser[0][0][0]
                    if loser_like - 5 > 0:
                        await dbcontrol(
                            r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(loser_like - random.randint(3,5), lose_user_id))
                        await get_bot().send_group_msg(group_id = group_id,message=f"千鸟酱对{lose_name}的好感降低了...")
                await get_bot().send_group_msg(group_id = group_id,message=f"结算：\n"
                f"\t胜者：{win_name}\n"
                f'\t累计胜场：{win_user["win_count"]}\n'
                f"-------------------\n"
                f"\t败者：{lose_name}\n"
                f'\t累计败场：{lose_user["lose_count"]}\n')
                self._current_player[group_id] = {}
                self._group_list.remove(group_id)
                if int(win_user["win_count"]) >= 20:
                    resmsg = await getcollection(win_user_id, "金牌训练家", if_can_reget=False)
                    if resmsg:
                        await get_bot().send_group_msg(group_id = group_id,message=Message(f"[CQ:at,qq={win_user_id}]" + resmsg))
                    if int(win_user["win_count"]) >= 100:
                        resmsg = await getcollection(win_user_id, "决斗的王", if_can_reget=False)
                        if resmsg:
                            await get_bot().send_group_msg(group_id = group_id, message=Message(f"[CQ:at,qq={win_user_id}]" + resmsg))
                if int(lose_user["lose_count"]) >= 20:
                    resmsg = await getcollection(lose_user_id, "慈善家", if_can_reget=False)
                    if resmsg:
                        await get_bot().send_group_msg(group_id = group_id,message=Message(f"[CQ:at,qq={lose_user_id}]" + resmsg))
                    if int(lose_user["lose_count"]) >= 100:
                        resmsg = await getcollection(lose_user_id, "决斗的神", if_can_reget=False)
                        if resmsg:
                            await get_bot().send_group_msg(group_id = group_id, message=Message(f"[CQ:at,qq={lose_user_id}]" + resmsg))
        except KeyError:
            await self.done(group_id)

    async def start(self,group_id):
        # print("hello11")
        self.job[group_id] = scheduler.add_job(self.check, "cron", second='*/5', id=f"{group_id}",args=[group_id] )
        # print("hello12")

    async def done(self,group_id):
        self.job[group_id].remove()


    async def caculate(self, bot: Bot, event: GroupMessageEvent, fighter, fighted, skill):
        with open(self.skilljsonfile, 'r+', encoding="utf-8") as f:
            file = json.load(f)
            # print(file)
            file_skill = file[f"{skill}"]
            skill_hurt = file_skill["hurt"]
            skill_attribute = file_skill["attribute"]
            skill_function = file_skill["function"]
            skill_parameter = file_skill["parameter"]

        fighted_blood = self._current_player[event.group_id][f"blood{fighted}"]
        fighter_blood = self._current_player[event.group_id][f"blood{fighter}"]
        fighted_attribute = self._current_player[event.group_id][f"attribute{fighted}"]
        fighter_attribute = self._current_player[event.group_id][f"attribute{fighter}"]
        fighted_accuracy = self._current_player[event.group_id][f"accuracy{fighted}"]
        fighter_accuracy = self._current_player[event.group_id][f"accuracy{fighter}"]
        fighted_atk = self._current_player[event.group_id][f"atk{fighted}"]
        fighter_atk = self._current_player[event.group_id][f"atk{fighter}"]
        fighted_state = self._current_player[event.group_id][f"state{fighted}"]
        fighter_state = self._current_player[event.group_id][f"state{fighter}"]
        c = calculate(fighter_blood, fighted_blood, fighter_attribute, fighted_attribute, fighter_atk, fighted_atk, fighter_accuracy, fighted_accuracy,fighter_state, fighted_state, skill_hurt, skill_attribute, skill_function, skill_parameter, skill,self.used_num,self.skilljsonfile)
        msg = c.cac()
        # await bot.send(event, msg)
        self._current_player[event.group_id][f"blood{fighted}"] = c.fighted_blood
        self._current_player[event.group_id][f"blood{fighter}"] = c.fighter_blood
        self._current_player[event.group_id][f"attribute{fighted}"] = c.fighted_attribute
        self._current_player[event.group_id][f"attribute{fighter}"] = c.fighter_attribute
        self._current_player[event.group_id][f"atk{fighted}"] = c.fighted_atk
        self._current_player[event.group_id][f"atk{fighter}"] = c.fighter_atk
        self._current_player[event.group_id][f"accuracy{fighted}"] = c.fighted_accuracy
        self._current_player[event.group_id][f"accuracy{fighter}"] = c.fighter_accuracy
        self._current_player[event.group_id][f"state{fighted}"] = c.fighted_state
        self._current_player[event.group_id][f"state{fighter}"] = c.fighter_state
        return msg
russian_manager = RussianManager()


class calculate():

    def __init__(self,fighter_blood,fighted_blood ,fighter_attribute ,fighted_attribute ,fighter_atk,fighted_atk,fighter_accuracy,fighted_accuracy,fighter_state ,fighted_state,skill_hurt,skill_attribute,skill_function,skill_parameter,skill,used_num,skilljsonfile):
        # 调参
        self.restraint_coefficient = 1.2 #克制系数
        self.atk_corfficient = 1.22      #攻击乘数
        self.ran_corfficient = 0.08      #随机长度
        self.def_corfficient = 0.30      #防御系数
        self.fra_corfficient = 1.40      #易伤系数
        self.con_corfficient = 0.45      #混乱系数
        #
        self.fighter_blood = fighter_blood
        self.fighted_blood = fighted_blood
        self.fighter_attribute = fighter_attribute
        self.fighted_attribute = fighted_attribute
        self.fighter_atk = fighter_atk
        self.fighted_atk = fighted_atk
        self.fighter_accuracy = fighter_accuracy
        self.fighted_accuracy = fighted_accuracy
        self.fighter_state = fighter_state
        self.fighted_state = fighted_state
        self.fighter_state_all = fighter_state
        self.fighted_state_all = fighted_state
        self.skill_function = skill_function #列表,["skill_change_atk","skill_rand_state"]
        self.skill_parameter = skill_parameter #字典,{"skill_change_atk":{"if_to_myself":1,"change_num":-12~12},"skill_rand_state":{"if_to_myself":1自己0对方,"rand_choice":{0:100,1:10,2:10,7:50}}}
        self.skill_hurt = skill_hurt
        self.skill_attribute = skill_attribute
        self.skill = skill
        self.used_num = used_num
        self.skilljsonfile = skilljsonfile
        self.fighter_blood_last = fighter_blood
        self.fighted_blood_last = fighted_blood

        self.is_restraint = 1.0
        self.def_cor = 1
        self.jump = 0
        self.iszero = 0
        self.fighter_notchange = 0
        self.fighted_notchange = 0
        self.acc = 0
        self.ifacc = 0


    def cac(self):
        # 判断疲惫
        message = ""
        msg = ""
        return_msg = ""

        if self.fighter_state == 1:
            self.fighter_state = 0
            # print("疲惫中！",end="")
            return "疲惫中！"

        else:
            #判断克制
            restraint = [[0,0,0,0,0,0,0],
                         [0,0,1,-1,0,0,1],
                         [0,-1,0,1,0,0,1],
                         [0,1,-1,0,0,0,1],
                         [0,0,-1,0,0,1,0],
                         [0,0,0,-1,1,0,0],
                         [1,-1,-1,-1,0,0,1]]
            restraint_text = ["微弱！","","克制！"]
            self.is_restraint = 1.2 ** restraint[self.skill_attribute][self.fighted_attribute]
            # print(restraint_text[(restraint[self.skill_attribute][self.fighted_attribute]+1)])

            if self.fighter_state == 9:
                self.fighter_state = 0
                self.skill = random.randint(0,int(self.used_num))
                with open(self.skilljsonfile, 'r+', encoding="utf-8") as f:
                    file = json.load(f)
                    # print(file)
                    file_skill = file[f"{self.skill}"]
                    self.skill_hurt = file_skill["hurt"]
                    self.skill_attribute = file_skill["attribute"]
                    self.skill_function = file_skill["function"]
                    self.skill_parameter = file_skill["parameter"]
                    name = str(file_skill["name"])
                msg += f"在疑惑中使用了{name}！"


            self.acc = self.fighter_accuracy
            if self.fighter_state == 10:
                self.fighter_state = 0
                self.acc = self.acc - 0.4
            if self.acc <= 0:
                self.acc = 0
            if self.acc >= 1:
                self.acc = 1
            self.ifacc = (random.randint(0,100) < self.acc*100)
            # if ifacc:
            #     pass
            # else:
            #     return f"未命中！"



            # 判断是否使用了防御
            if self.skill == 0 :
                self.fighter_state = 2
                self.jump = 1
                # print("你下一回合受到的伤害减弱{}%！".format(int(100*(1-def_corfficient))),end="")
                # return "你下一回合受到的伤害减弱{}%！".format(int(100*(1-self.def_corfficient)))
                msg += "你下一回合受到的伤害减弱{}%！".format(int(100*(1-self.def_corfficient)))
                self.iszero = 1

            #是否混乱
            if self.fighter_state == 7 and ("skill_random_damage" not in self.skill_function):
                self.fighter_state = 0
                if_confused = (random.randint(0,100) < self.con_corfficient*100)
                if if_confused:
                    fight = self.skill_hurt * (self.atk_corfficient ** (self.fighter_atk - 6))
                    self_damage = int(random.normalvariate(fight, fight * self.ran_corfficient))
                    if self.fighter_blood - self_damage <= 0:
                        self.fighter_blood = 1
                        return f"混乱了！对自己造成了{self.fighter_blood - 1}点伤害！"
                    else:
                        self.fighter_blood -= self_damage
                        return f"混乱了！对自己造成了{self_damage}点伤害！"
                else:
                    pass

            # fighter_blood_last = 0
            # fighted_blood_last = 0

            if self.skill_hurt != 0 and self.fighted_attribute == 6 and self.fighter_state != 8:
                if_confused = (random.randint(0, 100) < 40)
                if if_confused:
                    self.fighter_state = 9
                    msg += "对对方的属性感到迷惑！"

            if self.fighter_state == 8:#判断时滞
                self.fighter_notchange = 1
                msg += "完全感受不到时间的流逝……"
            if self.fighted_state == 8:
                self.fighted_notchange = 1
                msg += "完全感受不到对方身旁时间的流逝……"



            state_fun_name = f"self.state_judgement{self.fighted_state}"
            if self.fighted_state in [2,3,4,5,6]:
                msg1 = eval(state_fun_name)()
                msg += str(msg1)
                # print(msg)
                if self.iszero:
                    # fighter_blood_last = self.fighter_blood
                    # fighted_blood_last = self.fighted_blood
                    return msg


            #技能的效果
            for function in self.skill_function:
                if (str(function)) and (isinstance(self.skill_parameter,dict)):
                    fun_name = f"self.{function}"
                    parameter = self.skill_parameter[function]
                    returnmsg = eval(fun_name)(parameter)
                    returnmsg = str(returnmsg)
                    if returnmsg:
                        return_msg += returnmsg



            msg_dam = ""
            #伤害结算
            if not self.jump:
                if self.ifacc:
                    damage = int(self.damage())
                    if damage > 0:
                        msg_dam = restraint_text[(
                                    restraint[self.skill_attribute][self.fighted_attribute] + 1)] + f"造成了{damage}点伤害！"
                else:
                    msg_dam = restraint_text[(
                            restraint[self.skill_attribute][self.fighted_attribute] + 1)] + f"未命中！"


            # 属性变化
            self.fighter_attribute = self.skill_attribute

            if self.fighter_notchange == 1:
                self.fighter_state = 8
            if self.fighted_notchange == 1:
                self.fighted_state = 8

            message = msg + msg_dam + return_msg
            return message



    def state_judgement2(self):
        #防御
        self.fighted_state = 0
        self.def_cor = self.def_corfficient
        return ""

    def state_judgement3(self):
        #毒
        blooding = int(random.normalvariate(95, 95 * self.ran_corfficient))
        self.fighted_blood -= blooding
        # print("对方因为流血损失了{}点血量！".format(blooding), end="")
        return "对方因为流血损失了{}点血量！".format(blooding)

    def state_judgement4(self):
        # 顽强
        self.fighted_state = 0
        self.iszero = 1
        return_msg = ""

        for function in self.skill_function:
            if (str(function)) and (isinstance(self.skill_parameter, dict)):
                fun_name = f"self.{function}"
                parameter = self.skill_parameter[function]
                returnmsg = eval(fun_name)(parameter)
                returnmsg = str(returnmsg)
                if returnmsg:
                    return_msg += returnmsg
        # 伤害结算
        if not self.jump:
            damage = int(self.damage())
        # 属性变化
        self.fighter_attribute = self.skill_attribute

        damage = self.fighted_blood_last - self.fighted_blood

        if self.fighted_blood <= 0:
            self.fighted_blood = 1
            damage = self.fighted_blood_last - 1
            return return_msg + "造成了{}点伤害，但对方挺住了！".format(damage)
        else:
            damage = damage if damage > 0 else 0
            return return_msg + "造成了{}点伤害！".format(damage)

    def state_judgement5(self):
        # 荆棘
        self.fighted_state = 0
        self.iszero = 1
        return_msg = ""

        for function in self.skill_function:
            if (str(function)) and (isinstance(self.skill_parameter, dict)):
                fun_name = f"self.{function}"
                parameter = self.skill_parameter[function]
                returnmsg = eval(fun_name)(parameter)
                returnmsg = str(returnmsg)
                if returnmsg:
                    return_msg += returnmsg
        # 伤害结算
        if not self.jump:
            damage = int(self.damage())
        # 属性变化
        self.fighter_attribute = self.skill_attribute

        damage = self.fighted_blood_last - self.fighted_blood
        damage = damage if damage > 0 else 0

        self_damage = int(0.3 * damage)
        if self.fighter_blood - self_damage <= 0:
            self.fighter_blood = 1
            return f"造成了{damage}点伤害！同时由于对方的荆棘损失{self.fighter_blood - 1}点血量！"+return_msg
        else:
            self.fighter_blood -= self_damage
            return f"造成了{damage}点伤害！同时由于对方的荆棘损失{self_damage}点血量！"+return_msg




    def state_judgement6(self):
        #易伤
        self.fighted_state = 0
        self.def_cor = self.fra_corfficient
        return ""


    def damage(self,ifuse = 0,only_retrn = False):
        fight = (ifuse if ifuse else self.skill_hurt) * (self.atk_corfficient ** (self.fighter_atk - 6)) * self.is_restraint * self.def_cor
        fight_rand = int(random.normalvariate(fight,fight*self.ran_corfficient))
        # print("造成了{}点伤害！".format(fight_rand),end="")
        if not only_retrn:
            self.fighted_blood -= fight_rand
        return fight_rand


    def iter_method(self,data):
            total = sum(data.values())
            rad = random.randint(1, total)
            cur_total = 0
            res = ""
            for k, v in data.items():
                cur_total += v
                if rad <= cur_total:
                    res = k
                    break
            return int(res)

    def skill_rand_state(self,kw):#随机状态，格式：{"if_to_myself":1自己0对方,"rand_choice":{0:100,1:10,2:10,7:50}}，0正常1疲惫2防御3流血4顽强5荆棘6易伤7混乱8时滞
        # print(kw)
        states = ["是正常状态！","疲惫了！","进入防御状态了！","进入流血状态了！","变得顽强了！","身边长出荆棘了！","容易受到伤害了！","混乱了！","时间暂停了！","变得迷惑了！","失明了！"]
        if_to_myself = kw.get("if_to_myself", None)
        rand_chioce = kw.get("rand_choice",None) #参数应是字典
        if if_to_myself == 1:
            if rand_chioce:
                self.fighter_state = int(self.iter_method(rand_chioce))
                return states[self.fighter_state]
        elif if_to_myself == 0:
            if rand_chioce:
                self.fighted_state = int(self.iter_method(rand_chioce))
                return "对方" + states[self.fighted_state]



    def skill_change_atk(self,kw):  #攻击改变，参数格式：{"if_to_myself":1,"change_num":-12~12}
        # print(kw)
        if_to_myself = kw.get("if_to_myself", None)
        change_num = kw.get("change_num", 0)
        # print(change_num)
        # print(self.skill_more_b,self.skill_more_c)
        if if_to_myself == 1:
            self.fighter_atk += change_num
            if change_num == 0 and self.fighter_atk < 6:
                self.fighter_atk = 6
            if self.fighter_atk < 0:
                self.fighter_atk = 0
            if self.fighter_atk > 12:
                self.fighter_atk = 12
            # print("攻击变化为{}！".format(self.fighter_atk - 6), end="")
            return "攻击变化为{}！".format(self.fighter_atk - 6)
        elif if_to_myself == 0:
            self.fighted_atk += change_num
            if change_num == 0 and self.fighted_atk > 6:
                self.fighted_atk = 6
            if self.fighted_atk < 0 :
                self.fighted_atk = 0
            if self.fighted_atk > 12:
                self.fighted_atk = 12
            # print("对方攻击变化为{}！".format(self.fighted_atk - 6), end="")
            return "对方攻击变化为{}！".format(self.fighted_atk - 6)
        # print(self.fighter_atk)

    def skill_treatment(self,kw):#治疗自己：{"if_to_myself":1,"damage":400}
        if_to_myself = kw.get("if_to_myself", None)
        damage = kw.get("damage", 0)
        ratio = kw.get("ratio",0)
        # state = kw.get("state",None)
        # print(self.skill_more_b,self.skill_more_c)
        if if_to_myself == 1:
            msg = ""
            self.jump = 1
            self.fighter_blood += int(damage)
            # if state:
            #     msg = self.rand_state(state)
            return msg + f"回复了{damage}点血量！"
        elif if_to_myself == 0:
            msg = ""
            self.jump = 1
            if self.ifacc:
                real_damage = int(self.damage(ifuse=damage))
                self.fighter_blood += int(real_damage * ratio)
                # if state:
                #     msg = self.rand_state(state)
                return msg + f"造成了{real_damage}点伤害！回复了{int(real_damage * ratio)}点血量！"
            else:
                return msg + f"未命中！"
        # print(self.fighter_atk)

    def skill_addition(self,kw):#造成固伤
        if_to_myself = kw.get("if_to_myself", None)
        damage = kw.get("damage", 0)
        ratio = kw.get("ratio",100)
        rand = random.randint(0,100)
        if rand <= ratio:
            if if_to_myself == 1:
                # self.jump = 1
                if self.fighter_blood - damage > 0 :
                    self.fighter_blood -= damage
                    return  f"对自己造成了{damage}点固定伤害！"
                else:
                    damage = self.fighter_blood - 1
                    self.fighter_blood = 1
                    return f"对自己造成了{damage}点固定伤害！"
            elif if_to_myself == 0:
                if self.ifacc:
                # self.jump = 1
                    if damage == 0:
                        damage = self.fighted_blood-self.fighter_blood if (self.fighted_blood-self.fighter_blood > 0) else 0
                        self.fighted_blood -= damage
                        return f"造成了{damage}点固定伤害！"
                    else:
                        self.fighted_blood -= damage
                        return  f"造成了{damage}点固定伤害！"
                else:
                    return "未命中！"
        else:
            return ""

    def skill_change(self,kw):#交换属性
        # print(self.fighter_atk, self.fighted_atk, self.fighter_state, self.fighted_state)
        self.fighter_atk,self.fighted_atk = self.fighted_atk,self.fighter_atk
        self.fighter_state,self.fighted_state = self.fighted_state,self.fighter_state
        self.fighter_accuracy, self.fighted_accuracy = self.fighted_accuracy, self.fighter_accuracy
        # print(self.fighter_atk,self.fighted_atk,self.fighter_state,self.fighted_state)
        # print("交换了双方的属性！",end="")
        return "交换了双方的属性！"


    def skill_random_damage(self,kw):
        self.jump = 1
        down = kw.get("down",0)
        up = kw.get("up",0)
        ran = random.randint(down,up)
        if self.fighter_state == 7:
            self.fighter_state = 0
            dmg_self = 0
            dmg = 0
            self_damage = int(self.acc * self.con_corfficient * self.damage(ifuse=self.skill_hurt*ran,only_retrn=True))
            dmg = int(self.acc * (1 - self.con_corfficient) * self.damage(ifuse=self.skill_hurt * ran,only_retrn=True))
            self.fighted_blood -= dmg
            if self.fighter_blood - self_damage <= 0:
                dmg_self = self.fighter_blood_last - 1
                self.fighter_blood = 1
            else:
                self.fighter_blood -= self_damage
                dmg_self = self_damage
            return f"由于混乱对自己造成了{dmg_self}点伤害！同时对对方造成了{dmg}点伤害！"
        else:
            # dmg = 0
            # for i in range(0, ran):
            #     dm = self.damage()
            #     dmg += dm
            dmg = int(self.acc * self.damage(ifuse=self.skill_hurt*ran))
            return f"对对方造成了{dmg}点伤害！"




    def skill_if_positive(self,kw):
        msg = ""
        if_judge_myself = kw.get("if_judge_myself", None)
        if_is_positive = kw.get("if_is_positive", 0)
        if_to_myself = kw.get("if_to_myself", None)
        effect = str(kw.get("effect", None))
        ifispositive = 2
        if if_judge_myself:
            if self.fighter_state_all in [2,4,5]:
                ifispositive = 1
            if self.fighter_state_all in [1,3,6,7]:
                ifispositive = 0
        else:
            if self.fighted_state_all in [2,4,5]:
                ifispositive = 1
            if self.fighted_state_all in [1,3,6,7]:
                ifispositive = 0
        if if_is_positive == ifispositive:
            if if_to_myself and effect == "add":#延长
                self.fighter_state = self.fighter_state_all
                msg += "效果延长了！"
            if if_to_myself and effect == "atk":#增伤
                self.def_cor = self.def_cor* 1.7
                msg += "伤害增加了！"
            if if_to_myself and effect == "clean":#净化
                self.fighter_state = 0
                self.def_cor = self.def_cor * 1.4
                msg += "净化了不利状态并增加了伤害！"
            if not if_to_myself and effect == "add":#延长
                self.fighted_state = self.fighted_state_all
            if not if_to_myself and effect == "atk":  # 增伤
                self.def_cor = self.def_cor* 1.7
                msg += "伤害增加了！"
            if not if_to_myself and effect == "turn":  # 夺取
                self.fighter_state = self.fighted_state_all
                self.fighted_state = 0
                msg += "夺取了对方的效果！"
        return msg

    def skill_acc_damage(self, kw):
        self.jump = 1
        dmg = self.damage(ifuse=self.skill_hurt * (1+1-self.acc))
        return f"对对方造成了{dmg}点伤害！"

    def skill_acc_change(self, kw):
        if_to_myself = kw.get("if_to_myself", None)
        change_num = kw.get("change_num", 0)
        if if_to_myself == 1:
            self.fighter_accuracy += change_num
            return f"命中变化为{int(self.fighter_accuracy*100)}%！"
        elif if_to_myself == 0:
            self.fighted_accuracy += change_num
            return f"对方命中变化为{int(self.fighted_accuracy*100)}%！"
        # print(self.fighter_atk)